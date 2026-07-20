import assert from "node:assert/strict";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { randomUUID } from "node:crypto";
import { test } from "node:test";

import { NDJSONStore, newObservation } from "../src/index.js";
import { createDashboardServer } from "../src/dashboard.js";

test("dashboard serves shared UI, layered summary, and events", async () => {
  const path = join(tmpdir(), `llmwho-dashboard-${randomUUID()}.ndjson`);
  const store = new NDJSONStore(path);
  store.append(newObservation({
    url: "https://api.example/v1/chat/completions",
    durationMs: 15,
    outcome: "success",
    claimedModel: "a",
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
    const events = await (await fetch(`${base}/api/events?limit=1`)).json();
    assert.equal(events.length, 1);
    assert.equal(events[0].identity.status, "matched");
    assert.equal((await fetch(`${base}/missing`)).status, 404);
  } finally {
    await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  }
});
