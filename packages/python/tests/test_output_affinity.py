from copy import deepcopy
import json
from pathlib import Path
import unittest

from llmwho import science


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "shared/fixtures/output-affinity.json"


class OutputAffinityTests(unittest.TestCase):
    def test_shared_reference_vector(self) -> None:
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        analysis = science.output_affinity_matrix(
            fixture["corpora"],
            ngram_size=fixture["parameters"]["ngram_size"],
            model_weight=fixture["parameters"]["model_weight"],
        )
        report = analysis["evidence"]

        self.assertEqual(analysis["schema_version"], "1")
        self.assertEqual(analysis["protocol_version"], "1")
        self.assertEqual(analysis["plugin"]["id"], "output_affinity")
        self.assertEqual(analysis["plugin"]["version"], "1.0.0")
        self.assertIn("not-identity-proof", analysis["limitations"])
        self.assertEqual(report["metric"], "symmetric_smoothed_char_ngram_kl")
        self.assertEqual(report["interpretation"], "style_divergence")
        self.assertEqual(report["unit"], "bits_per_character_ngram")
        self.assertEqual(report["character_encoding"], "utf-16-code-unit")
        self.assertEqual([row["label"] for row in report["models"]], list(fixture["corpora"]))
        self.assertEqual(
            [row["characters"] for row in report["models"]],
            fixture["expected"]["characters"],
        )
        self.assertEqual(
            [row["ngrams"] for row in report["models"]],
            fixture["expected"]["ngrams"],
        )
        for actual, expected in zip(
            [row["entropy_bits"] for row in report["models"]],
            fixture["expected"]["entropy_bits"],
        ):
            self.assertAlmostEqual(actual, expected, places=12)
        for actual_row, expected_row in zip(report["matrix"], fixture["expected"]["matrix"]):
            for actual, expected in zip(actual_row, expected_row):
                self.assertAlmostEqual(actual, expected, places=12)
        self.assertAlmostEqual(report["min_divergence"], report["matrix"][0][1])
        self.assertAlmostEqual(report["max_divergence"], report["matrix"][1][2])

    def test_input_is_not_mutated_or_returned(self) -> None:
        corpora = {"A": ["alpha text"], "B": ["beta text"]}
        original = deepcopy(corpora)
        analysis = science.output_affinity_matrix(corpora)
        report = analysis["evidence"]
        self.assertEqual(corpora, original)
        serialized = json.dumps(report)
        self.assertNotIn("alpha text", serialized)
        self.assertNotIn("beta text", serialized)

    def test_utf16_code_units_and_whitespace_normalization(self) -> None:
        analysis = science.output_affinity_matrix(
            {"A": ["A🙂B"], "B": ["A\n🙂\tC"]},
            ngram_size=3,
        )
        report = analysis["evidence"]
        self.assertEqual([row["characters"] for row in report["models"]], [4, 6])
        self.assertEqual([row["ngrams"] for row in report["models"]], [2, 4])
        self.assertEqual(report["matrix"][0][1], report["matrix"][1][0])
        self.assertEqual(report["matrix"][0][0], 0.0)

    def test_validation_rejects_ambiguous_or_degenerate_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least two"):
            science.output_affinity_matrix({"A": ["text"]})
        with self.assertRaisesRegex(TypeError, "iterable of strings"):
            science.output_affinity_matrix({"A": "text", "B": ["text"]})
        with self.assertRaisesRegex(TypeError, "documents must be strings"):
            science.output_affinity_matrix({"A": ["text", 1], "B": ["text"]})  # type: ignore[list-item]
        with self.assertRaisesRegex(ValueError, "ngram_size"):
            science.output_affinity_matrix({"A": ["text"], "B": ["text"]}, ngram_size=0)
        with self.assertRaisesRegex(ValueError, "model_weight"):
            science.output_affinity_matrix({"A": ["text"], "B": ["text"]}, model_weight=1.0)

    def test_legacy_root_api_is_removed(self) -> None:
        import llmwho

        self.assertFalse(hasattr(llmwho, "output_affinity_matrix"))


if __name__ == "__main__":
    unittest.main()
