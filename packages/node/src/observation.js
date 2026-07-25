import { randomUUID } from "node:crypto";
import { providerDeclaration, unknownIdentity } from "./identity.js";
import { assertContentFree, endpointFromUrl } from "./privacy.js";
import { VERSION } from "./version.js";

const OUTCOMES = new Set([
  "success",
  "http_error",
  "timeout",
  "network_error",
  "stream_error",
]);
const IDENTITY_STATUSES = new Set(["unknown", "inferred"]);
const DECLARATION_STATUSES = new Set(["matched", "mismatch", "unverified"]);
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
  "model_declaration",
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
      "requested_model",
      "stream",
      "input_bytes",
      "role_count",
      "probe_case_id",
    ],
  });
  for (const key of ["operation", "requested_model", "probe_case_id"]) {
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
      "system_fingerprint",
      "status_code",
      "output_bytes",
      "usage",
    ],
  });
  for (const key of ["system_fingerprint"]) {
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

function validateModelDeclaration(value) {
  const declaration = object(value, "model_declaration", {
    allowed: ["status", "declared_model", "evidence"],
    required: ["status", "declared_model", "evidence"],
  });
  string(declaration.status, "model_declaration.status");
  if (!DECLARATION_STATUSES.has(declaration.status)) {
    throw new Error("invalid model declaration status");
  }
  const declaredModel = string(
    declaration.declared_model,
    "model_declaration.declared_model",
    { nonempty: true },
  );
  if (!Array.isArray(declaration.evidence) || declaration.evidence.length !== 1) {
    throw new Error("model_declaration.evidence must contain one item");
  }
  const evidence = object(declaration.evidence[0], "model_declaration.evidence[0]", {
    allowed: ["kind", "source", "value"],
    required: ["kind", "source", "value"],
  });
  if (evidence.kind !== "provider_declaration") {
    throw new Error("invalid model declaration evidence kind");
  }
  if (evidence.source !== "response.body.model") {
    throw new Error("invalid model declaration evidence source");
  }
  if (evidence.value !== declaredModel) {
    throw new Error("model declaration evidence value must match declared_model");
  }
}

function validateIdentity(value) {
  const identity = object(value, "identity", {
    allowed: ["status", "candidates", "evidence"],
    required: ["status", "candidates", "evidence"],
  });
  string(identity.status, "identity.status");
  if (!IDENTITY_STATUSES.has(identity.status)) throw new Error("invalid identity status");
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
      allowed: ["kind", "source", "value", "detector_id", "detector_version"],
      required: ["kind", "source", "detector_id", "detector_version"],
    });
    string(evidence.kind, `identity.evidence[${index}].kind`);
    string(evidence.source, `identity.evidence[${index}].source`);
    optionalString(evidence, "value", `identity.evidence[${index}]`);
    string(evidence.detector_id, `identity.evidence[${index}].detector_id`, {
      nonempty: true,
    });
    string(evidence.detector_version, `identity.evidence[${index}].detector_version`, {
      nonempty: true,
    });
  });
  if (identity.status === "unknown" && (identity.candidates.length || identity.evidence.length)) {
    throw new Error("unknown identity must not contain candidates or evidence");
  }
  if (identity.status === "inferred" && (!identity.candidates.length || !identity.evidence.length)) {
    throw new Error("inferred identity needs candidates and detector evidence");
  }
}

export function newObservation({
  url,
  durationMs,
  outcome,
  errorType,
  source = "passive",
  modality = "text",
  provider,
  requestedModel,
  declaredModel,
  request,
  response,
  probe,
  redactions = 0,
}) {
  const event = {
    schema_version: "2",
    event_id: randomUUID(),
    timestamp: new Date().toISOString(),
    source,
    modality,
    sdk: { name: "llmwho-node", version: VERSION },
    endpoint: endpointFromUrl(url),
    transport: { outcome, duration_ms: Math.max(0, durationMs) },
    identity: unknownIdentity(),
    privacy: { content_captured: false, redactions: Math.max(0, redactions) },
  };
  if (provider) event.endpoint.provider = provider;
  if (errorType) event.transport.error_type = errorType;
  const requestMetadata = { ...(request ?? {}) };
  if (requestedModel) requestMetadata.requested_model = requestedModel;
  if (Object.keys(requestMetadata).length) event.request = requestMetadata;
  if (response) event.response = { ...response };
  const declaration = providerDeclaration(requestedModel, declaredModel);
  if (declaration) event.model_declaration = declaration;
  if (probe) event.probe = { ...probe };
  validateObservation(event);
  return event;
}

export function validateObservation(event) {
  assertContentFree(event);
  const root = object(event, "ObservationV2", {
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
  if (event.schema_version !== "2") throw new Error("unsupported observation schema_version");
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
  if (Object.hasOwn(root, "model_declaration")) {
    validateModelDeclaration(root.model_declaration);
  }
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
