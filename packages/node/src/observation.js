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
  responseHeaders,
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
    identity: inferIdentity(claimedModel, declaredModel, responseHeaders),
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
  const required = [
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
  ];
  const missing = required.filter((key) => !(key in event));
  if (missing.length) throw new Error(`missing ObservationV1 fields: ${missing.sort().join(", ")}`);
  if (event.schema_version !== "1") throw new Error("unsupported observation schema_version");
  if (!["passive", "probe"].includes(event.source)) throw new Error("invalid observation source");
  if (!OUTCOMES.has(event.transport?.outcome)) throw new Error("invalid transport outcome");
  if (!(Number(event.transport?.duration_ms) >= 0)) throw new Error("duration_ms must be non-negative");
  if (!["matched", "mismatch", "unknown"].includes(event.identity?.status)) {
    throw new Error("invalid identity status");
  }
  if (!(Number(event.identity?.confidence) >= 0 && Number(event.identity?.confidence) <= 1)) {
    throw new Error("identity confidence must be between 0 and 1");
  }
  if (event.privacy?.content_captured !== false || !Number.isInteger(event.privacy?.redactions)) {
    throw new Error("privacy must declare content_captured=false and redactions");
  }
}
