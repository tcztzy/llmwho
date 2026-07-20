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
        self.assertIn("Passive by default", readme)
        self.assertIn("probabilistic", readme)
        self.assertIn("No raw prompts or responses", readme)


if __name__ == "__main__":
    unittest.main()
