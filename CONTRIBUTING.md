# Contributing

LLMWho welcomes focused issues and pull requests. Before adding a detector,
state its evidence, reference-access requirements, expected cost, known
confounders, open-set behavior, and calibration method. A detector must expose
uncertainty and must not turn capability similarity into a definitive identity.

## Development setup

Python:

```bash
uv run --project packages/python --extra test python -m unittest discover -s packages/python/tests -v
uv build --project packages/python
```

Node:

```bash
npm install --prefix packages/node
npm test --prefix packages/node
npm run typecheck --prefix packages/node
npm run build --prefix packages/node
```

Repository contract tests:

```bash
python3 -m unittest discover -s tests -v
```

Tests must use local fake endpoints; paid or external model calls do not belong
in the default suite. Changes to public behavior should update `SPEC.md`, the
relevant language tests, and user documentation together. Python and Node
events must remain compatible with `shared/observation-v1.schema.json`.

Never persist credentials, query strings, headers, raw prompts, or raw
responses. Telemetry code must remain fail-open and must preserve streaming and
exception behavior.
