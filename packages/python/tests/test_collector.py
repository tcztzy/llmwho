import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest import mock
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from llmwho.cli import main
from llmwho.collector import create_collector_server
from llmwho.observation import new_observation
from llmwho.storage import SQLiteStore


def event(identifier: str = "event-1") -> dict:
    value = new_observation(
        url="https://api.example/v1/chat/completions",
        duration_ms=12,
        outcome="success",
        claimed_model="expected",
        declared_model="expected",
        request={"operation": "chat.completions", "claimed_model": "expected"},
        response={"status_code": 200, "output_bytes": 4},
    )
    value["event_id"] = identifier
    return value


def otlp_payload(value: dict) -> dict:
    return {
        "resourceLogs": [
            {
                "unknownResourceField": True,
                "scopeLogs": [
                    {
                        "logRecords": [
                            {
                                "body": {"stringValue": json.dumps(value)},
                                "attributes": [
                                    {
                                        "key": "llmwho.event.type",
                                        "value": {"stringValue": "observation"},
                                    }
                                ],
                                "unknownRecordField": "ignored",
                            },
                            {
                                "body": {"stringValue": "unrelated log"},
                                "attributes": [],
                            },
                        ]
                    }
                ],
            }
        ],
        "unknownEnvelopeField": 1,
    }


class RunningCollector:
    def __init__(self, path: Path, *, token: str | None = None) -> None:
        self.store = SQLiteStore(path)
        self.server = create_collector_server(store=self.store, port=0, token=token)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.store.close()

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: object | None = None,
        token: str | None = None,
        content_type: str = "application/json",
    ):
        headers = {"Content-Type": content_type}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        body = None if payload is None else json.dumps(payload).encode()
        return urlopen(
            Request(
                f"{self.base_url}{path}",
                data=body,
                headers=headers,
                method=method,
            )
        )


class CollectorTests(unittest.TestCase):
    def test_native_ingest_is_atomic_idempotent_and_updates_dashboard(self) -> None:
        with TemporaryDirectory() as directory:
            collector = RunningCollector(Path(directory) / "collector.sqlite3")
            try:
                with collector.request(
                    "/api/v1/observations",
                    method="POST",
                    payload={"observations": [event()]},
                ) as response:
                    self.assertEqual(response.status, 202)
                    self.assertEqual(
                        json.load(response), {"accepted": 1, "duplicates": 0}
                    )
                with collector.request(
                    "/api/v1/observations",
                    method="POST",
                    payload={"observations": [event()]},
                ) as response:
                    self.assertEqual(
                        json.load(response), {"accepted": 0, "duplicates": 1}
                    )

                invalid = event("event-2")
                invalid["request"]["content"] = "must never persist or echo"
                with self.assertRaises(HTTPError) as rejected:
                    collector.request(
                        "/api/v1/observations",
                        method="POST",
                        payload={"observations": [event("event-3"), invalid]},
                    )
                self.assertEqual(rejected.exception.code, 400)
                self.assertNotIn("must never persist", rejected.exception.read().decode())
                rejected.exception.close()

                with collector.request("/api/summary") as response:
                    self.assertEqual(json.load(response)["events"], 1)
                with collector.request("/api/events?limit=10") as response:
                    self.assertEqual(
                        [value["event_id"] for value in json.load(response)],
                        ["event-1"],
                    )
            finally:
                collector.close()

    def test_otlp_json_ingest_ignores_unknown_fields_and_unrelated_logs(self) -> None:
        with TemporaryDirectory() as directory:
            collector = RunningCollector(Path(directory) / "collector.sqlite3")
            try:
                with collector.request(
                    "/v1/logs",
                    method="POST",
                    payload=otlp_payload(event("otlp-event")),
                ) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(json.load(response), {})
                self.assertEqual(
                    [value["event_id"] for value in collector.store.read()],
                    ["otlp-event"],
                )
                with self.assertRaises(HTTPError) as unsupported:
                    collector.request(
                        "/v1/logs",
                        method="POST",
                        payload={},
                        content_type="application/x-protobuf",
                    )
                self.assertEqual(unsupported.exception.code, 415)
                unsupported.exception.close()
            finally:
                collector.close()

    def test_token_protects_data_apis_without_leaking_secret(self) -> None:
        token = "collector-secret-value"
        with TemporaryDirectory() as directory:
            collector = RunningCollector(
                Path(directory) / "collector.sqlite3", token=token
            )
            try:
                with collector.request("/") as response:
                    self.assertEqual(response.status, 200)
                with collector.request("/api/health") as response:
                    self.assertEqual(json.load(response)["status"], "ok")
                with self.assertRaises(HTTPError) as unauthorized:
                    collector.request("/api/events")
                self.assertEqual(unauthorized.exception.code, 401)
                self.assertNotIn(token, unauthorized.exception.read().decode())
                unauthorized.exception.close()
                with collector.request("/api/events", token=token) as response:
                    self.assertEqual(json.load(response), [])
            finally:
                collector.close()

    def test_non_loopback_requires_token(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "collector.sqlite3"
            with self.assertRaisesRegex(ValueError, "requires a bearer token"):
                create_collector_server(
                    database_path=path,
                    host="0.0.0.0",
                    port=0,
                )
            server = create_collector_server(
                database_path=path,
                host="0.0.0.0",
                port=0,
                token="configured",
            )
            server.server_close()

    def test_database_cli_imports_and_exports_jsonl(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jsonl"
            source.write_text(f"{json.dumps(event())}\n", encoding="utf-8")
            database = root / "collector.sqlite3"
            exported = root / "exported.jsonl"
            output = io.StringIO()
            with mock.patch("sys.stdout", output):
                self.assertEqual(
                    main(
                        [
                            "database",
                            "import-jsonl",
                            "--database",
                            str(database),
                            "--jsonl",
                            str(source),
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    main(
                        [
                            "database",
                            "export-jsonl",
                            "--database",
                            str(database),
                            "--jsonl",
                            str(exported),
                        ]
                    ),
                    0,
                )
            reports = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(reports[0]["inserted"], 1)
            self.assertEqual(reports[1]["exported"], 1)
            self.assertEqual(json.loads(exported.read_text())["event_id"], "event-1")


if __name__ == "__main__":
    unittest.main()
