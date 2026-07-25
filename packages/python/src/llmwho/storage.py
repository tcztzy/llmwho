"""Content-free observation stores and JSONL interchange."""

import base64
import binascii
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sqlite3
from tempfile import NamedTemporaryFile
from threading import Lock, RLock
from typing import Any
from collections.abc import Iterable

from .observation import validate_observation


DEFAULT_JSONL_PATH = Path.home() / ".llmwho" / "events.jsonl"
DEFAULT_DATABASE_PATH = Path.home() / ".llmwho" / "collector.sqlite3"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    event_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    ingested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source TEXT NOT NULL,
    modality TEXT NOT NULL,
    sdk_name TEXT NOT NULL,
    sdk_version TEXT NOT NULL,
    endpoint_scheme TEXT NOT NULL,
    endpoint_host TEXT NOT NULL,
    endpoint_port INTEGER,
    endpoint_path TEXT NOT NULL,
    endpoint_provider TEXT,
    operation TEXT,
    requested_model TEXT,
    declared_model TEXT,
    declaration_status TEXT,
    outcome TEXT NOT NULL,
    duration_ms REAL NOT NULL,
    ttft_ms REAL,
    output_bytes INTEGER,
    stream INTEGER,
    probe_score REAL,
    identity_status TEXT NOT NULL,
    event_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS observations_timestamp_idx
    ON observations(timestamp, event_id);
CREATE INDEX IF NOT EXISTS observations_cohort_idx
    ON observations(
        endpoint_host,
        endpoint_path,
        requested_model,
        endpoint_provider,
        timestamp
    );
CREATE INDEX IF NOT EXISTS observations_provider_idx
    ON observations(endpoint_provider, timestamp, event_id);
CREATE INDEX IF NOT EXISTS observations_requested_model_idx
    ON observations(requested_model, timestamp, event_id);
CREATE INDEX IF NOT EXISTS observations_endpoint_idx
    ON observations(endpoint_host, endpoint_path, timestamp, event_id);

