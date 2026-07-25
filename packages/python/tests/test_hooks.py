import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import types
import unittest

from llmwho.hooks import HookHandle, _install_httpx, _install_requests, is_llm_url
from llmwho.storage import JSONLStore


class Headers(dict):
    pass


class HttpxRequest:
    def __init__(self, url: str, body: dict) -> None:
        self.url = url
        self.content = json.dumps(body).encode()
        self.headers = Headers({"Authorization": "Bearer never-store"})


class HttpxResponse:
    def __init__(self, body: dict, status_code: int = 200, consumed: bool = True) -> None:
        self.status_code = status_code
        self.content = json.dumps(body).encode()
        self.headers = Headers({"x-request-id": "request-1"})
        self.is_stream_consumed = consumed


class FakeHttpxClient:
    response = HttpxResponse(
        {
            "model": "actual-model",
            "system_fingerprint": "fp_123",
            "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
        }
    )

    def send(self, request, *args, **kwargs):
        return self.response


class FakeAsyncHttpxClient:
    response = FakeHttpxClient.response

    async def send(self, request, *args, **kwargs):
        return self.response


class FakePreparedRequest:
    def __init__(self, url: str) -> None:
        self.url = url
        self.body = json.dumps({"model": "requested", "messages": [{"role": "user"}]})
        self.headers = Headers({"X-Api-Key": "never-store"})


class FakeRequestsResponse:
    status_code = 200
    content = json.dumps({"model": "requested"}).encode()
    headers = Headers()


class FakeRequestsSession:
    def send(self, request, **kwargs):
        return FakeRequestsResponse()


class HookTests(unittest.TestCase):
    def test_known_routes_and_explicit_matcher(self) -> None:
        self.assertTrue(is_llm_url("https://api.example/v1/chat/completions"))
        self.assertTrue(is_llm_url("https://api.example/v1beta/models/x:generateContent"))
        self.assertFalse(is_llm_url("https://api.example/users"))
        self.assertTrue(is_llm_url("https://private.example/custom", "https://private.example"))

    def test_httpx_sync_and_async_preserve_values_and_record(self) -> None:
        module = types.SimpleNamespace(Client=FakeHttpxClient, AsyncClient=FakeAsyncHttpxClient)
        original_sync = FakeHttpxClient.send
        original_async = FakeAsyncHttpxClient.send
        with TemporaryDirectory() as directory:
            store = JSONLStore(Path(directory) / "events.jsonl")
            handle = HookHandle(store)
            _install_httpx(handle, module)
            request = HttpxRequest(
                "https://api.example/v1/chat/completions?api_key=never-store",
                {"model": "requested", "messages": [{"role": "user"}]},
            )
            sync_response = FakeHttpxClient().send(request)
            async_response = asyncio.run(FakeAsyncHttpxClient().send(request))
            self.assertIs(sync_response, FakeHttpxClient.response)
            self.assertIs(async_response, FakeAsyncHttpxClient.response)
            events = store.read()
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0]["identity"]["status"], "unknown")
            self.assertEqual(
                events[0]["model_declaration"]["status"],
                "mismatch",
            )
            self.assertEqual(events[0]["request"]["role_count"], 1)
            self.assertNotIn("never-store", store.path.read_text())
            handle.shutdown()
            self.assertIs(FakeHttpxClient.send, original_sync)
            self.assertIs(FakeAsyncHttpxClient.send, original_async)

    def test_requests_stream_is_not_consumed(self) -> None:
        module = types.SimpleNamespace(
            sessions=types.SimpleNamespace(Session=FakeRequestsSession)
        )
        original = FakeRequestsSession.send
        with TemporaryDirectory() as directory:
            store = JSONLStore(Path(directory) / "events.jsonl")
            handle = HookHandle(store)
            _install_requests(handle, module)
            response = FakeRequestsSession().send(
                FakePreparedRequest("https://api.example/v1/chat/completions"), stream=True
            )
            self.assertIsInstance(response, FakeRequestsResponse)
            event = store.read()[0]
            self.assertNotIn("declared_model", event["response"])
            handle.shutdown()
            self.assertIs(FakeRequestsSession.send, original)

    def test_telemetry_failure_does_not_break_request(self) -> None:
        module = types.SimpleNamespace(Client=FakeHttpxClient, AsyncClient=FakeAsyncHttpxClient)
        handle = HookHandle(JSONLStore("/dev/null/impossible"))
        _install_httpx(handle, module)
        try:
            response = FakeHttpxClient().send(
                HttpxRequest("https://api.example/v1/responses", {"model": "requested"})
            )
            self.assertIs(response, FakeHttpxClient.response)
        finally:
            handle.shutdown()


if __name__ == "__main__":
    unittest.main()
