import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";
import { test } from "node:test";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";

import * as llmwho from "../src/index.js";
import {
  JSONLStore,
  newObservation,
  quantile,
  summarize,
  validateObservation,
} from "../src/index.js";
import { endpointFromUrl, redactHeaders, redactText } from "../src/privacy.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");

test("legacy store name is removed", () => {
  const legacyName = ["ND", "JSONStore"].join("");
  assert.equal(Object.hasOwn(llmwho, legacyName), false);
});

test("shared fixture is accepted", () => {
  const fixture = JSON.parse(readFileSync(join(ROOT, "shared", "fixtures", "observation-v2.json")));
  validateObservation(fixture);
  fixture.schema_version = "1";
  assert.throws(() => validateObservation(fixture), /unsupported observation/);
});

test("URL and secrets are redacted", () => {
  assert.deepEqual(
    endpointFromUrl("https://user:pass@api.example.test:8443/v1/chat?api_key=secret#fragment"),
    { scheme: "https", host: "api.example.test", port: 8443, path: "/v1/chat" },
  );
  const [headers, headerCount] = redactHeaders({ Authorization: "Bearer secret", Accept: "json" });
  assert.equal(headers.Authorization, "[REDACTED]");
  assert.equal(headerCount, 1);
  const [cleaned, count] = redactText("failed Bearer abc.def and sk-abcdefghijk");
  assert.equal(cleaned.includes("abc.def"), false);
  assert.equal(cleaned.includes("sk-abcdefghijk"), false);
  assert.equal(count, 2);
});

test("provider declaration never becomes identity evidence", () => {
  const event = newObservation({
    url: "https://api.example.test/v1/chat/completions",
    durationMs: 1,
    outcome: "success",
    requestedModel: "model-a",
    declaredModel: "model-b",
  });
  assert.deepEqual(event.identity, { status: "unknown", candidates: [], evidence: [] });
  assert.equal(event.model_declaration.status, "mismatch");
  assert.deepEqual(event.model_declaration.evidence, [{
    kind: "provider_declaration",
    source: "response.body.model",
    value: "model-b",
  }]);
  assert.equal("confidence" in event.identity, false);
});

test("store rejects raw content and round trips", () => {
  const path = join(tmpdir(), `llmwho-${randomUUID()}.jsonl`);
  const event = newObservation({
    url: "https://api.example.test/v1/chat/completions?token=hidden",
    durationMs: 25,
    outcome: "success",
    requestedModel: "model-a",
    declaredModel: "model-a",
    request: { operation: "chat.completions", input_bytes: 21 },
  });
  const store = new JSONLStore(path);
  store.append(event);
  assert.deepEqual(store.read(), [event]);
  event.request.messages = [{ content: "secret" }];
  assert.throws(() => validateObservation(event), /raw content field/);
});

test("V36: complete schema validation rejects unknown and malformed fields", () => {
  const valid = newObservation({
    url: "https://api.example.test/v1/chat/completions",
    durationMs: 25,
    outcome: "success",
    requestedModel: "model-a",
    declaredModel: "model-a",
    response: { usage: { input_tokens: 1 } },
  });
  const copy = () => JSON.parse(JSON.stringify(valid));
  const unknown = copy();
  unknown.unexpected = true;
  const missingNested = copy();
  delete missingNested.sdk.version;
  const invalidPort = copy();
  invalidPort.endpoint.port = 0;
  const booleanInteger = copy();
  booleanInteger.response.usage.input_tokens = true;
  const invalidTimestamp = copy();
  invalidTimestamp.timestamp = "not-a-date";
  for (const event of [
    unknown,
    missingNested,
    invalidPort,
    booleanInteger,
    invalidTimestamp,
  ]) {
    assert.throws(() => validateObservation(event));
  }
});

test("summary keeps layers separate", () => {
  const rows = [
    [10, "success", "a"],
    [20, "success", "a"],
    [100, "timeout", undefined],
  ].map(([durationMs, outcome, declaredModel]) => newObservation({
    url: "https://api.example.test/v1/chat/completions",
    durationMs,
    outcome,
    requestedModel: "a",
    declaredModel,
  }));
  const report = summarize(rows);
  assert.equal(report.availability.success_rate, 2 / 3);
  assert.equal(report.transport.latency_ms.p50, 20);
  assert.deepEqual(report.identity.statuses, { unknown: 3 });
  assert.deepEqual(report.declarations.statuses, { matched: 2, missing: 1 });
  assert.equal(quantile([0, 10], 0.95), 9.5);
});
