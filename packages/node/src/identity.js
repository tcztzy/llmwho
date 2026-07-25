export function providerDeclaration(requestedModel, declaredModel) {
  if (!declaredModel) return undefined;
  const status = requestedModel
    ? declaredModel === requestedModel ? "matched" : "mismatch"
    : "unverified";
  return {
    status,
    declared_model: declaredModel,
    evidence: [{
      kind: "provider_declaration",
      source: "response.body.model",
      value: declaredModel,
    }],
  };
}

export function unknownIdentity() {
  return { status: "unknown", candidates: [], evidence: [] };
}
