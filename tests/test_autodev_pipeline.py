from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from autodev import AutoDevPipeline
from autodev.agents import inspect_generated_game
from intake.schema_validation import validate_context_bundle_contract, validate_project_brief_contract


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_COUNTER = 0
_TEMP_RUN_ID = str(time.time_ns())


@contextmanager
def temp_demo_dir() -> Iterator[Path]:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    path = TEST_TMP_ROOT / f"autodev-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class AutoDevPipelineTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_one_line_platformer_generates_safe_playable_artifact(self) -> None:
        objective = "我要生成一个超级玛丽第一关的游戏。关卡设计、人物和场景形象均完全模仿经典原始版的超级玛丽"
        with temp_demo_dir() as output_dir:
            result = AutoDevPipeline().run(objective, output_dir)
            payload = result.to_dict()
            index_path = output_dir / "index.html"
            report_path = output_dir / "autodev_report.json"

            self.assertEqual(result.status, "done")
            self.assertTrue(index_path.exists())
            self.assertTrue(report_path.exists())
            self.assertEqual(validate_project_brief_contract(payload["project_brief"]), [])
            self.assertEqual(validate_context_bundle_contract(payload["context_bundle"]), [])
            self.assertEqual(payload["project_brief"]["primary_input_mode"], "one_line_fallback")
            self.assertTrue(payload["project_brief"]["generated_from_one_liner"])
            self.assertEqual(payload["context_bundle"]["repository_map"]["root_path"], "")
            self.assertEqual(payload["context_bundle"]["risk_profile"]["risks"][0]["type"], "copyright_safety")
            self.assertTrue(inspect_generated_game(index_path)["passed"])

            html = index_path.read_text(encoding="utf-8").lower()
            self.assertIn("<canvas", html)
            self.assertIn("stage clear", html)
            self.assertNotIn("mario", html)
            self.assertNotIn("nintendo", html)

            agents = [event["agent"] for event in payload["agent_events"]]
            self.assertEqual(agents, ["architect", "frontend", "test", "reviewer"])

    def test_demo_cli_outputs_done_report(self) -> None:
        with temp_demo_dir() as output_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "autodev.demo_run",
                    "--objective",
                    "Build a small retro platform game",
                    "--output",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "done")
            self.assertTrue((output_dir / "index.html").exists())
            self.assertTrue((output_dir / "autodev_report.json").exists())


if __name__ == "__main__":
    unittest.main()
