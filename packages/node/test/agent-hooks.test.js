import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

import {
  MAX_HOOK_INPUT_BYTES,
  observeHookEvent,
} from "../src/agent-hooks.js";
import { JSONLStore } from "../src/storage.js";

const testDirectory = dirname(fileURLToPath(import.meta.url));
const cliPath = join(testDirectory, "../src/cli.js");
const fixture = JSON.parse(readFileSync(
  join(testDirectory, "../../../shared/fixtures/agent-hooks.json"),
  "utf8",
));

function testRoot() {
  const path = join(tmpdir(), `llmwho-agent-hooks-${randomUUID()}`);
  mkdirSync(path, { recursive: true });
  return path;
}

function stateBlob(path) {
  if (!existsSync(path)) return "";
  let result = "";
  for (const entry of readdirSync(path, { withFileTypes: true })) {
    const child = join(path, entry.name);
    result += entry.name;
    result += entry.isDirectory() ? stateBlob(child) : readFileSync(child, "utf8");
  }
  return result;
}

function stateFiles(path) {
  if (!existsSync(path)) return [];
  const result = [];
  for (const entry of readdirSync(path, { withFileTypes: true })) {
    const child = join(path, entry.name);
    if (entry.isDirectory()) result.push(...stateFiles(child));
    else if (entry.name.endsWith(".json")) result.push(child);
  }
  return result;
}

function assertExpected(event, expected) {
  assert.equal(event.endpoint.provider, expected.provider);
  assert.equal(event.endpoint.host, expected.host);
  assert.equal(event.endpoint.path, expected.path);
  assert.equal(event.transport.outcome, expected.outcome);
  assert.equal(event.transport.duration_ms, expected.duration_ms);
  if (expected.error_type) assert.equal(event.transport.error_type, expected.error_type);
  else assert.equal("error_type" in event.transport, false);
  assert.equal(event.request.operation, "agent.turn");
  assert.equal(event.request.input_bytes, expected.input_bytes);
  assert.equal(event.request.requested_model, expected.model);
  if (expected.output_bytes !== undefined) {
    assert.equal(event.response.output_bytes, expected.output_bytes);
  } else {
    assert.equal("response" in event, false);
  }
  assert.equal(event.identity.status, "unknown");
  assert.deepEqual(event.identity.candidates, []);
  assert.deepEqual(event.identity.evidence, []);
  assert.deepEqual(event.privacy, { content_captured: false, redactions: 0 });
}

test("shared hook sequences normalize turns without persisting content", () => {
  for (const client of ["claude-code", "codex"]) {
    const root = testRoot();
    const store = new JSONLStore(join(root, "events.jsonl"));
    const expectedEvents = [];
    for (const step of fixture[client]) {
      const event = observeHookEvent(client, step.payload, {
        store,
        nowMs: step.now_ms,
      });
      if (step.expected) {
        assert.ok(event);
        assertExpected(event, step.expected);
        expectedEvents.push(step.expected);
      } else {
        assert.equal(event, undefined);
      }
      const state = stateBlob(join(root, ".hook-state"));
      for (const forbidden of fixture.forbidden) assert.equal(state.includes(forbidden), false);
    }
    const events = store.read();
    assert.equal(events.length, expectedEvents.length);
    const persisted = readFileSync(store.path, "utf8");
    for (const forbidden of fixture.forbidden) assert.equal(persisted.includes(forbidden), false);
    assert.deepEqual(stateFiles(join(root, ".hook-state")), []);
  }
});

function runCli(client, eventName, payload, storage, { disabled = false } = {}) {
  const environment = { ...process.env };
  delete environment.LLMWHO_DISABLED;
  if (disabled) environment.LLMWHO_DISABLED = "true";
  return spawnSync(process.execPath, [
    cliPath,
    "hook",
    client,
    "--event",
    eventName,
    "--storage",
    storage,
  ], {
    input: payload,
    encoding: "utf8",
    env: environment,
  });
}

