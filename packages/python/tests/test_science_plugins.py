from __future__ import annotations

import io
import json
from types import SimpleNamespace
from unittest import mock
import unittest

from llmwho import science
from llmwho.science.registry import PluginRegistry
from llmwho.science.worker import serve


class _ExamplePlugin:
    id = "example"
    version = "2.0.0"
    summary = "Example test plugin"
    required_inputs = ("value",)
    limitations = ("test-only",)

    def analyze(self, payload):
        return {"doubled": payload["value"] * 2}


class _EntryPoint:
    name = "example"
    dist = SimpleNamespace(name="llmwho-example")

    @staticmethod
    def load():
        return _ExamplePlugin


class SciencePluginTests(unittest.TestCase):
    def test_builtin_plugin_uses_public_registry_contract(self) -> None:
        descriptors = science.plugins()
        self.assertEqual([item["id"] for item in descriptors], ["output_affinity"])
        self.assertEqual(descriptors[0]["source"], "builtin")

    def test_entry_point_plugin_is_discovered_and_versioned(self) -> None:
        with mock.patch("llmwho.science.registry.entry_points", return_value=[_EntryPoint()]):
            registry = PluginRegistry()
        report = registry.run("example", {"value": 4})
        self.assertEqual(report["plugin"]["source"], "llmwho-example")
        self.assertEqual(report["evidence"], {"doubled": 8})
        self.assertEqual(report["limitations"], ["test-only"])

    def test_duplicate_plugin_id_is_rejected(self) -> None:
        class Duplicate(_ExamplePlugin):
            id = "output_affinity"

        point = _EntryPoint()
        point.load = lambda: Duplicate
        with mock.patch("llmwho.science.registry.entry_points", return_value=[point]):
            with self.assertRaisesRegex(ValueError, "duplicate"):
                PluginRegistry()

    def test_non_json_plugin_result_is_rejected(self) -> None:
        class NonJson(_ExamplePlugin):
            def analyze(self, payload):
                return {"value": object()}

        point = _EntryPoint()
        point.load = lambda: NonJson
        with mock.patch("llmwho.science.registry.entry_points", return_value=[point]):
            registry = PluginRegistry()
        with self.assertRaisesRegex(TypeError, "JSON-safe"):
            registry.run("example", {"value": 1})

    def test_worker_protocol_does_not_echo_raw_input_in_errors(self) -> None:
        secret = "TOP-SECRET-RAW-PROSE"
        requests = [
            {
                "protocol_version": "1",
                "id": 1,
                "method": "analyze",
                "params": {
                    "plugin": "output_affinity",
                    "payload": {"corpora": {"A": [secret]}},
                },
            },
            {"protocol_version": "1", "id": 2, "method": "shutdown"},
        ]
        source = io.StringIO("".join(json.dumps(item) + "\n" for item in requests))
        destination = io.StringIO()
        self.assertEqual(serve(source, destination), 0)
        output = destination.getvalue()
        self.assertNotIn(secret, output)
        responses = [json.loads(line) for line in output.splitlines()]
        self.assertEqual(responses[0]["error"]["code"], "invalid_request")
        self.assertTrue(responses[1]["result"]["shutdown"])


if __name__ == "__main__":
    unittest.main()
