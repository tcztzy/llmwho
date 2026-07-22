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
from llmwho import science

analysis = science.output_affinity_matrix({
    "reference": ["First reference answer", "Second reference answer"],
    "endpoint": ["First endpoint answer", "Second endpoint answer"],
})

distance = analysis["evidence"]["matrix"][0][1]
```

Node.js:

```js
import { science } from "llmwho";

const analysis = await science.outputAffinityMatrix({
  reference: ["First reference answer", "Second reference answer"],
  endpoint: ["First endpoint answer", "Second endpoint answer"],
});

const distance = analysis.evidence.matrix[0][1];
```

Both APIs execute the same Python plugin. The calculation makes no provider
request, writes no corpus or observation event, and returns no source prose.
Node may first ask uv to provision the locked science environment; use
`science.setup({ offline: true })` to prohibit downloads. The caller explicitly
supplies and remains responsible for raw text held in memory.

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
multiple documents, and non-BMP characters through direct Python and Node
worker calls. We also ran the earlier dual implementations over the public
2026-07-18 Typebulb snapshot while validating the formula:

- 22 model corpora and 176 evaluation records were recovered;
- Node reproduced Kimi K3 ↔ Fable 5 as `0.4211233616031489` bits;
- Python produced `0.42112336160329455` bits;
- the former implementations differed by at most `1.34e-12` across 484 matrix
  cells because of platform `log2` rounding.

Version 0.3 removes that divergence: Node returns the Python plugin's serialized
numbers without reimplementing the calculation.

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
