from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

from autodev.real_unified_delivery import (
    RealUnifiedDeliveryHarness,
    build_unified_run_command,
    has_passing_browser_evidence,
    report_summary,
)
from autodev.unified_request import AutoDevRunRequest


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_RUN_ID = str(time.time_ns())
_TEMP_COUNTER = 0


def temp_root() -> Path:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    root = TEST_TMP_ROOT / f"real-unified-delivery-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    root.mkdir(parents=True, exist_ok=False)
    return root


class RealUnifiedDeliveryTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_build_unified_run_command_preserves_real_flags(self) -> None:
        request = AutoDevRunRequest.from_mapping(
            {
                "objective": "Ship docs",
                "documents": ["spec.md"],
                "repository_path": "repo",
                "real_codex": True,
                "real_github": True,
                "auto_browser_verify": True,
                "github_collect_ci": False,
                "generate_static_ci": False,
                "write_native_ui_tests": True,
                "auto_merge": True,
                "output_dir": "out",
            }
        )

        command = build_unified_run_command(request)

        self.assertIn("autodev.run", command)
        self.assertIn("--real-codex", command)
        self.assertIn("--real-github", command)
        self.assertIn("--auto-browser-verify", command)
        self.assertIn("--no-github-ci", command)
        self.assertIn("--no-generate-static-ci", command)
        self.assertIn("--write-native-ui-tests", command)
        self.assertIn("--auto-merge", command)

    def test_harness_passes_document_local_dry_run(self) -> None:
        root = temp_root()
        repo = write_repo(root)
        spec = write_spec(root)
        output = root / "out"
        probe_root = root / "probes"
        write_probe_index_fixture(probe_root)

        report = RealUnifiedDeliveryHarness().run(
            {
                "objective": "Add workspace support",
                "documents": [str(spec)],
                "repository_path": str(repo),
                "legacy_unlocked": True,
                "output_dir": str(output),
            },
            probe_index_root=probe_root,
            require_probe_index=True,
        ).to_dict()

        self.assertEqual(report["status"], "passed")
        gates = {gate["name"]: gate for gate in report["gates"]}
        self.assertEqual(gates["preflight_passed"]["status"], "passed")
        self.assertEqual(gates["unified_command_exit_zero"]["status"], "passed")
        self.assertEqual(gates["unified_run_done"]["status"], "passed")
        self.assertEqual(gates["delivery_ready_for_review"]["status"], "passed")
        self.assertEqual(gates["real_probe_index_available"]["status"], "passed")
        self.assertTrue((output / "real_unified_delivery_report.json").exists())
        self.assertTrue((output / "unified_run_report.json").exists())
        self.assertTrue((output / "document_run_report.json").exists())
        summary = report_summary(report)
        self.assertEqual(summary["status"], "passed")
        self.assertEqual(summary["failed_required_gates"], [])

    def test_harness_blocks_when_unified_cli_fails(self) -> None:
        root = temp_root()
        repo = write_repo(root)
        spec = write_spec(root)
        output = root / "out"

        def fake_runner(args, *, cwd, capture_output, text, check):
            return subprocess.CompletedProcess(args, 2, "", "boom")

        report = RealUnifiedDeliveryHarness(runner=fake_runner).run(
            {
                "objective": "Add workspace support",
                "documents": [str(spec)],
                "repository_path": str(repo),
                "legacy_unlocked": True,
                "output_dir": str(output),
            },
            include_probe_index=False,
        ).to_dict()

        self.assertEqual(report["status"], "blocked")
        self.assertTrue(any(blocker["id"] == "B-V2-47-UNIFIED-COMMAND" for blocker in report["blockers"]))
        self.assertTrue(any(gate["name"] == "unified_command_exit_zero" and gate["status"] == "failed" for gate in report["gates"]))

    def test_completed_browser_evidence_with_no_failures_passes_gate(self) -> None:
        artifact_report = {
            "browser_verification": {
                "status": "completed",
                "tests_failed": [],
                "console_errors": [],
                "tests_passed": ["browser artifact evidence"],
            }
        }

        self.assertTrue(has_passing_browser_evidence(artifact_report))

    def test_cli_outputs_summary(self) -> None:
        root = temp_root()
        repo = write_repo(root)
        spec = write_spec(root)
        output = root / "out"

        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "autodev.real_unified_delivery",
                "--objective",
                "Add workspace support",
                "--document",
                str(spec),
                "--repository-path",
                str(repo),
                "--legacy-unlocked",
                "--output",
                str(output),
                "--no-probe-index",
                "--summary",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["route"], "document_run")
        self.assertEqual(payload["execution_mode"], "dry_run")
        self.assertTrue((output / "real_unified_delivery_report.json").exists())


def write_repo(root: Path) -> Path:
    repo = root / "repo"
    (repo / "src" / "api").mkdir(parents=True)
    (repo / "src" / "pages").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src" / "api" / "workspaces.ts").write_text("export const api = true;\n", encoding="utf-8")
    (repo / "src" / "pages" / "dashboard.tsx").write_text("export const ui = true;\n", encoding="utf-8")
    (repo / "tests" / "workspaces.test.ts").write_text("test('workspace', () => {});\n", encoding="utf-8")
    (repo / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
    return repo


def write_spec(root: Path) -> Path:
    spec = root / "spec.md"
    spec.write_text(
        "\n".join(
            [
                "# Development Spec",
                "",
                "## Objective",
                "Add workspace support.",
                "",
                "## Requirements",
                "- Must add workspace API support in src/api/workspaces.ts.",
                "- Must add dashboard workspace switching in src/pages/dashboard.tsx.",
                "",
                "## Acceptance",
                "- Users can create a workspace.",
                "- Users can switch active workspace.",
            ]
        ),
        encoding="utf-8",
    )
    return spec


def write_probe_index_fixture(root: Path) -> None:
    report = root / "github" / "real_delivery_validation_report.json"
    report.parent.mkdir(parents=True)
    report.write_text(
        json.dumps(
            {
                "status": "passed",
                "branch": "agent/probe",
                "base_branch": "master",
                "github": {
                    "status": "pushed",
                    "commit": "abc123",
                    "pull_request_url": "https://github.example/pull/3",
                    "ci_status": "passed",
                    "merge": {"status": "skipped"},
                },
                "workspace": {"status": "ready"},
                "blockers": [],
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
