# Security and privacy

Please report vulnerabilities privately through GitHub security advisories.

LLMWho runs inside applications that may handle sensitive prompts and API
credentials. Its default policy stores derived metadata only. Authorization
headers, cookies, API keys, signed query values, and equivalent credentials
must never be persisted. LLMWho 0.4 does not implement raw prompt or response
capture, including when its reserved capture option is supplied.

Telemetry failures are designed to be fail-open for the host request. Reports
about secret leakage, request/stream mutation, hook ownership, unsafe dashboard
binding, or an identity claim that exceeds its evidence are treated as security
or trust-boundary issues.

Science plugins are executable Python code and run with the user's process
privileges. The Node SDK installs only plugin packages explicitly supplied to
`ScienceRuntimeManager`; pin and audit them like any application dependency.
Reference fingerprint bundles are data and must never be treated as plugins.
Science worker errors do not echo caller-supplied raw analysis input.

Collector binds loopback by default. Non-loopback mode requires an explicit
Bearer token, and every data endpoint then requires that token. The built-in
server does not terminate TLS; use a private network or TLS reverse proxy.
Dashboard HTML and health remain public but contain no observation data. The
browser keeps its entered token in memory only. Collector rejects an entire
batch if any event contains a forbidden raw-content field and never echoes the
body or credential in an error response.
