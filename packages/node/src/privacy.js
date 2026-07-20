const SENSITIVE_HEADERS = new Set([
  "authorization",
  "proxy-authorization",
  "cookie",
  "set-cookie",
  "x-api-key",
  "api-key",
]);

const FORBIDDEN_PERSISTED_KEYS = new Set([
  "authorization",
  "api_key",
  "body",
  "content",
  "input",
  "messages",
  "output",
  "prompt",
  "request_body",
  "response_body",
  "response_text",
]);

export const REDACTED = "[REDACTED]";

export function endpointFromUrl(value) {
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    return { scheme: "unknown", host: "", path: "/" };
  }
  const endpoint = {
    scheme: ["http:", "https:"].includes(parsed.protocol)
      ? parsed.protocol.slice(0, -1)
      : "unknown",
    host: parsed.hostname,
    path: parsed.pathname || "/",
  };
  if (parsed.port) endpoint.port = Number(parsed.port);
  return endpoint;
}

export function redactHeaders(headers) {
  const result = {};
  let redactions = 0;
  for (const [key, value] of Object.entries(headers ?? {})) {
    if (SENSITIVE_HEADERS.has(key.toLowerCase())) {
      result[key] = REDACTED;
      redactions += 1;
    } else {
      result[key] = String(value);
    }
  }
  return [result, redactions];
}

export function redactText(value) {
  let redactions = 0;
  let cleaned = String(value);
  const opaquePatterns = [
    /\bBearer\s+[A-Za-z0-9._~+\-/]+=*/gi,
    /\bsk-[A-Za-z0-9_-]{8,}\b/g,
  ];
  for (const pattern of opaquePatterns) {
    cleaned = cleaned.replace(pattern, () => {
      redactions += 1;
      return REDACTED;
    });
  }
  cleaned = cleaned.replace(
    /(api[_-]?key|access[_-]?token|signature)=([^&\s]+)/gi,
    (_match, name) => {
      redactions += 1;
      return `${name}=${REDACTED}`;
    },
  );
  return [cleaned, redactions];
}

export function assertContentFree(value, path = "$") {
  if (Array.isArray(value)) {
    value.forEach((child, index) => assertContentFree(child, `${path}[${index}]`));
    return;
  }
  if (value && typeof value === "object") {
    for (const [key, child] of Object.entries(value)) {
      if (FORBIDDEN_PERSISTED_KEYS.has(key.toLowerCase())) {
        throw new Error(`raw content field is forbidden at ${path}.${key}`);
      }
      assertContentFree(child, `${path}.${key}`);
    }
  }
}
