from __future__ import annotations

import json
import shutil
import subprocess
import time
import unittest
from pathlib import Path

from autodev.github_pr_lifecycle import GitHubPRLifecycle, lifecycle_summary


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_RUN_ID = str(time.time_ns())
_TEMP_COUNTER = 0


def temp_root() -> Path:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    root = TEST_TMP_ROOT / f"github-pr-lifecycle-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    root.mkdir(parents=True, exist_ok=False)
    return root


class GitHubPRLifecycleTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_inspect_writes_report_without_mutation(self) -> None:
        root = temp_root()
        calls: list[list[str]] = []

        def fake_runner(args, *, cwd, capture_output, text, check):
            calls.append(args)
            if args[:3] == ["gh", "pr", "view"]:
                return subprocess.CompletedProcess(args, 0, json.dumps(pr_payload()) + "\n", "")
            if args[:3] == ["gh", "pr", "checks"]:
                return subprocess.CompletedProcess(args, 0, json.dumps([{"name": "tests", "bucket": "pass"}]) + "\n", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        report = GitHubPRLifecycle(runner=fake_runner).run(
            repository_path=root,
            selector="3",
            output_dir=root / "out",
        ).to_dict()

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["action"], "inspect")
        self.assertEqual(report["pull_request"]["number"], 3)
        self.assertEqual(report["checks"][0]["bucket"], "pass")
        self.assertFalse(any(call[:3] == ["gh", "pr", "close"] for call in calls))
        self.assertTrue((root / "out" / "github_pr_lifecycle_report.json").exists())

    def test_ready_without_confirm_is_planned_and_non_mutating(self) -> None:
        root = temp_root()
        calls: list[list[str]] = []

        def fake_runner(args, *, cwd, capture_output, text, check):
            calls.append(args)
            if args[:3] == ["gh", "pr", "view"]:
                return subprocess.CompletedProcess(args, 0, json.dumps(pr_payload(is_draft=True)) + "\n", "")
            if args[:3] == ["gh", "pr", "checks"]:
                return subprocess.CompletedProcess(args, 0, "[]\n", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        report = GitHubPRLifecycle(runner=fake_runner).run(
            repository_path=root,
            selector="3",
            action="ready",
            output_dir=root / "out",
        ).to_dict()

        self.assertEqual(report["status"], "planned")
        self.assertEqual(report["warnings"][0]["id"], "W-PR-LIFECYCLE-CONFIRMATION-REQUIRED")
        self.assertFalse(any(call[:3] == ["gh", "pr", "ready"] for call in calls))

    def test_close_with_confirm_can_delete_branch(self) -> None:
        root = temp_root()
        calls: list[list[str]] = []
        viewed = {"count": 0}

        def fake_runner(args, *, cwd, capture_output, text, check):
            calls.append(args)
            if args[:3] == ["gh", "pr", "view"]:
                viewed["count"] += 1
                payload = pr_payload(state="CLOSED" if viewed["count"] > 1 else "OPEN")
                return subprocess.CompletedProcess(args, 0, json.dumps(payload) + "\n", "")
            if args[:3] == ["gh", "pr", "checks"]:
                return subprocess.CompletedProcess(args, 0, "[]\n", "")
            if args == ["gh", "pr", "close", "3", "--delete-branch"]:
                return subprocess.CompletedProcess(args, 0, "Closed pull request #3\n", "")
            return subprocess.CompletedProcess(args, 1, "", "unexpected command")

        report = GitHubPRLifecycle(runner=fake_runner).run(
            repository_path=root,
            selector="3",
            action="close",
            delete_branch=True,
            confirm=True,
            output_dir=root / "out",
        ).to_dict()

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["pull_request"]["state"], "CLOSED")
        self.assertIn(["gh", "pr", "close", "3", "--delete-branch"], calls)

    def test_lifecycle_summary_outputs_compact_status(self) -> None:
        payload = {
            "status": "passed",
            "action": "inspect",
            "selector": "3",
            "pull_request": pr_payload(),
            "blockers": [],
            "warnings": [],
        }

        summary = lifecycle_summary(payload)

        self.assertEqual(summary["status"], "passed")
        self.assertEqual(summary["number"], 3)
        self.assertEqual(summary["url"], "https://github.example/pull/3")
        self.assertEqual(summary["is_draft"], True)


def pr_payload(*, state: str = "OPEN", is_draft: bool = True) -> dict[str, object]:
    return {
        "number": 3,
        "url": "https://github.example/pull/3",
        "state": state,
        "isDraft": is_draft,
        "headRefName": "agent/probe",
        "baseRefName": "master",
        "mergeStateStatus": "CLEAN",
        "statusCheckRollup": [],
    }


if __name__ == "__main__":
    unittest.main()
