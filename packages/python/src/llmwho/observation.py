"""ObservationV2 construction and dependency-free runtime validation."""

from datetime import datetime, timezone
import math
from typing import Any
from collections.abc import Mapping
from uuid import uuid4

from .identity import provider_declaration, unknown_identity
from .privacy import assert_content_free, endpoint_from_url
from .version import __version__


OUTCOMES = frozenset(
    {"success", "http_error", "timeout", "network_error", "stream_error"}
)
IDENTITY_STATUSES = frozenset({"unknown", "inferred"})
DECLARATION_STATUSES = frozenset({"matched", "mismatch", "unverified"})
MODALITIES = frozenset(
    {"text", "image", "audio", "embedding", "multimodal", "unknown"}
)

_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "event_id",
        "timestamp",
        "source",
        "modality",
        "sdk",
        "endpoint",
        "transport",
        "model_declaration",
        "identity",
        "privacy",
        "request",
        "response",
        "probe",
    }
)


def _object(
    value: Any,
    path: str,
    *,
    allowed: set[str] | frozenset[str],
    required: set[str] | frozenset[str] = frozenset(),
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be an object")
    keys = set(value)
    missing = required.difference(keys)
    if missing:
        raise ValueError(f"missing {path} fields: {', '.join(sorted(missing))}")
    unknown = keys.difference(allowed)
    if unknown:
        raise ValueError(f"unknown {path} fields: {', '.join(sorted(unknown))}")
    return value


def _string(value: Any, path: str, *, nonempty: bool = False) -> str:
    if not isinstance(value, str) or (nonempty and not value):
        suffix = " non-empty" if nonempty else ""
        raise ValueError(f"{path} must be a{suffix} string")
    return value


def _number(
    value: Any,
    path: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{path} must be finite")
    if minimum is not None and result < minimum:
        raise ValueError(f"{path} must be at least {minimum}")
    if maximum is not None and result > maximum:
        raise ValueError(f"{path} must be at most {maximum}")
    return result


def _integer(
    value: Any,
    path: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{path} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{path} must be at most {maximum}")
    return value


def _optional_string(value: Mapping[str, Any], key: str, path: str) -> None:
    if key in value:
        _string(value[key], f"{path}.{key}")


def _validate_request(value: Any) -> None:
    request = _object(
        value,
        "request",
        allowed={
            "operation",
            "requested_model",
            "stream",
            "input_bytes",
            "role_count",
            "probe_case_id",
        },
    )
    for key in ("operation", "requested_model", "probe_case_id"):
        _optional_string(request, key, "request")
    if "stream" in request and not isinstance(request["stream"], bool):
        raise ValueError("request.stream must be a boolean")
    for key in ("input_bytes", "role_count"):
        if key in request:
            _integer(request[key], f"request.{key}", minimum=0)


def _validate_response(value: Any) -> None:
    response = _object(
        value,
        "response",
        allowed={
            "system_fingerprint",
            "status_code",
            "output_bytes",
            "usage",
        },
    )
    for key in ("system_fingerprint",):
        _optional_string(response, key, "response")
    if "status_code" in response:
        _integer(response["status_code"], "response.status_code", minimum=100, maximum=599)
    if "output_bytes" in response:
        _integer(response["output_bytes"], "response.output_bytes", minimum=0)
    if "usage" in response:
        usage = _object(
            response["usage"],
            "response.usage",
            allowed={"input_tokens", "output_tokens", "total_tokens"},
        )
        for key, child in usage.items():
            _integer(child, f"response.usage.{key}", minimum=0)


def _validate_model_declaration(value: Any) -> None:
    declaration = _object(
        value,
        "model_declaration",
        allowed={"status", "declared_model", "evidence"},
        required={"status", "declared_model", "evidence"},
    )
    status = _string(declaration["status"], "model_declaration.status")
    if status not in DECLARATION_STATUSES:
        raise ValueError("invalid model declaration status")
    declared_model = _string(
        declaration["declared_model"],
        "model_declaration.declared_model",
        nonempty=True,
    )
    evidence = declaration["evidence"]
    if not isinstance(evidence, list) or len(evidence) != 1:
        raise ValueError("model_declaration.evidence must contain one item")
    item = _object(
        evidence[0],
        "model_declaration.evidence[0]",
        allowed={"kind", "source", "value"},
        required={"kind", "source", "value"},
    )
    if item["kind"] != "provider_declaration":
        raise ValueError("invalid model declaration evidence kind")
    if item["source"] != "response.body.model":
        raise ValueError("invalid model declaration evidence source")
    if item["value"] != declared_model:
        raise ValueError("model declaration evidence value must match declared_model")


def _validate_identity(value: Any) -> None:
    identity = _object(
        value,
        "identity",
        allowed={"status", "candidates", "evidence"},
        required={"status", "candidates", "evidence"},
    )
    status = _string(identity["status"], "identity.status")
    if status not in IDENTITY_STATUSES:
        raise ValueError("invalid identity status")
    candidates = identity["candidates"]
    if not isinstance(candidates, list):
        raise ValueError("identity.candidates must be an array")
    for index, child in enumerate(candidates):
        candidate = _object(
            child,
            f"identity.candidates[{index}]",
            allowed={"label", "confidence"},
            required={"label", "confidence"},
        )
        _string(candidate["label"], f"identity.candidates[{index}].label")
        _number(
            candidate["confidence"],
            f"identity.candidates[{index}].confidence",
            minimum=0,
            maximum=1,
        )
    evidence = identity["evidence"]
    if not isinstance(evidence, list):
        raise ValueError("identity.evidence must be an array")
    for index, child in enumerate(evidence):
        item = _object(
            child,
            f"identity.evidence[{index}]",
            allowed={"kind", "source", "value", "detector_id", "detector_version"},
            required={"kind", "source", "detector_id", "detector_version"},
        )
        _string(item["kind"], f"identity.evidence[{index}].kind")
        _string(item["source"], f"identity.evidence[{index}].source")
        _optional_string(item, "value", f"identity.evidence[{index}]")
        _string(
            item["detector_id"],
            f"identity.evidence[{index}].detector_id",
            nonempty=True,
        )
        _string(
            item["detector_version"],
            f"identity.evidence[{index}].detector_version",
            nonempty=True,
        )
    if status == "unknown" and (candidates or evidence):
        raise ValueError("unknown identity must not contain candidates or evidence")
    if status == "inferred" and (not candidates or not evidence):
        raise ValueError("inferred identity needs candidates and detector evidence")


def new_observation(
    *,
    url: str,
    duration_ms: float,
    outcome: str,
    error_type: str | None = None,
    source: str = "passive",
    modality: str = "text",
    provider: str | None = None,
    requested_model: str | None = None,
    declared_model: str | None = None,
    request: Mapping[str, Any] | None = None,
    response: Mapping[str, Any] | None = None,
    probe: Mapping[str, Any] | None = None,
    redactions: int = 0,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "schema_version": "2",
        "event_id": str(uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": source,
        "modality": modality,
        "sdk": {"name": "llmwho-python", "version": __version__},
        "endpoint": endpoint_from_url(url),
        "transport": {"outcome": outcome, "duration_ms": max(0.0, duration_ms)},
        "identity": unknown_identity(),
        "privacy": {"content_captured": False, "redactions": max(0, redactions)},
    }
    if provider:
        event["endpoint"]["provider"] = provider
    if error_type:
        event["transport"]["error_type"] = error_type
    request_metadata = dict(request or {})
    if requested_model:
        request_metadata["requested_model"] = requested_model
    if request_metadata:
        event["request"] = request_metadata
    if response:
        event["response"] = dict(response)
    declaration = provider_declaration(requested_model, declared_model)
    if declaration:
        event["model_declaration"] = declaration
    if probe:
        event["probe"] = dict(probe)
    validate_observation(event)
    return event


def validate_observation(event: Mapping[str, Any]) -> None:
    assert_content_free(event)
    root = _object(
        event,
        "ObservationV2",
        allowed=_TOP_LEVEL_KEYS,
        required={
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
        },
    )
    if event["schema_version"] != "2":
        raise ValueError("unsupported observation schema_version")
    _string(root["event_id"], "event_id", nonempty=True)
    timestamp = _string(root["timestamp"], "timestamp", nonempty=True)
    try:
        parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("timestamp must be an ISO 8601 date-time") from error
    if parsed_timestamp.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    source = _string(root["source"], "source")
    if source not in {"passive", "probe"}:
        raise ValueError("invalid observation source")
    modality = _string(root["modality"], "modality")
    if modality not in MODALITIES:
        raise ValueError("invalid observation modality")
    sdk = _object(
        root["sdk"],
        "sdk",
        allowed={"name", "version"},
        required={"name", "version"},
    )
    _string(sdk["name"], "sdk.name", nonempty=True)
    _string(sdk["version"], "sdk.version", nonempty=True)
    endpoint = _object(
        root["endpoint"],
        "endpoint",
        allowed={"scheme", "host", "port", "path", "provider"},
        required={"scheme", "host", "path"},
    )
    scheme = _string(endpoint["scheme"], "endpoint.scheme")
    if scheme not in {"http", "https", "unknown"}:
        raise ValueError("invalid endpoint scheme")
    _string(endpoint["host"], "endpoint.host")
    _string(endpoint["path"], "endpoint.path")
    _optional_string(endpoint, "provider", "endpoint")
    if "port" in endpoint:
        _integer(endpoint["port"], "endpoint.port", minimum=1, maximum=65535)
    transport = _object(
        root["transport"],
        "transport",
        allowed={"outcome", "duration_ms", "ttft_ms", "error_type"},
        required={"outcome", "duration_ms"},
    )
    outcome = _string(transport["outcome"], "transport.outcome")
    if outcome not in OUTCOMES:
        raise ValueError("invalid transport outcome")
    _number(transport["duration_ms"], "transport.duration_ms", minimum=0)
    if "ttft_ms" in transport:
        _number(transport["ttft_ms"], "transport.ttft_ms", minimum=0)
    _optional_string(transport, "error_type", "transport")
    _validate_identity(root["identity"])
    privacy = _object(
        root["privacy"],
        "privacy",
        allowed={"content_captured", "redactions"},
        required={"content_captured", "redactions"},
    )
    if privacy["content_captured"] is not False:
        raise ValueError("privacy.content_captured must be false")
    _integer(privacy["redactions"], "privacy.redactions", minimum=0)
    if "request" in root:
        _validate_request(root["request"])
    if "response" in root:
        _validate_response(root["response"])
    if "model_declaration" in root:
        _validate_model_declaration(root["model_declaration"])
    if "probe" in root:
        probe = _object(
            root["probe"],
            "probe",
            allowed={"case_id", "passed", "score", "check"},
            required={"case_id", "passed", "score"},
        )
        _string(probe["case_id"], "probe.case_id")
        if not isinstance(probe["passed"], bool):
            raise ValueError("probe.passed must be a boolean")
        _number(probe["score"], "probe.score", minimum=0, maximum=1)
        _optional_string(probe, "check", "probe")
