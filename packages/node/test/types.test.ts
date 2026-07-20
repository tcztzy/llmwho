import {
  type ObservationV1,
  type ProbeReport,
  init,
  probe,
  summarize,
} from "../src/index.js";

const handle = init({
  storagePath: "/tmp/llmwho-events.ndjson",
  endpoint: (url: string) => url.includes("/private/llm"),
});

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
