from __future__ import annotations

import subprocess
import unittest

from intake.gh_auth import GitHubAuthPreflight, account_from_auth_status, auth_summary


class GitHubAuthPreflightTests(unittest.TestCase):
    def test_parses_account_without_tokens(self) -> None:
        text = "github.com\n  ✓ Logged in to github.com account octocat (/home/user/.config/gh/hosts.yml)\n  ✓ Git operations for github.com configured.\n"

        self.assertEqual(account_from_auth_status(text), "octocat")
        self.assertNotIn("token", auth_summary("✓ Token: secret\n✓ Logged in to github.com account octocat\n").lower())

    def test_authenticated_gh_passes(self) -> None:
        def runner(args, *, cwd, capture_output, text, check):
            if args == ["gh", "--version"]:
                return subprocess.CompletedProcess(args, 0, "gh version 2.0.0\n", "")
            if args == ["gh", "auth", "status"]:
                return subprocess.CompletedProcess(args, 0, "✓ Logged in to github.com account octocat\n", "")
            return subprocess.CompletedProcess(args, 1, "", "unexpected")

        result = GitHubAuthPreflight(runner=runner).check(required=True)

        self.assertEqual(result.status, "passed")
        self.assertEqual(result.account, "octocat")

    def test_unauthenticated_gh_blocks_when_required(self) -> None:
        def runner(args, *, cwd, capture_output, text, check):
            if args == ["gh", "--version"]:
                return subprocess.CompletedProcess(args, 0, "gh version 2.0.0\n", "")
            if args == ["gh", "auth", "status"]:
                return subprocess.CompletedProcess(args, 1, "", "You are not logged into any GitHub hosts.\n")
            return subprocess.CompletedProcess(args, 1, "", "unexpected")

        result = GitHubAuthPreflight(runner=runner).check(required=True)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.checks[-1].name, "gh_auth")


if __name__ == "__main__":
    unittest.main()
