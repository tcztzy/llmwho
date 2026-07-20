"""ObservationV1 construction and lightweight runtime validation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional
from uuid import uuid4

from .identity import infer_identity
from .privacy import assert_content_free, endpoint_from_url
from .version import __version__


OUTCOMES = frozenset(
    {"success", "http_error", "timeout", "network_error", "stream_error"}
)
IDENTITY_STATUSES = frozenset({"matched", "mismatch", "unknown"})


def new_observation(
    *,
    url: str,
    duration_ms: float,
    outcome: str,
    source: str = "passive",
    modality: str = "text",
    claimed_model: Optional[str] = None,
    declared_model: Optional[str] = None,
    response_headers: Optional[Mapping[str, str]] = None,
    request: Optional[Mapping[str, Any]] = None,
    response: Optional[Mapping[str, Any]] = None,
    probe: Optional[Mapping[str, Any]] = None,
    redactions: int = 0,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "schema_version": "1",
        "event_id": str(uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": source,
        "modality": modality,
        "sdk": {"name": "llmwho-python", "version": __version__},
        "endpoint": endpoint_from_url(url),
        "transport": {"outcome": outcome, "duration_ms": max(0.0, duration_ms)},
        "identity": infer_identity(claimed_model, declared_model, response_headers),
        "privacy": {"content_captured": False, "redactions": max(0, redactions)},
    }
    if request:
        event["request"] = dict(request)
    if response:
        event["response"] = dict(response)
    if probe:
        event["probe"] = dict(probe)
    validate_observation(event)
    return event


def validate_observation(event: Mapping[str, Any]) -> None:
    assert_content_free(event)
    required = {
        "schema_version",
        "event_id",
        "timestamp",
        "source",
        "modality",
        "sdk",
        "endpoint",
        "transport",
        "identity",
        "privacy",
    }
    missing = required.difference(event)
    if missing:
        raise ValueError(f"missing ObservationV1 fields: {', '.join(sorted(missing))}")
    if event["schema_version"] != "1":
        raise ValueError("unsupported observation schema_version")
    if event["source"] not in {"passive", "probe"}:
        raise ValueError("invalid observation source")
    transport = event["transport"]
    if transport.get("outcome") not in OUTCOMES:
        raise ValueError("invalid transport outcome")
    if float(transport.get("duration_ms", -1)) < 0:
        raise ValueError("duration_ms must be non-negative")
    identity = event["identity"]
    if identity.get("status") not in IDENTITY_STATUSES:
        raise ValueError("invalid identity status")
    confidence = float(identity.get("confidence", -1))
    if not 0 <= confidence <= 1:
        raise ValueError("identity confidence must be between 0 and 1")
    if event["privacy"] != {
        "content_captured": False,
        "redactions": event["privacy"].get("redactions"),
    }:
        raise ValueError("privacy must declare content_captured=false and redactions")
