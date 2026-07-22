import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { randomUUID } from "node:crypto";
import { test } from "node:test";

import { init } from "../src/index.js";
import { isLlmUrl } from "../src/hooks.js";

function storagePath() {
  return join(tmpdir(), `llmwho-hook-${randomUUID()}.jsonl`);
}

async function settleTelemetry() {
  await new Promise((resolve) => setTimeout(resolve, 20));
}

test("known LLM routes and explicit endpoints are matched", () => {
  assert.equal(isLlmUrl("https://api.example/v1/chat/completions"), true);
  assert.equal(isLlmUrl("https://api.example/v1beta/models/x:generateContent"), true);
  assert.equal(isLlmUrl("https://api.example/users"), false);
  assert.equal(isLlmUrl("https://private.example/custom", "https://private.example"), true);
});

test("init is idempotent, preserves Response identity, and stores no content", async () => {
  const original = globalThis.fetch;
  const response = new Response(JSON.stringify({
    model: "actual-model",
    choices: [{ message: { content: "never persist output" } }],
    usage: { prompt_tokens: 4, completion_tokens: 2, total_tokens: 6 },
  }), { status: 200, headers: { "content-type": "application/json" } });
  globalThis.fetch = async () => response;
  const path = storagePath();
  const handle = init({ storagePath: path });
  const second = init({ storagePath: storagePath() });
  assert.equal(second, handle);
  try {
    const received = await fetch("https://api.example/v1/chat/completions?api_key=never-store", {
      method: "POST",
      headers: { authorization: "Bearer never-store" },
      body: JSON.stringify({
        model: "requested-model",
        messages: [{ role: "user", content: "never persist input" }],
      }),
    });
    assert.equal(received, response);
    await settleTelemetry();
    const text = readFileSync(path, "utf8");
    assert.equal(text.includes("never-store"), false);
    assert.equal(text.includes("never persist input"), false);
    assert.equal(text.includes("never persist output"), false);
    const event = JSON.parse(text.trim());
    assert.equal(event.identity.status, "mismatch");
    assert.equal(event.request.role_count, 1);
  } finally {
    handle.shutdown();
    assert.equal(globalThis.fetch, original === handle.originalFetch ? original : handle.originalFetch);
    globalThis.fetch = original;
  }
});

test("non-LLM requests are ignored and streaming responses are not read", async () => {
  const original = globalThis.fetch;
  let cloneCalls = 0;
  const response = new Response("data: secret-stream\n\n", { status: 200 });
  response.clone = () => {
    cloneCalls += 1;
    throw new Error("must not clone stream");
  };
  globalThis.fetch = async () => response;
  const path = storagePath();
  const handle = init({ storagePath: path });
  try {
    await fetch("https://api.example/health");
    await fetch("https://api.example/v1/chat/completions", {
      method: "POST",
      body: JSON.stringify({ model: "model-a", stream: true }),
    });
    await settleTelemetry();
    assert.equal(cloneCalls, 0);
    const events = readFileSync(path, "utf8").trim().split("\n");
    assert.equal(events.length, 1);
  } finally {
    handle.shutdown();
    globalThis.fetch = original;
  }
});

test("network errors keep their object identity and are recorded", async () => {
  const original = globalThis.fetch;
  const failure = new TypeError("network failed with secret that is never stored");
  globalThis.fetch = async () => { throw failure; };
  const path = storagePath();
  const handle = init({ storagePath: path });
  try {
    await assert.rejects(
      fetch("https://api.example/v1/responses", {
        method: "POST",
        body: JSON.stringify({ model: "model-a" }),
      }),
      (error) => error === failure,
    );
    const text = readFileSync(path, "utf8");
    assert.equal(text.includes("secret"), false);
    assert.equal(JSON.parse(text).transport.outcome, "network_error");
  } finally {
    handle.shutdown();
    globalThis.fetch = original;
  }
});
