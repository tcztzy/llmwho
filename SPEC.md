# SPEC

## §G GOAL
`llmwho` monorepo → one-call Python/Node passive observation, self-hosted Collector + shared data layer, evidence-backed model identity guesses, opt-in active probes/science, live stability dashboard, published GitHub/PyPI/npm artifacts.

## §C CONSTRAINTS
- repo: `/Users/tcztzy/GitHub/llmwho`
- brand/package/CLI: `LLMWho` / `llmwho` / `llmwho`
- MVP: text LLM APIs; core event schema carries `modality` for future image/audio/video
- local-first & zero account/server required
- default capture ⊥ raw prompt/response; default capture derived metadata only
- secrets/API keys ∉ events, logs, errors, dashboard
- active network requests only after explicit user call
- output-affinity analysis accepts explicit caller-provided corpora only; passive capture/storage unchanged
- science analysis uses Python plugin runtime; Node discovers `uv` & provisions locked isolated env only after explicit `science.*`/science CLI call
- `init()`/module import/npm lifecycle scripts ⊥ `uv` discovery, Python setup, child process, download
- executable science plugins require explicit package configuration; reference profiles remain versioned data, ⊥ executable code
- identity result probabilistic; uncertainty/`unknown` first-class; ⊥ unsupported certainty claims
- provider declaration ≠ model identity; passive declaration agreement never yields identity candidate/confidence
- Python `>=3.10`; Node `>=18`; TypeScript declarations + ESM/CJS outputs
- optional HTTP libraries remain optional imports
- OpenAI-compatible transport first; passive generic detection for known LLM routes
- dashboard binds loopback by default
- v0.4 Collector owns shared SQLite writes; SDKs send validated content-free events over native HTTP or OTLP/HTTP
- JSONL = local spool/interchange/archive; ⊥ concurrent multi-service database
- Collector default single-node; scale-out storage ⊥ v0.4
- OTLP = boundary transport; internal schema ⊥ coupled to evolving GenAI semantic conventions
- remote Collector auth explicit; bearer token ∉ event/store/error response
- MIT license; public research/design docs cite primary sources

## §I INTERFACES
- py: `import llmwho; handle = llmwho.init()` → idempotent global hook install
- py: `llmwho.init(storage_path=..., capture_content=False, endpoint=...)`
- py: `llmwho.init(..., collector_url=..., collector_token=..., collector_protocol="native"|"otlp")`; env fallback `LLMWHO_COLLECTOR_*`
- py: `handle.shutdown()` → restore patched callables owned by handle
- py: `llmwho.probe(base_url=..., api_key=..., model=..., suite="smoke")` → `ProbeReport`
- js: `import { init } from "llmwho"; const handle = init()` → idempotent `globalThis.fetch` hook
- js: `init({collectorUrl, collectorToken, collectorProtocol: "native"|"otlp", ...})`; env fallback `LLMWHO_COLLECTOR_*`
- js: `handle.shutdown()` → restore owned fetch hook
- js: `probe({ baseUrl, apiKey, model, suite: "smoke" })` → `Promise<ProbeReport>`
- py: `llmwho.science.output_affinity_matrix(corpora, ngram_size=3, model_weight=0.8)` → `AnalysisReport`
- py: `llmwho.science.plugins()` / `llmwho.science.run(plugin_id, payload)` → discovered descriptors / `AnalysisReport`
- js: `await science.outputAffinityMatrix(corpora, { ngramSize: 3, modelWeight: 0.8 })` → `Promise<AnalysisReport>`
- js: `ScienceRuntimeManager({uvPath?, cacheDir?, pythonVersion?, offline?, pluginPackages?})`; `.status()` / `.setup()` / `.plugins()` / `.run()` / `.shutdown()`
- js-cli: `npx llmwho science status|setup|plugins [--offline]`
- cli: `llmwho summary [--json] [--storage PATH]`
- cli: `llmwho dashboard [--host 127.0.0.1] [--port 7734] [--storage PATH]`
- cli: `llmwho collector [--host 127.0.0.1] [--port 7734] [--database PATH] [--token-env NAME]`
- cli: `llmwho database import-jsonl|export-jsonl --database PATH --jsonl PATH`
- cli: `llmwho probe --base-url URL --model ID [--api-key-env NAME] [--suite smoke]`
- js-cli: `npx llmwho summary|dashboard|probe ...`
- event: JSONL `ObservationV2` with `schema_version="2"`, timestamp, SDK, endpoint, request, provider declaration, identity, transport, behavior, privacy fields
- anthropic: passive py/js hooks recognize direct `POST /v1/messages`; normalize `endpoint.provider="anthropic"`, `request.operation="messages"`, requested model, stream, role count, byte counts, provider-declared model, declaration status/evidence, status, and input/output/total token usage; stream body ⊥ read/clone
- agent-hook-cli: `llmwho hook claude-code|codex [--event EVENT] [--storage PATH]` reads one official lifecycle-hook JSON object from stdin; project `.claude/settings.json` / `.codex/hooks.json` configs emit content-free passive turn observations
- dashboard: local `GET /`, `GET /api/summary?since=&until=&endpoint_host=&endpoint_path=&provider=&requested_model=`, `GET /api/events?...&limit=&cursor=`; events response `{events,next_cursor}`
- collector: `GET /api/health`, windowed/cohort `GET /api/summary`, cursor-paged `GET /api/events`; `POST /api/v1/observations`; OTLP/HTTP JSON `POST /v1/logs`
- store: Python `SQLiteStore(path)` + Python/Node `RemoteStore(url, token=...)`; `append`, `read`, `close`
- env: `LLMWHO_STORAGE`, `LLMWHO_CAPTURE_CONTENT`, `LLMWHO_DISABLED`, `LLMWHO_COLLECTOR_URL`, `LLMWHO_COLLECTOR_TOKEN`, `LLMWHO_COLLECTOR_PROTOCOL`

