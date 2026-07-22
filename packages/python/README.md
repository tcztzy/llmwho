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
`~/.llmwho/events.jsonl`; it never sends active traffic. Calls are idempotent,
streaming responses are not consumed, and `handle.shutdown()` safely restores
only LLMWho-owned patches.

Send the same observations to a self-hosted Collector without changing request
sites:

```python
handle = llmwho.init(
    collector_url="http://127.0.0.1:7734",
    collector_token="…",
)
```

The remote queue is bounded, non-blocking, and fail-open. Native and OTLP modes
are available; no Collector URL keeps the local JSONL default. Run the service
with `llmwho collector`; deployment and security details are in the
[Collector guide](https://github.com/tcztzy/llmwho/blob/main/docs/COLLECTOR.md).

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
Version 0.4 uses the response body's declared `model` field and ignores
undocumented model response headers; its smoke suite measures capability
and does not uniquely identify arbitrary model weights. Raw prompts, responses,
headers, query strings, and credentials are never stored.

Full documentation, research review, and source:
[github.com/tcztzy/llmwho](https://github.com/tcztzy/llmwho).
