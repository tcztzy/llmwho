from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RepositoryContractTests(unittest.TestCase):
    def test_public_project_files_exist(self) -> None:
        for relative in (
            "README.md",
            "LICENSE",
            "SPEC.md",
            "docs/VISION.md",
            "docs/ROADMAP.md",
            "docs/RESEARCH.md",
            "docs/STABILITY.md",
            "SECURITY.md",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_vision_locks_founder_expectations(self) -> None:
        vision = (ROOT / "docs/VISION.md").read_text(encoding="utf-8")
        for phrase in (
            "import llmwho",
            "llmwho.init()",
            'import { init } from "llmwho"',
            "must not stack duplicate hooks",
            "Raw prompts and responses are not stored by default",
            "Active requests must never be triggered by",
            "Identity is an inference, not a magic label",
            "Stability has separate layers",
        ):
            self.assertIn(phrase, vision)

    def test_readme_states_probabilistic_and_passive_contract(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("or send synthetic traffic", readme)
        self.assertIn("probabilistic", readme)
        self.assertIn("does **not** include raw prompts", readme)

    def test_research_separates_evidence_status_and_product_claims(self) -> None:
        research = (ROOT / "docs/RESEARCH.md").read_text(encoding="utf-8")
        for phrase in (
            "Peer-reviewed work most relevant",
            "Directly relevant preprints",
            "Evidence hierarchy",
            "What the MVP will not claim",
            "LLMmap",
            "Model Equality Testing",
            "Behavioral Fingerprints for LLM Endpoint Stability and Identity",
            "one-call in-application passive hook",
        ):
            self.assertIn(phrase, research)

    def test_public_docs_explain_real_mvp_and_stability_layers(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        stability = (ROOT / "docs/STABILITY.md").read_text(encoding="utf-8")
        for phrase in (
            "version 0.2 infers identity from response-declared model",
            "metadata and headers",
            "Active probes cost requests and are never triggered by `init()`",
            "Raw content capture is deliberately unavailable in 0.2",
            "Capability similarity does not uniquely identify model weights",
        ):
            self.assertIn(phrase, readme)
        for phrase in (
            "AI Stupid Level",
            "Availability",
            "Transport",
            "Behavior",
            "Capability",
            "Identity",
            "emit automatic statistical drift alerts",
            "Wilson or beta-binomial",
        ):
            self.assertIn(phrase, stability)


if __name__ == "__main__":
    unittest.main()
