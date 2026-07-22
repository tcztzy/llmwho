import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RepositoryContractTests(unittest.TestCase):
    def test_release_versions_match_across_packages_and_bundled_engine(self) -> None:
        node = json.loads((ROOT / "packages/node/package.json").read_text())
        python_project = (ROOT / "packages/python/pyproject.toml").read_text()
        python_version = (ROOT / "packages/python/src/llmwho/version.py").read_text()
        node_version = (ROOT / "packages/node/src/version.js").read_text()
        version = node["version"]
        self.assertIn(f'version = "{version}"', python_project)
        self.assertIn(f'__version__ = "{version}"', python_version)
        self.assertIn(f'VERSION = "{version}"', node_version)

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
            "docs/SCIENCE_RUNTIME.md",
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
            "Raw content capture is deliberately unavailable in 0.3",
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
            "same Python plugin",
        ):
            self.assertIn(phrase, method)

    def test_science_runtime_contract_is_explicit_and_separate_from_init(self) -> None:
        readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
        runtime = " ".join(
            (ROOT / "docs/SCIENCE_RUNTIME.md").read_text(encoding="utf-8").split()
        )
        for phrase in (
            "npx llmwho science status",
            "await science.outputAffinityMatrix",
            "Executable plugin packages are trusted code",
        ):
            self.assertIn(phrase, readme)
        for phrase in (
            "do not search for uv",
            "uv sync --frozen --no-dev --no-editable --no-install-project",
            "llmwho.science.plugins",
            "does not write it to event storage",
            "reference fingerprint",
        ):
            self.assertIn(phrase, runtime)
        self.assertFalse((ROOT / "packages/node/src/output-affinity.js").exists())
        self.assertFalse((ROOT / "packages/python/src/llmwho/output_affinity.py").exists())

    def test_python_style_gate_bans_deferred_annotations(self) -> None:
        project = (ROOT / "packages/python/pyproject.toml").read_text(encoding="utf-8")
        pre_commit = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")

        self.assertIn('select = ["UP", "TID"]', project)
        self.assertIn('"__future__.annotations"', project)
        self.assertIn("astral-sh/ruff-pre-commit", pre_commit)
        self.assertIn("id: ruff-check", pre_commit)
        self.assertIn("args: [--config, packages/python/pyproject.toml]", pre_commit)

        roots = (
            ROOT / "packages/python/src",
            ROOT / "packages/python/tests",
            ROOT / "tests",
        )
        forbidden = "from __future__ import " + "annotations"
        for root in roots:
            for path in root.rglob("*.py"):
                self.assertNotIn(
                    forbidden,
                    path.read_text(encoding="utf-8"),
                    str(path.relative_to(ROOT)),
                )

    def test_jsonl_is_the_only_line_delimited_json_name(self) -> None:
        forbidden_name = "ND" + "JSON"
        forbidden_suffix = ".nd" + "json"
        roots = (
            ROOT / "docs",
            ROOT / "packages/node/src",
            ROOT / "packages/node/test",
            ROOT / "packages/python/src",
            ROOT / "packages/python/tests",
        )
        paths = [
            ROOT / "README.md",
            ROOT / "SPEC.md",
            ROOT / "packages/node/README.md",
            ROOT / "packages/python/README.md",
        ]
        for root in roots:
            paths.extend(
                path
                for path in root.rglob("*")
                if path.suffix in {".js", ".md", ".py", ".ts"}
            )

        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(forbidden_name, text, str(path.relative_to(ROOT)))
            self.assertNotIn(forbidden_suffix, text, str(path.relative_to(ROOT)))

    def test_release_workflow_uses_oidc_and_immutable_actions(self) -> None:
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        release = (ROOT / ".github/workflows/release.yml").read_text(
            encoding="utf-8"
        )
        guide = (ROOT / "docs/RELEASING.md").read_text(encoding="utf-8")

        self.assertIn("branches: [main]", ci)
        self.assertNotIn("id-token: write", ci)
        self.assertIn('tags:\n      - "v[0-9]*"', release)
        self.assertEqual(release.count("id-token: write"), 2)
        self.assertIn("name: pypi", release)
        self.assertIn("name: npm", release)
        self.assertIn(
            "needs: [build-python, build-node, publish-pypi, publish-npm]",
            release,
        )
        self.assertIn("needs: verify-registries", release)
        self.assertNotIn("secrets.", release)
        self.assertNotIn("NODE_AUTH_TOKEN", release)
        for workflow in (ci, release):
            for action in re.findall(r"uses: [^@\s]+@([^\s]+)", workflow):
                self.assertRegex(action, r"^[0-9a-f]{40}$")

        for phrase in (
            "No PyPI or npm token belongs in GitHub secrets",
            "release.yml",
            "`pypi`",
            "`npm`",
            "rerun only the failed job",
        ):
            self.assertIn(phrase, guide)

    def test_v33_partial_release_recovery_preserves_tag_and_artifacts(self) -> None:
        release = (ROOT / ".github/workflows/release.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("workflow_dispatch:", release)
        self.assertIn("RELEASE_TAG:", release)
        self.assertIn("RELEASE_REF:", release)
        self.assertIn("ref: ${{ env.RELEASE_REF }}", release)
        self.assertIn("npm publish ./dist/*.tgz --access public", release)
        self.assertNotIn("npm publish dist/*.tgz --access public", release)
        self.assertIn("inputs.publish_pypi", release)
        self.assertIn("inputs.publish_npm", release)
        self.assertIn("verify-registries:", release)
        self.assertIn("needs: verify-registries", release)
        self.assertIn(
            "if: always() && needs.verify-registries.result == 'success'",
            release,
        )
        self.assertNotIn("Select at least one registry for recovery", release)
        self.assertIn(
            "- name: Validate npm publish\n"
            "        if: github.event_name == 'push' || inputs.publish_npm",
            release,
        )


if __name__ == "__main__":
    unittest.main()
