"""Dependency-free loopback dashboard server."""

from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qs, urlsplit

from .storage import (
    JSONLStore,
    canonical_timestamp,
    decode_event_cursor,
    encode_event_cursor,
)
from .summary import summarize


HTML_PATH = Path(__file__).with_name("dashboard.html")
DEFAULT_SUMMARY_WINDOW = timedelta(hours=24)
COHORT_FILTERS = (
    "endpoint_host",
    "endpoint_path",
    "provider",
    "requested_model",
)
TIME_FILTERS = ("since", "until")


class ReadableStore(Protocol):
    def read(self, limit: int | None = None) -> list[dict]: ...


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        store: ReadableStore,
        handler_class: type[BaseHTTPRequestHandler] | None = None,
    ) -> None:
        self.store = store
        super().__init__(address, handler_class or DashboardHandler)


def _query_values(query: str, allowed: set[str]) -> dict[str, str]:
    parsed = parse_qs(query, keep_blank_values=True)
    if set(parsed).difference(allowed):
        raise ValueError("unsupported query parameter")
    if any(len(values) != 1 or not values[0] for values in parsed.values()):
        raise ValueError("query parameters must be non-empty and unique")
    return {name: values[0] for name, values in parsed.items()}


def _filters(values: dict[str, str], *, default_window: bool) -> dict[str, str]:
    result = {
        name: values[name]
        for name in COHORT_FILTERS
        if name in values
    }
    now = datetime.now(timezone.utc)
    if "until" in values:
        until = canonical_timestamp(values["until"])
        until_time = datetime.fromisoformat(until.replace("Z", "+00:00"))
    else:
        until_time = now
        until = canonical_timestamp(until_time.isoformat())
    if "since" in values:
        since = canonical_timestamp(values["since"])
        since_time = datetime.fromisoformat(since.replace("Z", "+00:00"))
    elif default_window:
        since_time = until_time - DEFAULT_SUMMARY_WINDOW
        since = canonical_timestamp(since_time.isoformat())
    else:
        since_time = None
        since = None
    if since_time is not None and since_time >= until_time:
        raise ValueError("since must be before until")
    if since is not None:
        result["since"] = since
    if "until" in values or default_window:
        result["until"] = until
    return result


def _matches(event: dict[str, Any], filters: dict[str, str]) -> bool:
    timestamp = canonical_timestamp(event["timestamp"])
    endpoint = event["endpoint"]
    request = event.get("request", {})
    return (
        ("since" not in filters or timestamp >= filters["since"])
        and ("until" not in filters or timestamp < filters["until"])
        and (
            "endpoint_host" not in filters
            or endpoint["host"] == filters["endpoint_host"]
        )
        and (
            "endpoint_path" not in filters
            or endpoint["path"] == filters["endpoint_path"]
        )
        and (
            "provider" not in filters
            or endpoint.get("provider") == filters["provider"]
        )
        and (
            "requested_model" not in filters
            or request.get("requested_model") == filters["requested_model"]
        )
    )


def _local_summary(store: ReadableStore, filters: dict[str, str]) -> dict[str, Any]:
    result = summarize(event for event in store.read() if _matches(event, filters))
    result["scope"] = {
        "since": filters.get("since"),
        "until": filters.get("until"),
        "cohort": {
            name: filters[name] for name in COHORT_FILTERS if name in filters
        },
    }
    return result


def _local_events(
    store: ReadableStore,
    filters: dict[str, str],
    *,
    limit: int,
    cursor: str | None,
) -> dict[str, Any]:
    rows = [
        (canonical_timestamp(event["timestamp"]), event["event_id"], event)
        for event in store.read()
        if _matches(event, filters)
    ]
    rows.sort(key=lambda row: (row[0], row[1]), reverse=True)
    if cursor is not None:
        cursor_key = decode_event_cursor(cursor)
        rows = [row for row in rows if (row[0], row[1]) < cursor_key]
    page = rows[:limit]
    return {
        "events": [row[2] for row in page],
        "next_cursor": (
            encode_event_cursor(page[-1][0], page[-1][1])
            if len(rows) > limit and page
            else None
        ),
    }


class DashboardHandler(BaseHTTPRequestHandler):
    server: DashboardServer

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'",
        )
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, value: object) -> None:
        self._send(
            status,
            "application/json; charset=utf-8",
            json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        )

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        try:
            if parsed.path == "/":
                self._send(200, "text/html; charset=utf-8", HTML_PATH.read_bytes())
                return
            if parsed.path == "/favicon.ico":
                self._send(204, "image/x-icon", b"")
                return
            if parsed.path == "/api/summary":
                values = _query_values(
                    parsed.query,
                    set((*TIME_FILTERS, *COHORT_FILTERS)),
                )
                filters = _filters(values, default_window=True)
                query_summary = getattr(self.server.store, "query_summary", None)
                value = (
                    query_summary(filters)
                    if callable(query_summary)
                    else _local_summary(self.server.store, filters)
                )
                self._json(200, value)
                return
            if parsed.path == "/api/events":
                values = _query_values(
                    parsed.query,
                    set((*TIME_FILTERS, *COHORT_FILTERS, "limit", "cursor")),
                )
                raw_limit = values.pop("limit", "500")
                try:
                    limit = int(raw_limit)
                except ValueError:
                    raise ValueError("limit must be an integer") from None
                if not 1 <= limit <= 2000:
                    raise ValueError("limit must be between 1 and 2000")
                cursor = values.pop("cursor", None)
                filters = _filters(values, default_window=False)
                query_events = getattr(self.server.store, "query_events", None)
                value = (
                    query_events(filters, limit=limit, cursor=cursor)
                    if callable(query_events)
                    else _local_events(
                        self.server.store,
                        filters,
                        limit=limit,
                        cursor=cursor,
                    )
                )
                self._json(200, value)
                return
        except ValueError:
            self._json(400, {"error": "invalid query"})
            return
        except Exception:
            self._json(500, {"error": "unable to read local observation store"})
            return
        self._json(404, {"error": "not found"})

    def log_message(self, format: str, *args: object) -> None:
        return


def create_dashboard_server(
    *,
    storage_path: str | None = None,
    host: str = "127.0.0.1",
    port: int = 7734,
    store: ReadableStore | None = None,
) -> DashboardServer:
    if not 0 <= port <= 65535:
        raise ValueError("port must be between 0 and 65535")
    return DashboardServer((host, port), store or JSONLStore(storage_path))


def serve_dashboard(
    *,
    storage_path: str | None = None,
    host: str = "127.0.0.1",
    port: int = 7734,
) -> None:
    server = create_dashboard_server(storage_path=storage_path, host=host, port=port)
    print(f"LLMWho dashboard: http://{host}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
