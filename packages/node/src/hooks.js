import { performance } from "node:perf_hooks";
import {
  ANTHROPIC_PROVIDER,
  anthropicRequestMetadata,
  anthropicResponseMetadata,
  isAnthropicMessagesUrl,
} from "./anthropic.js";
import { newObservation } from "./observation.js";
import { JSONLStore } from "./storage.js";

const KNOWN_LLM_PATH = /(?:\/chat\/completions|\/completions|\/responses|\/messages|\/api\/chat|\/api\/generate|:generatecontent|:streamgeneratecontent)(?:\/|$)/i;
const SECRET_QUERY_KEYS = new Set([
  "api_key",
  "apikey",
  "key",
  "token",
  "access_token",
  "signature",
  "sig",
]);
const SECRET_HEADERS = new Set([
  "authorization",
  "proxy-authorization",
  "cookie",
  "set-cookie",
  "x-api-key",
  "api-key",
]);

let activeHandle;

export function unhookedFetch() {
  return activeHandle?.active ? activeHandle.originalFetch : globalThis.fetch;
}

function enabled() {
  return !["1", "true", "yes", "on"].includes(
    String(process.env.LLMWHO_DISABLED ?? "").trim().toLowerCase(),
  );
}

export function isLlmUrl(value, endpoint) {
  if (typeof endpoint === "function") {
    try {
      return Boolean(endpoint(value));
    } catch {
      return false;
    }
  }
  if (typeof endpoint === "string" && endpoint) return value.startsWith(endpoint);
  try {
    return KNOWN_LLM_PATH.test(new URL(value).pathname);
  } catch {
    return false;
  }
}

function requestUrl(input) {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  if (input && typeof input.url === "string") return input.url;
  return String(input);
}

function headersObject(input, init) {
  const result = {};
  try {
    const headers = new Headers(input instanceof Request ? input.headers : undefined);
    const overrides = new Headers(init?.headers);
    overrides.forEach((value, key) => headers.set(key, value));
    headers.forEach((value, key) => { result[key] = value; });
  } catch {
    // Exotic header implementations should not affect the request.
  }
  return result;
}

function redactionCount(url, headers) {
  let count = Object.keys(headers).filter((key) => SECRET_HEADERS.has(key.toLowerCase())).length;
  try {
    for (const key of new URL(url).searchParams.keys()) {
      if (SECRET_QUERY_KEYS.has(key.toLowerCase())) count += 1;
    }
  } catch {
    // The URL matcher already rejected malformed URLs in the normal path.
  }
  return count;
}

function jsonBody(value) {
  if (typeof value === "string") {
    const bytes = Buffer.byteLength(value);
    try {
      const parsed = JSON.parse(value);
      return [parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : undefined, bytes];
    } catch {
      return [undefined, bytes];
    }
  }
  if (value instanceof Uint8Array) {
    const bytes = value.byteLength;
    try {
      const parsed = JSON.parse(Buffer.from(value).toString("utf8"));
      return [parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : undefined, bytes];
    } catch {
      return [undefined, bytes];
    }
  }
  return [undefined, 0];
}

function operation(path) {
  const value = path.toLowerCase();
  if (value.includes("/chat/completions")) return "chat.completions";
  if (value.includes("/responses")) return "responses";
  if (value.includes("/messages")) return "messages";
  if (value.includes("generatecontent")) return "generateContent";
  if (value.includes("/api/chat")) return "chat";
  if (value.includes("/api/generate")) return "generate";
  return "completions";
}

function requestMetadata(url, payload, bytes) {
  if (isAnthropicMessagesUrl(url)) {
    const [metadata, claimedModel] = anthropicRequestMetadata(payload, bytes);
    return [metadata, claimedModel, ANTHROPIC_PROVIDER];
  }
  const result = { operation: operation(new URL(url).pathname), input_bytes: bytes };
  let claimedModel;
  if (payload) {
    if (typeof payload.model === "string") {
      claimedModel = payload.model;
      result.claimed_model = claimedModel;
    }
    if (typeof payload.stream === "boolean") result.stream = payload.stream;
    if (Array.isArray(payload.messages)) result.role_count = payload.messages.length;
  }
  return [result, claimedModel, undefined];
}

