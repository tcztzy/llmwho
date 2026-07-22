from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

import llmwho


HTTP_CLIENTS_AVAILABLE = all(
    importlib.util.find_spec(name) is not None for name in ("httpx", "requests")
)


class LocalLLMHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        size = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(size)
        body = json.dumps(
            {
                "model": "server-model",
                "choices": [{"message": {"content": "not persisted"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


@unittest.skipUnless(HTTP_CLIENTS_AVAILABLE, "httpx and requests test extras are not installed")
class RealClientIntegrationTests(unittest.TestCase):
    def test_one_init_observes_httpx_and_requests(self) -> None:
        import httpx
        import requests

        server = ThreadingHTTPServer(("127.0.0.1", 0), LocalLLMHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            handle = llmwho.init(storage_path=path)
            try:
                url = f"http://127.0.0.1:{server.server_port}/v1/chat/completions"
                payload = {"model": "client-model", "messages": [{"role": "user", "content": "secret"}]}
                self.assertEqual(httpx.post(url, json=payload).status_code, 200)
                self.assertEqual(requests.post(url, json=payload).status_code, 200)
                events = handle.store.read()
                self.assertEqual(len(events), 2)
                self.assertEqual(
                    [event["identity"]["status"] for event in events],
                    ["mismatch", "mismatch"],
                )
                persisted = path.read_text(encoding="utf-8")
                self.assertNotIn("secret", persisted)
                self.assertNotIn("not persisted", persisted)
            finally:
                handle.shutdown()
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
