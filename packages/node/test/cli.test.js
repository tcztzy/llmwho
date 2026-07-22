import assert from "node:assert/strict";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { randomUUID } from "node:crypto";
import { test } from "node:test";

import { main } from "../src/cli.js";

test("summary CLI emits JSON for an empty store", async () => {
  const path = join(tmpdir(), `llmwho-cli-${randomUUID()}.jsonl`);
  let output = "";
  const originalWrite = process.stdout.write;
  process.stdout.write = (chunk) => { output += String(chunk); return true; };
  try {
    assert.equal(await main(["summary", "--storage", path, "--json"]), 0);
  } finally {
    process.stdout.write = originalWrite;
  }
  assert.equal(JSON.parse(output).events, 0);
});

test("science CLI exposes runtime status without touching passive init", async () => {
  let output = "";
  let configured;
  let shutdown = false;
  const originalWrite = process.stdout.write;
  process.stdout.write = (chunk) => { output += String(chunk); return true; };
  try {
    const exitCode = await main(
      [
        "science",
        "status",
        "--uv",
        "/opt/uv",
        "--python",
        "3.13",
        "--cache-dir",
        "/tmp/llmwho-science-test",
        "--offline",
      ],
      {
        createScienceRuntime: (options) => {
          configured = options;
          return {
            status: async () => ({ uv_found: true, environment_ready: false }),
            shutdown: async () => { shutdown = true; },
          };
        },
      },
    );
    assert.equal(exitCode, 0);
  } finally {
    process.stdout.write = originalWrite;
  }
  assert.equal(JSON.parse(output).uv_found, true);
  assert.equal(configured.uvPath, "/opt/uv");
  assert.equal(configured.pythonVersion, "3.13");
  assert.equal(configured.offline, true);
  assert.equal(shutdown, true);
});
