import { randomUUID } from "node:crypto";
import { inferIdentity } from "./identity.js";
import { assertContentFree, endpointFromUrl } from "./privacy.js";
import { VERSION } from "./version.js";

const OUTCOMES = new Set([
  "success",
  "http_error",
  "timeout",
  "network_error",
  "stream_error",
]);
const IDENTITY_STATUSES = new Set(["matched", "mismatch", "unknown"]);
const MODALITIES = new Set([
  "text",
  "image",
  "audio",
  "embedding",
  "multimodal",
  "unknown",
]);
const TOP_LEVEL_KEYS = new Set([
  "schema_version",
  "event_id",
  "timestamp",
  "source",
  "modality",
  "sdk",
  "endpoint",
  "transport",
  "identity",
  "privacy",
  "request",
  "response",
  "probe",
]);

function object(value, path, { allowed, required = [] }) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${path} must be an object`);
  }
  const keys = Object.keys(value);
  const missing = required.filter((key) => !Object.hasOwn(value, key));
  if (missing.length) throw new Error(`missing ${path} fields: ${missing.sort().join(", ")}`);
  const unknown = keys.filter((key) => !allowed.includes(key));
  if (unknown.length) throw new Error(`unknown ${path} fields: ${unknown.sort().join(", ")}`);
  return value;
}

function string(value, path, { nonempty = false } = {}) {
  if (typeof value !== "string" || (nonempty && !value)) {
    throw new Error(`${path} must be a${nonempty ? " non-empty" : ""} string`);
  }
  return value;
}

function number(value, path, { minimum, maximum } = {}) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${path} must be a finite number`);
  }
  if (minimum !== undefined && value < minimum) {
    throw new Error(`${path} must be at least ${minimum}`);
  }
  if (maximum !== undefined && value > maximum) {
    throw new Error(`${path} must be at most ${maximum}`);
  }
  return value;
}

function integer(value, path, { minimum, maximum } = {}) {
  if (!Number.isInteger(value)) throw new Error(`${path} must be an integer`);
  number(value, path, { minimum, maximum });
  return value;
}

function optionalString(value, key, path) {
  if (Object.hasOwn(value, key)) string(value[key], `${path}.${key}`);
}

function validateRequest(value) {
  const request = object(value, "request", {
    allowed: [
      "operation",
      "claimed_model",
      "stream",
      "input_bytes",
      "role_count",
      "probe_case_id",
    ],
  });
  for (const key of ["operation", "claimed_model", "probe_case_id"]) {
    optionalString(request, key, "request");
  }
  if (Object.hasOwn(request, "stream") && typeof request.stream !== "boolean") {
    throw new Error("request.stream must be a boolean");
  }
  for (const key of ["input_bytes", "role_count"]) {
    if (Object.hasOwn(request, key)) integer(request[key], `request.${key}`, { minimum: 0 });
  }
}

function validateResponse(value) {
  const response = object(value, "response", {
    allowed: [
      "declared_model",
      "system_fingerprint",
      "status_code",
      "output_bytes",
      "usage",
    ],
  });
  for (const key of ["declared_model", "system_fingerprint"]) {
    optionalString(response, key, "response");
  }
  if (Object.hasOwn(response, "status_code")) {
    integer(response.status_code, "response.status_code", { minimum: 100, maximum: 599 });
  }
  if (Object.hasOwn(response, "output_bytes")) {
    integer(response.output_bytes, "response.output_bytes", { minimum: 0 });
  }
  if (Object.hasOwn(response, "usage")) {
    const usage = object(response.usage, "response.usage", {
      allowed: ["input_tokens", "output_tokens", "total_tokens"],
    });
    for (const [key, child] of Object.entries(usage)) {
      integer(child, `response.usage.${key}`, { minimum: 0 });
    }
  }
}

function validateIdentity(value) {
  const identity = object(value, "identity", {
    allowed: [
      "status",
      "claimed_model",
      "observed_model",
      "confidence",
      "candidates",
      "evidence",
    ],
    required: ["status", "confidence", "candidates", "evidence"],
  });
  string(identity.status, "identity.status");
  if (!IDENTITY_STATUSES.has(identity.status)) throw new Error("invalid identity status");
  for (const key of ["claimed_model", "observed_model"]) {
    optionalString(identity, key, "identity");
  }
  number(identity.confidence, "identity.confidence", { minimum: 0, maximum: 1 });
  if (!Array.isArray(identity.candidates)) {
    throw new Error("identity.candidates must be an array");
  }
  identity.candidates.forEach((child, index) => {
    const candidate = object(child, `identity.candidates[${index}]`, {
      allowed: ["label", "confidence"],
      required: ["label", "confidence"],
    });
    string(candidate.label, `identity.candidates[${index}].label`);
    number(candidate.confidence, `identity.candidates[${index}].confidence`, {
      minimum: 0,
      maximum: 1,
    });
  });
  if (!Array.isArray(identity.evidence)) {
    throw new Error("identity.evidence must be an array");
  }
  identity.evidence.forEach((child, index) => {
    const evidence = object(child, `identity.evidence[${index}]`, {
      allowed: ["kind", "source", "value", "weight"],
      required: ["kind", "source", "weight"],
    });
    string(evidence.kind, `identity.evidence[${index}].kind`);
    string(evidence.source, `identity.evidence[${index}].source`);
    optionalString(evidence, "value", `identity.evidence[${index}]`);
    number(evidence.weight, `identity.evidence[${index}].weight`, {
      minimum: 0,
      maximum: 1,
    });
  });
}

