import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import types
import unittest

from llmwho.anthropic import (
    is_messages_url,
    request_metadata,
    response_metadata,
)
from llmwho.hooks import HookHandle, _install_httpx
from llmwho.storage import JSONLStore


FIXTURE_PATH = (
    Path(__file__).resolve().parents[3]
    / "shared"
    / "fixtures"
    / "anthropic-messages.json"
)


class _Request:
    def __init__(self, body: dict) -> None:
        self.url = "https://api.anthropic.com/v1/messages?api_key=never-store"
        self.content = json.dumps(body).encode()
        self.headers = {"x-api-key": "never-store", "anthropic-version": "2023-06-01"}


class _Response:
    def __init__(self, body: dict, *, consumed: bool = True) -> None:
        self.status_code = 200
        self.headers = {"request-id": "req_fixture"}
        self.is_stream_consumed = consumed
        self._content = json.dumps(body).encode()
        self.content_reads = 0

    @property
    def content(self) -> bytes:
        self.content_reads += 1
        if not self.is_stream_consumed:
            raise AssertionError("stream body must not be accessed")
        return self._content


class _Client:
    response: _Response

    def send(self, request, *args, **kwargs):
        return self.response


class _AsyncClient:
    response: _Response

    async def send(self, request, *args, **kwargs):
        return self.response


class AnthropicAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE_PATH.read_text())

    def test_shared_fixture_normalizes_content_free_metadata(self) -> None:
        fixture = self.fixture
        self.assertTrue(is_messages_url(fixture["url"]))
        self.assertFalse(is_messages_url("https://api.example/v1/messages"))

        request, requested = request_metadata(
            fixture["request"], fixture["request_size"]
        )
        response, declared = response_metadata(
            fixture["response"],
            fixture["response_size"],
            fixture["status_code"],
        )

        self.assertEqual(request, fixture["expected_request"])
        self.assertEqual(response, fixture["expected_response"])
        self.assertEqual(requested, fixture["request"]["model"])
        self.assertEqual(declared, fixture["response"]["model"])
        serialized = json.dumps({"request": request, "response": response})
        self.assertNotIn("fixture user content", serialized)
        self.assertNotIn("fixture response content", serialized)

    def test_malformed_optional_metadata_is_omitted(self) -> None:
        request, requested = request_metadata(
            {"model": 7, "stream": "yes", "messages": {}}, -1
        )
        response, declared = response_metadata(
            {
                "model": None,
                "usage": {"input_tokens": True, "output_tokens": -2},
            },
            -1,
            200,
        )
        self.assertEqual(request, {"operation": "messages", "input_bytes": 0})
        self.assertIsNone(requested)
        self.assertEqual(response, {"status_code": 200, "output_bytes": 0})
        self.assertIsNone(declared)

    def test_httpx_hook_normalizes_direct_response_and_redacts_content(self) -> None:
        fixture = self.fixture
        module = types.SimpleNamespace(Client=_Client, AsyncClient=_AsyncClient)
        _Client.response = _Response(fixture["response"])
        _AsyncClient.response = _Response(fixture["response"])
        with TemporaryDirectory() as directory:
            store = JSONLStore(Path(directory) / "events.jsonl")
            handle = HookHandle(store)
            _install_httpx(handle, module)
            try:
                response = _Client().send(_Request(fixture["request"]))
                async_response = asyncio.run(
                    _AsyncClient().send(_Request(fixture["request"]))
                )
                self.assertIs(response, _Client.response)
                self.assertIs(async_response, _AsyncClient.response)
                events = store.read()
                self.assertEqual(len(events), 2)
                for event in events:
                    self.assertEqual(event["endpoint"]["provider"], "anthropic")
                    self.assertEqual(event["request"]["operation"], "messages")
                    self.assertEqual(event["request"]["role_count"], 2)
                    self.assertEqual(event["response"]["usage"]["total_tokens"], 20)
                    self.assertEqual(
                        event["model_declaration"]["status"],
                        "matched",
                    )
                    self.assertEqual(event["identity"]["status"], "unknown")
                    self.assertEqual(event["identity"]["candidates"], [])
                    self.assertEqual(
                        event["privacy"],
                        {"content_captured": False, "redactions": 2},
                    )
                persisted = store.path.read_text()
                self.assertNotIn("fixture user content", persisted)
                self.assertNotIn("fixture response content", persisted)
                self.assertNotIn("never-store", persisted)
            finally:
                handle.shutdown()

    def test_httpx_stream_response_is_not_consumed(self) -> None:
        fixture = self.fixture
        stream_request = dict(fixture["request"], stream=True)
        module = types.SimpleNamespace(Client=_Client, AsyncClient=_AsyncClient)
        _Client.response = _Response(fixture["response"], consumed=False)
        _AsyncClient.response = _Response(fixture["response"], consumed=False)
        with TemporaryDirectory() as directory:
            store = JSONLStore(Path(directory) / "events.jsonl")
            handle = HookHandle(store)
            _install_httpx(handle, module)
            try:
                response = _Client().send(_Request(stream_request), stream=True)
                async_response = asyncio.run(
                    _AsyncClient().send(_Request(stream_request), stream=True)
                )
                self.assertIs(response, _Client.response)
                self.assertIs(async_response, _AsyncClient.response)
                self.assertEqual(response.content_reads, 0)
                self.assertEqual(async_response.content_reads, 0)
                events = store.read()
                self.assertEqual(len(events), 2)
                for event in events:
                    self.assertTrue(event["request"]["stream"])
                    self.assertEqual(event["response"]["output_bytes"], 0)
                    self.assertNotIn("model_declaration", event)
                    self.assertEqual(event["transport"]["outcome"], "success")
            finally:
                handle.shutdown()


if __name__ == "__main__":
    unittest.main()
