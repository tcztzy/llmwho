import { readFileSync } from "node:fs";

const tag = process.argv[2];
if (!tag) {
  throw new Error("usage: node scripts/check-release-tag.mjs vX.Y.Z");
}

const nodePackage = JSON.parse(readFileSync("packages/node/package.json", "utf8"));
const pythonProject = readFileSync("packages/python/pyproject.toml", "utf8");
const pythonVersionModule = readFileSync(
  "packages/python/src/llmwho/version.py",
  "utf8",
);
const nodeVersionModule = readFileSync("packages/node/src/version.js", "utf8");

const version = nodePackage.version;
if (!/^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/.test(version)) {
  throw new Error(`invalid package version: ${version}`);
}
if (tag !== `v${version}`) {
  throw new Error(`release tag ${tag} does not match package version ${version}`);
}

const declarations = [
  ["Python project", pythonProject, `version = "${version}"`],
  ["Python module", pythonVersionModule, `__version__ = "${version}"`],
  ["Node module", nodeVersionModule, `VERSION = "${version}"`],
];
for (const [label, source, declaration] of declarations) {
  if (!source.includes(declaration)) {
    throw new Error(`${label} does not declare version ${version}`);
  }
}

console.log(`release tag ${tag} matches all package versions`);
