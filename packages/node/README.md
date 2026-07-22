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
Identity results are probabilistic evidence, not cryptographic attestation.
Version 0.3 uses the response body's declared `model` field and ignores
undocumented model response headers; its smoke suite measures capability
and does not uniquely identify arbitrary model weights. Raw prompts, responses,
headers, query strings, and credentials are never stored.

Full documentation, research review, and source:
[github.com/tcztzy/llmwho](https://github.com/tcztzy/llmwho).
