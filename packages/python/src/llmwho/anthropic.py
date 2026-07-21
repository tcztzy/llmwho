"""Content-free normalization for direct Anthropic Messages API traffic."""

from __future__ import annotations

from typing import Any, Mapping, Optional
from urllib.parse import urlsplit


PROVIDER = "anthropic"
MESSAGES_OPERATION = "messages"


def is_messages_url(url: str) -> bool:
    """Return whether *url* is Anthropic's direct Messages endpoint."""

    try:
        parsed = urlsplit(url)
        return (
            (parsed.hostname or "").lower() == "api.anthropic.com"
            and parsed.path.rstrip("/") == "/v1/messages"
        )
    except Exception:
        return False


def _token(value: Any) -> Optional[int]:
    return value if type(value) is int and value >= 0 else None


def request_metadata(
    payload: Optional[Mapping[str, Any]], size: int
) -> tuple[dict[str, Any], Optional[str]]:
    """Normalize safe request metadata without retaining message content."""

    metadata: dict[str, Any] = {
        "operation": MESSAGES_OPERATION,
        "input_bytes": max(0, size),
    }
    claimed = None
    if payload:
        model = payload.get("model")
        if isinstance(model, str):
            claimed = model
            metadata["claimed_model"] = model
        stream = payload.get("stream")
        if isinstance(stream, bool):
            metadata["stream"] = stream
        messages = payload.get("messages")
        if isinstance(messages, list):
            metadata["role_count"] = len(messages)
    return metadata, claimed


def response_metadata(
    payload: Optional[Mapping[str, Any]], size: int, status_code: int
) -> tuple[dict[str, Any], Optional[str]]:
    """Normalize safe response metadata and Anthropic token accounting."""

    metadata: dict[str, Any] = {
        "status_code": status_code,
        "output_bytes": max(0, size),
    }
    declared = None
    if not payload:
        return metadata, declared

    model = payload.get("model")
    if isinstance(model, str):
        declared = model
        metadata["declared_model"] = model

    raw_usage = payload.get("usage")
    if isinstance(raw_usage, Mapping):
        input_tokens = _token(raw_usage.get("input_tokens"))
        output_tokens = _token(raw_usage.get("output_tokens"))
        usage: dict[str, int] = {}
        if input_tokens is not None:
            usage["input_tokens"] = input_tokens
        if output_tokens is not None:
            usage["output_tokens"] = output_tokens
        if input_tokens is not None and output_tokens is not None:
            usage["total_tokens"] = input_tokens + output_tokens
        if usage:
            metadata["usage"] = usage
    return metadata, declared
