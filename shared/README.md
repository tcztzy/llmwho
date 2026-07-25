# ObservationV2

`observation-v2.schema.json` is the language-neutral storage contract used by
both LLMWho SDKs and the dashboard. It intentionally excludes request headers,
query strings, raw prompts, raw responses, and arbitrary provider payloads.

The `modality` field can represent non-text systems in later releases, while
the 0.2 detector and probe suite only support text-generation endpoints.

Version 2 deliberately breaks version 1: providers' response-body model strings
are declarations, never identity candidates or confidence. Readers tolerate
optional fields, producers add no undeclared fields, and Collector rejects other
schema versions rather than carrying compatibility paths.

`fixtures/output-affinity.json` is the cross-language fixed vector for the
explicit, non-persisted output-style divergence API. It is not an observation
event and contains synthetic prose only.
