# Science runtime and plugins

LLMWho separates passive instrumentation from scientific analysis. Python and
Node hooks remain native, synchronous to their host, fail-open, and free of
science-runtime side effects. Explicit `science.*` calls use one authoritative
Python plugin implementation.

## Node lifecycle

Constructing/importing the npm package and calling `init()` do not search for
uv, create an environment, spawn Python, or download files. The first explicit
science operation performs this lifecycle:

1. discover configured `uvPath`, `LLMWHO_UV`, or `uv` on `PATH`;
2. require uv 0.5.9 or newer;
3. hash engine version, bundled source, `uv.lock`, Python request, plugins, OS, and CPU;
4. create an isolated environment under the user cache directory;
5. run `uv sync --frozen --no-dev --no-editable --no-install-project`
   with the pinned Python request;
6. install the bundled project from its explicit local directory so uv rebuilds
   it without relying on a same-version wheel cache;
7. install explicitly configured plugin packages;
8. validate plugin discovery and mark the environment ready;
9. start a reusable Python worker and exchange versioned JSONL messages.

Concurrent setup is serialized by an exclusive cache lock. An environment is
ready only when both its Python executable and completion marker match the
expected environment and protocol hashes.

```js
import { ScienceRuntimeManager, science } from "llmwho";

console.log(await science.status());
await science.setup();

const privateRuntime = new ScienceRuntimeManager({
  uvPath: "/opt/uv/bin/uv",
  cacheDir: "/var/cache/llmwho-science",
  pythonVersion: "3.12",
  offline: true,
  pluginPackages: ["acme-llmwho-detectors==1.4.0"],
});
```

`setup()` and first analysis may download a managed Python and dependencies.
`offline: true`/`--offline` prohibits network access. Missing uv produces
`UV_NOT_FOUND`; LLMWho does not run an installer script automatically.
The managed runtime requests Python 3.12 by default; use `pythonVersion` or CLI
`--python` only when a plugin requires another supported version.

## Python plugin contract

Third-party distributions register an entry point:

```toml
[project.entry-points."llmwho.science.plugins"]
my_detector = "my_detector:Plugin"
```

The loaded object declares `id`, `version`, `summary`, `required_inputs`, and
`limitations`, plus an `analyze(payload)` method returning JSON-safe evidence.
Duplicate IDs and malformed plugins are rejected. Reports always include
schema/protocol versions, plugin descriptor, evidence, and limitations.

```python
from llmwho import science

print(science.plugins())
report = science.run("my_detector", {"samples": [...]})
```

## Trust and privacy

Science input is explicit caller data. The worker does not write it to event
storage and protocol errors do not echo it. A plugin is executable Python with
the user's process privileges; configure only trusted, preferably exactly
pinned packages. Installing a reference fingerprint must not install code:
reference profiles belong in separately signed, versioned data bundles.

The worker protocol is local stdio, not a listening socket. Plugin failure does
not affect passive hooks, but it fails the explicit science operation.

Repository unit tests fake uv and require no download. Set
`LLMWHO_RUN_UV_INTEGRATION=1` to add the real uv → Python worker integration
gate used before packaging and release.
