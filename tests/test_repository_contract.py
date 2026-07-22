import json
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
            "docs/AGENT_HOOKS.md",
            "docs/OUTPUT_AFFINITY.md",
            "examples/hooks/claude-code.settings.json",
            "examples/hooks/codex.hooks.json",
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

    def test_v22_public_docs_explain_real_mvp_and_stability_layers(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        stability = (ROOT / "docs/STABILITY.md").read_text(encoding="utf-8")
        for phrase in (
            "declared `model` field",
            "Undocumented model response headers are ignored",
            "Active probes cost requests and are never triggered by `init()`",
            "Raw content capture is deliberately unavailable in 0.2",
            "Capability similarity does not uniquely identify model weights",
        ):
            self.assertIn(phrase, readme)
        self.assertNotIn("metadata and headers", readme)
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

    def test_agent_hook_templates_match_public_cli_and_privacy_contract(self) -> None:
        claude = json.loads(
            (ROOT / "examples/hooks/claude-code.settings.json").read_text()
        )
        codex = json.loads((ROOT / "examples/hooks/codex.hooks.json").read_text())
        self.assertEqual(
            set(claude["hooks"]),
            {
                "SessionStart",
                "UserPromptSubmit",
                "Stop",
                "StopFailure",
                "SessionEnd",
            },
        )
        for event, groups in claude["hooks"].items():
            command = groups[0]["hooks"][0]
            self.assertEqual(command["command"], "llmwho")
            self.assertEqual(
                command["args"],
                ["hook", "claude-code", "--event", event],
            )
        self.assertEqual(set(codex["hooks"]), {"UserPromptSubmit", "Stop"})
        for event, groups in codex["hooks"].items():
            command = groups[0]["hooks"][0]["command"]
            self.assertEqual(command, f"llmwho hook codex --event {event}")

        guide = (ROOT / "docs/AGENT_HOOKS.md").read_text()
        for phrase in (
            "never sends network traffic",
            "does not persist or read",
            "session IDs, turn IDs, API keys",
            "Malformed JSON, oversized input, state failure",
            "identity remains `unknown`",
        ):
            self.assertIn(phrase, guide)

    def test_v26_output_affinity_docs_state_method_and_claim_boundary(self) -> None:
        readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
        method = " ".join(
            (ROOT / "docs/OUTPUT_AFFINITY.md").read_text(encoding="utf-8").split()
        )
        for phrase in (
            "output_affinity_matrix",
            "outputAffinityMatrix",
            "Similar style is not proof of model identity",
        ):
            self.assertIn(phrase, readme)
        for phrase in (
            "UTF-16 character n-grams",
            "KL(P_A || Q_B)",
            "Kimi K3 ↔ Fable 5",
            "Adding or removing reference models changes it",
            "not an identity detector",
            "training-provenance detector",
        ):
            self.assertIn(phrase, method)


if __name__ == "__main__":
    unittest.main()
