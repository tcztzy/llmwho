import {
  type ObservationV2,
  type ProbeReport,
  type AnalysisReport,
  type OutputAffinityReport,
  RemoteStore,
  ScienceRuntimeManager,
  init,
  probe,
  science,
  summarize,
} from "../src/index.js";

const handle = init({
  storagePath: "/tmp/llmwho-events.jsonl",
  endpoint: (url: string) => url.includes("/private/llm"),
  collectorUrl: "http://127.0.0.1:7734",
  collectorToken: "token",
  collectorProtocol: "otlp",
});
const remote = new RemoteStore("http://127.0.0.1:7734", {
  protocol: "native",
  maxQueue: 10,
});
const remoteEvents: Promise<ObservationV2[]> = remote.read(10);

const affinity: Promise<AnalysisReport<OutputAffinityReport>> = science.outputAffinityMatrix(
  new Map([
    ["model-a", ["first answer"]],
    ["model-b", ["second answer"]],
  ]),
  { ngramSize: 3, modelWeight: 0.8 },
);
const customScience = new ScienceRuntimeManager({
  uvPath: "/opt/bin/uv",
  pythonVersion: "3.12",
  offline: true,
  pluginPackages: ["llmwho-example==1.2.3"],
});

async function checkPublicTypes(events: ObservationV2[]): Promise<ProbeReport> {
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
void customScience;
void remoteEvents;
