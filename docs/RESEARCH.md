# Research landscape and MVP implications

Last reviewed: 2026-07-20

This review asks what can be inferred about a text-generation model through an
API, how endpoint changes can be detected, and which claims a production tool
can responsibly make. It prioritizes peer-reviewed conference and journal
papers. Preprints are included when directly relevant and are labelled.

## Search and inclusion method

Sources were located through USENIX, ACL Anthology, PMLR, ICLR/OpenReview, ACM
Digital Library, IEEE, MIT Press, and arXiv. Searches combined *LLM
fingerprinting*, *black-box model identification*, *model equality*, *model
substitution*, *API drift*, *behavioral stability*, *log probability tracking*,
and *inter-token timing*. A work was included when it studies at least one of:

1. identifying a model or model family from black-box observations;
2. verifying equality/provenance against a reference model;
3. detecting changes in a hosted generative-model API;
4. measuring longitudinal or repeated-output stability;
5. instrumentation patterns directly relevant to a one-call SDK hook.

Reported paper metrics below describe the authors' experimental settings, not
guarantees that transfer to new providers, prompts, versions, or threat models.

## Four different questions

The literature often calls all four tasks "fingerprinting", but they require
different evidence and should not share one confidence number.

- **Closed-set identification:** which member of a known candidate set produced
  these observations?
- **Equality/change testing:** does the endpoint still behave like a stored or
  locally executable reference?
- **Provenance/ownership:** is a suspect model derived from an owner's base
  model, possibly after tuning, merging, or quantization?
- **Operational stability:** is one endpoint's effective behavior consistent
  over time, regardless of the exact hidden cause?

LLMWho addresses identification and operational stability for an API consumer.
It can host equality tests when the user supplies reference profiles. Most
ownership fingerprints assume cooperation or white-box access from the model
owner and therefore are research inputs, not default product claims.

## Evidence hierarchy

No single signal is universally sufficient. LLMWho should preserve the source
and strength of each piece of evidence.

1. **Cryptographic attestation or provider-signed identity:** strongest, but
   requires provider/infrastructure cooperation and is rarely available.
2. **Contradictory response metadata:** response `model`, version headers, and
   system fingerprints are useful operational evidence but are forgeable by an
   adversarial provider.
3. **Log probabilities or token rankings:** high-information behavioral access;
   powerful where exposed, but many chat APIs omit or truncate it.
4. **Controlled output distributions:** repeated active queries compared with
   candidate/reference distributions; broadly applicable but costs requests.
5. **Textual idiosyncrasies:** useful closed-set evidence over enough text;
   vulnerable to prompt, domain, system-message, and post-processing shift.
6. **Timing and traffic features:** passive and content-free, but entangle model,
   inference stack, load, geography, batching, and network path.
7. **Capability scores:** indicate service quality or gross substitution, not a
   unique model identity by themselves.

## Peer-reviewed work most relevant to LLMWho

