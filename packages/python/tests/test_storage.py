import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from llmwho.observation import new_observation
from llmwho.storage import SQLiteStore


def observation(label: str, *, duration_ms: float = 1) -> dict:
    event = new_observation(
        url=f"https://{label}.example/v1/chat/completions",
        duration_ms=duration_ms,
        outcome="success",
        requested_model=label,
        declared_model=label,
        request={"operation": "chat.completions", "requested_model": label},
    )
    event["event_id"] = label
    event["timestamp"] = f"2026-07-22T00:00:0{int(duration_ms)}Z"
    return event


class SQLiteStoreTests(unittest.TestCase):
    def test_schema_uses_wal_and_all_shared_tables(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "collector.sqlite3"
            with SQLiteStore(path) as store:
                self.assertEqual(store.table_names(), SQLiteStore.TABLES)
                with sqlite3.connect(path) as connection:
                    journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
                    version = connection.execute("PRAGMA user_version").fetchone()[0]
                    indexes = {
                        row[1]
                        for row in connection.execute(
                            "PRAGMA index_list(observations)"
                        ).fetchall()
                    }
                self.assertEqual(journal_mode, "wal")
                self.assertEqual(version, 2)
                self.assertTrue(
                    {
                        "observations_timestamp_idx",
                        "observations_provider_idx",
                        "observations_requested_model_idx",
                        "observations_endpoint_idx",
                    }.issubset(indexes)
                )

    def test_v43_database_and_sidecars_ignore_permissive_umask(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "collector.sqlite3"
            previous_umask = os.umask(0)
            try:
                with SQLiteStore(path) as store:
                    store.append(observation("private"))
                    candidates = [path, Path(f"{path}-wal"), Path(f"{path}-shm")]
                    for candidate in candidates:
                        if candidate.exists():
                            self.assertEqual(candidate.stat().st_mode & 0o777, 0o600)
            finally:
                os.umask(previous_umask)

    def test_append_is_idempotent_and_read_order_is_deterministic(self) -> None:
        with TemporaryDirectory() as directory, SQLiteStore(
            Path(directory) / "collector.sqlite3"
        ) as store:
            later = observation("later", duration_ms=2)
            earlier = observation("earlier", duration_ms=1)
            self.assertTrue(store.append(later))
            self.assertTrue(store.append(earlier))
            self.assertFalse(store.append(earlier))
            self.assertEqual(
                [event["event_id"] for event in store.read()],
                ["earlier", "later"],
            )
            self.assertEqual(
                [event["event_id"] for event in store.read(limit=1)],
                ["later"],
            )

    def test_append_many_validates_entire_batch_before_writing(self) -> None:
        with TemporaryDirectory() as directory, SQLiteStore(
            Path(directory) / "collector.sqlite3"
        ) as store:
            invalid = observation("invalid")
            invalid["privacy"]["content_captured"] = True
            with self.assertRaises(ValueError):
                store.append_many([observation("valid"), invalid])
            self.assertEqual(store.read(), [])

    def test_jsonl_import_export_round_trip_and_duplicate_report(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.jsonl"
            events = [observation("one", duration_ms=1), observation("two", duration_ms=2)]
            source_path.write_text(
                "".join(f"{json.dumps(event)}\n" for event in events),
                encoding="utf-8",
            )
            with SQLiteStore(root / "collector.sqlite3") as store:
                self.assertEqual(
                    store.import_jsonl(source_path),
                    {"read": 2, "inserted": 2, "duplicates": 0},
                )
                self.assertEqual(
                    store.import_jsonl(source_path),
                    {"read": 2, "inserted": 0, "duplicates": 2},
                )
                exported = root / "exported.jsonl"
                self.assertEqual(store.export_jsonl(exported), 2)
            rows = [json.loads(line) for line in exported.read_text().splitlines()]
            self.assertEqual([row["event_id"] for row in rows], ["one", "two"])
            self.assertEqual(exported.stat().st_mode & 0o777, 0o600)

    def test_v45_summary_uses_indexed_columns_without_event_json(self) -> None:
        with TemporaryDirectory() as directory, SQLiteStore(
            Path(directory) / "collector.sqlite3"
        ) as store:
            events = [
                observation("one", duration_ms=1),
                observation("two", duration_ms=2),
                observation("three", duration_ms=3),
            ]
            events[0]["response"] = {"status_code": 200, "output_bytes": 10}
            events[0]["request"]["stream"] = True
            events[1]["response"] = {"status_code": 200, "output_bytes": 20}
            events[2]["endpoint"]["provider"] = "other"
            for value in events:
                store.append(value)
            store._connection.execute(
                "UPDATE observations SET event_json = 'not-json' "
                "WHERE event_id = 'one'"
            )
            statements: list[str] = []
            store._connection.set_trace_callback(statements.append)
            summary = store.query_summary(
                {
                    "since": "2026-07-22T00:00:00.000000Z",
                    "until": "2026-07-23T00:00:00.000000Z",
                    "provider": "other",
                }
            )
            store._connection.set_trace_callback(None)
            self.assertEqual(summary["events"], 1)
            self.assertEqual(summary["transport"]["latency_ms"]["p50"], 3)
            self.assertEqual(summary["scope"]["cohort"], {"provider": "other"})
            self.assertTrue(statements)
            self.assertTrue(
                all("event_json" not in statement.lower() for statement in statements)
            )
            plan = store._connection.execute(
                "EXPLAIN QUERY PLAN SELECT COUNT(*) FROM observations "
                "WHERE requested_model = ? AND timestamp >= ?",
                ("one", "2026-07-22T00:00:00.000000Z"),
            ).fetchall()
            self.assertIn(
                "observations_requested_model_idx",
                " ".join(str(row) for row in plan),
            )

    def test_v45_cursor_pages_are_bounded_disjoint_and_filterable(self) -> None:
        with TemporaryDirectory() as directory, SQLiteStore(
            Path(directory) / "collector.sqlite3"
        ) as store:
            for index in range(1, 6):
                value = observation(f"event-{index}", duration_ms=index)
                if index == 5:
                    value["request"]["requested_model"] = "other"
                store.append(value)
            selected = {
                "since": "2026-07-22T00:00:00.000000Z",
                "until": "2026-07-23T00:00:00.000000Z",
                "requested_model": "event-1",
            }
            filtered = store.query_events(selected, limit=2)
            self.assertEqual(
                [value["event_id"] for value in filtered["events"]],
                ["event-1"],
            )
            self.assertIsNone(filtered["next_cursor"])

            first = store.query_events({}, limit=2)
            second = store.query_events(
                {},
                limit=2,
                cursor=first["next_cursor"],
            )
            third = store.query_events(
                {},
                limit=2,
                cursor=second["next_cursor"],
            )
            identifiers = [
                value["event_id"]
                for page in (first, second, third)
                for value in page["events"]
            ]
            self.assertEqual(len(identifiers), 5)
            self.assertEqual(len(set(identifiers)), 5)
            self.assertIsNone(third["next_cursor"])
            with self.assertRaisesRegex(ValueError, "invalid event cursor"):
                store.query_events({}, cursor="not-a-cursor")


if __name__ == "__main__":
    unittest.main()
