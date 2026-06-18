from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

from autodev.acceptance_run import AcceptanceHarness


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_RUN_ID = str(time.time_ns())
_TEMP_COUNTER = 0


def temp_root() -> Path:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    root = TEST_TMP_ROOT / f"acceptance-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    root.mkdir(parents=True, exist_ok=False)
    return root


class AcceptanceRunTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_acceptance_harness_generates_passing_report(self) -> None:
        root = temp_root()
        result = AcceptanceHarness().run(output_dir=root)
        payload = result.to_dict()

        self.assertEqual(payload["status"], "passed")
        self.assertTrue(all(check["passed"] for check in payload["checks"]))
        self.assertTrue((root / "acceptance_report.json").exists())
        self.assertEqual(payload["delivery"]["status"], "done")

    def test_acceptance_cli_outputs_report(self) -> None:
        root = temp_root()
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "autodev.acceptance_run",
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
        self.assertTrue((root / "acceptance_report.json").exists())


if __name__ == "__main__":
    unittest.main()
