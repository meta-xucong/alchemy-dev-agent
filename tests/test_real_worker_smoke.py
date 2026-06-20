from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

from autodev.real_worker_smoke import RealWorkerSmoke, smoke_summary


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_RUN_ID = str(time.time_ns())
_TEMP_COUNTER = 0


def temp_root() -> Path:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    root = TEST_TMP_ROOT / f"real-worker-smoke-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    root.mkdir(parents=True, exist_ok=False)
    return root


class RealWorkerSmokeTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_smoke_passes_with_fake_codex_runner(self) -> None:
        root = temp_root()

        report = RealWorkerSmoke(runner=fake_codex_runner).run(
            output_dir=root / "out",
            codex_executable=sys.executable,
            timeout_seconds=30,
        )
        payload = report.to_dict()

        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["worker_result"]["status"], "completed")
        self.assertEqual(payload["verification"]["status"], "passed")
        self.assertIn("return a + b", payload["repository"]["app_py"])
        self.assertTrue((root / "out" / "real_worker_smoke_report.json").exists())

    def test_smoke_blocks_when_codex_executable_missing(self) -> None:
        root = temp_root()

        report = RealWorkerSmoke().run(
            output_dir=root / "out",
            codex_executable=str(root / "missing-codex.exe"),
            timeout_seconds=30,
        )
        payload = report.to_dict()

        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["preflight"]["status"], "blocked")
        self.assertTrue(payload["blockers"])

    def test_smoke_summary_shape(self) -> None:
        summary = smoke_summary(
            {
                "status": "passed",
                "output_dir": "out",
                "preflight": {"status": "passed"},
                "worker_result": {"status": "completed"},
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
                "worker_status": "completed",
                "verification_status": "passed",
                "blocker_count": 0,
            },
        )


def fake_codex_runner(args, *, cwd, input, capture_output, text, timeout, check):
    if args[:3] == ["git", "status", "--porcelain"]:
        return subprocess.CompletedProcess(args, 0, "", "")
    repo = Path(cwd)
    (repo / "app.py").write_text(
        "\n".join(
            [
                '"""Tiny fixture module for the real worker smoke."""',
                "",
                "def add(a, b):",
                "    return a + b",
                "",
            ]
        ),
        encoding="utf-8",
    )
    payload = {
        "task_id": "T-REAL-SMOKE-001",
        "status": "completed",
        "summary": "Implemented add().",
        "files_changed": ["app.py"],
        "commands_run": [{"command": "python -c ...", "exit_code": 0, "summary": "passed"}],
        "tests_passed": ["python add assertion"],
        "tests_failed": [],
        "evidence": ["app.add(2, 3) == 5"],
        "known_issues": [],
        "follow_up_tasks": [],
        "confidence": 0.9,
    }
    return subprocess.CompletedProcess(args, 0, json.dumps(payload).encode("utf-8"), b"")


if __name__ == "__main__":
    unittest.main()
