from __future__ import annotations

import subprocess
import time
import unittest
from pathlib import Path

from autodev.real_env_check import EnvironmentCheck, RealEnvironmentCheck, decode_output, redact


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"


class RealEnvironmentCheckTests(unittest.TestCase):
    def test_redacts_token_lines(self) -> None:
        text = "github.com\n  - Token: gho_secret\n  - Token scopes: repo\n"

        redacted = redact(text)

        self.assertIn("Token: [redacted]", redacted)
        self.assertNotIn("gho_secret", redacted)

    def test_environment_check_payload(self) -> None:
        check = EnvironmentCheck("codex", "failed", "Access denied")

        self.assertEqual(
            check.to_dict(),
            {
                "name": "codex",
                "status": "failed",
                "summary": "Access denied",
                "required": True,
            },
        )

    def test_decode_output_replaces_invalid_bytes(self) -> None:
        self.assertIn("�", decode_output(b"\xff"))

    def test_check_uses_explicit_codex_executable(self) -> None:
        calls: list[list[str]] = []
        output = TEST_TMP_ROOT / f"real-env-{time.time_ns()}"
        output.mkdir(parents=True, exist_ok=True)
        fake_codex = output / "custom-codex.exe"
        fake_codex.write_text("", encoding="utf-8")

        def fake_runner(args, *, cwd, capture_output, text, check, timeout):
            calls.append(args)
            if Path(args[0]).name == "custom-codex.exe":
                return subprocess.CompletedProcess(args, 0, b"codex-cli 0.141.0\n", b"")
            if args == ["gh", "auth", "status"]:
                return subprocess.CompletedProcess(args, 0, b"Logged in\n", b"")
            return subprocess.CompletedProcess(args, 0, b"tool version\n", b"")

        report = RealEnvironmentCheck(runner=fake_runner).run(output_dir=output, codex_executable=str(fake_codex))

        self.assertEqual(report.status, "ready")
        self.assertIn([str(fake_codex), "--version"], calls)
        self.assertTrue((output / "real_environment_report.json").exists())

    def test_browser_automation_check_is_optional_by_default(self) -> None:
        output = TEST_TMP_ROOT / f"real-env-browser-optional-{time.time_ns()}"
        output.mkdir(parents=True, exist_ok=True)
        fake_codex = output / "custom-codex.exe"
        fake_codex.write_text("", encoding="utf-8")

        def fake_runner(args, *, cwd, capture_output, text, check, timeout):
            if Path(args[0]).name == "custom-codex.exe":
                return subprocess.CompletedProcess(args, 0, b"codex-cli 0.141.0\n", b"")
            if args == ["gh", "auth", "status"]:
                return subprocess.CompletedProcess(args, 0, b"Logged in\n", b"")
            return subprocess.CompletedProcess(args, 0, b"tool version\n", b"")

        report = RealEnvironmentCheck(runner=fake_runner).run(output_dir=output, codex_executable=str(fake_codex))
        checks = {check.name: check for check in report.checks}

        self.assertEqual(report.status, "ready")
        self.assertIn(checks["browser_automation"].status, {"passed", "skipped"})
        self.assertFalse(checks["browser_automation"].required)

    def test_browser_automation_can_be_required(self) -> None:
        output = TEST_TMP_ROOT / f"real-env-browser-required-{time.time_ns()}"
        output.mkdir(parents=True, exist_ok=True)
        fake_codex = output / "custom-codex.exe"
        fake_codex.write_text("", encoding="utf-8")

        def fake_runner(args, *, cwd, capture_output, text, check, timeout):
            if Path(args[0]).name == "custom-codex.exe":
                return subprocess.CompletedProcess(args, 0, b"codex-cli 0.141.0\n", b"")
            if args == ["gh", "auth", "status"]:
                return subprocess.CompletedProcess(args, 0, b"Logged in\n", b"")
            return subprocess.CompletedProcess(args, 0, b"tool version\n", b"")

        report = RealEnvironmentCheck(runner=fake_runner).run(
            output_dir=output,
            codex_executable=str(fake_codex),
            require_browser=True,
        )
        browser = {check.name: check for check in report.checks}["browser_automation"]

        if browser.status == "failed":
            self.assertEqual(report.status, "blocked")
            self.assertTrue(browser.required)
        else:
            self.assertEqual(report.status, "ready")


if __name__ == "__main__":
    unittest.main()
