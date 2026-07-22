"""Public Python science-analysis API."""

from collections.abc import Iterable, Mapping
from typing import Any

from .registry import PluginRegistry


def plugins() -> list[dict[str, Any]]:
    """Return descriptors for installed science plugins."""

    return PluginRegistry().descriptors()


def run(plugin_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Run one plugin and return a versioned analysis report."""

    return PluginRegistry().run(plugin_id, payload)


def output_affinity_matrix(
    corpora: Mapping[str, Iterable[str]],
    *,
    ngram_size: int = 3,
    model_weight: float = 0.8,
) -> dict[str, Any]:
    """Run the built-in output-affinity plugin."""

    return run(
        "output_affinity",
        {
            "corpora": corpora,
            "ngram_size": ngram_size,
            "model_weight": model_weight,
        },
    )


__all__ = ["output_affinity_matrix", "plugins", "run"]
