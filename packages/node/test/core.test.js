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
  inferIdentity,
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
  const fixture = JSON.parse(readFileSync(join(ROOT, "shared", "fixtures", "observation-v1.json")));
  validateObservation(fixture);
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

test("identity abstains without evidence", () => {
  assert.deepEqual(inferIdentity("gpt-something").status, "unknown");
  assert.deepEqual(inferIdentity("model-a", "model-b").status, "mismatch");
});

test("store rejects raw content and round trips", () => {
  const path = join(tmpdir(), `llmwho-${randomUUID()}.jsonl`);
  const event = newObservation({
    url: "https://api.example.test/v1/chat/completions?token=hidden",
    durationMs: 25,
    outcome: "success",
    claimedModel: "model-a",
    declaredModel: "model-a",
    request: { operation: "chat.completions", input_bytes: 21 },
  });
  const store = new JSONLStore(path);
  store.append(event);
  assert.deepEqual(store.read(), [event]);
  event.request.messages = [{ content: "secret" }];
  assert.throws(() => validateObservation(event), /raw content field/);
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
    claimedModel: "a",
    declaredModel,
  }));
  const report = summarize(rows);
  assert.equal(report.availability.success_rate, 2 / 3);
  assert.equal(report.transport.latency_ms.p50, 20);
  assert.deepEqual(report.identity.statuses, { matched: 2, unknown: 1 });
  assert.equal(quantile([0, 10], 0.95), 9.5);
});
