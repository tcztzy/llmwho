import {
  type ObservationV1,
  type ProbeReport,
  type OutputAffinityReport,
  init,
  outputAffinityMatrix,
  probe,
  summarize,
} from "../src/index.js";

const handle = init({
  storagePath: "/tmp/llmwho-events.ndjson",
  endpoint: (url: string) => url.includes("/private/llm"),
});

const affinity: OutputAffinityReport = outputAffinityMatrix(
  new Map([
    ["model-a", ["first answer"]],
    ["model-b", ["second answer"]],
  ]),
  { ngramSize: 3, modelWeight: 0.8 },
);

async function checkPublicTypes(events: ObservationV1[]): Promise<ProbeReport> {
  summarize(events);
  handle.shutdown();
  return probe({
    baseUrl: "http://127.0.0.1:8000/v1",
    model: "local-model",
    suite: "smoke",
  });
}

void checkPublicTypes;
void affinity;
