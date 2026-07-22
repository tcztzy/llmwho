"""Privacy boundaries shared by hooks, probes, and storage."""

import re
from typing import Any
from collections.abc import Mapping
from urllib.parse import urlsplit


REDACTED = "[REDACTED]"
SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "api-key",
    }
)
FORBIDDEN_PERSISTED_KEYS = frozenset(
    {
        "authorization",
        "api_key",
        "body",
        "content",
        "input",
        "messages",
        "output",
        "prompt",
        "request_body",
        "response_body",
        "response_text",
    }
)

_SECRET_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/]+=*"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)(api[_-]?key|access[_-]?token|signature)=([^&\s]+)"),
)


def endpoint_from_url(url: str) -> dict[str, Any]:
    """Return a query-, fragment-, and user-info-free endpoint descriptor."""

    parsed = urlsplit(url)
    endpoint: dict[str, Any] = {
        "scheme": parsed.scheme if parsed.scheme in {"http", "https"} else "unknown",
        "host": parsed.hostname or "",
        "path": parsed.path or "/",
    }
    try:
        if parsed.port is not None:
            endpoint["port"] = parsed.port
    except ValueError:
        pass
    return endpoint


def redact_headers(headers: Mapping[str, Any]) -> tuple[dict[str, str], int]:
    """Redact credentials in a caller-owned header mapping."""

    result: dict[str, str] = {}
    redactions = 0
    for key, value in headers.items():
        if str(key).lower() in SENSITIVE_HEADERS:
            result[str(key)] = REDACTED
            redactions += 1
        else:
            result[str(key)] = str(value)
    return result, redactions


def redact_text(value: str) -> tuple[str, int]:
    redactions = 0
    cleaned = value
    for pattern in _SECRET_PATTERNS:
        cleaned, count = pattern.subn(
            lambda match: (
                f"{match.group(1)}={REDACTED}" if match.lastindex else REDACTED
            ),
            cleaned,
        )
        redactions += count
    return cleaned, redactions


def assert_content_free(value: Any, path: str = "$") -> None:
    """Reject keys capable of carrying raw request/response content."""

    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in FORBIDDEN_PERSISTED_KEYS:
                raise ValueError(f"raw content field is forbidden at {path}.{key}")
            assert_content_free(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_content_free(child, f"{path}[{index}]")
