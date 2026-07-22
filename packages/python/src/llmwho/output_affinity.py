"""Character n-gram output-style divergence.

This module reproduces the Typebulb output-affinity matrix: each model's
explicitly supplied outputs become a UTF-16 character n-gram distribution,
then pairwise distance is the mean of both background-smoothed KL directions.
"""

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


def _normalize(text: str) -> str:
    r"""Match JavaScript's ``text.replace(/\s+/gu, " ").trim()``."""

    return _JS_WHITESPACE.sub(" ", text).strip(" ")


def _utf16le(text: str) -> bytes:
    # JavaScript strings and the source implementation count UTF-16 code units.
    return text.encode("utf-16-le", errors="surrogatepass")


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
    encoded = _utf16le(text)
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


def output_affinity_matrix(
    corpora: Mapping[str, Iterable[str]],
    *,
    ngram_size: int = 3,
    model_weight: float = 0.8,
) -> dict[str, Any]:
    """Return a JSON-safe pairwise output-style divergence report.

    ``corpora`` maps each model label to its response documents. Lower matrix
    values mean closer surface style. The function performs no network or disk
    I/O and does not infer model identity or training provenance.
    """

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
    for profile in profiles:
        background.update(profile.counts)
        background_ngrams += profile.ngrams

    directed = [
        [
            _directed_divergence(
                source, target, background, background_ngrams, weight
            )
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
                "label": profile.label,
                "documents": profile.documents,
                "characters": profile.characters,
                "ngrams": profile.ngrams,
                "entropy_bits": profile.entropy_bits,
            }
            for profile in profiles
        ],
        "matrix": matrix,
        "min_divergence": min(pair_values),
        "max_divergence": max(pair_values),
    }
