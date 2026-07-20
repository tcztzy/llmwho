# LLMWho

Know who is behind the endpoint.

LLMWho is a local-first observability and model-attestation toolkit for LLM
APIs. Its defining experience is deliberately small:

```python
import llmwho

llmwho.init()
```

```ts
import { init } from "llmwho";

init();
```

One call installs passive hooks on supported SDK/HTTP paths. LLMWho records
transport health and privacy-preserving behavioral evidence, estimates which
model may have answered, and powers a local stability dashboard. Explicit
probe APIs can send a controlled request suite when stronger evidence is
needed.

The project is under active construction. See [Vision](docs/VISION.md),
[Specification](SPEC.md), and [Roadmap](docs/ROADMAP.md).

## Principles

- Passive by default: `init()` never sends synthetic traffic.
- No raw prompts or responses are stored by default.
- API keys and authorization material are never telemetry.
- Identity is evidence-backed and probabilistic; `unknown` is a valid answer.
- Availability, latency, behavior, capability, and identity remain separate.
- The MVP targets text LLM APIs while the event model remains modality-aware.

## License

[MIT](LICENSE)
