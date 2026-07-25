import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import llmwho
from llmwho import JSONLStore, new_observation, quantile, summarize
from llmwho.observation import validate_observation
from llmwho.privacy import REDACTED, endpoint_from_url, redact_headers, redact_text


ROOT = Path(__file__).resolve().parents[3]


class CoreTests(unittest.TestCase):
    def test_legacy_store_name_is_removed(self) -> None:
        legacy_name = "ND" + "JSONStore"
        self.assertFalse(hasattr(llmwho, legacy_name))

    def test_shared_fixture_is_accepted(self) -> None:
        fixture = json.loads(
            (ROOT / "shared/fixtures/observation-v2.json").read_text(encoding="utf-8")
        )
        validate_observation(fixture)
        fixture["schema_version"] = "1"
        with self.assertRaisesRegex(ValueError, "unsupported observation"):
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

    def test_provider_declaration_never_becomes_identity_evidence(self) -> None:
        event = new_observation(
            url="https://api.example.test/v1/chat/completions",
            duration_ms=1,
            outcome="success",
            requested_model="model-a",
            declared_model="model-b",
        )
        self.assertEqual(
            event["identity"],
            {"status": "unknown", "candidates": [], "evidence": []},
        )
        self.assertEqual(event["model_declaration"]["status"], "mismatch")
        self.assertEqual(
            event["model_declaration"]["evidence"],
            [
                {
                    "kind": "provider_declaration",
                    "source": "response.body.model",
                    "value": "model-b",
                }
            ],
        )
        self.assertNotIn("confidence", event["identity"])

    def test_store_rejects_raw_content_and_round_trips(self) -> None:
        event = new_observation(
            url="https://api.example.test/v1/chat/completions?token=hidden",
            duration_ms=25,
            outcome="success",
            requested_model="model-a",
            declared_model="model-a",
            request={"operation": "chat.completions", "input_bytes": 21},
        )
        with TemporaryDirectory() as directory:
            store = JSONLStore(Path(directory) / "events.jsonl")
            store.append(event)
            self.assertEqual(store.read(), [event])
        event["request"]["messages"] = [{"content": "secret"}]
        with self.assertRaisesRegex(ValueError, "raw content field"):
            validate_observation(event)

    def test_v36_complete_schema_validation_rejects_unknown_and_malformed_fields(
        self,
    ) -> None:
        valid = new_observation(
            url="https://api.example.test/v1/chat/completions",
            duration_ms=25,
            outcome="success",
            requested_model="model-a",
            declared_model="model-a",
            response={"usage": {"input_tokens": 1}},
        )
        cases = []
        unknown = deepcopy(valid)
        unknown["unexpected"] = True
        cases.append(unknown)
        missing_nested = deepcopy(valid)
        del missing_nested["sdk"]["version"]
        cases.append(missing_nested)
        invalid_port = deepcopy(valid)
        invalid_port["endpoint"]["port"] = 0
        cases.append(invalid_port)
        boolean_integer = deepcopy(valid)
        boolean_integer["response"]["usage"]["input_tokens"] = True
        cases.append(boolean_integer)
        invalid_timestamp = deepcopy(valid)
        invalid_timestamp["timestamp"] = "not-a-date"
        cases.append(invalid_timestamp)
        for event in cases:
            with self.subTest(event=event), self.assertRaises(ValueError):
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
                    requested_model="a",
                    declared_model=declared,
                )
            )
        report = summarize(rows)
        self.assertAlmostEqual(report["availability"]["success_rate"], 2 / 3)
        self.assertEqual(report["transport"]["latency_ms"]["p50"], 20)
        self.assertEqual(report["identity"]["statuses"], {"unknown": 3})
        self.assertEqual(
            report["declarations"]["statuses"],
            {"matched": 2, "missing": 1},
        )
        self.assertEqual(quantile([0, 10], 0.95), 9.5)


if __name__ == "__main__":
    unittest.main()