## §V INVARIANTS
V1: ∀ process, repeated `init()` → one hook layer & shared handle; shutdown restores only LLMWho-owned patch
V2: ∀ recorded header/url/body/error → credentials & auth query values redacted before persistence
V3: default `capture_content=False` → raw request/response content ⊥ persistence
V4: passive hook → preserve return value, streaming semantics, status, exception type; telemetry failure ⊥ break app request
V5: `init()` ⊥ active network; only `probe()`/probe CLI sends synthetic requests
V6: identity inference → versioned detector evidence + candidate confidence; insufficient/uncalibrated evidence → `unknown`
V7: Python & JS events validate same `ObservationV2` field contract
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
V19: direct Anthropic Messages observations → same normalized Python/JS fields; when both counts exist `total_tokens=input_tokens+output_tokens`; malformed/absent metadata omitted
V20: Claude Code/Codex hook adapter → exit 0 & protocol-neutral stdout despite malformed input/telemetry failure; ⊥ network, transcript read, prompt/response/tool content, session/turn IDs persistence
V21: hook state → hashed session filename + safe model/start time/input byte count only; Python/JS turn event parity for provider, operation, model, duration, outcome, input/output bytes, privacy
V22: response body `model` → provider declaration only; undocumented model headers → no evidence
V23: output-affinity metric → normalized UTF-16 character n-grams + pooled-background interpolation + averaged bidirectional KL in bits; diagonal `0`; deterministic
V24: output-affinity Python/Node reports numerically agree; input corpora ⊥ network, persistence, observation events
V25: output-affinity report exposes corpus/sample/config metadata; labels result style divergence, ⊥ identity/distillation proof
V26: documentation contract tests normalize whitespace before semantic-fragment matching; formatting-only line wraps ! fail
V27: module import/`init()`/npm install → ⊥ `uv` lookup, Python env mutation/download, child process; explicit science operation may provision & reports failure
V28: Node science env identity → engine version + source hash + lock hash + Python request + plugin set + platform; lives in user cache; frozen sync; concurrent setup serialized; incomplete env ⊥ ready
V29: science plugin discovery → built-ins + Python `llmwho.science.plugins` entry points; duplicate/invalid plugins rejected; external code only from explicitly configured packages
V30: output-affinity has one Python implementation behind plugin protocol; Node API async; ⊥ JS numeric fallback/duplicate algorithm; Python/Node result parity exact after transport
V31: science worker uses versioned JSONL request/response protocol; raw analysis input ⊥ persistence/observation event/error echo; plugin result includes id/version/evidence/limitations
V32: release tag = `v` + Python/npm/module version; CI tests/builds/smoke-installs immutable artifacts before separate PyPI/npm OIDC environment jobs; registry token ⊥ GitHub secrets; GitHub Release only after both registry publishes succeed
V33: npm tarball publish uses explicit `./` filesystem spec; partial registry recovery rebuilds from immutable tag, publishes only selected missing registry, verifies same version exists on PyPI/npm before GitHub Release
V34: SQLite Collector store → WAL + `event_id` uniqueness + deterministic timestamp order; duplicate ingest idempotent; only Collector writes shared DB
V35: shared DB schema → observations, probe runs, analysis results, alerts, reference profiles; records append-only; JSONL only import/export/local spool
V36: native/OTLP Collector ingest validates complete `ObservationV2` before persistence; raw content/secret/invalid event → reject entire request, persist none
V37: Collector binds loopback by default; non-loopback → explicit bearer token; compare constant-time; token ∉ persistence/log/error body
V38: OTLP/HTTP JSON log mapping carries content-free `ObservationV2`; unsupported encoding → explicit 415; unknown OTLP fields ignored
V39: Python/Node remote sink → bounded non-blocking delivery, uninstrumented transport, fail-open host request, best-effort flush on shutdown; disabled/unconfigured → local JSONL
V40: Python/Node Collector config and wire payload parity; auth uses `Authorization: Bearer`; credentials ∉ events
V41: Collector dashboard reads same SQLite repository as ingest and polls live; availability/transport/behavior/capability/identity separation preserved
V42: v0.4 deployable as one Python process/container; `collector` includes ingest + dashboard; no external runtime dependency beyond Python stdlib
V43: Collector SQLite database/WAL/SHM + JSONL export → owner-only `0600` despite permissive process umask
V44: provider-controlled declaration → declaration status/evidence only; ⊥ identity candidate/confidence; no independent calibrated detector → identity `unknown`
V45: Collector summary defaults bounded 24h; cohort filters use indexed columns; summary ⊥ deserialize `event_json`; event pages deterministic, bounded, cursor-disjoint
V46: release CI builds non-root container, verifies health/auth/data API; protected `main` requires pull request + required CI before release tag
V47: v0.4 event boundary = intentional `ObservationV2` break; producers/Collector reject `schema_version!="2"`; ⊥ V1 compatibility path

