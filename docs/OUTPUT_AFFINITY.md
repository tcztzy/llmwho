# Output-affinity matrix

LLMWho provides an explicit, local calculation for comparing the surface style
of model outputs. It reproduces the character-trigram cross-entropy method in
Typebulb's [interactive matrix](https://typebulb.com/u/lab/you-re-relatively-right/full)
and its [inspectable source and data](https://typebulb.com/u/lab/you-re-relatively-right.md).
The originating author described the experiment in the
[original post](https://x.com/typebulbit/status/2078668867052646656).

This is an exploratory behavioral fingerprint, not an identity detector or a
training-provenance detector. Low divergence means two supplied corpora use similar
characters, punctuation, formatting, and local wording patterns. It does not
prove that one model is another model, that either model trained on the other,
or that capabilities transferred between them.

## Public API

Python:

```python
from llmwho import output_affinity_matrix

report = output_affinity_matrix({
    "reference": ["First reference answer", "Second reference answer"],
    "endpoint": ["First endpoint answer", "Second endpoint answer"],
})

distance = report["matrix"][0][1]
```

Node.js:

```js
import { outputAffinityMatrix } from "llmwho";

const report = outputAffinityMatrix({
  reference: ["First reference answer", "Second reference answer"],
  endpoint: ["First endpoint answer", "Second endpoint answer"],
});

const distance = report.matrix[0][1];
```

Both functions are pure calculations. They make no network request, write no
file or observation event, and return no source prose. The caller explicitly
supplies and remains responsible for any raw text held in memory.

## Exact calculation

For each insertion-ordered corpus:

1. Join its documents with one space.
2. Collapse ECMAScript whitespace and trim the result.
3. Count overlapping UTF-16 character n-grams. The default is `n=3`, matching
   JavaScript string indexing and the source implementation, including its
   behavior around emoji and other non-BMP characters.
4. Form the empirical n-gram distribution `P_m` for model `m` and pooled
   distribution `B` across every compared model.
5. Smooth the target distribution as `Q_m = 0.8 P_m + 0.2 B` by default.
6. Calculate both KL directions and average them:

```text
d(A, B) = 0.5 * (KL(P_A || Q_B) + KL(P_B || Q_A))
```

Values use bits per character n-gram. Lower means closer surface style. The
matrix is symmetric and its diagonal is fixed to zero. `model_weight` /
`modelWeight` must stay strictly between zero and one so every source n-gram
has non-zero probability under the smoothed target.

The JSON-safe report includes metric name, interpretation, units, encoding,
configuration, per-corpus document/character/n-gram counts and entropy, the
full matrix, and its off-diagonal range. It intentionally contains no identity
candidate or distillation verdict.

## Fidelity check

The repository's shared synthetic vector exercises whitespace, punctuation,
multiple documents, and non-BMP characters in both implementations. We also
ran both implementations over the public 2026-07-18 Typebulb snapshot:

- 22 model corpora and 176 evaluation records were recovered;
- Node reproduced Kimi K3 ↔ Fable 5 as `0.4211233616031489` bits;
- Python produced `0.42112336160329455` bits;
- maximum Python/Node absolute difference across all 484 matrix cells was
  `1.34e-12`, attributable to platform `log2` rounding.

The public snapshot is not vendored because it contains third-party model
prose. Network-free tests instead use
[`shared/fixtures/output-affinity.json`](../shared/fixtures/output-affinity.json).

## Experimental design limits

- A score is relative to the pooled background. Adding or removing reference
  models changes it. Freeze the reference pool for comparisons over time.
- Shared prompts, facts, system instructions, templates, output length, and
  decoding configuration can all reduce or increase divergence.
- Eight long answers can contain many trigrams while still representing only
  eight independent prompt samples. Character count is not sample size.
- The metric has no built-in confidence interval. Production studies should
  use many hidden prompts, repeat sampling, held-out prompt families, and
  document-level bootstrap intervals.
- Character n-grams emphasize local style. Error correlation, decisions,
  refusals, multilingual behavior, and capability probes remain separate
  evidence channels.
- A deliberately style-tuned substitute can evade this signal. Black-box
  similarity is not cryptographic model attestation.

Use the matrix to flag output-affinity changes or nominate hypotheses for
stronger testing. Do not label its result as model identity or distillation.
