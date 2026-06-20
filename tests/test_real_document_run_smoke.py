from __future__ import annotations

import shutil
import time
import unittest
from pathlib import Path

from autodev.real_document_run_smoke import RealDocumentRunSmoke, smoke_summary


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_RUN_ID = str(time.time_ns())
_TEMP_COUNTER = 0


def temp_root() -> Path:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    root = TEST_TMP_ROOT / f"real-document-run-smoke-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    root.mkdir(parents=True, exist_ok=False)
    return root


class RealDocumentRunSmokeTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_smoke_blocks_when_codex_missing(self) -> None:
        root = temp_root()

        report = RealDocumentRunSmoke().run(
            output_dir=root / "out",
            codex_executable=str(root / "missing-codex.exe"),
        )
        payload = report.to_dict()

        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["preflight"]["status"], "blocked")
        self.assertTrue(payload["blockers"])

    def test_summary_shape(self) -> None:
        summary = smoke_summary(
            {
                "status": "passed",
                "output_dir": "out",
                "preflight": {"status": "passed"},
                "document_run": {"status": "done", "worker_lifecycle_count": 1},
                "verification": {"status": "passed"},
                "blockers": [],
            }
        )

        self.assertEqual(
            summary,
            {
                "status": "passed",
                "output_dir": "out",
                "preflight_status": "passed",
                "document_run_status": "done",
                "worker_lifecycle_count": 1,
                "verification_status": "passed",
                "blocker_count": 0,
            },
        )


if __name__ == "__main__":
    unittest.main()
