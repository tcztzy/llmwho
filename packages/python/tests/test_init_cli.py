from __future__ import annotations

import io
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
import unittest

import llmwho
from llmwho.cli import main


class InitAndCliTests(unittest.TestCase):
    def tearDown(self) -> None:
        handle = getattr(llmwho.hooks, "_ACTIVE_HANDLE", None)
        if handle is not None:
            handle.shutdown()

    def test_init_is_idempotent_and_network_passive(self) -> None:
        with TemporaryDirectory() as directory, mock.patch(
            "llmwho.hooks._load_optional", return_value=None
        ) as optional:
            path = Path(directory) / "events.ndjson"
            first = llmwho.init(storage_path=path)
            second = llmwho.init(storage_path=Path(directory) / "ignored.ndjson")
            self.assertIs(first, second)
            self.assertEqual(first.store.path, path)
            self.assertFalse(path.exists())
            self.assertEqual(optional.call_count, 2)
            first.shutdown()
            self.assertFalse(first.active)

    def test_disabled_environment_installs_nothing(self) -> None:
        with mock.patch.dict(os.environ, {"LLMWHO_DISABLED": "true"}), mock.patch(
            "llmwho.hooks._load_optional"
        ) as optional:
            handle = llmwho.init()
            self.assertFalse(handle.active)
            optional.assert_not_called()

    def test_summary_cli_json(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "missing.ndjson"
            output = io.StringIO()
            with mock.patch("sys.stdout", output):
                exit_code = main(["summary", "--storage", str(path), "--json"])
            self.assertEqual(exit_code, 0)
            self.assertIn('"events": 0', output.getvalue())


if __name__ == "__main__":
    unittest.main()
