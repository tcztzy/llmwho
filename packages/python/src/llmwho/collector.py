"""Self-hosted observation Collector and live dashboard."""

import hmac
from http import HTTPStatus
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .dashboard import DashboardHandler, DashboardServer
from .storage import DEFAULT_DATABASE_PATH, SQLiteStore
from .version import __version__


MAX_REQUEST_BYTES = 4 * 1024 * 1024
MAX_BATCH_EVENTS = 1000
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
OTLP_EVENT_ATTRIBUTE = "llmwho.event.type"
OTLP_EVENT_TYPE = "observation"


class UnsupportedMediaTypeError(Exception):
    pass


class LengthRequiredError(Exception):
    pass


class PayloadTooLargeError(Exception):
    pass


def _media_type(value: str | None) -> str:
    return (value or "").split(";", 1)[0].strip().lower()


def _otlp_attribute(record: dict[str, Any], name: str) -> str | None:
    attributes = record.get("attributes")
    if not isinstance(attributes, list):
        return None
    for attribute in attributes:
        if not isinstance(attribute, dict) or attribute.get("key") != name:
            continue
        value = attribute.get("value")
        if isinstance(value, dict) and isinstance(value.get("stringValue"), str):
            return value["stringValue"]
    return None


def observations_from_otlp(payload: object) -> list[dict[str, Any]]:
    """Extract marked ObservationV2 log bodies; ignore unrelated OTLP logs."""

    if not isinstance(payload, dict):
        raise ValueError("invalid OTLP logs envelope")
    resource_logs = payload.get("resourceLogs", [])
    if not isinstance(resource_logs, list):
        raise ValueError("invalid OTLP resourceLogs")
    observations: list[dict[str, Any]] = []
    for resource in resource_logs:
        if not isinstance(resource, dict):
            raise ValueError("invalid OTLP resource log")
        scope_logs = resource.get("scopeLogs", [])
        if not isinstance(scope_logs, list):
            raise ValueError("invalid OTLP scopeLogs")
        for scope in scope_logs:
            if not isinstance(scope, dict):
                raise ValueError("invalid OTLP scope log")
            records = scope.get("logRecords", [])
            if not isinstance(records, list):
                raise ValueError("invalid OTLP logRecords")
            for record in records:
                if not isinstance(record, dict):
                    raise ValueError("invalid OTLP log record")
                if _otlp_attribute(record, OTLP_EVENT_ATTRIBUTE) != OTLP_EVENT_TYPE:
                    continue
                body = record.get("body")
                if not isinstance(body, dict) or not isinstance(
                    body.get("stringValue"), str
                ):
                    raise ValueError("marked OTLP observation needs a string body")
                try:
                    event = json.loads(body["stringValue"])
                except json.JSONDecodeError as error:
                    raise ValueError("invalid OTLP observation JSON") from error
                if not isinstance(event, dict):
                    raise ValueError("OTLP observation must be an object")
                observations.append(event)
    if len(observations) > MAX_BATCH_EVENTS:
        raise ValueError("too many observations")
    return observations


class CollectorServer(DashboardServer):
    store: SQLiteStore

    def __init__(
        self,
        address: tuple[str, int],
        store: SQLiteStore,
        *,
        token: str | None,
        owns_store: bool,
    ) -> None:
        self.token = token
        self.owns_store = owns_store
        super().__init__(address, store, CollectorHandler)

    def server_close(self) -> None:
        try:
            super().server_close()
        finally:
            if self.owns_store:
                self.store.close()


class CollectorHandler(DashboardHandler):
    server: CollectorServer

    def _authorized(self) -> bool:
        expected = self.server.token
        if expected is None:
            return True
        authorization = self.headers.get("Authorization", "")
        scheme, separator, supplied = authorization.partition(" ")
        return (
            bool(separator)
            and scheme.lower() == "bearer"
            and hmac.compare_digest(supplied, expected)
        )

    def _require_authorization(self) -> bool:
        if self._authorized():
            return True
        body = b'{"error":"unauthorized"}'
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("WWW-Authenticate", "Bearer")
        self.end_headers()
        self.wfile.write(body)
        return False

    def _read_json(self) -> object:
        if _media_type(self.headers.get("Content-Type")) != "application/json":
            raise UnsupportedMediaTypeError
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise LengthRequiredError
        try:
            length = int(raw_length)
        except ValueError as error:
            raise ValueError("invalid Content-Length") from error
        if length < 0:
            raise ValueError("invalid Content-Length")
        if length > MAX_REQUEST_BYTES:
            raise PayloadTooLargeError
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise LengthRequiredError
        try:
            return json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("invalid JSON") from error

    def _ingest_native(self, payload: object) -> tuple[int, int]:
        if not isinstance(payload, dict):
            raise ValueError("invalid observation envelope")
        observations = payload.get("observations")
        if not isinstance(observations, list):
            raise ValueError("observations must be an array")
        if len(observations) > MAX_BATCH_EVENTS:
            raise ValueError("too many observations")
        if not all(isinstance(event, dict) for event in observations):
            raise ValueError("each observation must be an object")
        inserted = self.server.store.append_many(observations)
        return inserted, len(observations) - inserted

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/health":
            self._json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": "llmwho-collector",
                    "version": __version__,
                    "schema_version": "2",
                },
            )
            return
        if path.startswith("/api/") and not self._require_authorization():
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path not in {"/api/v1/observations", "/v1/logs"}:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        if not self._require_authorization():
            return
        try:
            payload = self._read_json()
            if path == "/api/v1/observations":
                inserted, duplicates = self._ingest_native(payload)
                self._json(
                    HTTPStatus.ACCEPTED,
                    {"accepted": inserted, "duplicates": duplicates},
                )
                return
            events = observations_from_otlp(payload)
            self.server.store.append_many(events)
            self._json(HTTPStatus.OK, {})
        except UnsupportedMediaTypeError:
            self._json(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                {"error": "application/json required"},
            )
        except LengthRequiredError:
            self._json(HTTPStatus.LENGTH_REQUIRED, {"error": "request body required"})
        except PayloadTooLargeError:
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "request too large"})
        except (KeyError, TypeError, ValueError):
            message = (
                "invalid OTLP log payload"
                if path == "/v1/logs"
                else "invalid observation payload"
            )
            self._json(HTTPStatus.BAD_REQUEST, {"error": message})
        except Exception:
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "ingest failed"})


def create_collector_server(
    *,
    database_path: os.PathLike[str] | str | None = None,
    host: str = "127.0.0.1",
    port: int = 7734,
    token: str | None = None,
    store: SQLiteStore | None = None,
) -> CollectorServer:
    if not 0 <= port <= 65535:
        raise ValueError("port must be between 0 and 65535")
    normalized_token = token if token else None
    if host.lower() not in LOOPBACK_HOSTS and normalized_token is None:
        raise ValueError("non-loopback Collector requires a bearer token")
    repository = store or SQLiteStore(database_path)
    try:
        return CollectorServer(
            (host, port),
            repository,
            token=normalized_token,
            owns_store=store is None,
        )
    except Exception:
        if store is None:
            repository.close()
        raise


def serve_collector(
    *,
    database_path: os.PathLike[str] | str | None = None,
    host: str = "127.0.0.1",
    port: int = 7734,
    token: str | None = None,
) -> None:
    server = create_collector_server(
        database_path=database_path,
        host=host,
        port=port,
        token=token,
    )
    location = Path(database_path or DEFAULT_DATABASE_PATH)
    print(f"LLMWho Collector: http://{host}:{server.server_port}")
    print(f"Database: {location}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
