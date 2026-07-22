import { JSONLStore } from "./storage.js";
import { summarize } from "./summary.js";
import { VERSION } from "./version.js";
import { ScienceRuntimeManager } from "./science-runtime.js";
import { realpathSync } from "node:fs";
import { fileURLToPath } from "node:url";

function option(args, name, fallback) {
  const index = args.indexOf(name);
  return index === -1 ? fallback : args[index + 1];
}

function options(args, name) {
  const values = [];
  for (let index = 0; index < args.length; index += 1) {
    if (args[index] === name && args[index + 1] !== undefined
        && !args[index + 1].startsWith("--")) values.push(args[index + 1]);
  }
  return values;
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

export async function main(argv = process.argv.slice(2), dependencies = {}) {
  if (argv.includes("--version")) {
    process.stdout.write(`llmwho ${VERSION}\n`);
    return 0;
  }
  const [command] = argv;
  if (command === "summary") {
    const store = new JSONLStore(option(argv, "--storage", undefined));
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
  if (command === "hook") {
    const client = argv[1];
    if (!["claude-code", "codex"].includes(client)) {
      process.stderr.write("usage: llmwho hook claude-code|codex [options]\n");
      return 2;
    }
    const { runHookCli } = await import("./agent-hooks.js");
    return runHookCli({
      client,
      expectedEvent: option(argv, "--event", undefined),
      storagePath: option(argv, "--storage", undefined),
    });
  }
  if (command === "science") {
    const action = argv[1];
    if (!["status", "setup", "plugins"].includes(action)) {
      process.stderr.write("usage: llmwho science status|setup|plugins [options]\n");
      return 2;
    }
    const runtime = (dependencies.createScienceRuntime ?? ((config) => new ScienceRuntimeManager(config)))({
      uvPath: option(argv, "--uv", undefined),
      cacheDir: option(argv, "--cache-dir", undefined),
      pythonVersion: option(argv, "--python", undefined),
      offline: argv.includes("--offline"),
      pluginPackages: options(argv, "--plugin"),
      onProgress: ({ text }) => process.stderr.write(text),
    });
    try {
      const report = action === "status"
        ? await runtime.status()
        : action === "setup"
          ? await runtime.setup()
          : await runtime.plugins();
      process.stdout.write(`${JSON.stringify(report)}\n`);
      return action === "status" && !report.uv_found && !report.environment_ready ? 1 : 0;
    } finally {
      await runtime.shutdown();
    }
  }
  process.stderr.write("usage: llmwho summary|dashboard|probe|hook|science [options]\n");
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
  try {
    process.exitCode = await main();
  } catch (error) {
    process.stderr.write(`llmwho: ${error.code ?? "ERROR"}: ${error.message}\n`);
    process.exitCode = 1;
  }
}