function responseMetadata(payload, bytes, status, provider) {
  if (provider === ANTHROPIC_PROVIDER) {
    return anthropicResponseMetadata(payload, bytes, status);
  }
  const result = { status_code: status, output_bytes: bytes };
  let declaredModel;
  if (payload) {
    if (typeof payload.model === "string") {
      declaredModel = payload.model;
      result.declared_model = declaredModel;
    }
    if (typeof payload.system_fingerprint === "string") {
      result.system_fingerprint = payload.system_fingerprint;
    }
    if (payload.usage && typeof payload.usage === "object") {
      const usage = {};
      const aliases = {
        input_tokens: ["input_tokens", "prompt_tokens"],
        output_tokens: ["output_tokens", "completion_tokens"],
        total_tokens: ["total_tokens"],
      };
      for (const [target, candidates] of Object.entries(aliases)) {
        for (const candidate of candidates) {
          const value = payload.usage[candidate];
          if (Number.isInteger(value) && value >= 0) {
            usage[target] = value;
            break;
          }
        }
      }
      if (Object.keys(usage).length) result.usage = usage;
    }
  }
  return [result, declaredModel];
}

function observe(handle, fields) {
  try {
    handle.store.append(newObservation(fields));
  } catch {
    // Instrumentation is strictly fail-open for the host application.
  }
}

function isStreamingResponse(context, response) {
  if (context.request.stream === true) return true;
  try {
    return response.headers.get("content-type")
      ?.split(";", 1)[0]
      .trim()
      .toLowerCase() === "text/event-stream";
  } catch {
    return false;
  }
}

function recordResponse(handle, context, response) {
  const common = {
    url: context.url,
    durationMs: performance.now() - context.started,
    outcome: response.ok || (response.status >= 300 && response.status < 400)
      ? "success"
      : "http_error",
    claimedModel: context.claimedModel,
    provider: context.provider,
    request: context.request,
    redactions: context.redactions,
  };
  if (isStreamingResponse(context, response)) {
    const [metadata, declaredModel] = responseMetadata(
      undefined,
      0,
      response.status,
      context.provider,
    );
    observe(handle, { ...common, declaredModel, response: metadata });
    return;
  }
  try {
    response.clone().arrayBuffer().then((buffer) => {
      const [payload] = jsonBody(new Uint8Array(buffer));
      const [metadata, declaredModel] = responseMetadata(
        payload,
        buffer.byteLength,
        response.status,
        context.provider,
      );
      observe(handle, { ...common, declaredModel, response: metadata });
    }).catch(() => {
      const [metadata] = responseMetadata(undefined, 0, response.status, context.provider);
      observe(handle, { ...common, response: metadata });
    });
  } catch {
    const [metadata] = responseMetadata(undefined, 0, response.status, context.provider);
    observe(handle, { ...common, response: metadata });
  }
}

export class HookHandle {
  constructor({ store, endpoint, originalFetch, wrapper, active }) {
    this.store = store;
    this.endpoint = endpoint;
    this.originalFetch = originalFetch;
    this.wrapper = wrapper;
    this.active = active;
    this.captureContent = false;
  }

  shutdown() {
    if (!this.active) return;
    if (globalThis.fetch === this.wrapper) globalThis.fetch = this.originalFetch;
    this.active = false;
    if (activeHandle === this) activeHandle = undefined;
  }
}

export function init(options = {}) {
  if (activeHandle?.active) return activeHandle;
  const store = new JSONLStore(options.storagePath ?? process.env.LLMWHO_STORAGE);
  const originalFetch = globalThis.fetch;
  const handle = new HookHandle({
    store,
    endpoint: options.endpoint,
    originalFetch,
    wrapper: undefined,
    active: enabled() && typeof originalFetch === "function",
  });
  activeHandle = handle;
  if (!handle.active) return handle;

  async function llmwhoFetch(input, requestInit) {
    const url = requestUrl(input);
    if (!handle.active || !isLlmUrl(url, handle.endpoint)) {
      return Reflect.apply(originalFetch, this, [input, requestInit]);
    }
    const started = performance.now();
    const headers = headersObject(input, requestInit);
    const [payload, bytes] = jsonBody(requestInit?.body);
    let request;
    let claimedModel;
    let provider;
    try {
      [request, claimedModel, provider] = requestMetadata(url, payload, bytes);
    } catch {
      request = { operation: "unknown", input_bytes: bytes };
    }
    const redactions = redactionCount(url, headers);
    let response;
    try {
      response = await Reflect.apply(originalFetch, this, [input, requestInit]);
    } catch (error) {
      observe(handle, {
        url,
        durationMs: performance.now() - started,
        outcome: String(error?.name ?? "").toLowerCase().includes("timeout")
          ? "timeout"
          : "network_error",
        provider,
        claimedModel,
        request,
        redactions,
      });
      throw error;
    }
    try {
      recordResponse(
        handle,
        { url, started, request, claimedModel, provider, redactions },
        response,
      );
    } catch {
      // Response telemetry must never replace a successful application result.
    }
    return response;
  }

  handle.wrapper = llmwhoFetch;
  globalThis.fetch = llmwhoFetch;
  return handle;
}
