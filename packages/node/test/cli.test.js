import assert from "node:assert/strict";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { randomUUID } from "node:crypto";
import { test } from "node:test";

import { main } from "../src/cli.js";

test("summary CLI emits JSON for an empty store", async () => {
  const path = join(tmpdir(), `llmwho-cli-${randomUUID()}.ndjson`);
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
