import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from unittest import mock
import unittest

import llmwho
from llmwho.collector import create_collector_server
from llmwho.observation import new_observation
from llmwho.remote import RemoteStore, otlp_logs_payload
from llmwho.storage import JSONLStore, SQLiteStore


def event(identifier: str) -> dict:
    value = new_observation(
        url="https://api.example/v1/chat/completions",
        duration_ms=5,
        outcome="success",
        claimed_model="model",
        declared_model="model",
    )
    value["event_id"] = identifier
    return value


class PausedRemoteStore(RemoteStore):
    def __init__(self, *args, **kwargs) -> None:
        self.release_worker = Event()
        super().__init__(*args, **kwargs)

    def _run(self) -> None:
        self.release_worker.wait(timeout=2)
        super()._run()


class RemoteStoreTests(unittest.TestCase):
    def tearDown(self) -> None:
        handle = getattr(llmwho.hooks, "_ACTIVE_HANDLE", None)
        if handle is not None:
            handle.shutdown()

    def test_native_and_otlp_delivery_share_collector_wire_contract(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SQLiteStore(Path(directory) / "collector.sqlite3")
            server = create_collector_server(
                store=repository,
                port=0,
                token="collector-token",
            )
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}"
            try:
                native = RemoteStore(url, token="collector-token", flush_interval=0)
                otlp = RemoteStore(
                    url,
                    token="collector-token",
                    protocol="otlp",
                    flush_interval=0,
                )
                self.assertTrue(native.append(event("native")))
                self.assertTrue(otlp.append(event("otlp")))
                self.assertTrue(native.close())
                self.assertTrue(otlp.close())
                self.assertEqual(native.delivered, 1)
                self.assertEqual(otlp.delivered, 1)
                rows = repository.read()
                self.assertEqual(
                    {value["event_id"] for value in rows}, {"native", "otlp"}
                )
                self.assertNotIn("collector-token", json.dumps(rows))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                repository.close()

    def test_bounded_queue_drops_without_blocking_and_failures_are_swallowed(self) -> None:
        store = PausedRemoteStore(
            "http://127.0.0.1:9",
            max_queue=1,
            flush_interval=0,
            request_timeout=0.05,
        )
        self.assertTrue(store.append(event("queued")))
        self.assertFalse(store.append(event("dropped")))
        self.assertEqual(store.dropped, 1)
        store.release_worker.set()
        self.assertTrue(store.close())
        self.assertEqual(store.delivery_failures, 1)

    def test_init_uses_remote_store_and_shutdown_flushes(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SQLiteStore(Path(directory) / "collector.sqlite3")
            server = create_collector_server(store=repository, port=0)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}"
            try:
                with mock.patch(
                    "llmwho.hooks._load_optional", return_value=None
                ), mock.patch.dict(
                    "os.environ",
                    {"LLMWHO_COLLECTOR_URL": url},
                    clear=False,
                ):
                    handle = llmwho.init()
                    self.assertIsInstance(handle.store, RemoteStore)
                    self.assertTrue(handle.store.append(event("from-init")))
                    handle.shutdown()
                self.assertEqual(repository.read()[0]["event_id"], "from-init")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                repository.close()

    def test_disabled_init_stays_local(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {
                "LLMWHO_DISABLED": "true",
                "LLMWHO_COLLECTOR_URL": "https://collector.example",
            },
            clear=False,
        ):
            handle = llmwho.init()
            self.assertIsInstance(handle.store, JSONLStore)
            self.assertFalse(handle.active)

    def test_otlp_payload_contains_only_events_and_safe_metadata(self) -> None:
        value = event("wire")
        payload = otlp_logs_payload([value])
        serialized = json.dumps(payload)
        self.assertIn('"llmwho.event.type"', serialized)
        self.assertIn('"llmwho.schema.version"', serialized)
        record = payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]
        self.assertEqual(json.loads(record["body"]["stringValue"])["event_id"], "wire")
        self.assertNotIn("authorization", serialized.lower())

    def test_collector_url_rejects_embedded_credentials(self) -> None:
        with self.assertRaises(ValueError):
            RemoteStore("https://user:secret@collector.example")


if __name__ == "__main__":
    unittest.main()
