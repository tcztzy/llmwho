"""Built-in character n-gram output-affinity science plugin."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import math
import re
from typing import Any


_JS_WHITESPACE = re.compile(
    "[\u0009-\u000d\u0020\u00a0\u1680\u2000-\u200a"
    "\u2028\u2029\u202f\u205f\u3000\ufeff]+"
)
_METRIC = "symmetric_smoothed_char_ngram_kl"


@dataclass(frozen=True)
class _Profile:
    label: str
    documents: int
    characters: int
    ngrams: int
    counts: Counter[bytes]
    entropy_bits: float


def _ordered_corpora(value: Any) -> Mapping[str, Iterable[str]]:
    if isinstance(value, Mapping):
        return value
    if not isinstance(value, list):
        raise TypeError("corpora must be a mapping or ordered entry list")
    result: dict[str, Iterable[str]] = {}
    for entry in value:
        if not isinstance(entry, list) or len(entry) != 2:
            raise TypeError("corpora entries must be label/document pairs")
        label, documents = entry
        if not isinstance(label, str) or not label or label in result:
            raise ValueError("corpus labels must be unique non-empty strings")
        result[label] = documents
    return result


def _normalize(text: str) -> str:
    r"""Match JavaScript's ``text.replace(/\s+/gu, " ").trim()``."""

    return _JS_WHITESPACE.sub(" ", text).strip(" ")


def _profile(label: str, outputs: Iterable[str], ngram_size: int) -> _Profile:
    if isinstance(outputs, (str, bytes)):
        raise TypeError(f"corpus {label!r} must be an iterable of strings")
    try:
        documents = list(outputs)
    except TypeError as error:
        raise TypeError(f"corpus {label!r} must be an iterable of strings") from error
    if not documents:
        raise ValueError(f"corpus {label!r} must contain at least one document")
    if any(not isinstance(document, str) for document in documents):
        raise TypeError(f"corpus {label!r} documents must be strings")

    text = _normalize(" ".join(documents))
    encoded = text.encode("utf-16-le", errors="surrogatepass")
    characters = len(encoded) // 2
    if characters < ngram_size:
        raise ValueError(
            f"corpus {label!r} needs at least {ngram_size} normalized UTF-16 code units"
        )

    ngrams = characters - ngram_size + 1
    width = ngram_size * 2
    counts = Counter(encoded[index * 2 : index * 2 + width] for index in range(ngrams))
    entropy = -sum(
        (count / ngrams) * math.log2(count / ngrams) for count in counts.values()
    )
    return _Profile(label, len(documents), characters, ngrams, counts, entropy)


def _directed_divergence(
    source: _Profile,
    target: _Profile,
    background: Counter[bytes],
    background_ngrams: int,
    model_weight: float,
) -> float:
    background_weight = 1.0 - model_weight
    cross_entropy = 0.0
    for ngram, count in source.counts.items():
        source_probability = count / source.ngrams
        target_probability = (
            model_weight * (target.counts.get(ngram, 0) / target.ngrams)
            + background_weight * (background[ngram] / background_ngrams)
        )
        cross_entropy -= source_probability * math.log2(target_probability)
    return cross_entropy - source.entropy_bits


def calculate_output_affinity(
    corpora: Mapping[str, Iterable[str]],
    *,
    ngram_size: int = 3,
    model_weight: float = 0.8,
) -> dict[str, Any]:
    """Calculate deterministic output-style evidence without I/O."""

    if not isinstance(corpora, Mapping):
        raise TypeError("corpora must be a mapping of labels to string iterables")
    if len(corpora) < 2:
        raise ValueError("corpora must contain at least two models")
    if isinstance(ngram_size, bool) or not isinstance(ngram_size, int) or ngram_size < 1:
        raise ValueError("ngram_size must be a positive integer")
    if (
        isinstance(model_weight, bool)
        or not isinstance(model_weight, (int, float))
        or not math.isfinite(model_weight)
        or not 0.0 < model_weight < 1.0
    ):
        raise ValueError("model_weight must be a finite number between 0 and 1")
    weight = float(model_weight)

    profiles = []
    for label, outputs in corpora.items():
        if not isinstance(label, str) or not label:
            raise ValueError("corpus labels must be non-empty strings")
        profiles.append(_profile(label, outputs, ngram_size))

    background: Counter[bytes] = Counter()
    background_ngrams = 0
    for item in profiles:
        background.update(item.counts)
        background_ngrams += item.ngrams

    directed = [
        [
            _directed_divergence(source, target, background, background_ngrams, weight)
            for target in profiles
        ]
        for source in profiles
    ]
    matrix = []
    pair_values = []
    for row_index in range(len(profiles)):
        row = []
        for column_index in range(len(profiles)):
            if row_index == column_index:
                value = 0.0
            else:
                value = (
                    directed[row_index][column_index]
                    + directed[column_index][row_index]
                ) / 2.0
                if column_index < row_index:
                    pair_values.append(value)
            row.append(value)
        matrix.append(row)

    return {
        "metric": _METRIC,
        "interpretation": "style_divergence",
        "unit": "bits_per_character_ngram",
        "character_encoding": "utf-16-code-unit",
        "ngram_size": ngram_size,
        "model_weight": weight,
        "background_weight": 1.0 - weight,
        "models": [
            {
                "label": item.label,
                "documents": item.documents,
                "characters": item.characters,
                "ngrams": item.ngrams,
                "entropy_bits": item.entropy_bits,
            }
            for item in profiles
        ],
        "matrix": matrix,
        "min_divergence": min(pair_values),
        "max_divergence": max(pair_values),
    }


class OutputAffinityPlugin:
    id = "output_affinity"
    version = "1.0.0"
    summary = "Symmetric smoothed UTF-16 character n-gram divergence"
    required_inputs = ("corpora",)
    limitations = (
        "style-affinity-only",
        "not-identity-proof",
        "not-distillation-proof",
        "not-capability-proof",
    )

    def analyze(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return calculate_output_affinity(
            _ordered_corpora(payload["corpora"]),
            ngram_size=payload.get("ngram_size", 3),
            model_weight=payload.get("model_weight", 0.8),
        )
