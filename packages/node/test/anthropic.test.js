import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";
import { test } from "node:test";

import {
  anthropicRequestMetadata,
  anthropicResponseMetadata,
  isAnthropicMessagesUrl,
} from "../src/anthropic.js";
import { init } from "../src/index.js";

const testDirectory = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(
  join(testDirectory, "../../../shared/fixtures/anthropic-messages.json"),
  "utf8",
));

function storagePath() {
  return join(tmpdir(), `llmwho-anthropic-${randomUUID()}.ndjson`);
}

async function settleTelemetry() {
  await new Promise((resolve) => setTimeout(resolve, 20));
}

test("shared fixture normalizes content-free Anthropic metadata", () => {
  assert.equal(isAnthropicMessagesUrl(fixture.url), true);
  assert.equal(isAnthropicMessagesUrl("https://api.example/v1/messages"), false);

  const [request, claimedModel] = anthropicRequestMetadata(
    fixture.request,
    fixture.request_size,
  );
  const [response, declaredModel] = anthropicResponseMetadata(
    fixture.response,
    fixture.response_size,
    fixture.status_code,
  );

  assert.deepEqual(request, fixture.expected_request);
  assert.deepEqual(response, fixture.expected_response);
  assert.equal(claimedModel, fixture.request.model);
  assert.equal(declaredModel, fixture.response.model);
  const serialized = JSON.stringify({ request, response });
  assert.equal(serialized.includes("fixture user content"), false);
  assert.equal(serialized.includes("fixture response content"), false);
});

test("malformed optional Anthropic metadata is omitted", () => {
  const [request, claimedModel] = anthropicRequestMetadata(
    { model: 7, stream: "yes", messages: {} },
    -1,
  );
  const [response, declaredModel] = anthropicResponseMetadata(
    { model: null, usage: { input_tokens: true, output_tokens: -2 } },
    -1,
    200,
  );
  assert.deepEqual(request, { operation: "messages", input_bytes: 0 });
  assert.equal(claimedModel, undefined);
  assert.deepEqual(response, { status_code: 200, output_bytes: 0 });
  assert.equal(declaredModel, undefined);
});

test("fetch hook normalizes direct Anthropic response without storing content", async () => {
  const original = globalThis.fetch;
  const providerResponse = new Response(JSON.stringify(fixture.response), {
    status: 200,
    headers: { "request-id": "req_fixture" },
  });
  globalThis.fetch = async () => providerResponse;
  const path = storagePath();
  const handle = init({ storagePath: path });
  try {
    const received = await fetch(`${fixture.url}?api_key=never-store`, {
      method: "POST",
      headers: {
        "x-api-key": "never-store",
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify(fixture.request),
    });
    assert.equal(received, providerResponse);
    await settleTelemetry();
    const persisted = readFileSync(path, "utf8");
    const event = JSON.parse(persisted);
    assert.equal(event.endpoint.provider, "anthropic");
    assert.equal(event.request.operation, "messages");
    assert.equal(event.request.role_count, 2);
    assert.equal(event.response.usage.total_tokens, 20);
    assert.deepEqual(event.privacy, { content_captured: false, redactions: 2 });
    assert.equal(persisted.includes("fixture user content"), false);
    assert.equal(persisted.includes("fixture response content"), false);
    assert.equal(persisted.includes("never-store"), false);
  } finally {
    handle.shutdown();
    globalThis.fetch = original;
  }
});

test("direct Anthropic stream response is never cloned or read", async () => {
  const original = globalThis.fetch;
  let cloneCalls = 0;
  const streamResponse = new Response("data: fixture stream content\n\n", { status: 200 });
  streamResponse.clone = () => {
    cloneCalls += 1;
    throw new Error("stream body must not be cloned");
  };
  globalThis.fetch = async () => streamResponse;
  const path = storagePath();
  const handle = init({ storagePath: path });
  try {
    const received = await fetch(fixture.url, {
      method: "POST",
      body: JSON.stringify({ ...fixture.request, stream: true }),
    });
    assert.equal(received, streamResponse);
    await settleTelemetry();
    const event = JSON.parse(readFileSync(path, "utf8"));
    assert.equal(cloneCalls, 0);
    assert.equal(event.endpoint.provider, "anthropic");
    assert.equal(event.request.stream, true);
    assert.equal(event.response.output_bytes, 0);
    assert.equal("declared_model" in event.response, false);
    assert.equal(event.transport.outcome, "success");
  } finally {
    handle.shutdown();
    globalThis.fetch = original;
  }
});

test("Anthropic event-stream media type is safe when request metadata is unavailable", async () => {
  const original = globalThis.fetch;
  let cloneCalls = 0;
  const streamResponse = new Response("data: fixture stream content\n\n", {
    status: 200,
    headers: { "content-type": "text/event-stream; charset=utf-8" },
  });
  streamResponse.clone = () => {
    cloneCalls += 1;
    throw new Error("event stream body must not be cloned");
  };
  globalThis.fetch = async () => streamResponse;
  const path = storagePath();
  const handle = init({ storagePath: path });
  try {
    const received = await fetch(fixture.url, {
      method: "POST",
      body: "not-json",
    });
    assert.equal(received, streamResponse);
    await settleTelemetry();
    const event = JSON.parse(readFileSync(path, "utf8"));
    assert.equal(cloneCalls, 0);
    assert.equal(event.endpoint.provider, "anthropic");
    assert.equal(event.request.operation, "messages");
    assert.equal(event.response.output_bytes, 0);
  } finally {
    handle.shutdown();
    globalThis.fetch = original;
  }
});
