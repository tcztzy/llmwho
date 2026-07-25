import assert from "node:assert/strict";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { randomUUID } from "node:crypto";
import { test } from "node:test";

import { JSONLStore, newObservation } from "../src/index.js";
import { createDashboardServer } from "../src/dashboard.js";

test("dashboard serves shared UI, layered summary, and events", async () => {
  const path = join(tmpdir(), `llmwho-dashboard-${randomUUID()}.jsonl`);
  const store = new JSONLStore(path);
  store.append(newObservation({
    url: "https://api.example/v1/chat/completions",
    durationMs: 15,
    outcome: "success",
    requestedModel: "a",
    declaredModel: "a",
    response: { status_code: 200, output_bytes: 12 },
  }));
  const server = createDashboardServer({ storagePath: path });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  const base = `http://127.0.0.1:${address.port}`;
  try {
    const htmlResponse = await fetch(base);
    assert.equal(htmlResponse.status, 200);
    const html = await htmlResponse.text();
    assert.equal(html.includes("Endpoint identity &amp; stability"), true);
    const summary = await (await fetch(`${base}/api/summary`)).json();
    assert.equal(summary.events, 1);
    assert.equal(summary.behavior.output_bytes_p50, 12);
    assert.equal(typeof summary.scope.since, "string");
    const page = await (await fetch(`${base}/api/events?limit=1`)).json();
    assert.equal(page.events.length, 1);
    assert.equal(page.next_cursor, null);
    assert.equal(page.events[0].identity.status, "unknown");
    assert.equal(page.events[0].model_declaration.status, "matched");
    assert.equal((await fetch(`${base}/api/events?limit=0`)).status, 400);
    assert.equal((await fetch(`${base}/missing`)).status, 404);
  } finally {
    await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  }
});

test("dashboard applies cohort filters and disjoint cursor pages", async () => {
  const path = join(tmpdir(), `llmwho-dashboard-${randomUUID()}.jsonl`);
  const store = new JSONLStore(path);
  for (let index = 0; index < 3; index += 1) {
    const value = newObservation({
      url: "https://api.example/v1/chat/completions",
      durationMs: index + 1,
      outcome: "success",
      requestedModel: index === 2 ? "other" : "expected",
    });
    value.event_id = `event-${index}`;
    value.timestamp = new Date(Date.now() - index * 1000).toISOString();
    store.append(value);
  }
  const server = createDashboardServer({ storagePath: path });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address();
  const base = `http://127.0.0.1:${port}`;
  try {
    const summary = await (
      await fetch(`${base}/api/summary?requested_model=other`)
    ).json();
    assert.equal(summary.events, 1);
    assert.deepEqual(summary.scope.cohort, { requested_model: "other" });

    const first = await (await fetch(`${base}/api/events?limit=2`)).json();
    const second = await (
      await fetch(`${base}/api/events?limit=2&cursor=${encodeURIComponent(first.next_cursor)}`)
    ).json();
    assert.equal(first.events.length, 2);
    assert.equal(second.events.length, 1);
    assert.equal(second.next_cursor, null);
    assert.equal(
      new Set([...first.events, ...second.events].map((value) => value.event_id)).size,
      3,
    );
  } finally {
    await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  }
});
