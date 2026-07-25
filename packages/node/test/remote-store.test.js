import assert from "node:assert/strict";
import { setTimeout as delay } from "node:timers/promises";
import { afterEach, test } from "node:test";

import {
  JSONLStore,
  RemoteStore,
  init,
  newObservation,
  otlpLogsPayload,
} from "../src/index.js";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
  delete process.env.LLMWHO_COLLECTOR_URL;
  delete process.env.LLMWHO_COLLECTOR_TOKEN;
  delete process.env.LLMWHO_COLLECTOR_PROTOCOL;
  delete process.env.LLMWHO_DISABLED;
});

function event(identifier = "event-1") {
  const value = newObservation({
    url: "https://api.example/v1/chat/completions",
    durationMs: 5,
    outcome: "success",
    requestedModel: "model",
    declaredModel: "model",
  });
  value.event_id = identifier;
  return value;
}

async function waitFor(predicate) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (predicate()) return;
    await delay(10);
  }
  assert.fail("condition was not met within 1 second");
}

test("native RemoteStore sends bounded content-free batches with bearer auth", async () => {
  const calls = [];
  const store = new RemoteStore("https://collector.example", {
    token: "collector-secret",
    flushIntervalMs: 60_000,
    fetchImpl: async (url, options) => {
      calls.push([url, options]);
      return new Response("{}", { status: 202 });
    },
  });
  assert.equal(store.append(event("native")), true);
  assert.equal(await store.close(), true);
  assert.equal(store.delivered, 1);
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "https://collector.example/api/v1/observations");
  assert.equal(calls[0][1].headers.authorization, "Bearer collector-secret");
  const body = JSON.parse(calls[0][1].body);
  assert.equal(body.observations[0].event_id, "native");
  assert.equal(calls[0][1].body.includes("collector-secret"), false);
});

test("OTLP RemoteStore uses marked log records and swallows delivery failures", async () => {
  let body;
  const store = new RemoteStore("https://collector.example", {
    protocol: "otlp",
    flushIntervalMs: 60_000,
    fetchImpl: async (url, options) => {
      assert.equal(url, "https://collector.example/v1/logs");
      body = JSON.parse(options.body);
      throw new Error("offline");
    },
  });
  assert.equal(store.append(event("otlp")), true);
  assert.equal(await store.close(), true);
  assert.equal(store.deliveryFailures, 1);
  const record = body.resourceLogs[0].scopeLogs[0].logRecords[0];
  assert.equal(JSON.parse(record.body.stringValue).event_id, "otlp");
  assert.equal(
    record.attributes.find((attribute) => attribute.key === "llmwho.event.type")
      .value.stringValue,
    "observation",
  );
});

test("RemoteStore queue drops immediately when full", async () => {
  const store = new RemoteStore("https://collector.example", {
    maxQueue: 1,
    flushIntervalMs: 60_000,
    fetchImpl: async () => new Response("{}", { status: 202 }),
  });
  assert.equal(store.append(event("queued")), true);
  assert.equal(store.append(event("dropped")), false);
  assert.equal(store.dropped, 1);
  assert.equal(await store.close(), true);
});

test("init uses original fetch for Collector delivery without recursive observation", async () => {
  const calls = [];
  globalThis.fetch = async (input, options = {}) => {
    const url = String(input);
    calls.push([url, options]);
    if (url.includes("collector.example")) {
      return new Response("{}", { status: 202 });
    }
    return new Response(JSON.stringify({ model: "model", usage: {} }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };
  const handle = init({
    collectorUrl: "https://collector.example",
    collectorToken: "token",
  });
  assert.equal(handle.store instanceof RemoteStore, true);
  const response = await globalThis.fetch("https://api.example/v1/chat/completions", {
    method: "POST",
    body: JSON.stringify({ model: "model", messages: [] }),
  });
  assert.equal(response.status, 200);
  await waitFor(() => calls.some(([url]) => url.includes("collector.example")));
  assert.equal(await handle.store.close(), true);
  handle.shutdown();
  assert.equal(calls.length, 2);
  const collectorCall = calls.find(([url]) => url.includes("collector.example"));
  const payload = JSON.parse(collectorCall[1].body);
  assert.equal(payload.observations.length, 1);
  assert.equal(payload.observations[0].endpoint.host, "api.example");
  assert.equal(collectorCall[1].body.includes("token"), false);
});

test("disabled init ignores remote configuration and remains local", () => {
  process.env.LLMWHO_DISABLED = "true";
  process.env.LLMWHO_COLLECTOR_URL = "https://collector.example";
  const handle = init();
  assert.equal(handle.active, false);
  assert.equal(handle.store instanceof JSONLStore, true);
});

test("Python and Node OTLP mapping fields remain semantically aligned", () => {
  const payload = otlpLogsPayload([event("wire")]);
  const record = payload.resourceLogs[0].scopeLogs[0].logRecords[0];
  assert.deepEqual(
    record.attributes.map(({ key, value }) => [key, value.stringValue]),
    [
      ["llmwho.event.type", "observation"],
      ["llmwho.schema.version", "2"],
    ],
  );
  assert.equal(JSON.parse(record.body.stringValue).event_id, "wire");
});

test("RemoteStore rejects credentials embedded in Collector URL", () => {
  assert.throws(
    () => new RemoteStore("https://user:secret@collector.example"),
    /without credentials/,
  );
});

test("RemoteStore follows Collector cursor pages and restores chronological order", async () => {
  const newer = event("newer");
  const older = event("older");
  newer.timestamp = "2026-07-25T00:00:02.000Z";
  older.timestamp = "2026-07-25T00:00:01.000Z";
  const urls = [];
  const store = new RemoteStore("https://collector.example", {
    fetchImpl: async (url) => {
      urls.push(String(url));
      return urls.length === 1
        ? new Response(JSON.stringify({ events: [newer], next_cursor: "next-page" }))
        : new Response(JSON.stringify({ events: [older], next_cursor: null }));
    },
  });
  assert.deepEqual(
    (await store.read()).map((value) => value.event_id),
    ["older", "newer"],
  );
  assert.equal(urls.length, 2);
  assert.equal(new URL(urls[1]).searchParams.get("cursor"), "next-page");
  assert.equal(await store.close(), true);
});
