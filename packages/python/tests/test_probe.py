from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from llmwho import probe
from llmwho.storage import NDJSONStore


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

    def do_POST(self) -> None:
        size = int(self.headers["Content-Length"])
        request = json.loads(self.rfile.read(size))
        type(self).seen_authorization = self.headers.get("Authorization")
        prompt = request["messages"][-1]["content"]
        body = json.dumps(
            {
                "model": "server-model",
                "system_fingerprint": "fp_local",
                "choices": [{"message": {"content": answer_for(prompt)}}],
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class ProbeTests(unittest.TestCase):
    def test_smoke_suite_is_explicit_deterministic_and_content_free(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), ProbeHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with TemporaryDirectory() as directory:
                path = Path(directory) / "events.ndjson"
                report = probe(
                    base_url=f"http://127.0.0.1:{server.server_port}",
                    api_key="probe-secret",
                    model="client-model",
                    storage_path=str(path),
                )
                self.assertTrue(report["completed"])
                self.assertEqual(report["capability"], {"passed": 4, "total": 4, "mean_score": 1.0})
                self.assertEqual(report["identity"]["statuses"], {"mismatch": 4})
                events = NDJSONStore(path).read()
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

    def test_rejects_unknown_suite_before_network(self) -> None:
        with self.assertRaisesRegex(ValueError, "only the smoke suite"):
            probe(base_url="http://127.0.0.1:1", model="x", suite="large")


if __name__ == "__main__":
    unittest.main()
