export function quantile(values, probability) {
  if (!values.length) return null;
  if (!(probability >= 0 && probability <= 1)) {
    throw new Error("probability must be between 0 and 1");
  }
  const ordered = values.map(Number).sort((a, b) => a - b);
  const index = (ordered.length - 1) * probability;
  const lower = Math.floor(index);
  const upper = Math.min(lower + 1, ordered.length - 1);
  const fraction = index - lower;
  return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction;
}

function counts(values) {
  const result = {};
  for (const value of values) result[value] = (result[value] ?? 0) + 1;
  return Object.fromEntries(Object.entries(result).sort(([a], [b]) => a.localeCompare(b)));
}

export function summarize(events) {
  const rows = [...events];
  const outcomes = counts(rows.map((row) => row.transport.outcome));
  const statuses = counts(rows.map((row) => row.identity.status));
  const declarationStatuses = counts(
    rows.map((row) => row.model_declaration?.status ?? "missing"),
  );
  const declaredModels = counts(
    rows.map((row) => row.model_declaration?.declared_model).filter(Boolean),
  );
  const durations = rows.map((row) => Number(row.transport.duration_ms));
  const probeScores = rows.filter((row) => row.probe).map((row) => Number(row.probe.score));
  const outputSizes = rows
    .filter((row) => row.response && "output_bytes" in row.response)
    .map((row) => Number(row.response.output_bytes));
  return {
    events: rows.length,
    availability: {
      success_rate: rows.length ? (outcomes.success ?? 0) / rows.length : null,
      outcomes,
    },
    transport: {
      latency_ms: {
        p50: quantile(durations, 0.5),
        p95: quantile(durations, 0.95),
        p99: quantile(durations, 0.99),
      },
    },
    identity: { statuses },
    declarations: {
      statuses: declarationStatuses,
      declared_models: declaredModels,
    },
    behavior: {
      observed_responses: outputSizes.length,
      stream_requests: rows.filter((row) => row.request?.stream === true).length,
      output_bytes_p50: quantile(outputSizes, 0.5),
    },
    capability: {
      probe_count: probeScores.length,
      mean_score: probeScores.length
        ? probeScores.reduce((sum, value) => sum + value, 0) / probeScores.length
        : null,
    },
  };
}
