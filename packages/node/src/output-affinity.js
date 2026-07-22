const JS_WHITESPACE = /[\u0009-\u000d\u0020\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+/gu;
const METRIC = "symmetric_smoothed_char_ngram_kl";

function normalize(text) {
  return text.replace(JS_WHITESPACE, " ").trim();
}

function entriesFromCorpora(corpora) {
  if (corpora instanceof Map) return [...corpora.entries()];
  if (corpora && typeof corpora === "object" && !Array.isArray(corpora)) {
    return Object.entries(corpora);
  }
  throw new TypeError("corpora must be an object or Map of labels to string iterables");
}

function profile(label, outputs, ngramSize) {
  if (typeof outputs === "string" || outputs === null || outputs === undefined
      || typeof outputs[Symbol.iterator] !== "function") {
    throw new TypeError(`corpus ${JSON.stringify(label)} must be an iterable of strings`);
  }
  const documents = [...outputs];
  if (documents.length === 0) {
    throw new RangeError(`corpus ${JSON.stringify(label)} must contain at least one document`);
  }
  if (documents.some((document) => typeof document !== "string")) {
    throw new TypeError(`corpus ${JSON.stringify(label)} documents must be strings`);
  }

  const text = normalize(documents.join(" "));
  const characters = text.length;
  if (characters < ngramSize) {
    throw new RangeError(
      `corpus ${JSON.stringify(label)} needs at least ${ngramSize} normalized UTF-16 code units`,
    );
  }
  const ngrams = characters - ngramSize + 1;
  const counts = new Map();
  for (let index = 0; index < ngrams; index += 1) {
    const ngram = text.slice(index, index + ngramSize);
    counts.set(ngram, (counts.get(ngram) ?? 0) + 1);
  }
  let entropyBits = 0;
  for (const count of counts.values()) {
    const probability = count / ngrams;
    entropyBits -= probability * Math.log2(probability);
  }
  return {
    label,
    documents: documents.length,
    characters,
    ngrams,
    counts,
    entropyBits,
  };
}

function directedDivergence(source, target, background, backgroundNgrams, modelWeight) {
  const backgroundWeight = 1 - modelWeight;
  let crossEntropy = 0;
  for (const [ngram, count] of source.counts) {
    const sourceProbability = count / source.ngrams;
    const targetProbability = (
      modelWeight * ((target.counts.get(ngram) ?? 0) / target.ngrams)
      + backgroundWeight * (background.get(ngram) / backgroundNgrams)
    );
    crossEntropy -= sourceProbability * Math.log2(targetProbability);
  }
  return crossEntropy - source.entropyBits;
}

/**
 * Build a pairwise output-style divergence matrix from caller-supplied prose.
 * Lower values mean closer surface style. This function performs no I/O and
 * makes no model-identity or training-provenance claim.
 */
export function outputAffinityMatrix(corpora, options = {}) {
  const ngramSize = options.ngramSize ?? 3;
  const modelWeight = options.modelWeight ?? 0.8;
  if (!Number.isInteger(ngramSize) || ngramSize < 1) {
    throw new RangeError("ngramSize must be a positive integer");
  }
  if (typeof modelWeight !== "number" || !Number.isFinite(modelWeight)
      || modelWeight <= 0 || modelWeight >= 1) {
    throw new RangeError("modelWeight must be a finite number between 0 and 1");
  }

  const entries = entriesFromCorpora(corpora);
  if (entries.length < 2) throw new RangeError("corpora must contain at least two models");
  const profiles = entries.map(([label, outputs]) => {
    if (typeof label !== "string" || label.length === 0) {
      throw new RangeError("corpus labels must be non-empty strings");
    }
    return profile(label, outputs, ngramSize);
  });

  const background = new Map();
  let backgroundNgrams = 0;
  for (const item of profiles) {
    for (const [ngram, count] of item.counts) {
      background.set(ngram, (background.get(ngram) ?? 0) + count);
    }
    backgroundNgrams += item.ngrams;
  }

  const directed = profiles.map((source) => profiles.map((target) => (
    directedDivergence(source, target, background, backgroundNgrams, modelWeight)
  )));
  const pairValues = [];
  const matrix = profiles.map((_, rowIndex) => profiles.map((__, columnIndex) => {
    if (rowIndex === columnIndex) return 0;
    const value = (
      directed[rowIndex][columnIndex] + directed[columnIndex][rowIndex]
    ) / 2;
    if (columnIndex < rowIndex) pairValues.push(value);
    return value;
  }));

  return {
    metric: METRIC,
    interpretation: "style_divergence",
    unit: "bits_per_character_ngram",
    character_encoding: "utf-16-code-unit",
    ngram_size: ngramSize,
    model_weight: modelWeight,
    background_weight: 1 - modelWeight,
    models: profiles.map((item) => ({
      label: item.label,
      documents: item.documents,
      characters: item.characters,
      ngrams: item.ngrams,
      entropy_bits: item.entropyBits,
    })),
    matrix,
    min_divergence: Math.min(...pairValues),
    max_divergence: Math.max(...pairValues),
  };
}
