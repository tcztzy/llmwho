# Self-hosted Collector

LLMWho 0.4 adds one deployable process that owns ingestion, SQLite persistence,
queries, and the live dashboard. Applications and gateways send content-free
`ObservationV2` events; dashboard and later science workers consume the same
logical data layer through the Collector instead of opening its database.

```text
Python / Node / gateway adapter
              |
       native HTTP or OTLP
              v
      LLMWho Collector
       |             |
 SQLite WAL      live dashboard
```

## Run locally

Loopback mode needs no token:

```bash
llmwho collector
```

It listens on `127.0.0.1:7734` and stores data in
`~/.llmwho/collector.sqlite3`. A non-loopback bind is rejected unless a bearer
token is configured:

```bash
export LLMWHO_COLLECTOR_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
llmwho collector --host 0.0.0.0 --database /var/lib/llmwho/collector.sqlite3
```

The built-in server is plain HTTP. Keep it on loopback or a private host; put a
TLS reverse proxy in front before sending bearer credentials across a network.
Do not place tokens in URLs, command arguments, events, or checked-in files.

## Run the all-in-one container

Set the required token in the current shell, then start the checked-in Compose
deployment:

```bash
export LLMWHO_COLLECTOR_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
docker compose up --build -d
```

Compose publishes only `127.0.0.1:7734`, mounts the SQLite volume at `/data`,
runs as UID 10001, and makes the remaining container filesystem read-only.
Open <http://127.0.0.1:7734/>. The page asks for the token when its API returns
401 and keeps the value in page memory only.

## Connect applications

Python:

```python
import llmwho

handle = llmwho.init(
    collector_url="http://127.0.0.1:7734",
    collector_token="…",
)
```

Node.js:

```js
import { init } from "llmwho";

const handle = init({
  collectorUrl: "http://127.0.0.1:7734",
  collectorToken: "…",
});
```

Use environment variables for an unchanged application integration:

```bash
export LLMWHO_COLLECTOR_URL=http://127.0.0.1:7734
export LLMWHO_COLLECTOR_TOKEN=…
export LLMWHO_COLLECTOR_PROTOCOL=native  # or otlp
```

Both SDKs validate locally, enqueue without waiting on Collector latency, batch
delivery, and use transport that is not instrumented by their own hook. Queues
are bounded; delivery errors and queue overflow never alter the application
request. `shutdown()` starts or waits for a best-effort flush, depending on the
language runtime. The local JSONL store remains the zero-configuration path
when no Collector is configured.

## Ingestion and query APIs

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | dashboard shell; contains no observation data |
| `GET` | `/api/health` | unauthenticated health and version |
| `GET` | `/api/summary` | layered summary |
| `GET` | `/api/events?limit=500` | validated observations |
| `POST` | `/api/v1/observations` | native `{ "observations": [...] }` batch |
| `POST` | `/v1/logs` | OTLP/HTTP JSON logs |

When a token is configured, every data endpoint requires
`Authorization: Bearer …`; only `/`, `/favicon.ico`, and `/api/health` remain
public. Native batches are atomic after validation. Duplicate `event_id` values
are accepted idempotently.

OTLP mode puts one compact `ObservationV2` JSON object in each
`LogRecord.body.stringValue` and marks it with
`llmwho.event.type=observation`. Unmarked logs and unknown OTLP fields are
ignored. Version 0.4 accepts OTLP/HTTP JSON, not protobuf. OTLP traces and
metrics are not silently reinterpreted as identity evidence. OTLP defines the
stable transport and JSON encoding used here; LLMWho retains its own internal
evidence schema because GenAI semantic fields continue to evolve. See the
[OTLP specification](https://opentelemetry.io/docs/specs/otlp/).

Existing AI gateways can send through an adapter that constructs the marked,
content-free log record. Direct ingestion of vendor-specific gateway traces is
not claimed in 0.4. Envoy AI Gateway already exposes GenAI metrics, tracing,
and access-log metadata, making it a planned adapter source rather than a
reason to build another gateway. See its
[observability documentation](https://aigateway.envoyproxy.io/docs/0.5/capabilities/observability/).

## Shared data layer

Collector creates SQLite in WAL mode with append-only tables for:

- observations;
- probe runs;
- analysis results;
- alerts;
- reference profiles.

Only observations have a public write endpoint in 0.4. Other tables reserve
the common evidence contract for later workers; they do not imply unfinished
detectors are active. Endpoint, model, transport, and timestamp columns are
indexed for later cohort queries, while the full validated event remains the
authoritative record.

Do not let dashboard, science, or exporter processes write the SQLite file
directly. Collector is its owner. JSONL is interchange, archive, and local SDK
spool—not a concurrent service database:

```bash
llmwho database import-jsonl \
  --database ~/.llmwho/collector.sqlite3 \
  --jsonl ~/.llmwho/events.jsonl

llmwho database export-jsonl \
  --database ~/.llmwho/collector.sqlite3 \
  --jsonl ./llmwho-backup.jsonl
```

Import validates the complete batch before writing. Export uses an atomic
replacement and creates the resulting file with mode `0600`.

## Privacy boundary

Collector accepts only content-free `ObservationV2` events. Version 1 is
intentionally rejected rather than translated. A batch containing
raw `prompt`, `messages`, `content`, `body`, `input`, `output`, request or
response bodies, or a privacy declaration other than
`content_captured=false` is rejected without persisting any member. Error
responses never echo the rejected body or token.

Derived byte counts, token usage, endpoint paths, model declarations, timings,
and detector evidence still reveal operational metadata. Treat the database as
sensitive, restrict filesystem and dashboard access, rotate bearer tokens, and
back it up through the export command.
