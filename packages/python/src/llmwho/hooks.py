"""One-call passive instrumentation for optional Python HTTP clients."""

import importlib
import importlib.util
import json
import os
import re
from dataclasses import dataclass, field
from threading import RLock
from time import perf_counter
from typing import Any
from collections.abc import Callable, Mapping
from urllib.parse import parse_qsl, urlsplit

from .anthropic import (
    PROVIDER as ANTHROPIC_PROVIDER,
    is_messages_url as is_anthropic_messages_url,
    request_metadata as anthropic_request_metadata,
    response_metadata as anthropic_response_metadata,
)
from .observation import new_observation
from .privacy import SENSITIVE_HEADERS
from .remote import RemoteStore
from .storage import JSONLStore


EndpointMatcher = Callable[[str], bool] | str | None

_KNOWN_LLM_PATH = re.compile(
    r"(?:/chat/completions|/completions|/responses|/messages|"
    r"/api/chat|/api/generate|:generatecontent|:streamgeneratecontent)(?:/|$|\?)",
    re.IGNORECASE,
)
_STATE_LOCK = RLock()
_ACTIVE_HANDLE: "HookHandle | None" = None


def _environment_enabled() -> bool:
    return os.environ.get("LLMWHO_DISABLED", "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }


def is_llm_url(url: str, endpoint: EndpointMatcher = None) -> bool:
    if callable(endpoint):
        try:
            return bool(endpoint(url))
        except Exception:
            return False
    if isinstance(endpoint, str) and endpoint:
        return url.startswith(endpoint)
    return bool(_KNOWN_LLM_PATH.search(urlsplit(url).path))


def _redaction_count(url: str, headers: Mapping[str, Any]) -> int:
    count = sum(1 for key in headers if str(key).lower() in SENSITIVE_HEADERS)
    try:
        count += sum(
            1
            for key, _ in parse_qsl(urlsplit(url).query, keep_blank_values=True)
            if key.lower()
            in {"api_key", "apikey", "key", "token", "access_token", "signature", "sig"}
        )
    except Exception:
        pass
    return count


def _json_mapping(body: Any) -> tuple[dict[str, Any] | None, int]:
    if body is None:
        return None, 0
    if isinstance(body, str):
        raw = body.encode("utf-8")
    elif isinstance(body, (bytes, bytearray, memoryview)):
        raw = bytes(body)
    else:
        return None, 0
    size = len(raw)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, size
    return (value if isinstance(value, dict) else None), size


def _request_metadata(payload: Mapping[str, Any] | None, size: int, path: str) -> tuple[dict, str | None]:
    metadata: dict[str, Any] = {"operation": _operation(path), "input_bytes": size}
    claimed = None
    if payload:
        if isinstance(payload.get("model"), str):
            claimed = payload["model"]
            metadata["claimed_model"] = claimed
        if isinstance(payload.get("stream"), bool):
            metadata["stream"] = payload["stream"]
        messages = payload.get("messages")
        if isinstance(messages, list):
            metadata["role_count"] = len(messages)
    return metadata, claimed


def _response_metadata(payload: Mapping[str, Any] | None, size: int, status_code: int) -> tuple[dict, str | None]:
    metadata: dict[str, Any] = {"status_code": status_code, "output_bytes": size}
    declared = None
    if payload:
        if isinstance(payload.get("model"), str):
            declared = payload["model"]
            metadata["declared_model"] = declared
        if isinstance(payload.get("system_fingerprint"), str):
            metadata["system_fingerprint"] = payload["system_fingerprint"]
        usage = payload.get("usage")
        if isinstance(usage, Mapping):
            safe_usage = {}
            aliases = {
                "input_tokens": ("input_tokens", "prompt_tokens"),
                "output_tokens": ("output_tokens", "completion_tokens"),
                "total_tokens": ("total_tokens",),
            }
            for target, candidates in aliases.items():
                for candidate in candidates:
                    value = usage.get(candidate)
                    if isinstance(value, int) and value >= 0:
                        safe_usage[target] = value
                        break
            if safe_usage:
                metadata["usage"] = safe_usage
    return metadata, declared


def _normalized_request_metadata(
    url: str, payload: Mapping[str, Any] | None, size: int
) -> tuple[dict[str, Any], str | None, str | None]:
    if is_anthropic_messages_url(url):
        metadata, claimed = anthropic_request_metadata(payload, size)
        return metadata, claimed, ANTHROPIC_PROVIDER
    metadata, claimed = _request_metadata(payload, size, urlsplit(url).path)
    return metadata, claimed, None


def _normalized_response_metadata(
    provider: str | None,
    payload: Mapping[str, Any] | None,
    size: int,
    status_code: int,
) -> tuple[dict[str, Any], str | None]:
    if provider == ANTHROPIC_PROVIDER:
        return anthropic_response_metadata(payload, size, status_code)
    return _response_metadata(payload, size, status_code)


def _operation(path: str) -> str:
    lowered = path.lower()
    if "/chat/completions" in lowered:
        return "chat.completions"
    if "/responses" in lowered:
        return "responses"
    if "/messages" in lowered:
        return "messages"
    if "generatecontent" in lowered:
        return "generateContent"
    if "/api/chat" in lowered:
        return "chat"
    if "/api/generate" in lowered:
        return "generate"
    return "completions"


def _outcome(status_code: int) -> str:
    return "success" if 200 <= status_code < 400 else "http_error"


def _exception_outcome(error: Exception) -> str:
    name = type(error).__name__.lower()
    return "timeout" if "timeout" in name else "network_error"


@dataclass
class HookHandle:
    store: JSONLStore | RemoteStore
    endpoint: EndpointMatcher = None
    capture_content: bool = False
    _patches: list[tuple[Any, str, Any, Any]] = field(default_factory=list)
    active: bool = True

    def _patch(self, owner: Any, attribute: str, wrapper: Any) -> None:
        original = getattr(owner, attribute)
        setattr(owner, attribute, wrapper)
        self._patches.append((owner, attribute, original, wrapper))

    def _observe(self, **fields: Any) -> None:
        try:
            self.store.append(new_observation(**fields))
        except Exception:
            # Instrumentation is strictly fail-open for the host application.
            return

    def shutdown(self) -> None:
        global _ACTIVE_HANDLE
        with _STATE_LOCK:
            if not self.active:
                return
            for owner, attribute, original, wrapper in reversed(self._patches):
                if getattr(owner, attribute, None) is wrapper:
                    setattr(owner, attribute, original)
            self._patches.clear()
            self.active = False
            self.store.close()
            if _ACTIVE_HANDLE is self:
                _ACTIVE_HANDLE = None


def _httpx_body(request: Any) -> tuple[dict[str, Any] | None, int]:
    try:
        return _json_mapping(request.content)
    except Exception:
        return None, 0


def _httpx_response_body(response: Any) -> tuple[dict[str, Any] | None, int]:
    try:
        if not response.is_stream_consumed:
            return None, 0
        return _json_mapping(response.content)
    except Exception:
        return None, 0


def _install_httpx(handle: HookHandle, module: Any) -> None:
    sync_original = module.Client.send

    def send(client: Any, request: Any, *args: Any, **kwargs: Any) -> Any:
        url = str(request.url)
        if not handle.active or not is_llm_url(url, handle.endpoint):
            return sync_original(client, request, *args, **kwargs)
        started = perf_counter()
        request_payload, request_size = _httpx_body(request)
        request_meta, claimed, provider = _normalized_request_metadata(
            url, request_payload, request_size
        )
        redactions = _redaction_count(url, request.headers)
        try:
            response = sync_original(client, request, *args, **kwargs)
        except Exception as error:
            handle._observe(
                url=url,
                duration_ms=(perf_counter() - started) * 1000,
                outcome=_exception_outcome(error),
                provider=provider,
                claimed_model=claimed,
                request=request_meta,
                redactions=redactions,
            )
            raise
        response_payload, response_size = _httpx_response_body(response)
        response_meta, declared = _normalized_response_metadata(
            provider, response_payload, response_size, response.status_code
        )
        handle._observe(
            url=url,
            duration_ms=(perf_counter() - started) * 1000,
            outcome=_outcome(response.status_code),
            provider=provider,
            claimed_model=claimed,
            declared_model=declared,
            request=request_meta,
            response=response_meta,
            redactions=redactions,
        )
        return response

    handle._patch(module.Client, "send", send)

    async_original = module.AsyncClient.send

    async def async_send(client: Any, request: Any, *args: Any, **kwargs: Any) -> Any:
        url = str(request.url)
        if not handle.active or not is_llm_url(url, handle.endpoint):
            return await async_original(client, request, *args, **kwargs)
        started = perf_counter()
        request_payload, request_size = _httpx_body(request)
        request_meta, claimed, provider = _normalized_request_metadata(
            url, request_payload, request_size
        )
        redactions = _redaction_count(url, request.headers)
        try:
            response = await async_original(client, request, *args, **kwargs)
        except Exception as error:
            handle._observe(
                url=url,
                duration_ms=(perf_counter() - started) * 1000,
                outcome=_exception_outcome(error),
                provider=provider,
                claimed_model=claimed,
                request=request_meta,
                redactions=redactions,
            )
            raise
        response_payload, response_size = _httpx_response_body(response)
        response_meta, declared = _normalized_response_metadata(
            provider, response_payload, response_size, response.status_code
        )
        handle._observe(
            url=url,
            duration_ms=(perf_counter() - started) * 1000,
            outcome=_outcome(response.status_code),
            provider=provider,
            claimed_model=claimed,
            declared_model=declared,
            request=request_meta,
            response=response_meta,
            redactions=redactions,
        )
        return response

    handle._patch(module.AsyncClient, "send", async_send)


def _install_requests(handle: HookHandle, module: Any) -> None:
    original = module.sessions.Session.send

    def send(session: Any, request: Any, **kwargs: Any) -> Any:
        url = str(request.url)
        if not handle.active or not is_llm_url(url, handle.endpoint):
            return original(session, request, **kwargs)
        started = perf_counter()
        request_payload, request_size = _json_mapping(request.body)
        request_meta, claimed, provider = _normalized_request_metadata(
            url, request_payload, request_size
        )
        redactions = _redaction_count(url, request.headers)
        try:
            response = original(session, request, **kwargs)
        except Exception as error:
            handle._observe(
                url=url,
                duration_ms=(perf_counter() - started) * 1000,
                outcome=_exception_outcome(error),
                provider=provider,
                claimed_model=claimed,
                request=request_meta,
                redactions=redactions,
            )
            raise
        if kwargs.get("stream"):
            response_payload, response_size = None, 0
        else:
            response_payload, response_size = _json_mapping(response.content)
        response_meta, declared = _normalized_response_metadata(
            provider, response_payload, response_size, response.status_code
        )
        handle._observe(
            url=url,
            duration_ms=(perf_counter() - started) * 1000,
            outcome=_outcome(response.status_code),
            provider=provider,
            claimed_model=claimed,
            declared_model=declared,
            request=request_meta,
            response=response_meta,
            redactions=redactions,
        )
        return response

    handle._patch(module.sessions.Session, "send", send)


def _load_optional(name: str) -> Any | None:
    try:
        if importlib.util.find_spec(name) is None:
            return None
        return importlib.import_module(name)
    except Exception:
        return None


def init(
    *,
    storage_path: os.PathLike[str] | str | None = None,
    capture_content: bool = False,
    endpoint: EndpointMatcher = None,
    collector_url: str | None = None,
    collector_token: str | None = None,
    collector_protocol: str | None = None,
) -> HookHandle:
    """Install one process-wide passive hook layer and return its handle.

    Importing LLMWho and calling ``init`` never sends network traffic. The
    ``capture_content`` option is reserved; ObservationV1 remains content-free
    even when callers pass it in this release.
    """

    global _ACTIVE_HANDLE
    with _STATE_LOCK:
        if _ACTIVE_HANDLE is not None and _ACTIVE_HANDLE.active:
            return _ACTIVE_HANDLE
        configured_path = storage_path or os.environ.get("LLMWHO_STORAGE")
        active = _environment_enabled()
        configured_collector = collector_url or os.environ.get("LLMWHO_COLLECTOR_URL")
        if active and configured_collector:
            token = (
                collector_token
                if collector_token is not None
                else os.environ.get("LLMWHO_COLLECTOR_TOKEN")
            )
            store: JSONLStore | RemoteStore = RemoteStore(
                configured_collector,
                token=token,
                protocol=collector_protocol
                or os.environ.get("LLMWHO_COLLECTOR_PROTOCOL", "native"),
            )
        else:
            store = JSONLStore(configured_path)
        handle = HookHandle(
            store=store,
            endpoint=endpoint,
            capture_content=False,
            active=active,
        )
        _ACTIVE_HANDLE = handle
        if not handle.active:
            return handle
        httpx = _load_optional("httpx")
        if httpx is not None:
            try:
                _install_httpx(handle, httpx)
            except Exception:
                pass
        requests = _load_optional("requests")
        if requests is not None:
            try:
                _install_requests(handle, requests)
            except Exception:
                pass
        return handle
