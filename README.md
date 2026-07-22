# LLMWho

**Know who is probably behind the endpoint—and whether that endpoint is still
behaving like the service you chose.**

LLMWho is a local-first middleware and self-hosted Collector for passive LLM
API observation, explicit active probes, and layered stability monitoring. Its
main application integration is one call:

```python
import llmwho

handle = llmwho.init()
```

```js
import { init } from "llmwho";

const handle = init();
```

That call hooks supported HTTP paths in the current process. It does not add a
proxy, change a base URL, wrap each client, or send synthetic traffic. Existing
return values, exceptions, and streaming bodies stay under application control.

> **Alpha honesty:** version 0.4 infers identity from the response body's
> declared `model` field. Undocumented model response headers are ignored.
> This provider-controlled signal can reveal accidental routing changes,
> but a dishonest provider can forge them. The smoke probe measures endpoint
> capability and consistency; it is not yet an LLMmap-style behavioral model
> classifier. Identity conclusions remain evidence-backed and probabilistic;
> every result can say `unknown`.

LLMWho also exposes a Python science-plugin runtime for explicit analyses such
as the output-affinity matrix. It is never started by passive hooks and its
results are not identity or distillation proof.

## Install

Python 3.10+:

```bash
pip install llmwho
```

Node.js 18+:

```bash
npm install llmwho
```

