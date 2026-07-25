# llmwho

Passive LLM endpoint identity and stability instrumentation for Node.js.

```bash
npm install llmwho
```

```js
import { init } from "llmwho";

const handle = init();
```

Direct Anthropic Messages API calls need no LLMWho-specific wrapper:

```js
import Anthropic from "@anthropic-ai/sdk";
import { init } from "llmwho";

init();
const client = new Anthropic();
await client.messages.create({
  model: "claude-sonnet-4-20250514",
  max_tokens: 64,
  messages: [{ role: "user", content: "Hello" }],
});
```

One call instruments `globalThis.fetch` for recognized LLM routes. It writes
content-free observations to `~/.llmwho/events.jsonl`; it never sends active
traffic. Calls are idempotent, streaming responses are not consumed, and
`handle.shutdown()` safely restores only the LLMWho-owned hook.

Send the same observations to a self-hosted Collector without changing request
sites:

```js
const handle = init({
  collectorUrl: "http://127.0.0.1:7734",
  collectorToken: "…",
});
```

The remote queue is bounded, non-blocking, and fail-open. Native and OTLP modes
are available; no Collector URL keeps the local JSONL default. Run the Python
service with `llmwho collector`; deployment and security details are in the
[Collector guide](https://github.com/tcztzy/llmwho/blob/main/docs/COLLECTOR.md).

The CLI also accepts content-free Claude Code and Codex lifecycle events:
`llmwho hook claude-code|codex --event EVENT`. Project configuration and
privacy details are in the
[agent hook guide](https://github.com/tcztzy/llmwho/blob/main/docs/AGENT_HOOKS.md).

Run an explicit OpenAI-compatible compatibility canary:

```js
import { probe } from "llmwho";

const report = await probe({
  baseUrl: "https://api.openai.com/v1",
  apiKey: process.env.OPENAI_API_KEY,
  model: "gpt-4o-mini",
});
```

Run the authoritative Python output-affinity plugin:

```js
import { science } from "llmwho";

const analysis = await science.outputAffinityMatrix({
  reference: ["reference answer"],
  endpoint: ["endpoint answer"],
});
console.log(analysis.evidence.matrix[0][1]);
```

Science calls discover [uv](https://docs.astral.sh/uv/) and create a locked,
cached Python environment. Package import, npm installation, and `init()` do
not perform setup. Inspect or prepare it with `npx llmwho science status|setup`;
add `--offline` to prohibit downloads. The symmetric character-trigram distance
measures surface style only. It does not prove model identity, distillation, or
capability transfer. Full [science runtime](https://github.com/tcztzy/llmwho/blob/main/docs/SCIENCE_RUNTIME.md)
and [output-affinity](https://github.com/tcztzy/llmwho/blob/main/docs/OUTPUT_AFFINITY.md)
documentation is available in the repository.

Inspect local history:

```bash
npx llmwho summary
npx llmwho dashboard
```

The package provides ESM and CommonJS entry points plus TypeScript declarations.
Version 0.4 records the response body's declared `model` field only as a
provider declaration. It never turns that declaration into model identity or
confidence. Identity remains `unknown` unless an independent calibrated
detector supplies evidence. Undocumented model response headers are ignored;
the smoke suite measures capability and does not uniquely identify arbitrary
model weights. Raw prompts, responses, headers, query strings, and credentials
are never stored.

Full documentation, research review, and source:
[github.com/tcztzy/llmwho](https://github.com/tcztzy/llmwho).
