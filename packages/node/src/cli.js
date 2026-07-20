import { NDJSONStore } from "./storage.js";
import { summarize } from "./summary.js";
import { VERSION } from "./version.js";
import { realpathSync } from "node:fs";
import { fileURLToPath } from "node:url";

function option(args, name, fallback) {
  const index = args.indexOf(name);
  return index === -1 ? fallback : args[index + 1];
}

function printSummary(report, json) {
  if (json) {
    process.stdout.write(`${JSON.stringify(report)}\n`);
    return;
  }
  const success = report.availability.success_rate;
  const latency = report.transport.latency_ms;
  process.stdout.write(`events: ${report.events}\n`);
  process.stdout.write(`availability: ${success === null ? "n/a" : `${(success * 100).toFixed(1)}%`}\n`);
  process.stdout.write(`latency p50/p95/p99 ms: ${latency.p50} / ${latency.p95} / ${latency.p99}\n`);
  process.stdout.write(`identity: ${JSON.stringify(report.identity.statuses)}\n`);
  process.stdout.write(`capability probes: ${report.capability.probe_count}\n`);
}

export async function main(argv = process.argv.slice(2)) {
  if (argv.includes("--version")) {
    process.stdout.write(`llmwho ${VERSION}\n`);
    return 0;
  }
  const [command] = argv;
  if (command === "summary") {
    const store = new NDJSONStore(option(argv, "--storage", undefined));
    printSummary(summarize(store.read()), argv.includes("--json"));
    return 0;
  }
  if (command === "dashboard") {
    const { serveDashboard } = await import("./dashboard.js");
    await serveDashboard({
      storagePath: option(argv, "--storage", undefined),
      host: option(argv, "--host", "127.0.0.1"),
      port: Number(option(argv, "--port", "7734")),
    });
    return 0;
  }
  if (command === "probe") {
    const { probe } = await import("./probe.js");
    const keyName = option(argv, "--api-key-env", "OPENAI_API_KEY");
    const report = await probe({
      baseUrl: option(argv, "--base-url", undefined),
      model: option(argv, "--model", undefined),
      apiKey: process.env[keyName],
      suite: option(argv, "--suite", "smoke"),
      storagePath: option(argv, "--storage", undefined),
    });
    process.stdout.write(`${JSON.stringify(report)}\n`);
    return report.completed ? 0 : 1;
  }
  process.stderr.write("usage: llmwho summary|dashboard|probe [options]\n");
  return 2;
}

let isMain = false;
try {
  isMain = Boolean(process.argv[1])
    && realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url));
} catch {
  isMain = false;
}
if (isMain) {
  process.exitCode = await main();
}
