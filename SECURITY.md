# Security and privacy

Please report vulnerabilities privately through GitHub security advisories.

LLMWho runs inside applications that may handle sensitive prompts and API
credentials. Its default policy stores derived metadata only. Authorization
headers, cookies, API keys, signed query values, and equivalent credentials
must never be persisted. LLMWho 0.3 does not implement raw prompt or response
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
