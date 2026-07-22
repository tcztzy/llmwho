import json
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
        claimed_model=label,
        declared_model=label,
        request={"operation": "chat.completions", "claimed_model": label},
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
                self.assertEqual(journal_mode, "wal")
                self.assertEqual(version, 1)

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


if __name__ == "__main__":
    unittest.main()
