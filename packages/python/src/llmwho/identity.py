"""Keep provider declarations separate from model identity."""


def provider_declaration(
    requested_model: str | None = None,
    declared_model: str | None = None,
) -> dict | None:
    """Describe what provider declared without treating it as identity evidence."""

    if not declared_model:
        return None
    if requested_model:
        status = "matched" if declared_model == requested_model else "mismatch"
    else:
        status = "unverified"
    return {
        "status": status,
        "declared_model": declared_model,
        "evidence": [
            {
                "kind": "provider_declaration",
                "source": "response.body.model",
                "value": declared_model,
            }
        ],
    }


def unknown_identity() -> dict:
    """Return an explicit abstention when no calibrated detector ran."""

    return {"status": "unknown", "candidates": [], "evidence": []}
