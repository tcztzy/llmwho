export function inferIdentity(claimedModel, declaredModel) {
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
