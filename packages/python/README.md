# llmwho

Passive LLM endpoint identity and stability instrumentation for Python.

```bash
pip install llmwho
```

```python
import llmwho

handle = llmwho.init()
```

One call instruments installed HTTPX (sync and async) and requests clients for
recognized LLM routes. It writes content-free observations to
`~/.llmwho/events.ndjson`; it never sends active traffic. Calls are idempotent,
streaming responses are not consumed, and `handle.shutdown()` safely restores
only LLMWho-owned patches.

Run an explicit OpenAI-compatible compatibility canary:

```python
report = llmwho.probe(
    base_url="https://api.openai.com/v1",
    api_key="…",
    model="gpt-4o-mini",
)
```

Inspect local history:

```bash
llmwho summary
llmwho dashboard
```

Identity results are probabilistic evidence, not cryptographic attestation.
Version 0.1 uses response model metadata; its smoke suite measures capability
and does not uniquely identify arbitrary model weights. Raw prompts, responses,
headers, query strings, and credentials are never stored.

Full documentation, research review, and source:
[github.com/tcztzy/llmwho](https://github.com/tcztzy/llmwho).
