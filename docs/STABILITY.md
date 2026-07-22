# Stability model and AI Stupid Level adaptation

Last reviewed: 2026-07-20

LLMWho treats a hosted model as an **effective endpoint**: model weights plus
system prompt, decoding, safety filters, inference engine, hardware, routing,
load, region, and network path. Stability means that this delivered system
continues to satisfy a chosen contract—not merely that a model-name string or
HTTP process remains unchanged.

## What AI Stupid Level gets directionally right

[AI Stupid Level](https://aistupidlevel.info/) presents continuously refreshed
coding, reasoning, tool-calling, speed, and drift views instead of a one-time
leaderboard. Its [methodology page](https://aistupidlevel.info/methodology)
currently describes four schedules: a coding suite every four hours, daily
reasoning and tool-use suites, and a small hourly canary. It also describes
repeated trials, confidence intervals, version-header collection, and CUSUM
change detection.

Those are useful product patterns:

- use small canaries frequently and expensive suites less often;
- repeat stochastic tests instead of trusting one response;
- retain time series and change points, not only current rank;
- execute code/tool tasks where objective evaluation is possible;
- display confidence and sample size;
- preserve response version metadata for root-cause analysis.

LLMWho adopts those patterns at the user's own endpoint. It does not import the
site's scores or treat its public ranking as evidence about a request made with
a different key, route, region, gateway, prompt, or date.

## The important terminology split

The methodology gives “stability” a 10% weight inside a coding score, where it
means edge-case handling and absence of crashes. LLMWho calls that **behavioral
or capability robustness**. Operational service stability is broader and is
reported in five non-interchangeable layers:

| Layer | Question | MVP evidence | Example failure |
|---|---|---|---|
| Availability | Did a usable response arrive? | status/outcome counts | timeout, 429, network failure |
| Transport | How was it delivered? | p50/p95/p99 latency | tail-latency regression |
| Behavior | Did response shape stay compatible? | streaming and output-size metadata | empty/truncated format |
| Capability | Can controlled tasks still be completed? | deterministic smoke cases | JSON-contract failure |
| Identity | Is the delivered endpoint consistent with its claim/reference? | body/header model evidence | requested A, response declares B |

A provider can have 99.99% HTTP availability while silently degrading task
quality. Conversely, a strong model can be operationally unusable because of
timeouts. A correct capability response cannot prove which model produced it.
No overall score is allowed to hide these distinctions.

## MVP adaptation

LLMWho 0.3 combines two sampling channels:

### Passive production observations

`init()` records traffic that the application already sends. This gives high
ecological validity for availability, latency, response metadata, routing
mixture, and compatibility. It also has uncontrolled prompts and sampling
settings, so passive capability comparisons can be confounded by workload
changes. Raw content remains unavailable to the store.

### Explicit controlled canaries

`probe(..., suite="smoke")` sends four short cases with deterministic checks.
They are cheap enough to establish the end-to-end plumbing and detect gross
format/instruction regressions. They are not broad enough to rank intelligence
or identify a model uniquely. Each trial remains visible, including HTTP and
transport failures.

The dashboard then joins both channels by observation time while keeping their
source labels. It shows current evidence and history; version 0.3 does not yet
emit automatic statistical drift alerts.

## Statistical changes before alerting

LLMWho should not copy fixed monitoring parameters or universal false-positive
claims from another workload. Before automated drift alerts ship:

1. cohort observations by endpoint, route, requested model, region, and probe
   suite version;
2. keep baseline and test windows disjoint;
3. use Wilson or beta-binomial uncertainty for small binary pass/fail samples;
4. use latency quantiles and distribution comparisons rather than means alone;
5. calibrate CUSUM or alternative thresholds on each metric's null history;
6. use sequentially valid evidence or a multiple-testing policy for recurring
   checks;
7. expose sample size, missingness, effect size, and recovery—not only severity;
8. treat mixed routing as a candidate distribution rather than one forced label.

Five repeated trials can be a sensible cost choice, but it does not by itself
guarantee a reliable 95% interval for bounded, binary, heavy-tailed, or
correlated measurements. The interval must match the data-generating process.

## Planned cadence model

The scheduler is intentionally outside the 0.2 middleware, but the data model
supports a later policy such as:

| Cadence | Work | Purpose |
|---|---|---|
| Every request | passive observation | availability, latency, metadata mixture |
| 5–15 minutes | one rotating canary | fast format/routing warning |
| Hourly | complete smoke suite, repeated | controlled short-window capability |
| Daily/weekly | broader domain suite | slower skill and safety drift |
| On alert | reference/fingerprint suite | higher-cost confirmation and diagnosis |

Scheduling must be explicit, rate- and cost-aware, and disabled by default.
`init()` will never become a hidden active scheduler.

## Relationship to identity detection

Capability drift is evidence that the endpoint changed; it is not an identity
label. Identity escalation should use a separate chain:

1. provider-signed attestation when available;
2. contradictory response metadata and known fingerprints;
3. reference-backed logprob/token-rank distribution tests;
4. calibrated active classifiers with open-set rejection;
5. textual or timing similarity only as weak, confounded evidence.

This separation is the core fit between a continuous capability dashboard and
LLMWho: AI Stupid Level-style monitoring supplies one important layer, while
the middleware adds endpoint-specific passive transport and identity evidence.
The research basis and limitations of candidate detectors are catalogued in
[RESEARCH.md](RESEARCH.md).
