from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

from autodev.local_repository_acceptance import LocalRepositoryAcceptanceHarness


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_RUN_ID = str(time.time_ns())
_TEMP_COUNTER = 0


def temp_root() -> Path:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    root = TEST_TMP_ROOT / f"local-repository-acceptance-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    root.mkdir(parents=True, exist_ok=False)
    return root


class LocalRepositoryAcceptanceTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_harness_passes_local_import_and_feedback_reopen(self) -> None:
        root = temp_root()

        result = LocalRepositoryAcceptanceHarness().run(output_dir=root)
        payload = result.to_dict()

        self.assertEqual(payload["status"], "passed")
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertTrue(checks["local_repository_source"]["passed"])
        self.assertTrue(checks["debug_task_created"]["passed"])
        self.assertEqual(payload["initial_run"]["run_id"], "run_001")
        self.assertEqual(payload["reopened_run"]["run_id"], "run_002")
        self.assertTrue((root / "local_repository_acceptance_report.json").exists())

    def test_cli_outputs_local_repository_acceptance_report(self) -> None:
        root = temp_root()

        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "autodev.local_repository_acceptance",
                "--output",
                str(root),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "passed")
        self.assertTrue((root / "local_repository_acceptance_report.json").exists())


if __name__ == "__main__":
    unittest.main()
