import { performance } from "node:perf_hooks";
import { newObservation } from "./observation.js";
import { JSONLStore } from "./storage.js";
import { unhookedFetch } from "./hooks.js";
import { VERSION } from "./version.js";

function chatUrl(baseUrl) {
  if (!baseUrl || typeof baseUrl !== "string") throw new Error("baseUrl is required");
  const clean = baseUrl.replace(/\/+$/, "");
  const path = new URL(clean).pathname.replace(/\/+$/, "").toLowerCase();
  if (path.endsWith("/chat/completions")) return clean;
  if (path.endsWith("/v1")) return `${clean}/chat/completions`;
  return `${clean}/v1/chat/completions`;
}

function content(payload) {
  const value = payload?.choices?.[0]?.message?.content;
  return typeof value === "string" ? value : undefined;
}

const exact = (expected) => (value) => typeof value === "string" && value.trim() === expected;
const jsonContract = (value) => {
  if (typeof value !== "string") return false;
  try {
    const parsed = JSON.parse(value);
    return parsed && Object.keys(parsed).length === 1 && parsed.llmwho === 1;
  } catch {
    return false;
  }
};

export const SMOKE_CASES = [
  {
    id: "exact_instruction",
    check: "exact:LLMWHO_OK",
    prompt: "Reply with exactly LLMWHO_OK and no other characters.",
    score: exact("LLMWHO_OK"),
  },
  {
    id: "json_contract",
    check: 'json:{"llmwho":1}',
    prompt: 'Return exactly one JSON object: {"llmwho":1}. Do not use Markdown.',
    score: jsonContract,
  },
  {
    id: "invalid_premise",
    check: "exact:FALSE",
    prompt: "Is the statement 2 + 2 = 5 true? Reply with exactly FALSE.",
    score: exact("FALSE"),
  },
  {
    id: "arithmetic",
    check: "exact:323",
    prompt: "Compute 17 multiplied by 19. Reply with digits only.",
    score: exact("323"),
  },
];

function declarationRollup(events) {
  const statuses = {};
  const declaredModels = {};
  for (const event of events) {
    const declaration = event.model_declaration;
    const status = declaration?.status ?? "missing";
    statuses[status] = (statuses[status] ?? 0) + 1;
    if (declaration) {
      const declared = declaration.declared_model;
      declaredModels[declared] = (declaredModels[declared] ?? 0) + 1;
    }
  }
  return { statuses, declared_models: declaredModels };
}

export async function probe({
  baseUrl,
  model,
  apiKey,
  suite = "smoke",
  storagePath,
  timeoutMs = 30_000,
  fetchImpl,
}) {
  if (suite !== "smoke") {
    throw new Error(`only the smoke suite is available in LLMWho ${VERSION}`);
  }
  if (!model || typeof model !== "string") throw new Error("model is required");
  if (!(timeoutMs > 0)) throw new Error("timeoutMs must be positive");
  const url = chatUrl(baseUrl);
  const requestFetch = fetchImpl ?? unhookedFetch();
  if (typeof requestFetch !== "function") throw new Error("fetch is unavailable");
  const store = new JSONLStore(storagePath);
  const startedAt = new Date().toISOString();
  const cases = [];
  const events = [];

  for (const probeCase of SMOKE_CASES) {
    const body = JSON.stringify({
      model,
      temperature: 0,
      max_tokens: 32,
      messages: [
        {
          role: "system",
          content: "This is a deterministic API compatibility test. Follow the exact-output instruction.",
        },
        { role: "user", content: probeCase.prompt },
      ],
    });
    const headers = {
      "content-type": "application/json",
      "user-agent": `llmwho/${VERSION}`,
    };
    if (apiKey) headers.authorization = `Bearer ${apiKey}`;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const started = performance.now();
    let outcome = "network_error";
    let statusCode;
    let responsePayload;
    let outputBytes = 0;
    try {
      const response = await Reflect.apply(requestFetch, globalThis, [url, {
        method: "POST",
        headers,
        body,
        signal: controller.signal,
      }]);
      statusCode = response.status;
      const buffer = await response.arrayBuffer();
      outputBytes = buffer.byteLength;
      try {
        const parsed = JSON.parse(Buffer.from(buffer).toString("utf8"));
        responsePayload = parsed && typeof parsed === "object" && !Array.isArray(parsed)
          ? parsed
          : undefined;
      } catch {
        responsePayload = undefined;
      }
      outcome = response.ok || (response.status >= 300 && response.status < 400)
        ? "success"
        : "http_error";
    } catch (error) {
      outcome = error?.name === "AbortError" || String(error?.name).toLowerCase().includes("timeout")
        ? "timeout"
        : "network_error";
    } finally {
      clearTimeout(timer);
    }
    const durationMs = performance.now() - started;
    const passed = outcome === "success" && probeCase.score(content(responsePayload));
    const declaredModel = typeof responsePayload?.model === "string" ? responsePayload.model : undefined;
    const response = { output_bytes: outputBytes };
    if (statusCode !== undefined) response.status_code = statusCode;
    if (typeof responsePayload?.system_fingerprint === "string") {
      response.system_fingerprint = responsePayload.system_fingerprint;
    }
    const event = newObservation({
      url,
      durationMs,
      outcome,
      source: "probe",
      requestedModel: model,
      declaredModel,
      request: {
        operation: "chat.completions",
        requested_model: model,
        stream: false,
        input_bytes: Buffer.byteLength(body),
        role_count: 2,
        probe_case_id: probeCase.id,
      },
      response,
      probe: {
        case_id: probeCase.id,
        passed,
        score: passed ? 1 : 0,
        check: probeCase.check,
      },
      redactions: apiKey ? 1 : 0,
    });
    events.push(event);
    try {
      store.append(event);
    } catch {
      // The report remains usable if local telemetry storage fails.
    }
    cases.push({
      case_id: probeCase.id,
      passed,
      score: passed ? 1 : 0,
      outcome,
      status_code: statusCode ?? null,
      duration_ms: durationMs,
      model_declaration: event.model_declaration,
      identity: event.identity,
    });
  }

  return {
    schema_version: "2",
    suite: "smoke",
    model,
    endpoint: events[0].endpoint,
    started_at: startedAt,
    completed_at: new Date().toISOString(),
    completed: true,
    capability: {
      passed: cases.filter((item) => item.passed).length,
      total: cases.length,
      mean_score: cases.reduce((sum, item) => sum + item.score, 0) / cases.length,
    },
    declarations: declarationRollup(events),
    identity: { status: "unknown", candidates: [], evidence: [] },
    cases,
  };
}
