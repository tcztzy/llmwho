import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { randomUUID } from "node:crypto";
import { test } from "node:test";

import { probe } from "../src/index.js";

function answerFor(prompt) {
  if (prompt.includes("LLMWHO_OK")) return "LLMWHO_OK";
  if (prompt.includes("JSON object")) return '{"llmwho":1}';
  if (prompt.includes("2 + 2")) return "FALSE";
  if (prompt.includes("17 multiplied")) return "323";
  return "unexpected";
}

test("smoke probe is deterministic and content-free", async () => {
  const authorizations = [];
  const server = createServer((request, response) => {
    let body = "";
    request.setEncoding("utf8");
    request.on("data", (chunk) => { body += chunk; });
    request.on("end", () => {
      const payload = JSON.parse(body);
      authorizations.push(request.headers.authorization);
      const output = JSON.stringify({
        model: "server-model",
        system_fingerprint: "fp_local",
        choices: [{ message: { content: answerFor(payload.messages.at(-1).content) } }],
      });
      response.writeHead(200, { "content-type": "application/json" });
      response.end(output);
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const path = join(tmpdir(), `llmwho-probe-${randomUUID()}.jsonl`);
  try {
    const address = server.address();
    const report = await probe({
      baseUrl: `http://127.0.0.1:${address.port}`,
      apiKey: "probe-secret",
      model: "client-model",
      storagePath: path,
    });
    assert.deepEqual(report.capability, { passed: 4, total: 4, mean_score: 1 });
    assert.deepEqual(report.identity.statuses, { mismatch: 4 });
    assert.deepEqual(authorizations, Array(4).fill("Bearer probe-secret"));
    const persisted = readFileSync(path, "utf8");
    assert.equal(persisted.includes("probe-secret"), false);
    assert.equal(persisted.includes("Reply with exactly"), false);
    assert.equal(persisted.trim().split("\n").length, 4);
  } finally {
    await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  }
});

test("V22: undocumented model response headers are ignored", async () => {
  const server = createServer((request, response) => {
    let body = "";
    request.setEncoding("utf8");
    request.on("data", (chunk) => { body += chunk; });
    request.on("end", () => {
      const payload = JSON.parse(body);
      const output = JSON.stringify({
        choices: [{ message: { content: answerFor(payload.messages.at(-1).content) } }],
      });
      response.writeHead(200, {
        "content-type": "application/json",
        "x-model-id": "header-model-a",
        "x-model-name": "header-model-b",
        "x-model": "header-model-c",
        "openai-model": "header-model-d",
      });
      response.end(output);
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const path = join(tmpdir(), `llmwho-probe-${randomUUID()}.jsonl`);
  try {
    const address = server.address();
    const report = await probe({
      baseUrl: `http://127.0.0.1:${address.port}`,
      model: "client-model",
      storagePath: path,
    });
    assert.deepEqual(report.identity.statuses, { unknown: 4 });
    assert.deepEqual(report.identity.observed_models, {});
    const events = readFileSync(path, "utf8").trim().split("\n").map(JSON.parse);
    assert.equal(events.every((event) => event.identity.evidence.length === 0), true);
  } finally {
    await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  }
});

test("unknown suite is rejected before fetch", async () => {
  let calls = 0;
  await assert.rejects(
    probe({
      baseUrl: "http://127.0.0.1:1",
      model: "x",
      suite: "large",
      fetchImpl: async () => { calls += 1; },
    }),
    /only the smoke suite/,
  );
  assert.equal(calls, 0);
});
