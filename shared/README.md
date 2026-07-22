# ObservationV1

`observation-v1.schema.json` is the language-neutral storage contract used by
both LLMWho SDKs and the dashboard. It intentionally excludes request headers,
query strings, raw prompts, raw responses, and arbitrary provider payloads.

The `modality` field can represent non-text systems in later releases, while
the 0.2 detector and probe suite only support text-generation endpoints.

Within schema version 1, readers must tolerate fields being absent when an API
does not expose them. Producers must not add undeclared fields. A future change
that needs new persisted data will publish a new schema version and migration.

`fixtures/output-affinity.json` is the cross-language fixed vector for the
explicit, non-persisted output-style divergence API. It is not an observation
event and contains synthetic prose only.
