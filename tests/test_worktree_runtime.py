from __future__ import annotations

import shutil
import subprocess
import time
import unittest
from pathlib import Path

from runtime import RealRunWorkspace


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_RUN_ID = str(time.time_ns())
_TEMP_COUNTER = 0


def temp_root() -> Path:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    root = TEST_TMP_ROOT / f"worktree-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "README.md").write_text("# fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True, text=True)


class RealRunWorkspaceTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_disabled_workspace_uses_source_path(self) -> None:
        root = temp_root()
        repo = root / "repo"
        init_git_repo(repo)

        session = RealRunWorkspace().prepare(source_path=repo, output_dir=root / "run", enabled=False)

        self.assertEqual(session.status, "skipped")
        self.assertFalse(session.enabled)
        self.assertEqual(Path(session.execution_path), repo.resolve())
        self.assertIn("disabled", session.warnings[0])

    def test_prepare_creates_isolated_worktree_and_cleanup_removes_it(self) -> None:
        root = temp_root()
        repo = root / "repo"
        init_git_repo(repo)

        workspace = RealRunWorkspace()
        session = workspace.prepare(
            source_path=repo,
            output_dir=root / "run",
            enabled=True,
            keep=False,
            branch_prefix="agent/test-real-run",
        )

        self.assertEqual(session.status, "ready", session.to_dict())
        self.assertTrue(Path(session.worktree_path).exists())
        self.assertNotEqual(Path(session.worktree_path).resolve(), repo.resolve())
        self.assertTrue((Path(session.worktree_path) / "README.md").exists())

        (Path(session.worktree_path) / "generated.txt").write_text("worker output\n", encoding="utf-8")
        cleaned = workspace.cleanup(session)

        self.assertEqual(cleaned.status, "cleaned", cleaned.to_dict())
        self.assertFalse(Path(session.worktree_path).exists())

        branch_check = subprocess.run(
            ["git", "rev-parse", "--verify", session.branch],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(branch_check.returncode, 0)

    def test_prepare_blocks_for_non_git_source(self) -> None:
        root = temp_root()
        source = root / "not-repo"
        source.mkdir()

        session = RealRunWorkspace().prepare(source_path=source, output_dir=root / "run", enabled=True)

        self.assertEqual(session.status, "blocked")
        self.assertTrue(session.blockers)
        self.assertIn("must be a git repository root", session.blockers[0])

    def test_prepare_blocks_for_path_outside_any_git_repo(self) -> None:
        root = temp_root()
        source = (Path(__file__).resolve().parents[2] / f".worktree-non-git-test-{_TEMP_RUN_ID}").resolve()
        if source.exists():
            shutil.rmtree(source, ignore_errors=True)
        source.mkdir(parents=True)
        try:
            session = RealRunWorkspace().prepare(source_path=source, output_dir=root / "run", enabled=True)
        finally:
            shutil.rmtree(source, ignore_errors=True)

        self.assertEqual(session.status, "blocked")
        self.assertTrue(session.blockers)
        self.assertIn("not inside a git repository", session.blockers[0])

    def test_prepare_blocks_when_source_has_uncommitted_changes(self) -> None:
        root = temp_root()
        repo = root / "repo"
        init_git_repo(repo)
        (repo / "README.md").write_text("# dirty\n", encoding="utf-8")

        session = RealRunWorkspace().prepare(source_path=repo, output_dir=root / "run", enabled=True)

        self.assertEqual(session.status, "blocked")
        self.assertTrue(session.blockers)
        self.assertIn("uncommitted changes", session.blockers[0])

    def test_dirty_check_ignores_only_the_exact_output_directory(self) -> None:
        root = temp_root()
        repo = root / "repo"
        init_git_repo(repo)
        (repo / ".alchemy" / "run" / "workspaces").mkdir(parents=True)
        (repo / ".alchemy" / "run" / "workspaces" / "ignored.txt").write_text("run artifact\n", encoding="utf-8")
        (repo / ".alchemy" / "other.txt").write_text("real dirty file\n", encoding="utf-8")

        session = RealRunWorkspace().prepare(
            source_path=repo,
            output_dir=repo / ".alchemy" / "run" / "workspaces",
            enabled=True,
        )

        self.assertEqual(session.status, "blocked")
        self.assertTrue(session.blockers)
        self.assertIn(".alchemy/other.txt", session.blockers[0])
        self.assertNotIn("ignored.txt", session.blockers[0])


if __name__ == "__main__":
    unittest.main()
