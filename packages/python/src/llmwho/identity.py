"""Conservative identity inference from provider-declared metadata."""

from __future__ import annotations

from typing import Mapping, Optional


MODEL_HEADERS = (
    "x-model-id",
    "x-model-name",
    "x-model",
    "openai-model",
)


def infer_identity(
    claimed_model: Optional[str] = None,
    declared_model: Optional[str] = None,
    response_headers: Optional[Mapping[str, str]] = None,
) -> dict:
    """Build an evidence ledger; never infer identity from style alone."""

    evidence = []
    observed = declared_model or None
    weight = 0.0
    if declared_model:
        weight = 0.98
        evidence.append(
            {
                "kind": "response_model",
                "source": "response.body.model",
                "value": declared_model,
                "weight": weight,
            }
        )
    if not observed and response_headers:
        lowered = {str(key).lower(): str(value) for key, value in response_headers.items()}
        for header in MODEL_HEADERS:
            if lowered.get(header):
                observed = lowered[header]
                weight = 0.85
                evidence.append(
                    {
                        "kind": "response_model_header",
                        "source": f"response.headers.{header}",
                        "value": observed,
                        "weight": weight,
                    }
                )
                break

    if observed and claimed_model:
        status = "matched" if observed == claimed_model else "mismatch"
        confidence = weight
    else:
        status = "unknown"
        confidence = weight if observed else 0.0

    result = {
        "status": status,
        "confidence": confidence,
        "candidates": ([{"label": observed, "confidence": weight}] if observed else []),
        "evidence": evidence,
    }
    if claimed_model:
        result["claimed_model"] = claimed_model
    if observed:
        result["observed_model"] = observed
    return result
