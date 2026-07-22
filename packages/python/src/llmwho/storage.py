"""Content-free observation stores and JSONL interchange."""

import json
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
    claimed_model TEXT,
    observed_model TEXT,
    outcome TEXT NOT NULL,
    duration_ms REAL NOT NULL,
    ttft_ms REAL,
    event_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS observations_timestamp_idx
    ON observations(timestamp, event_id);
CREATE INDEX IF NOT EXISTS observations_cohort_idx
    ON observations(
        endpoint_host,
        endpoint_path,
        claimed_model,
        endpoint_provider,
        timestamp
    );

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


def _compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


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
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=NORMAL")
            self._connection.execute("PRAGMA foreign_keys=ON")
            self._connection.executescript(_SCHEMA)
            self._connection.execute("PRAGMA user_version=1")
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
        identity = event["identity"]
        transport = event["transport"]
        return (
            event["event_id"],
            event["timestamp"],
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
            request.get("claimed_model"),
            identity.get("observed_model"),
            transport["outcome"],
            float(transport["duration_ms"]),
            transport.get("ttft_ms"),
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
                endpoint_provider, operation, claimed_model, observed_model,
                outcome, duration_ms, ttft_ms, event_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
