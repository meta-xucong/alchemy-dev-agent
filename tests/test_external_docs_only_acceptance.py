from __future__ import annotations

import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

from autodev.external_docs_only_acceptance import ExternalDocsOnlyAcceptance


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_RUN_ID = str(time.time_ns())
_TEMP_COUNTER = 0


def temp_root() -> Path:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    root = TEST_TMP_ROOT / f"external-docs-only-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    root.mkdir(parents=True, exist_ok=False)
    return root


class ExternalDocsOnlyAcceptanceTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_harness_reports_v2_22_planning_contract(self) -> None:
        root = temp_root()

        report = ExternalDocsOnlyAcceptance().run(output_dir=root / "out")
        payload = report.to_dict()

        self.assertEqual(payload["status"], "passed")
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertTrue(checks["document_driven"]["passed"])
        self.assertTrue(checks["no_one_line_fallback"]["passed"])
        self.assertTrue(checks["artifact_gate_planned"]["passed"])
        self.assertTrue((root / "out" / "external_docs_only_acceptance_report.json").exists())

    def test_cli_reports_v2_22_planning_contract(self) -> None:
        root = temp_root()

        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "autodev.external_docs_only_acceptance",
                "--output",
                str(root / "out"),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"status": "passed"', result.stdout)


if __name__ == "__main__":
    unittest.main()
