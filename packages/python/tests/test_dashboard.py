from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from llmwho.dashboard import create_dashboard_server
from llmwho.observation import new_observation
from llmwho.storage import NDJSONStore


class DashboardTests(unittest.TestCase):
    def test_loopback_dashboard_serves_html_summary_and_events(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.ndjson"
            store = NDJSONStore(path)
            store.append(
                new_observation(
                    url="https://api.example/v1/chat/completions",
                    duration_ms=15,
                    outcome="success",
                    claimed_model="a",
                    declared_model="a",
                    response={"status_code": 200, "output_bytes": 12},
                )
            )
            server = create_dashboard_server(storage_path=str(path), port=0)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                html = urlopen(base).read().decode()
                self.assertIn("Endpoint identity &amp; stability", html)
                self.assertIn("Availability", html)
                summary = json.loads(urlopen(f"{base}/api/summary").read())
                self.assertEqual(summary["events"], 1)
                self.assertEqual(summary["behavior"]["output_bytes_p50"], 12)
                events = json.loads(urlopen(f"{base}/api/events?limit=1").read())
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]["identity"]["status"], "matched")
                with self.assertRaises(HTTPError) as missing:
                    urlopen(f"{base}/missing")
                self.assertEqual(missing.exception.code, 404)
                missing.exception.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