| Work | Venue | Access and method | Main lesson for LLMWho |
|---|---|---|---|
| [LLMmap](https://www.usenix.org/conference/usenixsecurity25/presentation/pasquini) | USENIX Security 2025 | Active crafted queries plus a learned closed-set classifier; reports over 95% accuracy across 42 versions with as few as 8 interactions | Strong precedent for an active `identify` suite. Candidate corpus and classifier must be versioned, open-set aware, and continuously refreshed. |
| [TRAP](https://aclanthology.org/2024.findings-acl.683/) | Findings of ACL 2024 | Target-specific adversarial suffix optimized with white-box access; reported >95% TPR and <0.2% FPR after one interaction | Very query-efficient, but unsuitable as generic MVP because each target needs owner/reference access and adversarial prompts can trigger filters. |
| [Model Equality Testing](https://arxiv.org/abs/2410.20247) | ICLR 2025 | Two-sample testing between black-box API outputs and a reference distribution using MMD-style statistics | Equality is more defensible than naming an unknown model. Add reference profiles and task-specific distributions after MVP. |
| [ESF](https://aclanthology.org/2025.findings-acl.546/) | Findings of ACL 2025 | Sensitive token positions plus randomness-set consistency; reported >99.2% tamper detection with 5 samples | Optimize future probes for sensitivity and explicitly model a set/distribution of valid outputs rather than one expected string. Fingerprint construction assumes access to the protected reference. |
| [Idiosyncrasies in Large Language Models](https://proceedings.mlr.press/v267/sun25z.html) | ICML 2025 | Fine-tuned text-embedding classifier; reports 97.1% held-out accuracy for five major model families and persistence after rewriting/translation/summarization | Text carries model-family signal, but held-out in-distribution classification is not open-world proof. A future classifier needs unknown rejection and prompt/domain calibration. |
| [LLMs Have Rhythm](https://arxiv.org/abs/2502.20589) | IEEE Open Journal of the Communications Society | Passive inter-token/network timing features; weighted F1 about 85% across days, 74% across networks, 71% through VPN in proprietary-model experiments | Streaming timing is valuable privacy-preserving evidence. Treat it as endpoint/inference-stack evidence, stratified by region and load, not a pure model label. |
| [Stealing Part of a Production Language Model](https://proceedings.mlr.press/v235/carlini24a.html) | ICML 2024, Best Paper | Carefully chosen logprob/logit-bias queries recover nontrivial architecture information from production models | Probability APIs leak strong structural evidence, but extraction can be expensive and security-sensitive. LLMWho should use exposed logprobs conservatively and never implement weight extraction in the MVP. |
| [Log Probability Tracking of LLM APIs](https://openreview.net/pdf?id=hFxivbAgVP) | ICLR 2026 | One-token outputs and average token logprob tests detect small changes under gray-box logprob access | Add an optional low-cost logprob canary when a provider exposes it. Keep a strict-output fallback for black-box endpoints. |
| [Auditing Black-Box LLM APIs with a Rank-Based Uniformity Test](https://arxiv.org/abs/2506.06975) | ICLR 2026 | Rank-based asymmetric two-sample test against an authentic local reference; evaluates quantization, tuning, jailbreak prompts, mixed and full substitution | Reference-backed rank tests are a strong advanced adapter. They cannot identify arbitrary models without candidate/reference access. |
| [Behavioral Fingerprints for LLM Endpoint Stability and Identity](https://doi.org/10.1145/3786335.3813194) | ACM CAIS 2026 | Fixed prompts, repeated first-token samples, summed energy distance, permutation p-values, and sequential e-value evidence; about 800 short requests per fingerprint | Closest stability prior. It validates distributional endpoint fingerprints and event timelines, but its query volume is too high for default MVP. LLMWho differentiates through passive application hooks and lower-cost layered probes. |
| [How Is ChatGPT's Behavior Changing over Time?](https://hdsr.mitpress.mit.edu/pub/y95zitmz/release/2) | Harvard Data Science Review 2024 | Longitudinal task evaluation of nominally stable GPT services, with bootstrap confidence intervals | Capability and instruction-following drift can be material even under a stable product name. Preserve per-capability series; do not treat all change as uniformly worse. |
| [How Did the Model Change?](https://openreview.net/pdf?id=gFDFKC4gHL4) | ICLR 2022 | Budget-aware adaptive sampling (MASA) to estimate silent ML API shifts | Probe selection should eventually target the most informative tasks under a cost budget instead of running every test equally. |
| [FDLLM](https://doi.org/10.1109/Trustcom66490.2025.00159) | IEEE TrustCom 2025 | Learned multilingual, multidomain output-text attribution over a 90,000-sample, 20-model dataset | Confirms value of reference corpora and multilingual features; model churn and open-set rejection remain operational requirements. |
| [Fingerprinting LLMs via Prompt Injection](https://aclanthology.org/2026.acl-long.541/) | ACL 2026 | Optimized prompts enforce model-specific token preferences; black/gray-box verification and robustness tests over post-trained/quantized variants | Prompts selected for information gain can outperform generic benchmarks, but optimization requires base-model access and must be safety-reviewed. |
| [HuRef](https://proceedings.neurips.cc/paper_files/paper/2024/hash/e46fc33e80e9fa2febcdb058fba4beca-Abstract-Conference.html) | NeurIPS 2024 | Parameter-direction fingerprint with owner-side verification and zero-knowledge proof support | Useful provenance architecture, but not a consumer-side black-box identification method. Keep attestation extensible so signed/ZK proofs could supersede heuristics. |
| [MergePrint](https://aclanthology.org/2025.acl-long.342/) | ACL 2025 | Owner-inserted black-box fingerprint designed to survive model merging | Supports future verification plugins for cooperative model owners; not evidence available to ordinary API consumers. |

## Directly relevant preprints and emerging work

These works affect the roadmap but should not be represented as settled evidence.

- [Are You Getting What You Pay For?](https://arxiv.org/abs/2504.04715)
  formalizes model substitution attacks and compares benchmark, text-output,
  and logprob approaches. Its central warning is product-defining: output-only
  methods struggle against subtle, randomized, or adaptive substitution, while
  stronger hardware attestation requires provider cooperation.
- [Token-Efficient Change Detection in LLM APIs (B3IT)](https://arxiv.org/abs/2602.11083)
  finds "border inputs" whose top tokens are nearly tied and reports roughly
  30x cost reduction over existing methods. Border prompts are endpoint-specific
  and may need rediscovery after changes.
- [RoFL](https://arxiv.org/abs/2505.12682) studies non-invasive statistical
  fingerprints intended to survive common model and inference alterations.
- [A Fingerprint for Large Language Models](https://arxiv.org/abs/2407.01235)
  compares vector spaces of model outputs for ownership verification.
- [FLIPS](https://arxiv.org/abs/2606.03330) uses biases in pseudo-random binary
  sequences and explicitly evaluates open-set identification across many model
  instances. It is a promising candidate for a future low-cost identity suite.
- [Token Rankings are Unforgeable Language Model Signatures](https://arxiv.org/abs/2606.04459)
  argues that exposed top-k rankings contain a structurally strong signature.
- [One Token Is Enough](https://arxiv.org/abs/2607.10252) studies empirical
  one-token answer distributions to trivial multilingual prompts. Its extreme
  recency makes independent replication especially important.
- [Fingerprinting Inference Systems of LLMs](https://arxiv.org/abs/2605.29979)
  shows that engine, attention backend, and hardware differences can propagate
  into text. This reinforces that "actual model" and "effective endpoint" are
  related but not identical targets.
- [Evaluating Performance Drift from Model Switching](https://arxiv.org/abs/2603.03111)
  reports that switching models mid-conversation can materially change outcomes.
  LLMWho should eventually attach identity evidence to conversation/session IDs.

## Adjacent systems and implementation precedent

- [Project VAIL Stability Monitor/Arena](https://doi.org/10.1145/3786335.3813194)
  is the nearest endpoint-stability system. It actively samples fixed prompts;
  it does not provide LLMWho's one-call in-application passive hook.
- [AI Stupid Level](https://aistupidlevel.info/methodology) continuously runs
  capability suites and exposes drift timelines. It is useful as a dashboard
  reference, but capability drift must remain separate from transport and
  identity stability.
- [LLMmap's open-source implementation](https://github.com/pasquini-dario/LLMmap)
  exposes the cost of maintaining a current training corpus and classifier.
- [Model Equality Testing code](https://github.com/i-gao/model-equality-testing)
  provides reference implementations of two-sample comparisons.
- [Langfuse](https://github.com/langfuse/langfuse) demonstrates broad LLM SDK
  instrumentation, while focusing on application traces/evaluation rather than
  hidden-model identity.
- [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/)
  standardize provider, operation, token, and content attributes. LLMWho should
  remain export-compatible, while defaulting content capture off because the
  convention explicitly marks content-bearing fields as sensitive.

## MVP decisions derived from the evidence

### What the MVP will do

1. **One-call passive instrumentation.** Hook common Python HTTP clients and
   Node `fetch`, restrict collection to recognized LLM routes, and record
   endpoint, declared model, safe headers, errors, latency, usage, and derived
   behavior without raw content by default.
2. **Evidence ledger, not one magic classifier.** Each observation lists its
   evidence. Contradictory response metadata can produce a named candidate;
   missing evidence produces `unknown`. The MVP does not convert response style
   into high-confidence identity.
3. **Controlled deterministic smoke probes.** Explicit probes measure JSON
   adherence, exact instruction following, invalid-premise handling, and simple
   reasoning. Their first purpose is capability/stability, not unique identity.
4. **Endpoint history.** Track identity evidence distributions, header/system
   fingerprint changes, availability, latency, error classes, and probe results
   as separate time series.
5. **Portable reference hooks.** Event and report schemas leave room for future
   LLMmap-like classifiers, logprob tests, timing classifiers, signed owner
   fingerprints, and user-built reference profiles.

### What the MVP will not claim

- A single arbitrary answer uniquely identifies an unknown model.
- A capability score proves model identity.
- Similar prose proves common model provenance.
- Timing alone separates model weights from hardware, load, inference engine,
  network, or geographic route.
- Absence of detected change proves equality or provider honesty.

### Statistical requirements for later detectors

- Binary probe checks should use binomial/Wilson or beta-binomial uncertainty,
  not a normal interval around five pass/fail samples.
- Latency needs quantiles and distribution comparisons; a mean alone hides tail
  instability.
- Baseline and test windows must not overlap, or the current change contaminates
  its own reference.
- Repeated monitoring requires sequentially valid evidence or an explicit
  multiple-testing policy; repeatedly applying ordinary p-value thresholds
  inflates false alarms.
- Closed-set classifiers must expose out-of-distribution/unknown rejection and
  calibration on changed prompts, languages, models, and dates.
- Mixed routing should be modeled as a candidate distribution, not forced into
  one label.

## Product differentiation after reviewing prior art

The research landscape validates active black-box fingerprinting and continuous
distribution-shift monitoring. It does not remove the integration gap LLMWho is
designed to fill:

> Existing fingerprint systems mostly start with a dedicated experiment that
> sends queries. LLMWho starts inside the user's real application with one
> `init()` call, treats ordinary traffic as privacy-preserving operational
> evidence, and escalates to explicit active probes only when necessary.

This positioning also avoids competing as another generic tracing backend or
public leaderboard. The unit of trust is the user's endpoint, route, key,
region, and workload—not a globally advertised model name.

## Research limitations

This is a scoped engineering review, not a formal systematic review or
meta-analysis. Fast-moving 2025–2026 work has limited independent replication;
many evaluations use closed candidate sets and historical API versions that no
longer exist. Vendor behavior and API metadata can change. Before promoting any
future detector to a default identity signal, LLMWho must reproduce it across
held-out dates, prompts, providers, regions, sampling settings, and unknown
models, and publish calibration and abstention results.
