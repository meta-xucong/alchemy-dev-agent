from __future__ import annotations

import json
import shutil
import subprocess
import time
import unittest
from pathlib import Path

from autodev.real_readiness_probe import RealReadinessProbe, readiness_summary


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_RUN_ID = str(time.time_ns())
_TEMP_COUNTER = 0


def temp_root() -> Path:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    root = TEST_TMP_ROOT / f"real-readiness-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    root.mkdir(parents=True, exist_ok=False)
    return root


class RealReadinessProbeTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_probe_reports_ready_with_fake_tools(self) -> None:
        root = temp_root()
        fake_codex = root / "codex.exe"
        fake_codex.write_text("", encoding="utf-8")

        report = RealReadinessProbe(
            env_runner=ready_env_runner(fake_codex),
            preflight_runner=ready_preflight_runner(fake_codex),
        ).run(output_dir=root / "out", codex_executable=str(fake_codex), include_private_github=True)
        payload = report.to_dict()

        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["environment"]["status"], "ready")
        self.assertEqual(len(payload["request_preflights"]), 2)
        self.assertTrue(all(item["status"] == "passed" for item in payload["request_preflights"]))
        self.assertTrue((root / "out" / "real_readiness_report.json").exists())
        summary = readiness_summary(payload)
        self.assertEqual(summary["blocker_count"], 0)

    def test_probe_reports_blocked_when_codex_missing(self) -> None:
        root = temp_root()
        missing_codex = root / "missing-codex.exe"

        report = RealReadinessProbe(
            env_runner=ready_env_runner(missing_codex),
            preflight_runner=ready_preflight_runner(missing_codex),
        ).run(output_dir=root / "out", codex_executable=str(missing_codex))
        payload = report.to_dict()

        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(any("codex" in str(blocker).lower() for blocker in payload["blockers"]))

    def test_cli_summary_shape_from_report(self) -> None:
        report = {
            "status": "ready",
            "output_dir": "out",
            "environment": {"status": "ready"},
            "request_preflights": [{"name": "local_real_pr", "status": "passed", "blockers": [], "warnings": []}],
            "blockers": [],
            "warnings": [],
        }

        summary = readiness_summary(report)

        self.assertEqual(
            summary,
            {
                "status": "ready",
                "output_dir": "out",
                "environment_status": "ready",
                "request_preflights": [
                    {"name": "local_real_pr", "status": "passed", "blocker_count": 0, "warning_count": 0}
                ],
                "blocker_count": 0,
                "warning_count": 0,
            },
        )


def ready_env_runner(fake_codex: Path):
    def runner(args, *, cwd, capture_output, text, check, timeout):
        if args[0] == str(fake_codex):
            return subprocess.CompletedProcess(args, 0, b"codex-cli test\n", b"")
        if args == ["gh", "auth", "status"]:
            return subprocess.CompletedProcess(args, 0, b"Logged in to github.com account test-user\n", b"")
        return subprocess.CompletedProcess(args, 0, b"tool version\n", b"")

    return runner


def ready_preflight_runner(fake_codex: Path):
    def runner(args, *, cwd, capture_output, text, check):
        if args[0] == str(fake_codex):
            return subprocess.CompletedProcess(args, 0, "codex-cli test\n", "")
        if args == ["gh", "auth", "status"]:
            return subprocess.CompletedProcess(args, 0, "Logged in to github.com account test-user\n", "")
        return subprocess.CompletedProcess(args, 0, "tool version\n", "")

    return runner


if __name__ == "__main__":
    unittest.main()
