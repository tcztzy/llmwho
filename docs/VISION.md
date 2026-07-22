# Product vision

## Why LLMWho exists

An API request can name one model while the provider silently routes it to a
different snapshot, quantization, fallback, or model family. Even when the
name is honest, model quality and service behavior can change without a
versioned contract. Conventional uptime monitoring sees HTTP failures but not
silent capability or identity changes. Point-in-time benchmarks see capability
but not the endpoint a production application actually reaches.

LLMWho joins those missing views. It asks:

> What is probably behind this endpoint, what evidence supports that answer,
> and is the endpoint consistently delivering the service and capability it
> claims?

## Founder expectation: one-call instrumentation

The primary product constraint is a two-line integration:

```python
import llmwho
llmwho.init()
```

or:

```ts
import { init } from "llmwho";
init();
```

That call should install hooks on supported SDKs or HTTP request libraries.
Applications should not need to wrap every client, replace their endpoint,
adopt a proxy, or rewrite request sites. Existing return values, exceptions,
streaming behavior, and retry logic must remain intact. Calling `init()` twice
must not stack duplicate hooks.

The zero-configuration path writes privacy-preserving observations locally.
Configuration may change storage or capture policy, but it must not be required
to obtain useful transport and identity signals.

## Passive and active evidence

Passive observation is the default. It learns from traffic the application was
already going to send. It can capture:

- endpoint and provider-shaped route;
- requested and response-declared model names;
- safe response headers and system fingerprints;
- status, error category, retry evidence, latency, and streaming completion;
- token counts and derived output characteristics;
- changes in identity evidence across time.

Passive observations alone are confounded by changing production prompts.
LLMWho therefore also offers explicit active probes: small, versioned request
suites with deterministic checks. Active requests must never be triggered by
`init()` and must be visibly opt-in because they consume money, rate limits,
and provider capacity.

Scientific analysis is a separate explicit plane. Python owns the canonical
detector implementations and plugin registry; Node discovers uv, provisions a
locked isolated environment, and calls the same plugins over local stdio.
Import and `init()` must not inspect or prepare that runtime.

## Identity is an inference, not a magic label

There is no universal black-box procedure that can identify every unknown LLM
from one answer. Providers can modify system prompts, sampling settings,
quantization, output filters, and routing. LLMWho therefore returns candidates,
confidence, and evidence rather than an unsupported definitive name.

High-confidence evidence can include a conflicting response-declared model or
a stable provider fingerprint with a known reference. Behavioral similarity is
weaker evidence. Missing or contradictory evidence must result in `unknown` or
low confidence.

## Stability has separate layers

LLMWho must not compress unlike failures into a flattering single score:

1. **Availability:** success, timeout, rate limit, transport and stream failure.
2. **Transport:** time to first byte/token, total latency, throughput and tails.
3. **Behavior:** format adherence, refusal, length and semantic consistency.
4. **Capability:** deterministic probe pass rates and longitudinal drift.
5. **Identity:** claimed-versus-observed agreement, candidate distribution,
   unknown share, fingerprint changes and routing mixture.

An optional summary can exist, but every component and sample size must stay
visible. Failed requests remain data: capability conditional on success and
end-to-end effective reliability are different quantities.

## Privacy and operational posture

Raw prompts and responses are not stored by default. Authentication headers,
API keys, signed query parameters, cookies, and equivalent credentials are
never recorded. Derived features should be calculated in-process before raw
content is discarded. Telemetry failures must never break the host request.

The zero-configuration path remains local-first and writes a portable JSONL
event stream. Version 0.4 adds an optional self-hosted Collector that owns a
shared SQLite data layer and live dashboard. It binds loopback by default;
remote deployment is explicit, authenticated, and never required for an
individual developer.

## Scope

The first release targets text LLM APIs and OpenAI-compatible request shapes.
Text-to-image systems require different fingerprints and quality metrics, so
they are not part of the MVP. The shared observation schema nevertheless has a
`modality` field so future image, audio, or video adapters do not require a
new telemetry foundation.

## Definition of a successful MVP

- Python and Node users install `llmwho`, call `init()`, and existing LLM HTTP
  traffic produces local observations without code changes at call sites.
- A controlled probe suite can be invoked explicitly against an
  OpenAI-compatible endpoint.
- A local dashboard shows service, behavior, capability, and identity evidence
  separately over time.
- Every identity guess explains itself and can say `unknown`.
- Published npm and PyPI packages expose matching concepts and event fields.
- Python and Node science calls execute the same versioned Python plugins and
  report plugin identity, evidence, limitations, and protocol version.
- An administrator can deploy one Collector process, point both SDKs at it,
  and observe the same content-free events through its live dashboard.
