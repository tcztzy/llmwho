from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from llmwho import probe
from llmwho.storage import JSONLStore


def answer_for(prompt: str) -> str:
    if "LLMWHO_OK" in prompt:
        return "LLMWHO_OK"
    if "JSON object" in prompt:
        return '{"llmwho":1}'
    if "2 + 2" in prompt:
        return "FALSE"
    if "17 multiplied" in prompt:
        return "323"
    return "unexpected"


class ProbeHandler(BaseHTTPRequestHandler):
    seen_authorization = None
    declared_model = "server-model"
    model_headers: dict[str, str] = {}

    def do_POST(self) -> None:
        size = int(self.headers["Content-Length"])
        request = json.loads(self.rfile.read(size))
        type(self).seen_authorization = self.headers.get("Authorization")
        prompt = request["messages"][-1]["content"]
        payload = {
            "system_fingerprint": "fp_local",
            "choices": [{"message": {"content": answer_for(prompt)}}],
        }
        if type(self).declared_model:
            payload["model"] = type(self).declared_model
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for name, value in type(self).model_headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class HeaderOnlyProbeHandler(ProbeHandler):
    declared_model = None
    model_headers = {
        "x-model-id": "header-model-a",
        "x-model-name": "header-model-b",
        "x-model": "header-model-c",
        "openai-model": "header-model-d",
    }


class ProbeTests(unittest.TestCase):
    def test_smoke_suite_is_explicit_deterministic_and_content_free(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), ProbeHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with TemporaryDirectory() as directory:
                path = Path(directory) / "events.jsonl"
                report = probe(
                    base_url=f"http://127.0.0.1:{server.server_port}",
                    api_key="probe-secret",
                    model="client-model",
                    storage_path=str(path),
                )
                self.assertTrue(report["completed"])
                self.assertEqual(report["capability"], {"passed": 4, "total": 4, "mean_score": 1.0})
                self.assertEqual(
                    report["declarations"]["statuses"],
                    {"mismatch": 4},
                )
                self.assertEqual(report["identity"]["status"], "unknown")
                events = JSONLStore(path).read()
                self.assertEqual(len(events), 4)
                self.assertTrue(all(event["source"] == "probe" for event in events))
                persisted = path.read_text(encoding="utf-8")
                self.assertNotIn("probe-secret", persisted)
                self.assertNotIn("Reply with exactly", persisted)
                self.assertEqual(ProbeHandler.seen_authorization, "Bearer probe-secret")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_v22_undocumented_model_headers_are_ignored(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), HeaderOnlyProbeHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with TemporaryDirectory() as directory:
                path = Path(directory) / "events.jsonl"
                report = probe(
                    base_url=f"http://127.0.0.1:{server.server_port}",
                    model="client-model",
                    storage_path=str(path),
                )
                self.assertEqual(
                    report["declarations"]["statuses"],
                    {"missing": 4},
                )
                self.assertEqual(report["declarations"]["declared_models"], {})
                self.assertEqual(report["identity"]["status"], "unknown")
                events = JSONLStore(path).read()
                self.assertTrue(all(event["identity"]["evidence"] == [] for event in events))
                self.assertTrue(
                    all("model_declaration" not in event for event in events)
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_rejects_unknown_suite_before_network(self) -> None:
        with self.assertRaisesRegex(ValueError, "only the smoke suite"):
            probe(base_url="http://127.0.0.1:1", model="x", suite="large")


if __name__ == "__main__":
    unittest.main()