export function newObservation({
  url,
  durationMs,
  outcome,
  errorType,
  source = "passive",
  modality = "text",
  provider,
  claimedModel,
  declaredModel,
  request,
  response,
  probe,
  redactions = 0,
}) {
  const event = {
    schema_version: "1",
    event_id: randomUUID(),
    timestamp: new Date().toISOString(),
    source,
    modality,
    sdk: { name: "llmwho-node", version: VERSION },
    endpoint: endpointFromUrl(url),
    transport: { outcome, duration_ms: Math.max(0, durationMs) },
    identity: inferIdentity(claimedModel, declaredModel),
    privacy: { content_captured: false, redactions: Math.max(0, redactions) },
  };
  if (provider) event.endpoint.provider = provider;
  if (errorType) event.transport.error_type = errorType;
  if (request) event.request = { ...request };
  if (response) event.response = { ...response };
  if (probe) event.probe = { ...probe };
  validateObservation(event);
  return event;
}

export function validateObservation(event) {
  assertContentFree(event);
  const root = object(event, "ObservationV1", {
    allowed: [...TOP_LEVEL_KEYS],
    required: [
      "schema_version",
      "event_id",
      "timestamp",
      "source",
      "modality",
      "sdk",
      "endpoint",
      "transport",
      "identity",
      "privacy",
    ],
  });
  if (event.schema_version !== "1") throw new Error("unsupported observation schema_version");
  string(root.event_id, "event_id", { nonempty: true });
  const timestamp = string(root.timestamp, "timestamp", { nonempty: true });
  if (!/(?:Z|[+-]\d{2}:\d{2})$/.test(timestamp) || Number.isNaN(Date.parse(timestamp))) {
    throw new Error("timestamp must be an ISO 8601 date-time with timezone");
  }
  string(root.source, "source");
  if (!["passive", "probe"].includes(root.source)) throw new Error("invalid observation source");
  string(root.modality, "modality");
  if (!MODALITIES.has(root.modality)) throw new Error("invalid observation modality");
  const sdk = object(root.sdk, "sdk", {
    allowed: ["name", "version"],
    required: ["name", "version"],
  });
  string(sdk.name, "sdk.name", { nonempty: true });
  string(sdk.version, "sdk.version", { nonempty: true });
  const endpoint = object(root.endpoint, "endpoint", {
    allowed: ["scheme", "host", "port", "path", "provider"],
    required: ["scheme", "host", "path"],
  });
  string(endpoint.scheme, "endpoint.scheme");
  if (!["http", "https", "unknown"].includes(endpoint.scheme)) {
    throw new Error("invalid endpoint scheme");
  }
  string(endpoint.host, "endpoint.host");
  string(endpoint.path, "endpoint.path");
  optionalString(endpoint, "provider", "endpoint");
  if (Object.hasOwn(endpoint, "port")) {
    integer(endpoint.port, "endpoint.port", { minimum: 1, maximum: 65535 });
  }
  const transport = object(root.transport, "transport", {
    allowed: ["outcome", "duration_ms", "ttft_ms", "error_type"],
    required: ["outcome", "duration_ms"],
  });
  string(transport.outcome, "transport.outcome");
  if (!OUTCOMES.has(transport.outcome)) throw new Error("invalid transport outcome");
  number(transport.duration_ms, "transport.duration_ms", { minimum: 0 });
  if (Object.hasOwn(transport, "ttft_ms")) {
    number(transport.ttft_ms, "transport.ttft_ms", { minimum: 0 });
  }
  optionalString(transport, "error_type", "transport");
  validateIdentity(root.identity);
  const privacy = object(root.privacy, "privacy", {
    allowed: ["content_captured", "redactions"],
    required: ["content_captured", "redactions"],
  });
  if (privacy.content_captured !== false) {
    throw new Error("privacy.content_captured must be false");
  }
  integer(privacy.redactions, "privacy.redactions", { minimum: 0 });
  if (Object.hasOwn(root, "request")) validateRequest(root.request);
  if (Object.hasOwn(root, "response")) validateResponse(root.response);
  if (Object.hasOwn(root, "probe")) {
    const probe = object(root.probe, "probe", {
      allowed: ["case_id", "passed", "score", "check"],
      required: ["case_id", "passed", "score"],
    });
    string(probe.case_id, "probe.case_id");
    if (typeof probe.passed !== "boolean") throw new Error("probe.passed must be a boolean");
    number(probe.score, "probe.score", { minimum: 0, maximum: 1 });
    optionalString(probe, "check", "probe");
  }
}