## §T TASKS
id|status|task|cites
T1|x|scaffold monorepo, vision, license, contributor metadata|V3,V5,V6,V9,V16
T2|x|research black-box LLM fingerprinting, attribution, provenance, drift, reliability; write cited synthesis|V6,V16
T3|x|define shared `ObservationV1`, privacy/redaction, JSONL storage, identity evidence, summary math|V2,V3,V6,V7,V8,V10
T4|x|implement Python `init()` hooks, API, CLI, tests|V1,V2,V3,V4,V5,V11,V15,I.py
T5|x|implement npm `init()` fetch hook, API, CLI, tests|V1,V2,V3,V4,V5,V7,V11,I.js
T6|x|implement deterministic active smoke probe & report in Python/JS|V5,V6,V8,V12,V13,I.py,I.js
T7|x|implement shared local dashboard & stability/identity views|V8,V9,V10,V14,I.dashboard
T8|x|write README/tutorial/limitations; run cross-language release verification|V6,V16,V17
T9|x|create GitHub repo, push source, publish PyPI/npm, tag release, install-verify registry artifacts|V17,V18
T10|x|implement direct Anthropic Messages adapter, parity/privacy/stream tests, concise README examples|V1,V2,V3,V4,V5,V7,V11,V13,V15,V19,I.anthropic
T11|x|implement Claude Code/Codex project-hook CLI adapters, safe turn state, configs, parity/fail-open tests, docs|V2,V3,V4,V5,V7,V8,V13,V15,V20,V21,I.agent-hook-cli
T12|x|implement reproducible output-affinity matrix in Python/Node, public APIs, parity vectors, docs|V3,V5,V6,V12,V13,V23,V24,V25,I.py,I.js
T13|x|replace dual output-affinity with uv-managed Python science plugin runtime, async Node bridge, CLI, packaging, tests, docs|V3,V5,V13,V15,V17,V18,V23,V25,V27,V28,V29,V30,V31,I.py,I.js,I.js-cli
T14|x|add pull-request CI and tag-driven OIDC publishing for PyPI/npm/GitHub Releases|V17,V18,V32
T15|x|make tag release selectively recoverable after partial registry publish; verify both registries before GitHub Release|V17,V18,V32,V33
T16|x|make registry-verified GitHub Release run after intentionally skipped recovery publish jobs|V32,V33
T17|x|skip registry publish dry-run when recovery only rebuilds already-published artifacts|V17,V32,V33
T18|x|pass explicit repository context to isolated GitHub Release job without source checkout|V32,V33
T19|x|implement SQLite shared repository, schema, idempotence, JSONL import/export, tests|V2,V3,V7,V34,V35,V36,I.store
T20|x|implement authenticated Collector native + OTLP ingest, shared dashboard/query API, CLI, tests|V2,V3,V9,V13,V14,V34,V36,V37,V38,V41,I.collector,I.cli
T21|x|implement bounded fail-open Python/Node remote sinks, init/env config, shutdown flush, parity tests|V1,V2,V3,V4,V5,V7,V13,V39,V40,I.py,I.js,I.store
T22|x|ship all-in-one container, live Collector docs/tutorial/security guidance, contract tests|V2,V3,V9,V16,V37,V41,V42
T23|x|bump v0.4 versions; run Python/Node lint, type, test, build, install, repository gates|V17,V18,V32,V33,V42,V43
T24|x|replace provider-declaration identity confidence with breaking ObservationV2 declaration semantics across Python/Node/docs|V6,V7,V19,V20,V21,V22,V44,V47,I.event,I.anthropic
T25|x|implement bounded indexed Collector summary + cohort filters + cursor event pages; update dashboard|V9,V10,V34,V41,V45,I.dashboard,I.collector
T26|x|add container CI smoke + protected-main release gate; document maintainer setup|V17,V32,V42,V46

