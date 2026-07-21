"""Conservative identity inference from provider-declared metadata."""

from __future__ import annotations

from typing import Optional


def infer_identity(
    claimed_model: Optional[str] = None,
    declared_model: Optional[str] = None,
) -> dict:
    """Build an evidence ledger from the response-declared model."""

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
