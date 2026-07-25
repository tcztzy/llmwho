"""Fail-open adapters for Claude Code and Codex lifecycle hooks."""

import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from typing import Any
from collections.abc import Mapping

from .observation import new_observation
from .storage import JSONLStore


MAX_HOOK_INPUT_BYTES = 8 * 1024 * 1024
CLIENTS = {
    "claude-code": {"provider": "anthropic", "keep_model": True},
    "codex": {"provider": "openai", "keep_model": False},
}
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+\-]{0,255}\Z")
_FAILURE_TYPES = frozenset(
    {
        "rate_limit",
        "overloaded",
        "authentication_failed",
        "oauth_org_not_allowed",
        "billing_error",
        "invalid_request",
        "model_not_found",
        "server_error",
        "max_output_tokens",
        "timeout",
        "unknown",
    }
)


def _enabled() -> bool:
    return os.environ.get("LLMWHO_DISABLED", "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }


def _safe_model(value: Any) -> str | None:
    return value if isinstance(value, str) and _MODEL.fullmatch(value) else None


def _state_path(store: JSONLStore, client: str, session_id: Any) -> Path | None:
    if not isinstance(session_id, str) or not session_id:
        return None
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    return store.path.parent / ".hook-state" / client / f"{digest}.json"


def _read_state(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(value, dict):
        return {}
    state: dict[str, Any] = {}
    model = _safe_model(value.get("model"))
    if model:
        state["model"] = model
    started = value.get("started_at_ms")
    if (
        type(started) in {int, float}
        and math.isfinite(started)
        and started >= 0
    ):
        state["started_at_ms"] = float(started)
    input_bytes = value.get("input_bytes")
    if (
        type(input_bytes) is int
        and 0 <= input_bytes <= MAX_HOOK_INPUT_BYTES
    ):
        state["input_bytes"] = input_bytes
    return state


def _delete_state(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except Exception:
        return


def _write_state(path: Path | None, state: Mapping[str, Any]) -> None:
    if path is None:
        return
    safe: dict[str, Any] = {}
    model = _safe_model(state.get("model"))
    if model:
        safe["model"] = model
    started = state.get("started_at_ms")
    if (
        type(started) in {int, float}
        and math.isfinite(started)
        and started >= 0
    ):
        safe["started_at_ms"] = float(started)
    input_bytes = state.get("input_bytes")
    if (
        type(input_bytes) is int
        and 0 <= input_bytes <= MAX_HOOK_INPUT_BYTES
    ):
        safe["input_bytes"] = input_bytes
    if not safe:
        _delete_state(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(
        temporary,
        os.O_CREAT | os.O_TRUNC | os.O_WRONLY,
        0o600,
    )
    try:
        os.write(
            descriptor,
            json.dumps(safe, separators=(",", ":")).encode("utf-8"),
        )
    finally:
        os.close(descriptor)
    os.replace(temporary, path)


def _duration_ms(state: Mapping[str, Any], now_ms: float) -> float:
    started = state.get("started_at_ms")
    if type(started) not in {int, float}:
        return 0.0
    return max(0.0, now_ms - float(started))


def _failure_type(value: Any) -> str:
    return value if isinstance(value, str) and value in _FAILURE_TYPES else "unknown"


def observe_hook_event(
    client: str,
    payload: Mapping[str, Any],
    *,
    store: JSONLStore,
    expected_event: str | None = None,
    now_ms: float | None = None,
) -> dict[str, Any] | None:
    """Update safe hook state and append one turn observation when applicable."""

    config = CLIENTS.get(client)
    if config is None:
        raise ValueError("unsupported hook client")
    event_name = payload.get("hook_event_name")
    if not isinstance(event_name, str):
        return None
    if expected_event and event_name != expected_event:
        return None

    current_ms = time.time() * 1000 if now_ms is None else max(0.0, now_ms)
    path = _state_path(store, client, payload.get("session_id"))
    state = _read_state(path)
    model = _safe_model(payload.get("model"))
    if model:
        state["model"] = model

    if event_name == "SessionStart":
        _write_state(path, state)
        return None
    if event_name == "UserPromptSubmit":
        state["started_at_ms"] = current_ms
        prompt = payload.get("prompt")
        if isinstance(prompt, str):
            state["input_bytes"] = len(prompt.encode("utf-8"))
        else:
            state.pop("input_bytes", None)
        _write_state(path, state)
        return None
    if event_name == "SessionEnd":
        _delete_state(path)
        return None
    if event_name not in {"Stop", "StopFailure"}:
        return None

    duration_ms = _duration_ms(state, current_ms)
    requested_model = model or _safe_model(state.get("model"))
    request: dict[str, Any] = {"operation": "agent.turn"}
    input_bytes = state.get("input_bytes")
    if type(input_bytes) is int:
        request["input_bytes"] = input_bytes
    if requested_model:
        request["requested_model"] = requested_model

    response = None
    outcome = "success"
    error_type = None
    if event_name == "Stop":
        assistant_message = payload.get("last_assistant_message")
        if isinstance(assistant_message, str):
            response = {"output_bytes": len(assistant_message.encode("utf-8"))}
    else:
        error_type = _failure_type(payload.get("error"))
        outcome = "timeout" if error_type == "timeout" else "http_error"

    event = new_observation(
        url=f"hook://{client}/{event_name.lower()}",
        duration_ms=duration_ms,
        outcome=outcome,
        provider=str(config["provider"]),
        requested_model=requested_model,
        request=request,
        response=response,
        error_type=error_type,
    )
    store.append(event)

    state.pop("started_at_ms", None)
    state.pop("input_bytes", None)
    if config["keep_model"]:
        _write_state(path, state)
    else:
        _delete_state(path)
    return event


def _read_stdin() -> bytes | None:
    stream = getattr(sys.stdin, "buffer", sys.stdin)
    value = stream.read(MAX_HOOK_INPUT_BYTES + 1)
    raw = value.encode("utf-8") if isinstance(value, str) else bytes(value)
    if len(raw) <= MAX_HOOK_INPUT_BYTES:
        return raw
    while stream.read(64 * 1024):
        pass
    return None


def _write_protocol_output(client: str, event_name: str | None) -> None:
    if client == "codex" and event_name in {"Stop", "SubagentStop"}:
        sys.stdout.write("{}\n")


def run_hook_cli(
    client: str,
    *,
    expected_event: str | None = None,
    storage_path: str | None = None,
) -> int:
    """Read one hook payload. Telemetry failure never changes hook control flow."""

    actual_event = None
    try:
        raw = _read_stdin()
        if raw is not None:
            value = json.loads(raw.decode("utf-8"))
            if isinstance(value, dict):
                actual_event = value.get("hook_event_name")
                if _enabled():
                    configured_path = storage_path or os.environ.get("LLMWHO_STORAGE")
                    observe_hook_event(
                        client,
                        value,
                        store=JSONLStore(configured_path),
                        expected_event=expected_event,
                    )
    except Exception:
        pass
    _write_protocol_output(client, expected_event or actual_event)
    return 0
