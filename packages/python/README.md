# llmwho

Passive LLM endpoint identity and stability instrumentation for Python.

```bash
pip install llmwho
```

```python
import llmwho

handle = llmwho.init()
```

Direct Anthropic Messages API calls need no LLMWho-specific wrapper:

```python
import llmwho
from anthropic import Anthropic

llmwho.init()
client = Anthropic()
client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=64,
    messages=[{"role": "user", "content": "Hello"}],
)
```

One call instruments installed HTTPX (sync and async) and requests clients for
recognized LLM routes. It writes content-free observations to
`~/.llmwho/events.ndjson`; it never sends active traffic. Calls are idempotent,
streaming responses are not consumed, and `handle.shutdown()` safely restores
only LLMWho-owned patches.

The CLI also accepts content-free Claude Code and Codex lifecycle events:
`llmwho hook claude-code|codex --event EVENT`. Project configuration and
privacy details are in the
[agent hook guide](https://github.com/tcztzy/llmwho/blob/main/docs/AGENT_HOOKS.md).

Run an explicit OpenAI-compatible compatibility canary:

```python
report = llmwho.probe(
    base_url="https://api.openai.com/v1",
    api_key="…",
    model="gpt-4o-mini",
)
```

Compare explicitly supplied output corpora without network or persistence:

```python
report = llmwho.science.output_affinity_matrix({
    "reference": ["reference answer"],
    "endpoint": ["endpoint answer"],
})
print(report["evidence"]["matrix"][0][1])
```

The symmetric character-trigram distance measures surface style only. It does
not prove model identity, distillation, or capability transfer. Full method and
limits: [Output-affinity matrix](https://github.com/tcztzy/llmwho/blob/main/docs/OUTPUT_AFFINITY.md).

Inspect local history:

```bash
llmwho summary
llmwho dashboard
```

Identity results are probabilistic evidence, not cryptographic attestation.
Version 0.3 uses the response body's declared `model` field and ignores
undocumented model response headers; its smoke suite measures capability
and does not uniquely identify arbitrary model weights. Raw prompts, responses,
headers, query strings, and credentials are never stored.

Full documentation, research review, and source:
[github.com/tcztzy/llmwho](https://github.com/tcztzy/llmwho).
