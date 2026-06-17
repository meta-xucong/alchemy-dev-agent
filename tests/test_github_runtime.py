from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from intake.github_runtime import GitHubSourceRuntime
from intake.github_source import parse_github_source


TEST_TMP_ROOT = Path(tempfile.gettempdir()) / "alchemy-dev-agent-github-runtime-tests"
_TEMP_COUNTER = 0
_TEMP_RUN_ID = str(time.time_ns())


@contextmanager
def temp_git_dir() -> Iterator[Path]:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    path = TEST_TMP_ROOT / f"github-runtime-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=False)


def assert_git_ok(result: subprocess.CompletedProcess) -> None:
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)


def create_local_remote(root: Path) -> Path:
    source = root / "source"
    remote = root / "remote.git"
    source.mkdir()
    assert_git_ok(run_git(["init"], source))
    assert_git_ok(run_git(["checkout", "-B", "main"], source))
    assert_git_ok(run_git(["config", "user.email", "alchemy@example.test"], source))
    assert_git_ok(run_git(["config", "user.name", "Alchemy Test"], source))
    (source / "README.md").write_text("# Remote Repo\n", encoding="utf-8")
    assert_git_ok(run_git(["add", "README.md"], source))
    assert_git_ok(run_git(["commit", "-m", "initial"], source))
    assert_git_ok(run_git(["clone", "--bare", str(source), str(remote)], root))
    return remote


class GitHubSourceRuntimeTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_clones_public_repository_source(self) -> None:
        with temp_git_dir() as root:
            remote = create_local_remote(root)
            target = root / "checkout"
            repository = parse_github_source(
                "https://github.com/example/repo",
                project_id="proj_test",
                visibility="public",
                local_path=str(target),
            )
            repository.url = str(remote)

            result = GitHubSourceRuntime().prepare(repository)

            self.assertEqual(result.status, "available", result.to_dict())
            self.assertTrue((target / ".git").exists())
            self.assertTrue((target / "README.md").exists())
            self.assertEqual(result.repository.access_status, "available")
            self.assertFalse(result.repository.gh_auth_required)
            self.assertEqual(result.blockers, [])

    def test_fetches_existing_public_checkout(self) -> None:
        with temp_git_dir() as root:
            remote = create_local_remote(root)
            target = root / "checkout"
            clone = subprocess.run(["git", "clone", str(remote), str(target)], capture_output=True, text=True, check=False)
            self.assertEqual(clone.returncode, 0, clone.stderr or clone.stdout)
            repository = parse_github_source(
                "https://github.com/example/repo",
                project_id="proj_test",
                visibility="public",
                local_path=str(target),
            )
            repository.url = str(remote)

            result = GitHubSourceRuntime().prepare(repository)

            self.assertEqual(result.status, "available", result.to_dict())
            self.assertIn(["git", "fetch", "origin", "main"], result.commands_run)
            self.assertIn(["git", "checkout", "-B", "main", "origin/main"], result.commands_run)

    def test_private_repository_is_optional_blocked_path(self) -> None:
        repository = parse_github_source(
            "https://github.com/example/private-repo",
            project_id="proj_test",
            visibility="private",
        )

        result = GitHubSourceRuntime().prepare(repository)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.blockers[0].code, "private_repository_not_supported_in_public_runtime")
        self.assertTrue(result.repository.gh_auth_required)
        self.assertEqual(result.repository.access_status, "auth_required")


if __name__ == "__main__":
    unittest.main()
