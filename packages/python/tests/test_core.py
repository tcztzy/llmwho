from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from llmwho import NDJSONStore, infer_identity, new_observation, quantile, summarize
from llmwho.observation import validate_observation
from llmwho.privacy import REDACTED, endpoint_from_url, redact_headers, redact_text


ROOT = Path(__file__).resolve().parents[3]


class CoreTests(unittest.TestCase):
    def test_shared_fixture_is_accepted(self) -> None:
        fixture = json.loads(
            (ROOT / "shared/fixtures/observation-v1.json").read_text(encoding="utf-8")
        )
        validate_observation(fixture)

    def test_url_and_secrets_are_redacted(self) -> None:
        endpoint = endpoint_from_url(
            "https://user:pass@api.example.test:8443/v1/chat?api_key=secret#fragment"
        )
        self.assertEqual(
            endpoint,
            {
                "scheme": "https",
                "host": "api.example.test",
                "port": 8443,
                "path": "/v1/chat",
            },
        )
        headers, count = redact_headers(
            {"Authorization": "Bearer secret", "Content-Type": "application/json"}
        )
        self.assertEqual(headers["Authorization"], REDACTED)
        self.assertEqual(count, 1)
        cleaned, count = redact_text("failed Bearer abc.def and sk-abcdefghijk")
        self.assertNotIn("abc.def", cleaned)
        self.assertNotIn("sk-abcdefghijk", cleaned)
        self.assertEqual(count, 2)

    def test_identity_abstains_without_evidence(self) -> None:
        unknown = infer_identity(claimed_model="gpt-something")
        self.assertEqual(unknown["status"], "unknown")
        self.assertEqual(unknown["confidence"], 0.0)
        mismatch = infer_identity("model-a", "model-b")
        self.assertEqual(mismatch["status"], "mismatch")
        self.assertEqual(mismatch["observed_model"], "model-b")

    def test_store_rejects_raw_content_and_round_trips(self) -> None:
        event = new_observation(
            url="https://api.example.test/v1/chat/completions?token=hidden",
            duration_ms=25,
            outcome="success",
            claimed_model="model-a",
            declared_model="model-a",
            request={"operation": "chat.completions", "input_bytes": 21},
        )
        with TemporaryDirectory() as directory:
            store = NDJSONStore(Path(directory) / "events.ndjson")
            store.append(event)
            self.assertEqual(store.read(), [event])
        event["request"]["messages"] = [{"content": "secret"}]
        with self.assertRaisesRegex(ValueError, "raw content field"):
            validate_observation(event)

    def test_summary_keeps_layers_separate(self) -> None:
        rows = []
        for duration, outcome, declared in (
            (10, "success", "a"),
            (20, "success", "a"),
            (100, "timeout", None),
        ):
            rows.append(
                new_observation(
                    url="https://api.example.test/v1/chat/completions",
                    duration_ms=duration,
                    outcome=outcome,
                    claimed_model="a",
                    declared_model=declared,
                )
            )
        report = summarize(rows)
        self.assertAlmostEqual(report["availability"]["success_rate"], 2 / 3)
        self.assertEqual(report["transport"]["latency_ms"]["p50"], 20)
        self.assertEqual(report["identity"]["statuses"], {"matched": 2, "unknown": 1})
        self.assertEqual(quantile([0, 10], 0.95), 9.5)


if __name__ == "__main__":
    unittest.main()
