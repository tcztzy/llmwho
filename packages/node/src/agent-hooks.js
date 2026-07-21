import { createHash } from "node:crypto";
import {
  mkdirSync,
  readFileSync,
  readSync,
  renameSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { dirname, join } from "node:path";

import { newObservation } from "./observation.js";
import { NDJSONStore } from "./storage.js";

export const MAX_HOOK_INPUT_BYTES = 8 * 1024 * 1024;
const CLIENTS = {
  "claude-code": { provider: "anthropic", keepModel: true },
  codex: { provider: "openai", keepModel: false },
};
const MODEL = /^[A-Za-z0-9][A-Za-z0-9._:/+\-]{0,255}$/;
const FAILURE_TYPES = new Set([
  "rate_limit",
  "overloaded",
  "authentication_failed",
  "oauth_org_not_allowed",
  "billing_error",
  "invalid_request",
  "model_not_found",
  "server_error",
  "max_output_tokens",
  "timeout",
  "unknown",
]);

function enabled() {
  return !["1", "true", "yes", "on"].includes(
    String(process.env.LLMWHO_DISABLED ?? "").trim().toLowerCase(),
  );
}

function safeModel(value) {
  return typeof value === "string" && MODEL.test(value) ? value : undefined;
}

function statePath(store, client, sessionId) {
  if (typeof sessionId !== "string" || !sessionId) return undefined;
  const digest = createHash("sha256").update(sessionId, "utf8").digest("hex");
  return join(dirname(store.path), ".hook-state", client, `${digest}.json`);
}

function readState(path) {
  if (!path) return {};
  let value;
  try {
    value = JSON.parse(readFileSync(path, "utf8"));
  } catch {
    return {};
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const state = {};
  const model = safeModel(value.model);
  if (model) state.model = model;
  if (Number.isFinite(value.started_at_ms) && value.started_at_ms >= 0) {
    state.started_at_ms = value.started_at_ms;
  }
  if (
    Number.isSafeInteger(value.input_bytes)
    && value.input_bytes >= 0
    && value.input_bytes <= MAX_HOOK_INPUT_BYTES
  ) {
    state.input_bytes = value.input_bytes;
  }
  return state;
}

function deleteState(path) {
  if (!path) return;
  try {
    unlinkSync(path);
  } catch (error) {
    if (error.code !== "ENOENT") return;
  }
}

function writeState(path, state) {
  if (!path) return;
  const safe = {};
  const model = safeModel(state.model);
  if (model) safe.model = model;
  if (Number.isFinite(state.started_at_ms) && state.started_at_ms >= 0) {
    safe.started_at_ms = state.started_at_ms;
  }
  if (
    Number.isSafeInteger(state.input_bytes)
    && state.input_bytes >= 0
    && state.input_bytes <= MAX_HOOK_INPUT_BYTES
  ) {
    safe.input_bytes = state.input_bytes;
  }
  if (!Object.keys(safe).length) {
    deleteState(path);
    return;
  }
  mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
  const temporary = `${path}.${process.pid}.tmp`;
  writeFileSync(temporary, JSON.stringify(safe), { encoding: "utf8", mode: 0o600 });
  renameSync(temporary, path);
}

function durationMs(state, nowMs) {
  return Number.isFinite(state.started_at_ms)
    ? Math.max(0, nowMs - state.started_at_ms)
    : 0;
}

function failureType(value) {
  return typeof value === "string" && FAILURE_TYPES.has(value) ? value : "unknown";
}

export function observeHookEvent(client, payload, {
  store,
  expectedEvent,
  nowMs = Date.now(),
}) {
  const config = CLIENTS[client];
  if (!config) throw new Error("unsupported hook client");
  const eventName = payload?.hook_event_name;
  if (typeof eventName !== "string") return undefined;
  if (expectedEvent && eventName !== expectedEvent) return undefined;

  const currentMs = Math.max(0, nowMs);
  const path = statePath(store, client, payload.session_id);
  const state = readState(path);
  const model = safeModel(payload.model);
  if (model) state.model = model;

  if (eventName === "SessionStart") {
    writeState(path, state);
    return undefined;
  }
  if (eventName === "UserPromptSubmit") {
    state.started_at_ms = currentMs;
    if (typeof payload.prompt === "string") {
      state.input_bytes = Buffer.byteLength(payload.prompt);
    } else {
      delete state.input_bytes;
    }
    writeState(path, state);
    return undefined;
  }
  if (eventName === "SessionEnd") {
    deleteState(path);
    return undefined;
  }
  if (!["Stop", "StopFailure"].includes(eventName)) return undefined;

  const claimedModel = model ?? safeModel(state.model);
  const request = { operation: "agent.turn" };
  if (Number.isSafeInteger(state.input_bytes)) request.input_bytes = state.input_bytes;
  if (claimedModel) request.claimed_model = claimedModel;

  let response;
  let outcome = "success";
  let errorType;
  if (eventName === "Stop") {
    if (typeof payload.last_assistant_message === "string") {
      response = { output_bytes: Buffer.byteLength(payload.last_assistant_message) };
    }
  } else {
    errorType = failureType(payload.error);
    outcome = errorType === "timeout" ? "timeout" : "http_error";
  }

  const event = newObservation({
    url: `hook://${client}/${eventName.toLowerCase()}`,
    durationMs: durationMs(state, currentMs),
    outcome,
    errorType,
    provider: config.provider,
    claimedModel,
    request,
    response,
  });
  store.append(event);

  delete state.started_at_ms;
  delete state.input_bytes;
  if (config.keepModel) writeState(path, state);
  else deleteState(path);
  return event;
}

function readStdin() {
  const chunks = [];
  const buffer = Buffer.allocUnsafe(64 * 1024);
  let total = 0;
  let tooLarge = false;
  while (true) {
    const size = readSync(0, buffer, 0, buffer.length, null);
    if (size === 0) break;
    total += size;
    if (total > MAX_HOOK_INPUT_BYTES) {
      tooLarge = true;
      continue;
    }
    chunks.push(Buffer.from(buffer.subarray(0, size)));
  }
  return tooLarge ? undefined : Buffer.concat(chunks);
}

function writeProtocolOutput(client, eventName) {
  if (client === "codex" && ["Stop", "SubagentStop"].includes(eventName)) {
    process.stdout.write("{}\n");
  }
}

export function runHookCli({ client, expectedEvent, storagePath }) {
  let actualEvent;
  try {
    const raw = readStdin();
    if (raw) {
      const payload = JSON.parse(raw.toString("utf8"));
      if (payload && typeof payload === "object" && !Array.isArray(payload)) {
        actualEvent = payload.hook_event_name;
        if (enabled()) {
          observeHookEvent(client, payload, {
            store: new NDJSONStore(storagePath ?? process.env.LLMWHO_STORAGE),
            expectedEvent,
          });
        }
      }
    }
  } catch {
    // Hooks must remain fail-open and must never replace agent control flow.
  }
  writeProtocolOutput(client, expectedEvent ?? actualEvent);
  return 0;
}
