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
content-free observations to `~/.llmwho/events.ndjson`; it never sends active
traffic. Calls are idempotent, streaming responses are not consumed, and
`handle.shutdown()` safely restores only the LLMWho-owned hook.

Run an explicit OpenAI-compatible compatibility canary:

```js
import { probe } from "llmwho";

const report = await probe({
  baseUrl: "https://api.openai.com/v1",
  apiKey: process.env.OPENAI_API_KEY,
  model: "gpt-4o-mini",
});
```

Inspect local history:

```bash
npx llmwho summary
npx llmwho dashboard
```

The package provides ESM and CommonJS entry points plus TypeScript declarations.
Identity results are probabilistic evidence, not cryptographic attestation.
Version 0.1 uses response model metadata; its smoke suite measures capability
and does not uniquely identify arbitrary model weights. Raw prompts, responses,
headers, query strings, and credentials are never stored.

Full documentation, research review, and source:
[github.com/tcztzy/llmwho](https://github.com/tcztzy/llmwho).
