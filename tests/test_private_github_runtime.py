from __future__ import annotations

import shutil
import subprocess
import time
import unittest
from pathlib import Path

from intake.github_source import parse_github_source
from intake.private_github_runtime import PrivateGitHubSourceRuntime


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_RUN_ID = str(time.time_ns())
_TEMP_COUNTER = 0


def temp_root() -> Path:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    root = TEST_TMP_ROOT / f"private-github-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    root.mkdir(parents=True, exist_ok=False)
    return root


class PrivateGitHubSourceRuntimeTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_private_clone_uses_gh_after_auth_preflight(self) -> None:
        root = temp_root()
        repo = parse_github_source(
            "https://github.com/example/private-repo",
            project_id="proj_private",
            visibility="private",
            local_path=str(root / "repo"),
        )
        self.assertIsNotNone(repo)
        calls: list[list[str]] = []

        def runner(args, *, cwd, capture_output, text, check):
            calls.append(args)
            if args == ["gh", "--version"]:
                return subprocess.CompletedProcess(args, 0, "gh version 2.0.0\n", "")
            if args == ["gh", "auth", "status"]:
                return subprocess.CompletedProcess(args, 0, "✓ Logged in to github.com account octocat\n", "")
            if args[:3] == ["gh", "repo", "clone"]:
                return subprocess.CompletedProcess(args, 0, "cloned\n", "")
            return subprocess.CompletedProcess(args, 1, "", "unexpected")

        result = PrivateGitHubSourceRuntime(runner=runner).prepare(repo)  # type: ignore[arg-type]

        self.assertEqual(result.status, "available")
        self.assertEqual(result.repository.access_status, "available")
        self.assertIn(["gh", "repo", "clone", "example/private-repo", str(root / "repo"), "--", "--branch", "main", "--single-branch"], calls)
        self.assertEqual(result.auth["account"], "octocat")

    def test_private_fetch_existing_checkout_uses_git_after_auth_preflight(self) -> None:
        root = temp_root()
        checkout = root / "repo"
        (checkout / ".git").mkdir(parents=True)
        repo = parse_github_source(
            "https://github.com/example/private-repo",
            project_id="proj_private",
            visibility="private",
            local_path=str(checkout),
        )
        self.assertIsNotNone(repo)
        calls: list[list[str]] = []

        def runner(args, *, cwd, capture_output, text, check):
            calls.append(args)
            if args == ["gh", "--version"]:
                return subprocess.CompletedProcess(args, 0, "gh version 2.0.0\n", "")
            if args == ["gh", "auth", "status"]:
                return subprocess.CompletedProcess(args, 0, "✓ Logged in to github.com account octocat\n", "")
            return subprocess.CompletedProcess(args, 0, "ok\n", "")

        result = PrivateGitHubSourceRuntime(runner=runner).prepare(repo)  # type: ignore[arg-type]

        self.assertEqual(result.status, "available")
        self.assertIn(["git", "fetch", "origin", "main"], calls)
        self.assertIn(["git", "checkout", "-B", "main", "origin/main"], calls)

    def test_private_runtime_blocks_when_gh_auth_is_missing(self) -> None:
        root = temp_root()
        repo = parse_github_source(
            "https://github.com/example/private-repo",
            project_id="proj_private",
            visibility="private",
            local_path=str(root / "repo"),
        )
        self.assertIsNotNone(repo)

        def runner(args, *, cwd, capture_output, text, check):
            if args == ["gh", "--version"]:
                return subprocess.CompletedProcess(args, 0, "gh version 2.0.0\n", "")
            if args == ["gh", "auth", "status"]:
                return subprocess.CompletedProcess(args, 1, "", "not logged in")
            return subprocess.CompletedProcess(args, 1, "", "unexpected")

        result = PrivateGitHubSourceRuntime(runner=runner).prepare(repo)  # type: ignore[arg-type]

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.repository.access_status, "auth_required")
        self.assertEqual(result.blockers[0].code, "github_cli_auth_required")


if __name__ == "__main__":
    unittest.main()