CREATE TABLE IF NOT EXISTS probe_runs (
    record_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    suite TEXT NOT NULL,
    record_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS analysis_results (
    record_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    plugin_id TEXT NOT NULL,
    plugin_version TEXT NOT NULL,
    record_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
    record_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    detector_id TEXT NOT NULL,
    status TEXT NOT NULL,
    record_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reference_profiles (
    record_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    record_json TEXT NOT NULL
);
"""

_FILTER_COLUMNS = {
    "since": "timestamp",
    "until": "timestamp",
    "endpoint_host": "endpoint_host",
    "endpoint_path": "endpoint_path",
    "provider": "endpoint_provider",
    "requested_model": "requested_model",
}


def _compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def canonical_timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return (
        parsed.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def encode_event_cursor(timestamp: str, event_id: str) -> str:
    payload = _compact_json([timestamp, event_id]).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_event_cursor(cursor: str) -> tuple[str, str]:
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.b64decode(
            cursor + padding,
            altchars=b"-_",
            validate=True,
        )
        value = json.loads(raw)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid event cursor") from error
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise ValueError("invalid event cursor")
    try:
        timestamp = canonical_timestamp(value[0])
    except (TypeError, ValueError) as error:
        raise ValueError("invalid event cursor") from error
    return timestamp, value[1]


class JSONLStore:
    def __init__(self, path: os.PathLike[str] | str | None = None) -> None:
        self.path = Path(path or DEFAULT_JSONL_PATH)
        self._lock = Lock()

    def append(self, event: dict[str, Any]) -> None:
        validate_observation(event)
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            descriptor = os.open(
                self.path,
                os.O_APPEND | os.O_CREAT | os.O_WRONLY,
                0o600,
            )
            try:
                os.write(descriptor, line.encode("utf-8"))
            finally:
                os.close(descriptor)

    def read(self, limit: int | None = None) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events = []
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    event = json.loads(line)
                    validate_observation(event)
                    events.append(event)
        return events[-limit:] if limit is not None else events

    def iter_events(self) -> Iterable[dict[str, Any]]:
        yield from self.read()

    def close(self) -> None:
        """Match remote/database store lifecycle without owning resources."""


class SQLiteStore:
    """Thread-safe, append-only Collector repository."""

    TABLES = frozenset(
        {
            "observations",
            "probe_runs",
            "analysis_results",
            "alerts",
            "reference_profiles",
        }
    )

    def __init__(self, path: os.PathLike[str] | str | None = None) -> None:
        self.path = Path(path or DEFAULT_DATABASE_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._lock = RLock()
        self._closed = False
        self._connection = sqlite3.connect(
            self.path,
            check_same_thread=False,
            isolation_level=None,
        )
        os.chmod(self.path, 0o600)
        with self._lock:
            schema_version = self._connection.execute(
                "PRAGMA user_version"
            ).fetchone()[0]
            if schema_version not in {0, 2}:
                self._connection.close()
                self._closed = True
                raise RuntimeError(
                    "unsupported Collector database schema; "
                    "ObservationV2 requires a new database"
                )
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=NORMAL")
            self._connection.execute("PRAGMA foreign_keys=ON")
            self._connection.executescript(_SCHEMA)
            self._connection.execute("PRAGMA user_version=2")
            self._protect_sidecars()

    def _protect_sidecars(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(f"{self.path}{suffix}")
            if candidate.exists():
                os.chmod(candidate, 0o600)

    def _assert_open(self) -> None:
        if self._closed:
            raise RuntimeError("SQLiteStore is closed")

    @staticmethod
    def _row(event: dict[str, Any]) -> tuple[object, ...]:
        endpoint = event["endpoint"]
        request = event.get("request", {})
        declaration = event.get("model_declaration", {})
        transport = event["transport"]
        response = event.get("response", {})
        probe = event.get("probe", {})
        stream = request.get("stream")
        return (
            event["event_id"],
            canonical_timestamp(event["timestamp"]),
            event["source"],
            event["modality"],
            event["sdk"]["name"],
            event["sdk"]["version"],
            endpoint["scheme"],
            endpoint["host"],
            endpoint.get("port"),
            endpoint["path"],
            endpoint.get("provider"),
            request.get("operation"),
            request.get("requested_model"),
            declaration.get("declared_model"),
            declaration.get("status"),
            transport["outcome"],
            float(transport["duration_ms"]),
            transport.get("ttft_ms"),
            response.get("output_bytes"),
            None if stream is None else int(stream is True),
            probe.get("score"),
            event["identity"]["status"],
            _compact_json(event),
        )

    def append(self, event: dict[str, Any]) -> bool:
        """Append one observation; return false when event_id already exists."""

        return self.append_many([event]) == 1

    def append_many(self, events: Iterable[dict[str, Any]]) -> int:
        rows = list(events)
        for event in rows:
            validate_observation(event)
        if not rows:
            return 0
        values = [self._row(event) for event in rows]
        statement = """
            INSERT OR IGNORE INTO observations (
                event_id, timestamp, source, modality, sdk_name, sdk_version,
                endpoint_scheme, endpoint_host, endpoint_port, endpoint_path,
                endpoint_provider, operation, requested_model, declared_model,
                declaration_status, outcome, duration_ms, ttft_ms, output_bytes,
                stream, probe_score, identity_status, event_json
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?
            )
        """
        with self._lock:
            self._assert_open()
            before = self._connection.total_changes
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.executemany(statement, values)
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
            self._connection.execute("COMMIT")
            self._protect_sidecars()
            return self._connection.total_changes - before

    def read(self, limit: int | None = None) -> list[dict[str, Any]]:
        if limit is not None and limit < 0:
            raise ValueError("limit must be non-negative")
        with self._lock:
            self._assert_open()
            if limit is None:
                rows = self._connection.execute(
                    "SELECT event_json FROM observations "
                    "ORDER BY timestamp ASC, event_id ASC"
                ).fetchall()
            elif limit == 0:
                rows = []
            else:
                rows = self._connection.execute(
                    "SELECT event_json FROM ("
                    "SELECT event_id, timestamp, event_json FROM observations "
                    "ORDER BY timestamp DESC, event_id DESC LIMIT ?"
                    ") ORDER BY timestamp ASC, event_id ASC",
                    (limit,),
                ).fetchall()
        events = [json.loads(row[0]) for row in rows]
        for event in events:
            validate_observation(event)
        return events

    @staticmethod
    def _filter_sql(filters: dict[str, str]) -> tuple[str, list[object]]:
        unknown = set(filters).difference(_FILTER_COLUMNS)
        if unknown:
            raise ValueError("unsupported observation filter")
        clauses: list[str] = []
        values: list[object] = []
        for name, value in filters.items():
            column = _FILTER_COLUMNS[name]
            if name == "since":
                clauses.append(f"{column} >= ?")
            elif name == "until":
                clauses.append(f"{column} < ?")
            else:
                clauses.append(f"{column} = ?")
            values.append(value)
        return (" AND ".join(clauses) if clauses else "1 = 1"), values

    def query_summary(self, filters: dict[str, str]) -> dict[str, Any]:
        """Aggregate indexed columns without loading authoritative event JSON."""

        where, parameters = self._filter_sql(filters)

        def counts(column: str, *, missing: str | None = None) -> dict[str, int]:
            expression = f"COALESCE({column}, ?)" if missing is not None else column
            values = [missing, *parameters] if missing is not None else parameters
            non_null = "" if missing is not None else f" AND {column} IS NOT NULL"
            rows = self._connection.execute(
                f"SELECT {expression} AS value, COUNT(*) FROM observations "
                f"WHERE {where}{non_null} GROUP BY value ORDER BY value",
                values,
            ).fetchall()
            return {str(key): int(count) for key, count in rows}

        def quantile(column: str, probability: float) -> float | None:
            count = int(
                self._connection.execute(
                    f"SELECT COUNT({column}) FROM observations WHERE {where}",
                    parameters,
                ).fetchone()[0]
            )
            if count == 0:
                return None
            index = (count - 1) * probability
            lower = math.floor(index)
            upper = math.ceil(index)
            rows = self._connection.execute(
                f"SELECT {column} FROM observations "
                f"WHERE {where} AND {column} IS NOT NULL "
                f"ORDER BY {column} ASC LIMIT ? OFFSET ?",
                [*parameters, upper - lower + 1, lower],
            ).fetchall()
            lower_value = float(rows[0][0])
            upper_value = float(rows[-1][0])
            return lower_value + (upper_value - lower_value) * (index - lower)

        with self._lock:
            self._assert_open()
            total = int(
                self._connection.execute(
                    f"SELECT COUNT(*) FROM observations WHERE {where}",
                    parameters,
                ).fetchone()[0]
            )
            outcomes = counts("outcome")
            identities = counts("identity_status")
            declaration_statuses = counts("declaration_status", missing="missing")
            declared_models = counts("declared_model")
            behavior = self._connection.execute(
                "SELECT COUNT(output_bytes), "
                "COALESCE(SUM(CASE WHEN stream = 1 THEN 1 ELSE 0 END), 0) "
                f"FROM observations WHERE {where}",
                parameters,
            ).fetchone()
            capability = self._connection.execute(
                f"SELECT COUNT(probe_score), AVG(probe_score) "
                f"FROM observations WHERE {where}",
                parameters,
            ).fetchone()
            latency = {
                "p50": quantile("duration_ms", 0.5),
                "p95": quantile("duration_ms", 0.95),
                "p99": quantile("duration_ms", 0.99),
            }
            output_bytes_p50 = quantile("output_bytes", 0.5)
        return {
            "events": total,
            "scope": {
                "since": filters.get("since"),
                "until": filters.get("until"),
                "cohort": {
                    name: filters[name]
                    for name in (
                        "endpoint_host",
                        "endpoint_path",
                        "provider",
                        "requested_model",
                    )
                    if name in filters
                },
            },
            "availability": {
                "success_rate": outcomes.get("success", 0) / total if total else None,
                "outcomes": outcomes,
            },
            "transport": {"latency_ms": latency},
            "identity": {"statuses": identities},
            "declarations": {
                "statuses": declaration_statuses,
                "declared_models": declared_models,
            },
            "behavior": {
                "observed_responses": int(behavior[0]),
                "stream_requests": int(behavior[1]),
                "output_bytes_p50": output_bytes_p50,
            },
            "capability": {
                "probe_count": int(capability[0]),
                "mean_score": (
                    float(capability[1]) if capability[1] is not None else None
                ),
            },
        }

    def query_events(
        self,
        filters: dict[str, str],
        *,
        limit: int = 500,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        if not 1 <= limit <= 2000:
            raise ValueError("event page limit must be between 1 and 2000")
        where, parameters = self._filter_sql(filters)
        if cursor is not None:
            cursor_timestamp, cursor_event_id = decode_event_cursor(cursor)
            where += " AND (timestamp < ? OR (timestamp = ? AND event_id < ?))"
            parameters.extend(
                [cursor_timestamp, cursor_timestamp, cursor_event_id]
            )
        with self._lock:
            self._assert_open()
            rows = self._connection.execute(
                "SELECT timestamp, event_id, event_json FROM observations "
                f"WHERE {where} ORDER BY timestamp DESC, event_id DESC LIMIT ?",
                [*parameters, limit + 1],
            ).fetchall()
        page = rows[:limit]
        events = [json.loads(row[2]) for row in page]
        for event in events:
            validate_observation(event)
        next_cursor = (
            encode_event_cursor(page[-1][0], page[-1][1])
            if len(rows) > limit and page
            else None
        )
        return {"events": events, "next_cursor": next_cursor}

    def iter_events(self) -> Iterable[dict[str, Any]]:
        yield from self.read()

    def table_names(self) -> frozenset[str]:
        with self._lock:
            self._assert_open()
            rows = self._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        return frozenset(row[0] for row in rows).intersection(self.TABLES)

    def import_jsonl(self, path: os.PathLike[str] | str) -> dict[str, int]:
        events = JSONLStore(path).read()
        inserted = self.append_many(events)
        return {
            "read": len(events),
            "inserted": inserted,
            "duplicates": len(events) - inserted,
        }

    def export_jsonl(self, path: os.PathLike[str] | str) -> int:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        events = self.read()
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            os.chmod(temporary, 0o600)
            for event in events:
                handle.write(_compact_json(event))
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(temporary, destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return len(events)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._connection.close()
            self._closed = True

    def __enter__(self) -> "SQLiteStore":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
