# LLMWho

**Know who is probably behind the endpoint—and whether that endpoint is still
behaving like the service you chose.**

LLMWho is a local-first middleware for passive LLM API observation, explicit
active probes, and layered stability monitoring. Its main integration is one
call:

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

> **Alpha honesty:** version 0.1 infers identity from response-declared model
> metadata and headers. Those signals can reveal accidental routing changes,
> but a dishonest provider can forge them. The smoke probe measures endpoint
> capability and consistency; it is not yet an LLMmap-style behavioral model
> classifier. Identity conclusions remain evidence-backed and probabilistic;
> every result can say `unknown`.

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
`globalThis.fetch`, which is built into supported Node versions.

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

Repeated `init()` calls return the same active handle; they do not stack hook
layers. By default, events are appended to `~/.llmwho/events.ndjson`.

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
| Explicit route | `endpoint=prefix_or_callable` | `endpoint: prefixOrFunction` | — |
| Disable hooks | — | — | `LLMWHO_DISABLED=true` |
| Content capture | reserved | reserved | `LLMWHO_CAPTURE_CONTENT` reserved |

Raw content capture is deliberately unavailable in 0.1 even if the reserved
option is supplied. This keeps every `ObservationV1` portable and content-free.

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
- The 0.1 smoke suite is a compatibility canary, not a broad intelligence score.

Future detectors must be calibrated on held-out models and dates, reject
open-set unknowns, preserve sample size and uncertainty, and explain their
reference requirements. See [Product vision](docs/VISION.md) and
[Roadmap](docs/ROADMAP.md).

## Development

```bash
uv run --project packages/python --extra test python -m unittest discover -s packages/python/tests -v
npm install --prefix packages/node
npm test --prefix packages/node
npm run typecheck --prefix packages/node
npm run build --prefix packages/node
```

The repository is an MIT-licensed monorepo. Public behavior is defined in
[`SPEC.md`](SPEC.md); contributions should update tests and documentation with
the implementation.
