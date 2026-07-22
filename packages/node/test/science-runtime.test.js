import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { access, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import * as llmwho from "../src/index.js";

const { ScienceRuntimeManager, init, science } = llmwho;


const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const ENGINE = join(ROOT, "packages", "python");
const UV_AVAILABLE = spawnSync("uv", ["--version"], { encoding: "utf8" }).status === 0;
const RUN_UV_INTEGRATION = process.env.LLMWHO_RUN_UV_INTEGRATION === "1" && UV_AVAILABLE;

async function missing(path) {
  try {
    await access(path);
    return false;
  } catch {
    return true;
  }
}

test("import, manager construction, and init do not discover uv or create science state", async () => {
  const cacheDir = join(tmpdir(), `llmwho-science-passive-${process.pid}-${Date.now()}`);
  let commands = 0;
  const manager = new ScienceRuntimeManager({
    cacheDir,
    engineProjectDir: ENGINE,
    commandRunner: async () => {
      commands += 1;
      throw new Error("must not run");
    },
  });
  const handle = init();
  try {
    assert.equal(commands, 0);
    assert.equal(await missing(cacheDir), true);
    assert.ok(science instanceof ScienceRuntimeManager);
    assert.ok(manager instanceof ScienceRuntimeManager);
    assert.equal("outputAffinityMatrix" in llmwho, false);
  } finally {
    handle.shutdown();
  }
});

test("setup uses a frozen uv environment keyed by plugins and serializes concurrent calls", async () => {
  const cacheDir = join(tmpdir(), `llmwho-science-fake-${process.pid}-${Date.now()}`);
  const commands = [];
  const commandRunner = async (command, args, options) => {
    commands.push({ command, args, environment: options.env });
    if (args[0] === "--version") return { stdout: "uv 0.11.30\n", stderr: "" };
    if (args[0] === "sync") {
      const pythonPath = process.platform === "win32"
        ? join(options.env.UV_PROJECT_ENVIRONMENT, "Scripts", "python.exe")
        : join(options.env.UV_PROJECT_ENVIRONMENT, "bin", "python");
      await mkdir(dirname(pythonPath), { recursive: true });
      await writeFile(pythonPath, "test runtime", "utf8");
    }
    return { stdout: "", stderr: "" };
  };
  const manager = new ScienceRuntimeManager({
    uvPath: "/test/uv",
    cacheDir,
    engineProjectDir: ENGINE,
    pluginPackages: ["llmwho-example==1.2.3"],
    commandRunner,
  });
  const concurrentManager = new ScienceRuntimeManager({
    uvPath: "/test/uv",
    cacheDir,
    engineProjectDir: ENGINE,
    pluginPackages: ["llmwho-example==1.2.3"],
    commandRunner,
  });
  try {
    const [first, second] = await Promise.all([
      manager.setup(),
      concurrentManager.setup(),
    ]);
    assert.equal(first.environment_ready, true);
    assert.equal(second.environment_hash, first.environment_hash);
    assert.deepEqual(first.plugin_packages, ["llmwho-example==1.2.3"]);
    const syncCalls = commands.filter(({ args }) => args[0] === "sync");
    assert.equal(syncCalls.length, 1);
    assert.ok(syncCalls[0].args.includes("--frozen"));
    assert.ok(syncCalls[0].args.includes("--no-dev"));
    assert.ok(syncCalls[0].args.includes("--no-editable"));
    assert.ok(syncCalls[0].args.includes("--no-install-project"));
    assert.deepEqual(syncCalls[0].args.slice(-2), ["--python", "3.12"]);
    assert.ok(syncCalls[0].environment.UV_PROJECT_ENVIRONMENT.startsWith(cacheDir));
    const engineInstall = commands.find(({ args }) => args[0] === "pip" && args.includes(ENGINE));
    assert.ok(engineInstall);
    const pluginCall = commands.find(({ args }) => (
      args[0] === "pip" && args.includes("llmwho-example==1.2.3")
    ));
    assert.ok(pluginCall.args.includes("llmwho-example==1.2.3"));
    manager._runCommand = async () => {
      const error = new Error("uv removed");
      error.code = "ENOENT";
      throw error;
    };
    const readyWithoutUv = await manager.setup();
    assert.equal(readyWithoutUv.environment_ready, true);
    assert.equal(readyWithoutUv.uv_found, false);
  } finally {
    await rm(cacheDir, { recursive: true, force: true });
  }
});

test("status reports missing uv without mutating the cache", async () => {
  const cacheDir = join(tmpdir(), `llmwho-science-missing-${process.pid}-${Date.now()}`);
  const manager = new ScienceRuntimeManager({
    uvPath: "/missing/uv",
    cacheDir,
    engineProjectDir: ENGINE,
    commandRunner: async () => {
      const error = new Error("not found");
      error.code = "ENOENT";
      throw error;
    },
  });
  const status = await manager.status();
  assert.equal(status.uv_found, false);
  assert.equal(status.uv_reason, "not_found");
  assert.equal(status.environment_ready, false);
  assert.equal(await missing(cacheDir), true);
});

test("Node science API executes the authoritative Python plugin", { skip: !RUN_UV_INTEGRATION }, async () => {
  const cacheDir = join(tmpdir(), `llmwho-science-integration-${process.pid}-${Date.now()}`);
  const fixture = JSON.parse(await import("node:fs/promises").then(({ readFile }) => (
    readFile(join(ROOT, "shared", "fixtures", "output-affinity.json"), "utf8")
  )));
  const manager = new ScienceRuntimeManager({
    cacheDir,
    engineProjectDir: ENGINE,
    pythonVersion: "3.12",
  });
  try {
    const plugins = await manager.plugins();
    assert.deepEqual(plugins.map(({ id }) => id), ["output_affinity"]);
    const analysis = await manager.outputAffinityMatrix(fixture.corpora, {
      ngramSize: fixture.parameters.ngram_size,
      modelWeight: fixture.parameters.model_weight,
    });
    assert.equal(analysis.plugin.id, "output_affinity");
    assert.equal(analysis.plugin.source, "builtin");
    assert.ok(analysis.limitations.includes("not-identity-proof"));
    assert.deepEqual(analysis.evidence.matrix, fixture.expected.matrix);
    assert.deepEqual(
      analysis.evidence.models.map(({ characters }) => characters),
      fixture.expected.characters,
    );
    assert.equal(JSON.stringify(analysis).includes("Quick zephyrs"), false);
    const ordered = await manager.outputAffinityMatrix(new Map([
      ["2", ["second model text"]],
      ["1", ["first model text"]],
    ]));
    assert.deepEqual(ordered.evidence.models.map(({ label }) => label), ["2", "1"]);
    await assert.rejects(
      manager.outputAffinityMatrix({ only: ["TOP-SECRET-RAW-PROSE"] }),
      (error) => error.code === "invalid_request"
        && !error.message.includes("TOP-SECRET-RAW-PROSE"),
    );
    const circular = {};
    circular.self = circular;
    await assert.rejects(
      manager.run("output_affinity", circular),
      (error) => error.code === "REQUEST_NOT_SERIALIZABLE",
    );
  } finally {
    await manager.shutdown();
    await rm(cacheDir, { recursive: true, force: true });
  }
});
