from __future__ import annotations

import shutil
import subprocess
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from autodev.preflight import ExecutionPreflight


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_COUNTER = 0
_TEMP_RUN_ID = str(time.time_ns())


@contextmanager
def temp_preflight_dir() -> Iterator[Path]:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    path = TEST_TMP_ROOT / f"preflight-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class ExecutionPreflightTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_dry_run_preflight_skips_codex_and_gh(self) -> None:
        with temp_preflight_dir() as repo:
            result = ExecutionPreflight().check(repository_path=repo)

        payload = result.to_dict()
        self.assertEqual(payload["status"], "passed")
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual(checks["repository_path"]["status"], "passed")
        self.assertEqual(checks["codex"]["status"], "skipped")
        self.assertEqual(checks["gh"]["status"], "skipped")

    def test_real_codex_requires_executable(self) -> None:
        with temp_preflight_dir() as repo:
            result = ExecutionPreflight().check(
                repository_path=repo,
                real_codex=True,
                codex_executable="definitely-missing-codex-for-test",
            )

        payload = result.to_dict()
        self.assertEqual(payload["status"], "blocked")
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual(checks["codex"]["status"], "failed")
        self.assertTrue(checks["codex"]["required"])

    def test_runner_failure_marks_command_failed(self) -> None:
        def failing_runner(args, *, cwd, capture_output, text, check):
            return subprocess.CompletedProcess(args, 2, "", "bad version")

        with temp_preflight_dir() as repo:
            result = ExecutionPreflight(runner=failing_runner).check(
                repository_path=repo,
                real_codex=True,
                codex_executable="git",
            )

        checks = {check.name: check for check in result.checks}
        self.assertEqual(checks["codex"].status, "failed")


if __name__ == "__main__":
    unittest.main()
