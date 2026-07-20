# SPEC

## §G GOAL
`llmwho` monorepo → one-call Python/Node hooks for passive LLM API observation, evidence-backed model identity guesses, opt-in active probes, local stability dashboard, published GitHub/PyPI/npm artifacts.

## §C CONSTRAINTS
- repo: `/Users/tcztzy/GitHub/llmwho`
- brand/package/CLI: `LLMWho` / `llmwho` / `llmwho`
- MVP: text LLM APIs; core event schema carries `modality` for future image/audio/video
- local-first & zero account/server required
- default capture ⊥ raw prompt/response; default capture derived metadata only
- secrets/API keys ∉ events, logs, errors, dashboard
- active network requests only after explicit user call
- identity result probabilistic; uncertainty/`unknown` first-class; ⊥ unsupported certainty claims
- Python `>=3.10`; Node `>=18`; TypeScript declarations + ESM/CJS outputs
- optional HTTP libraries remain optional imports
- OpenAI-compatible transport first; passive generic detection for known LLM routes
- dashboard binds loopback by default
- MIT license; public research/design docs cite primary sources

## §I INTERFACES
- py: `import llmwho; handle = llmwho.init()` → idempotent global hook install
- py: `llmwho.init(storage_path=..., capture_content=False, endpoint=...)`
- py: `handle.shutdown()` → restore patched callables owned by handle
- py: `llmwho.probe(base_url=..., api_key=..., model=..., suite="smoke")` → `ProbeReport`
- js: `import { init } from "llmwho"; const handle = init()` → idempotent `globalThis.fetch` hook
- js: `handle.shutdown()` → restore owned fetch hook
- js: `probe({ baseUrl, apiKey, model, suite: "smoke" })` → `Promise<ProbeReport>`
- cli: `llmwho summary [--json] [--storage PATH]`
- cli: `llmwho dashboard [--host 127.0.0.1] [--port 7734] [--storage PATH]`
- cli: `llmwho probe --base-url URL --model ID [--api-key-env NAME] [--suite smoke]`
- js-cli: `npx llmwho summary|dashboard|probe ...`
- event: NDJSON `ObservationV1` with `schema_version="1"`, timestamp, SDK, endpoint, transport, identity, behavior, privacy fields
- dashboard: local `GET /`, `GET /api/summary`, `GET /api/events`
- env: `LLMWHO_STORAGE`, `LLMWHO_CAPTURE_CONTENT`, `LLMWHO_DISABLED`

## §V INVARIANTS
V1: ∀ process, repeated `init()` → one hook layer & shared handle; shutdown restores only LLMWho-owned patch
V2: ∀ recorded header/url/body/error → credentials & auth query values redacted before persistence
V3: default `capture_content=False` → raw request/response content ⊥ persistence
V4: passive hook → preserve return value, streaming semantics, status, exception type; telemetry failure ⊥ break app request
V5: `init()` ⊥ active network; only `probe()`/probe CLI sends synthetic requests
V6: identity inference → evidence list + confidence + candidates; insufficient evidence → `unknown`
V7: Python & JS events validate same `ObservationV1` field contract
V8: timeout/HTTP error/stream error remain first-class stability outcomes; ⊥ drop failed trials
V9: dashboard keeps availability, transport, behavior, capability, identity distinct; aggregate score ⊥ hide components
V10: summary quantiles deterministic & small-sample safe
V11: hooks ignore non-LLM URLs unless explicit endpoint matcher configured
V12: active probe scoring deterministic for deterministic checks; judge-free MVP
V13: tests use local fakes; ⊥ paid/external API required
V14: local server default host `127.0.0.1`; non-loopback requires explicit arg
V15: package import succeeds without `requests`, `httpx`, dashboard extras, or provider SDKs
V16: research doc separates published evidence, preprints, inference, and product decisions
V17: release gates → Python tests/build/install & Node tests/build/install pass before registry upload
V18: published npm/PyPI artifacts version match git tag & expose §I interfaces

## §T TASKS
id|status|task|cites
T1|x|scaffold monorepo, vision, license, contributor metadata|V3,V5,V6,V9,V16
T2|x|research black-box LLM fingerprinting, attribution, provenance, drift, reliability; write cited synthesis|V6,V16
T3|x|define shared `ObservationV1`, privacy/redaction, NDJSON storage, identity evidence, summary math|V2,V3,V6,V7,V8,V10
T4|x|implement Python `init()` hooks, API, CLI, tests|V1,V2,V3,V4,V5,V11,V15,I.py
T5|x|implement npm `init()` fetch hook, API, CLI, tests|V1,V2,V3,V4,V5,V7,V11,I.js
T6|x|implement deterministic active smoke probe & report in Python/JS|V5,V6,V8,V12,V13,I.py,I.js
T7|x|implement shared local dashboard & stability/identity views|V8,V9,V10,V14,I.dashboard
T8|~|write README/tutorial/limitations; run cross-language release verification|V6,V16,V17
T9|.|create GitHub repo, push source, publish PyPI/npm, tag release, install-verify registry artifacts|V17,V18

## §B BUGS
id|date|cause|fix
B1|2026-07-20|README contract tests matched formatting and obsolete phrases|test semantic fragments; no new invariant
