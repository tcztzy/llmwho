#!/usr/bin/env bash
set -euo pipefail

tarball=$1
smoke_dir=$(mktemp -d)
trap 'rm -rf "$smoke_dir"' EXIT

(
  cd "$smoke_dir"
  npm init --yes >/dev/null
  npm install --ignore-scripts "$OLDPWD/$tarball" >/dev/null
  node --input-type=module <<'NODE'
const llmwho = await import("llmwho");
if (typeof llmwho.JSONLStore !== "function"
    || typeof llmwho.RemoteStore !== "function"
    || "NDJSONStore" in llmwho) {
  throw new Error("ESM storage exports do not match the release contract");
}
const report = await llmwho.science.outputAffinityMatrix({
  alpha: ["alpha reference output"],
  beta: ["beta endpoint output"],
});
if (report.plugin.id !== "output_affinity") {
  throw new Error("bundled Python science plugin did not run");
}
await llmwho.science.shutdown();
NODE
  node <<'NODE'
const llmwho = require("llmwho");
if (typeof llmwho.JSONLStore !== "function"
    || typeof llmwho.RemoteStore !== "function"
    || "NDJSONStore" in llmwho) {
  throw new Error("CommonJS storage exports do not match the release contract");
}
NODE
)