test("hook CLI correlates processes and preserves Claude/Codex output protocols", () => {
  const root = testRoot();
  const claudeStorage = join(root, "claude.jsonl");
  const claudePayloads = [
    {
      session_id: "cross-process-session",
      hook_event_name: "SessionStart",
      model: "claude-sonnet-5",
    },
    {
      session_id: "cross-process-session",
      hook_event_name: "UserPromptSubmit",
      prompt: "do not persist this prompt",
    },
    {
      session_id: "cross-process-session",
      hook_event_name: "Stop",
      last_assistant_message: "do not persist this answer",
    },
  ];
  for (const payload of claudePayloads) {
    const result = runCli(
      "claude-code",
      payload.hook_event_name,
      JSON.stringify(payload),
      claudeStorage,
    );
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.stdout, "");
    assert.equal(result.stderr, "");
  }
  const claudeEvent = new JSONLStore(claudeStorage).read()[0];
  assert.equal(claudeEvent.endpoint.provider, "anthropic");
  assert.equal(claudeEvent.request.requested_model, "claude-sonnet-5");
  const claudePersisted = readFileSync(claudeStorage, "utf8");
  assert.equal(claudePersisted.includes("cross-process-session"), false);
  assert.equal(claudePersisted.includes("do not persist"), false);

  const codexStorage = join(root, "codex.jsonl");
  const codexPayloads = [
    {
      session_id: "codex-cross-process",
      turn_id: "turn-secret",
      hook_event_name: "UserPromptSubmit",
      model: "gpt-5.3-codex",
      prompt: "private codex prompt",
    },
    {
      session_id: "codex-cross-process",
      turn_id: "turn-secret",
      hook_event_name: "Stop",
      model: "gpt-5.3-codex",
      last_assistant_message: "private codex answer",
    },
  ];
  for (const payload of codexPayloads) {
    const result = runCli(
      "codex",
      payload.hook_event_name,
      JSON.stringify(payload),
      codexStorage,
    );
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.stdout, payload.hook_event_name === "Stop" ? "{}\n" : "");
  }
  const codexEvent = new JSONLStore(codexStorage).read()[0];
  assert.equal(codexEvent.endpoint.provider, "openai");
  assert.equal(readFileSync(codexStorage, "utf8").includes("private codex"), false);
});

test("hook CLI stays fail-open for malformed input, storage failure, and disable", () => {
  const root = testRoot();
  const malformedStorage = join(root, "malformed.jsonl");
  const malformed = runCli("codex", "Stop", "{not-json", malformedStorage);
  assert.equal(malformed.status, 0);
  assert.equal(malformed.stdout, "{}\n");
  assert.equal(malformed.stderr, "");
  assert.equal(existsSync(malformedStorage), false);

  const blocker = join(root, "blocker");
  writeFileSync(blocker, "file blocks child path", "utf8");
  const failure = runCli("codex", "Stop", JSON.stringify({
    session_id: "secret",
    hook_event_name: "Stop",
    model: "gpt-5.3-codex",
  }), join(blocker, "events.jsonl"));
  assert.equal(failure.status, 0);
  assert.equal(failure.stdout, "{}\n");
  assert.equal(failure.stderr, "");

  const disabledStorage = join(root, "disabled.jsonl");
  const disabled = runCli("codex", "Stop", JSON.stringify({
    session_id: "secret",
    hook_event_name: "Stop",
    model: "gpt-5.3-codex",
  }), disabledStorage, { disabled: true });
  assert.equal(disabled.status, 0);
  assert.equal(disabled.stdout, "{}\n");
  assert.equal(existsSync(disabledStorage), false);

  const oversizedStorage = join(root, "oversized.jsonl");
  const oversized = runCli(
    "codex",
    "Stop",
    "x".repeat(MAX_HOOK_INPUT_BYTES + 1),
    oversizedStorage,
  );
  assert.equal(oversized.status, 0);
  assert.equal(oversized.stdout, "{}\n");
  assert.equal(oversized.stderr, "");
  assert.equal(existsSync(oversizedStorage), false);
});

test("hook state rejects unsafe model values", () => {
  const root = testRoot();
  const store = new JSONLStore(join(root, "events.jsonl"));
  const event = observeHookEvent("claude-code", {
    session_id: "unsafe-model-session",
    hook_event_name: "UserPromptSubmit",
    model: "claude-safe\nprivate-metadata",
  }, {
    store,
    nowMs: 1,
  });
  assert.equal(event, undefined);
  const state = stateBlob(join(root, ".hook-state"));
  assert.equal(state.includes("claude-safe"), false);
  assert.equal(state.includes("private-metadata"), false);
});
