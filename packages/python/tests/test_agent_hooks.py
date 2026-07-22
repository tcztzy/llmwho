import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from llmwho.agent_hooks import MAX_HOOK_INPUT_BYTES, observe_hook_event
from llmwho.storage import JSONLStore


FIXTURE_PATH = (
    Path(__file__).resolve().parents[3]
    / "shared"
    / "fixtures"
    / "agent-hooks.json"
)


class AgentHookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def _assert_expected(self, event: dict, expected: dict) -> None:
        self.assertEqual(event["endpoint"]["provider"], expected["provider"])
        self.assertEqual(event["endpoint"]["host"], expected["host"])
        self.assertEqual(event["endpoint"]["path"], expected["path"])
        self.assertEqual(event["transport"]["outcome"], expected["outcome"])
        self.assertEqual(
            event["transport"]["duration_ms"], expected["duration_ms"]
        )
        if "error_type" in expected:
            self.assertEqual(
                event["transport"]["error_type"], expected["error_type"]
            )
        else:
            self.assertNotIn("error_type", event["transport"])
        self.assertEqual(event["request"]["operation"], "agent.turn")
        self.assertEqual(event["request"]["input_bytes"], expected["input_bytes"])
        self.assertEqual(event["request"]["claimed_model"], expected["model"])
        if "output_bytes" in expected:
            self.assertEqual(
                event["response"]["output_bytes"], expected["output_bytes"]
            )
        else:
            self.assertNotIn("response", event)
        self.assertEqual(event["identity"]["status"], "unknown")
        self.assertEqual(event["identity"]["claimed_model"], expected["model"])
        self.assertEqual(
            event["privacy"], {"content_captured": False, "redactions": 0}
        )

    def test_shared_sequences_normalize_turns_without_persisting_content(self) -> None:
        for client in ("claude-code", "codex"):
            with self.subTest(client=client), TemporaryDirectory() as directory:
                store = JSONLStore(Path(directory) / "events.jsonl")
                expected_events = []
                for step in self.fixture[client]:
                    event = observe_hook_event(
                        client,
                        step["payload"],
                        store=store,
                        now_ms=step["now_ms"],
                    )
                    expected = step.get("expected")
                    if expected:
                        self.assertIsNotNone(event)
                        self._assert_expected(event, expected)
                        expected_events.append(expected)
                    else:
                        self.assertIsNone(event)

                    state_root = Path(directory) / ".hook-state"
                    state_blob = ""
                    if state_root.exists():
                        for path in state_root.rglob("*"):
                            state_blob += str(path.relative_to(state_root))
                            if path.is_file():
                                state_blob += path.read_text(encoding="utf-8")
                    for forbidden in self.fixture["forbidden"]:
                        self.assertNotIn(forbidden, state_blob)

                events = store.read()
                self.assertEqual(len(events), len(expected_events))
                persisted = store.path.read_text(encoding="utf-8")
                for forbidden in self.fixture["forbidden"]:
                    self.assertNotIn(forbidden, persisted)
                state_files = list(
                    (Path(directory) / ".hook-state").glob("**/*.json")
                )
                self.assertEqual(state_files, [])

    def _run_cli(
        self,
        client: str,
        event_name: str,
        payload: str,
        storage: Path,
        *,
        disabled: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.pop("LLMWHO_DISABLED", None)
        if disabled:
            environment["LLMWHO_DISABLED"] = "true"
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "llmwho",
                "hook",
                client,
                "--event",
                event_name,
                "--storage",
                str(storage),
            ],
            input=payload,
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )

    def test_cli_correlates_separate_processes_and_preserves_protocol_output(self) -> None:
        with TemporaryDirectory() as directory:
            storage = Path(directory) / "claude.jsonl"
            payloads = (
                {
                    "session_id": "cross-process-session",
                    "hook_event_name": "SessionStart",
                    "model": "claude-sonnet-5",
                },
                {
                    "session_id": "cross-process-session",
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "do not persist this prompt",
                },
                {
                    "session_id": "cross-process-session",
                    "hook_event_name": "Stop",
                    "last_assistant_message": "do not persist this answer",
                },
            )
            for payload in payloads:
                event_name = payload["hook_event_name"]
                result = self._run_cli(
                    "claude-code",
                    event_name,
                    json.dumps(payload),
                    storage,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "")
            event = JSONLStore(storage).read()[0]
            self.assertEqual(event["endpoint"]["provider"], "anthropic")
            self.assertEqual(event["request"]["claimed_model"], "claude-sonnet-5")
            persisted = storage.read_text(encoding="utf-8")
            self.assertNotIn("cross-process-session", persisted)
            self.assertNotIn("do not persist", persisted)

            codex_storage = Path(directory) / "codex.jsonl"
            codex_payloads = (
                {
                    "session_id": "codex-cross-process",
                    "turn_id": "turn-secret",
                    "hook_event_name": "UserPromptSubmit",
                    "model": "gpt-5.3-codex",
                    "prompt": "private codex prompt",
                },
                {
                    "session_id": "codex-cross-process",
                    "turn_id": "turn-secret",
                    "hook_event_name": "Stop",
                    "model": "gpt-5.3-codex",
                    "last_assistant_message": "private codex answer",
                },
            )
            for payload in codex_payloads:
                result = self._run_cli(
                    "codex",
                    payload["hook_event_name"],
                    json.dumps(payload),
                    codex_storage,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                expected_stdout = "{}\n" if payload["hook_event_name"] == "Stop" else ""
                self.assertEqual(result.stdout, expected_stdout)
            codex_event = JSONLStore(codex_storage).read()[0]
            self.assertEqual(codex_event["endpoint"]["provider"], "openai")
            self.assertNotIn("private codex", codex_storage.read_text())

    def test_cli_is_fail_open_for_bad_input_storage_failure_and_disable(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            malformed_storage = root / "malformed.jsonl"
            malformed = self._run_cli(
                "codex", "Stop", "{not-json", malformed_storage
            )
            self.assertEqual(malformed.returncode, 0)
            self.assertEqual(malformed.stdout, "{}\n")
            self.assertEqual(malformed.stderr, "")
            self.assertFalse(malformed_storage.exists())

            blocker = root / "blocker"
            blocker.write_text("file blocks child path", encoding="utf-8")
            failure = self._run_cli(
                "codex",
                "Stop",
                json.dumps(
                    {
                        "session_id": "secret",
                        "hook_event_name": "Stop",
                        "model": "gpt-5.3-codex",
                    }
                ),
                blocker / "events.jsonl",
            )
            self.assertEqual(failure.returncode, 0)
            self.assertEqual(failure.stdout, "{}\n")
            self.assertEqual(failure.stderr, "")

            disabled_storage = root / "disabled.jsonl"
            disabled = self._run_cli(
                "codex",
                "Stop",
                json.dumps(
                    {
                        "session_id": "secret",
                        "hook_event_name": "Stop",
                        "model": "gpt-5.3-codex",
                    }
                ),
                disabled_storage,
                disabled=True,
            )
            self.assertEqual(disabled.returncode, 0)
            self.assertEqual(disabled.stdout, "{}\n")
            self.assertFalse(disabled_storage.exists())

            oversized_storage = root / "oversized.jsonl"
            oversized = self._run_cli(
                "codex",
                "Stop",
                "x" * (MAX_HOOK_INPUT_BYTES + 1),
                oversized_storage,
            )
            self.assertEqual(oversized.returncode, 0)
            self.assertEqual(oversized.stdout, "{}\n")
            self.assertEqual(oversized.stderr, "")
            self.assertFalse(oversized_storage.exists())

    def test_state_rejects_unsafe_model_values(self) -> None:
        with TemporaryDirectory() as directory:
            store = JSONLStore(Path(directory) / "events.jsonl")
            event = observe_hook_event(
                "claude-code",
                {
                    "session_id": "unsafe-model-session",
                    "hook_event_name": "UserPromptSubmit",
                    "model": "claude-safe\nprivate-metadata",
                },
                store=store,
                now_ms=1,
            )
            self.assertIsNone(event)
            state_blob = "".join(
                path.read_text(encoding="utf-8")
                for path in (Path(directory) / ".hook-state").glob("**/*.json")
            )
            self.assertNotIn("claude-safe", state_blob)
            self.assertNotIn("private-metadata", state_blob)


if __name__ == "__main__":
    unittest.main()