The Python package has no required runtime dependencies. If an application has
HTTPX or requests installed, `init()` instruments them. The Node package hooks
`globalThis.fetch`, which is built into supported Node versions. Node science
operations additionally require [uv](https://docs.astral.sh/uv/): the npm SDK
discovers it and creates a locked Python environment on first explicit science
call. Import, npm installation, and `init()` never perform that setup.

## Passive observation

Call `init()` before constructing or using the LLM client:

```python
import llmwho
from openai import OpenAI

telemetry = llmwho.init()
client = OpenAI()
answer = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello"}],
)

# Optional: restore only the callables patched by this handle.
telemetry.shutdown()
```

```js
import OpenAI from "openai";
import { init } from "llmwho";

const telemetry = init();
const client = new OpenAI();
await client.chat.completions.create({
  model: "gpt-4o-mini",
  messages: [{ role: "user", content: "Hello" }],
});

telemetry.shutdown();
```

### Direct Anthropic Messages API

Anthropic SDK stays an application dependency; LLMWho does not import it:

```python
import llmwho
from anthropic import Anthropic

llmwho.init()
client = Anthropic()
message = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=64,
    messages=[{"role": "user", "content": "Hello"}],
)
```

```js
import Anthropic from "@anthropic-ai/sdk";
import { init } from "llmwho";

init();
const client = new Anthropic();
const message = await client.messages.create({
  model: "claude-sonnet-4-20250514",
  max_tokens: 64,
  messages: [{ role: "user", content: "Hello" }],
});
```

Direct `api.anthropic.com/v1/messages` observations normalize provider,
operation, model, stream, role-count, byte-count, status, and token-usage
fields. SDK streaming calls are observed without reading or cloning their
response bodies.

### Claude Code and Codex project hooks

When an agent owns its HTTP transport, configure its project lifecycle hooks
to call the same content-free observer:

```bash
llmwho hook claude-code --event Stop
llmwho hook codex --event Stop
```

The commands read official hook JSON from stdin; users should configure them,
not run them by hand. Copy or merge the ready-made
[Claude Code](examples/hooks/claude-code.settings.json) and
[Codex](examples/hooks/codex.hooks.json) templates. See
[Agent hook setup, privacy, and limits](docs/AGENT_HOOKS.md).

Repeated `init()` calls return the same active handle; they do not stack hook
layers. By default, events are appended to `~/.llmwho/events.jsonl`.

Recognized routes include OpenAI-compatible chat/completions/responses,
Anthropic-shaped `/messages`, Gemini `:generateContent`, and Ollama
`/api/chat`/`/api/generate`. Non-LLM URLs are ignored. A private or unusual
route can be explicitly included:

```python
llmwho.init(endpoint="https://gateway.example/internal/ai")
```

```js
init({ endpoint: "https://gateway.example/internal/ai" });
```

### Configuration

| Purpose | Python | Node | Environment |
|---|---|---|---|
| Event file | `storage_path="…"` | `storagePath: "…"` | `LLMWHO_STORAGE` |
| Collector URL | `collector_url="…"` | `collectorUrl: "…"` | `LLMWHO_COLLECTOR_URL` |
| Collector token | `collector_token="…"` | `collectorToken: "…"` | `LLMWHO_COLLECTOR_TOKEN` |
| Wire protocol | `collector_protocol="native"` | `collectorProtocol: "native"` | `LLMWHO_COLLECTOR_PROTOCOL` |
| Explicit route | `endpoint=prefix_or_callable` | `endpoint: prefixOrFunction` | — |
| Disable hooks | — | — | `LLMWHO_DISABLED=true` |
| Content capture | reserved | reserved | `LLMWHO_CAPTURE_CONTENT` reserved |

Raw content capture is deliberately unavailable in 0.4 even if the reserved
option is supplied. This keeps every `ObservationV1` portable and content-free.

## Self-hosted Collector

Run one process for central ingestion, SQLite WAL persistence, queries, and the
live dashboard:

```bash
llmwho collector
```

Then point any Python or Node application at it:

```bash
export LLMWHO_COLLECTOR_URL=http://127.0.0.1:7734
```

When configured, SDKs validate and enqueue observations without waiting for
Collector latency. Both native batches and marked OTLP/HTTP JSON logs are
supported. The queue is bounded and delivery remains fail-open; without a
Collector URL, the SDK keeps using local JSONL.

Non-loopback binds require `LLMWHO_COLLECTOR_TOKEN`; data APIs require the same
value as a Bearer token. The dashboard asks for it in protected deployments and
keeps it in page memory. Use TLS before sending that credential across a
network. For Docker Compose, API details, OTLP mapping, JSONL import/export, and
the data ownership model, see [Self-hosted Collector](docs/COLLECTOR.md).

## Explicit active probe

Active probes cost requests and are never triggered by `init()`. The `smoke`
suite sends four short, temperature-zero cases for exact instruction following,
JSON adherence, invalid-premise handling, and arithmetic:

```python
report = llmwho.probe(
    base_url="https://api.openai.com/v1",
    api_key="…",
    model="gpt-4o-mini",
)
print(report["capability"])
```

```js
import { probe } from "llmwho";

const report = await probe({
  baseUrl: "https://api.openai.com/v1",
  apiKey: process.env.OPENAI_API_KEY,
  model: "gpt-4o-mini",
});
console.log(report.capability);
```

Use the CLI without placing a key on the command line:

```bash
llmwho probe --base-url https://api.openai.com/v1 --model gpt-4o-mini
npx llmwho probe --base-url https://api.openai.com/v1 --model gpt-4o-mini
```

The default key environment variable is `OPENAI_API_KEY`; change it with
`--api-key-env NAME`. Each attempted case is recorded even when it times out or
returns an HTTP error.

## Summary and dashboard

```bash
llmwho summary
llmwho summary --json
llmwho dashboard                 # http://127.0.0.1:7734

npx llmwho summary
npx llmwho dashboard
```

The dashboard deliberately keeps five layers separate:

1. availability—success, timeout, HTTP, network, and stream outcomes;
2. transport—latency distribution and tails;
3. behavior—content-free response-size and streaming indicators;
4. capability—judge-free active-probe results;
5. identity—claimed/observed agreement, candidates, and unknown share.

See [Stability model](docs/STABILITY.md) for the adaptation of continuous
benchmark systems such as AI Stupid Level, and [Research landscape](docs/RESEARCH.md)
for the peer-reviewed fingerprinting and API-drift work behind the roadmap.

## Python science plugins

Scientific detectors have one Python implementation and a versioned plugin
contract. Python discovers installed plugins through the
`llmwho.science.plugins` entry-point group. Node manages a separate Python
environment with uv and talks to the same plugins over a local JSONL worker.

Inspect or prepare the Node runtime explicitly:

```bash
npx llmwho science status
npx llmwho science setup
npx llmwho science plugins
```

`science.setup()` may download Python and locked dependencies through uv. Use
`--offline` when only existing Python installations and caches are allowed.
Executable plugin packages are trusted code and must be configured explicitly;
reference-profile bundles are data and must not contain executable code. See
[Science runtime and plugins](docs/SCIENCE_RUNTIME.md).

### Explicit output-affinity matrix

Compare model prose locally with the reproducible, symmetric character-trigram
divergence used by the recent Typebulb model-style matrix:

```python
from llmwho import science

analysis = science.output_affinity_matrix({
    "reference": ["reference answer one", "reference answer two"],
    "endpoint": ["endpoint answer one", "endpoint answer two"],
})
print(analysis["evidence"]["matrix"][0][1])
```

```js
import { science } from "llmwho";

const analysis = await science.outputAffinityMatrix({
  reference: ["reference answer one", "reference answer two"],
  endpoint: ["endpoint answer one", "endpoint answer two"],
});
console.log(analysis.evidence.matrix[0][1]);
```

Lower values mean closer surface style. Analysis sends no provider request and
stores no corpus or observation event; the caller explicitly supplies raw
outputs, and the report contains only derived counts and distances. Node may
provision its Python environment before calculation. Similar style is not proof
of model identity, distillation, or capability transfer. See formula, fidelity
check, controls, and limitations in
[Output-affinity matrix](docs/OUTPUT_AFFINITY.md).

## What is stored

An event may include:

- query-free endpoint scheme, host, port, and path;
- operation, requested model, streaming flag, byte counts, and role count;
- status, latency, usage, response-declared model, and system fingerprint;
- identity candidates, confidence, and the evidence ledger;
- deterministic probe case ID, pass/fail, and score.

It does **not** include raw prompts, messages, responses, request/response
headers, URL query strings, cookies, authorization values, or API keys.
Telemetry construction and storage are fail-open: they must not replace a
successful response or the application's original exception.

## Limits and threat model

- Response metadata is operational evidence, not cryptographic attestation.
- Capability similarity does not uniquely identify model weights.
- A model name does not distinguish quantization, fine-tuning, system prompts,
  decoding settings, inference engines, regional routes, or mixed backends.
- Timing reflects network, load, batching, hardware, and inference software as
  well as the model.
- Passive production workloads change over time and are not a controlled
  benchmark.
- The 0.4 smoke suite is a compatibility canary, not a broad intelligence score.
- Output-affinity depends on its prompt set and pooled reference models; it
  measures local writing style, not model provenance.

Future detectors must be calibrated on held-out models and dates, reject
open-set unknowns, preserve sample size and uncertainty, and explain their
reference requirements. See [Product vision](docs/VISION.md) and
[Roadmap](docs/ROADMAP.md).

## Development

```bash
pre-commit install
pre-commit run --all-files
ruff check --config packages/python/pyproject.toml .
uv run --project packages/python --extra test python -m unittest discover -s packages/python/tests -v
npm install --prefix packages/node
npm test --prefix packages/node
LLMWHO_RUN_UV_INTEGRATION=1 npm test --prefix packages/node
npm run typecheck --prefix packages/node
npm run build --prefix packages/node
```

The repository is an MIT-licensed monorepo. Public behavior is defined in
[`SPEC.md`](SPEC.md); contributions should update tests and documentation with
the implementation. Maintainers publish immutable, tag-matched artifacts using
the tokenless GitHub Actions process in [Releasing LLMWho](docs/RELEASING.md).
