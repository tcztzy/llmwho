import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import { outputAffinityMatrix } from "../src/index.js";


const ROOT = join(import.meta.dirname, "..", "..", "..");
const FIXTURE = JSON.parse(readFileSync(join(ROOT, "shared", "fixtures", "output-affinity.json")));

function close(actual, expected, tolerance = 1e-12) {
  assert.ok(Math.abs(actual - expected) <= tolerance, `${actual} != ${expected}`);
}

test("output affinity matches shared reference vector", () => {
  const report = outputAffinityMatrix(FIXTURE.corpora, {
    ngramSize: FIXTURE.parameters.ngram_size,
    modelWeight: FIXTURE.parameters.model_weight,
  });
  assert.equal(report.metric, "symmetric_smoothed_char_ngram_kl");
  assert.equal(report.interpretation, "style_divergence");
  assert.equal(report.unit, "bits_per_character_ngram");
  assert.equal(report.character_encoding, "utf-16-code-unit");
  assert.deepEqual(report.models.map((row) => row.label), Object.keys(FIXTURE.corpora));
  assert.deepEqual(report.models.map((row) => row.characters), FIXTURE.expected.characters);
  assert.deepEqual(report.models.map((row) => row.ngrams), FIXTURE.expected.ngrams);
  report.models.forEach((row, index) => close(row.entropy_bits, FIXTURE.expected.entropy_bits[index]));
  report.matrix.forEach((row, rowIndex) => row.forEach((value, columnIndex) => {
    close(value, FIXTURE.expected.matrix[rowIndex][columnIndex]);
  }));
  close(report.min_divergence, report.matrix[0][1]);
  close(report.max_divergence, report.matrix[1][2]);
});

test("output affinity does not mutate or return source prose", () => {
  const corpora = { A: ["alpha text"], B: ["beta text"] };
  const original = structuredClone(corpora);
  const report = outputAffinityMatrix(corpora);
  assert.deepEqual(corpora, original);
  assert.equal(JSON.stringify(report).includes("alpha text"), false);
  assert.equal(JSON.stringify(report).includes("beta text"), false);
});

test("output affinity counts UTF-16 code units and normalizes whitespace", () => {
  const report = outputAffinityMatrix({ A: ["A🙂B"], B: ["A\n🙂\tC"] });
  assert.deepEqual(report.models.map((row) => row.characters), [4, 6]);
  assert.deepEqual(report.models.map((row) => row.ngrams), [2, 4]);
  assert.equal(report.matrix[0][1], report.matrix[1][0]);
  assert.equal(report.matrix[0][0], 0);
});

test("output affinity validates ambiguous or degenerate input", () => {
  assert.throws(() => outputAffinityMatrix({ A: ["text"] }), /at least two/);
  assert.throws(() => outputAffinityMatrix({ A: "text", B: ["text"] }), /iterable of strings/);
  assert.throws(() => outputAffinityMatrix({ A: ["text", 1], B: ["text"] }), /documents must be strings/);
  assert.throws(() => outputAffinityMatrix({ A: ["text"], B: ["text"] }, { ngramSize: 0 }), /ngramSize/);
  assert.throws(() => outputAffinityMatrix({ A: ["text"], B: ["text"] }, { modelWeight: 1 }), /modelWeight/);
});
