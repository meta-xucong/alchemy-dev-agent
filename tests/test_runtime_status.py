from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.runtime_status import RuntimeStatusProbe, read_toml_model


class RuntimeStatusTests(unittest.TestCase):
    def test_reads_only_the_local_codex_model_selector(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text('model = "gpt-5.6-sol"\n[features]\nexample = true\n', encoding="utf-8")
            self.assertEqual(read_toml_model(config), "gpt-5.6-sol")

            config.write_text('[codex]\nmodel = "gpt-5.4"\n', encoding="utf-8")
            self.assertEqual(read_toml_model(config), "gpt-5.4")

    def test_local_status_reports_tools_without_exposing_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text('model = "gpt-5.6-sol"\n', encoding="utf-8")

            def runner(command, **_kwargs):
                return subprocess.CompletedProcess(command, 0, stdout=b"tool 1.2.3\n", stderr=b"")

            with patch("server.runtime_status.shutil.which", return_value="C:/tools/tool.exe"):
                result = RuntimeStatusProbe(command_runner=runner, codex_config_path=config).local_status()

            self.assertTrue(result["codex_cli"]["connected"])
            self.assertEqual(result["codex_cli"]["model"], "gpt-5.6-sol")
            self.assertTrue(result["github"]["connected"])
