# Security and privacy

Please report vulnerabilities privately through GitHub security advisories
once the public repository is available.

LLMWho runs inside applications that may handle sensitive prompts and API
credentials. Its default policy stores derived metadata only. Authorization
headers, cookies, API keys, signed query values, and equivalent credentials
must never be persisted. Raw prompt or response capture requires explicit
configuration and should be used only with an appropriate data policy.
