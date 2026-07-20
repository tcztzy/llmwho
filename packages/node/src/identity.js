const MODEL_HEADERS = ["x-model-id", "x-model-name", "x-model", "openai-model"];

export function inferIdentity(claimedModel, declaredModel, responseHeaders) {
  const evidence = [];
  let observed = declaredModel || undefined;
  let weight = 0;
  if (declaredModel) {
    weight = 0.98;
    evidence.push({
      kind: "response_model",
      source: "response.body.model",
      value: declaredModel,
      weight,
    });
  }
  if (!observed && responseHeaders) {
    const lowered = Object.fromEntries(
      Object.entries(responseHeaders).map(([key, value]) => [key.toLowerCase(), String(value)]),
    );
    for (const header of MODEL_HEADERS) {
      if (lowered[header]) {
        observed = lowered[header];
        weight = 0.85;
        evidence.push({
          kind: "response_model_header",
          source: `response.headers.${header}`,
          value: observed,
          weight,
        });
        break;
      }
    }
  }

  const status = observed && claimedModel
    ? observed === claimedModel ? "matched" : "mismatch"
    : "unknown";
  const result = {
    status,
    confidence: observed ? weight : 0,
    candidates: observed ? [{ label: observed, confidence: weight }] : [],
    evidence,
  };
  if (claimedModel) result.claimed_model = claimedModel;
  if (observed) result.observed_model = observed;
  return result;
}