## §B BUGS
id|date|cause|fix
B1|2026-07-20|README contract tests matched formatting and obsolete phrases|test semantic fragments; no new invariant
B2|2026-07-21|doc contract required unsupported model-header evidence|V22
B3|2026-07-22|output-affinity doc contract matched raw line wrapping|V26
B4|2026-07-22|artifact smoke test assumed `npm pack --prefix` changed package cwd|run pack from `packages/node`; no new invariant
B5|2026-07-22|npm 12 parsed bare `dist/*.tgz` as GitHub shorthand after PyPI publish succeeded|V33
B6|2026-07-22|GitHub Actions skip propagation suppressed GitHub Release after intentionally skipped PyPI recovery job|V33
B7|2026-07-22|npm 12 publish dry-run rejects an already-published version during release-only recovery|V33
B8|2026-07-22|isolated GitHub Release job lacked `.git` and explicit `gh --repo` context|V33
B9|2026-07-22|OTLP test searched unescaped event JSON inside an outer JSON serialization|decode `body.stringValue` before semantic assertions; no new invariant
B10|2026-07-22|Collector doc contract bound one paraphrase despite equivalent atomic-rejection wording|assert separate semantic fragments under V26; no new invariant
B11|2026-07-22|container verifier overmounted owned `/data` with root-owned tmpfs, blocking UID 10001|verify V42 with image-initialized anonymous volume; no new invariant
B12|2026-07-22|runtime validator checked core fields but not full shared-schema keys/types at Collector boundary|enforce complete Python/Node `ObservationV1` shape and add V36 parity tests; no new invariant
B13|2026-07-22|SQLite creation inherited process umask and could expose operational metadata to group/others|V43
B14|2026-07-22|local release verifier left `uv run` then assumed a system `python` executable|run repository contracts inside explicit uv environment; no new invariant
B15|2026-07-25|provider-controlled `response.body.model` received arbitrary `0.98` identity confidence|V44,V47
B16|2026-07-25|Collector dashboard poll read/deserialized/sorted full observation history every 5s|V45
B17|2026-07-25|container deliverable had no CI runtime smoke and `main` accepted unguarded release commits|V46
B18|2026-07-25|Node 18 CI test assumed response-clone delivery completed after one event-loop turn|wait on the observable Collector call with a bounded deadline; no new invariant
B19|2026-07-25|Node artifact smoke unconditionally prefixed its original cwd to an already-absolute tarball path|resolve relative paths once, preserve absolute paths, and fail clearly when absent; no new invariant
