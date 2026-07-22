"""Deterministic, layered endpoint summaries."""

from collections import Counter
from collections.abc import Iterable, Sequence


def quantile(values: Sequence[float], probability: float) -> float | None:
    """R type-7 linear quantile, with identical behavior in the Node SDK."""

    if not values:
        return None
    if not 0 <= probability <= 1:
        raise ValueError("probability must be between 0 and 1")
    ordered = sorted(float(value) for value in values)
    index = (len(ordered) - 1) * probability
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def summarize(events: Iterable[dict]) -> dict:
    rows = list(events)
    outcomes = Counter(row["transport"]["outcome"] for row in rows)
    identities = Counter(row["identity"]["status"] for row in rows)
    durations = [float(row["transport"]["duration_ms"]) for row in rows]
    observed = Counter(
        row["identity"]["observed_model"]
        for row in rows
        if row["identity"].get("observed_model")
    )
    probe_rows = [row for row in rows if row.get("probe")]
    probe_scores = [float(row["probe"]["score"]) for row in probe_rows]
    output_sizes = [
        float(row["response"]["output_bytes"])
        for row in rows
        if row.get("response") and "output_bytes" in row["response"]
    ]
    stream_requests = sum(
        1 for row in rows if row.get("request", {}).get("stream") is True
    )
    total = len(rows)
    return {
        "events": total,
        "availability": {
            "success_rate": outcomes["success"] / total if total else None,
            "outcomes": dict(sorted(outcomes.items())),
        },
        "transport": {
            "latency_ms": {
                "p50": quantile(durations, 0.5),
                "p95": quantile(durations, 0.95),
                "p99": quantile(durations, 0.99),
            }
        },
        "identity": {
            "statuses": dict(sorted(identities.items())),
            "observed_models": dict(sorted(observed.items())),
        },
        "behavior": {
            "observed_responses": len(output_sizes),
            "stream_requests": stream_requests,
            "output_bytes_p50": quantile(output_sizes, 0.5),
        },
        "capability": {
            "probe_count": len(probe_scores),
            "mean_score": (
                sum(probe_scores) / len(probe_scores) if probe_scores else None
            ),
        },
    }
