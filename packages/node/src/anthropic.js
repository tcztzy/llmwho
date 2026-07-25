export const ANTHROPIC_PROVIDER = "anthropic";
export const MESSAGES_OPERATION = "messages";

export function isAnthropicMessagesUrl(value) {
  try {
    const url = new URL(value);
    return url.hostname.toLowerCase() === "api.anthropic.com"
      && url.pathname.replace(/\/+$/, "") === "/v1/messages";
  } catch {
    return false;
  }
}

function token(value) {
  return Number.isInteger(value) && value >= 0 ? value : undefined;
}

export function anthropicRequestMetadata(payload, bytes) {
  const metadata = {
    operation: MESSAGES_OPERATION,
    input_bytes: Math.max(0, bytes),
  };
  let requestedModel;
  if (payload && typeof payload === "object") {
    if (typeof payload.model === "string") {
      requestedModel = payload.model;
      metadata.requested_model = requestedModel;
    }
    if (typeof payload.stream === "boolean") metadata.stream = payload.stream;
    if (Array.isArray(payload.messages)) metadata.role_count = payload.messages.length;
  }
  return [metadata, requestedModel];
}

export function anthropicResponseMetadata(payload, bytes, status) {
  const metadata = {
    status_code: status,
    output_bytes: Math.max(0, bytes),
  };
  let declaredModel;
  if (!payload || typeof payload !== "object") return [metadata, declaredModel];

  if (typeof payload.model === "string") {
    declaredModel = payload.model;
  }
  if (payload.usage && typeof payload.usage === "object") {
    const inputTokens = token(payload.usage.input_tokens);
    const outputTokens = token(payload.usage.output_tokens);
    const usage = {};
    if (inputTokens !== undefined) usage.input_tokens = inputTokens;
    if (outputTokens !== undefined) usage.output_tokens = outputTokens;
    if (inputTokens !== undefined && outputTokens !== undefined) {
      usage.total_tokens = inputTokens + outputTokens;
    }
    if (Object.keys(usage).length) metadata.usage = usage;
  }
  return [metadata, declaredModel];
}
