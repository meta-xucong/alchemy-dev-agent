"""Isolated git worktree lifecycle for real worker runs."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from .subprocess_utils import clean_git_env, run_hidden


class WorktreeRunner(Protocol):
    def __call__(
        self,
        args: list[str],
        *,
        cwd: str | Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        ...


@dataclass(slots=True)
class WorktreeCommand:
    command: list[str]
    cwd: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "command": list(self.command),
            "cwd": self.cwd,
            "exit_code": self.exit_code,
            "stdout": _trim(self.stdout),
            "stderr": _trim(self.stderr),
        }


@dataclass(slots=True)
class WorktreeSession:
    enabled: bool
    status: str
    source_path: str
    execution_path: str
    worktree_path: str = ""
    branch: str = ""
    keep: bool = True
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    commands_run: list[WorktreeCommand] = field(default_factory=list)

    @classmethod
    def skipped(cls, source_path: str | Path, reason: str) -> "WorktreeSession":
        resolved = str(Path(source_path).resolve())
        return cls(
            enabled=False,
            status="skipped",
            source_path=resolved,
            execution_path=resolved,
            warnings=[reason],
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "status": self.status,
            "source_path": self.source_path,
            "execution_path": self.execution_path,
            "worktree_path": self.worktree_path,
            "branch": self.branch,
            "keep": self.keep,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "commands_run": [command.to_dict() for command in self.commands_run],
        }


class RealRunWorkspace:
    """Prepare and optionally clean an isolated git worktree for real Codex runs."""

    def __init__(self, runner: WorktreeRunner = subprocess.run) -> None:
        self.runner = runner

    def prepare(
        self,
        *,
        source_path: str | Path,
        output_dir: str | Path,
        enabled: bool = True,
        keep: bool = True,
        branch_prefix: str = "agent/alchemy-real-run",
    ) -> WorktreeSession:
        source = Path(source_path).resolve()
        if not enabled:
            return WorktreeSession.skipped(source, "Real-run worktree isolation is disabled.")

        session = WorktreeSession(
            enabled=True,
            status="blocked",
            source_path=str(source),
            execution_path=str(source),
            keep=keep,
        )
        if not source.exists():
            session.blockers.append(f"Source repository path does not exist: {source}")
            return session
        if not source.is_dir():
            session.blockers.append(f"Source repository path is not a directory: {source}")
            return session

        repo_root = self._repo_root(source, session)
        if repo_root is None:
            session.blockers.append(f"Source path is not inside a git repository: {source}")
            return session
        if repo_root != source:
            session.blockers.append(f"Source path must be a git repository root for isolated real execution: {source}")
            return session

        dirty_paths = self._dirty_paths(repo_root, session)
        visible_dirty_paths = self._exclude_output_paths(dirty_paths, repo_root, Path(output_dir).resolve())
        if visible_dirty_paths:
            session.blockers.append(
                "Source repository has uncommitted changes; commit, stash, or clean them before isolated real execution: "
                + ", ".join(visible_dirty_paths[:10])
            )
            return session

        output = Path(output_dir).resolve()
        output.mkdir(parents=True, exist_ok=True)
        suffix = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
        branch = self._unique_branch(repo_root, f"{branch_prefix}-{suffix}", session)
        target = output / f"real_run_worktree_{suffix}"
        add_result = self._run(["git", "worktree", "add", "-b", branch, str(target), "HEAD"], cwd=repo_root, session=session)
        if add_result.returncode != 0:
            session.blockers.append(add_result.stderr.strip() or add_result.stdout.strip() or "git worktree add failed.")
            return session

        session.status = "ready"
        session.branch = branch
        session.worktree_path = str(target)
        session.execution_path = str(target)

        worktree_dirty = self._dirty_paths(target, session)
        if worktree_dirty:
            session.status = "blocked"
            session.blockers.append("New worktree is not clean after creation: " + ", ".join(worktree_dirty[:10]))
        return session

    def cleanup(self, session: WorktreeSession, *, remove_branch: bool = True) -> WorktreeSession:
        if not session.enabled or not session.worktree_path:
            return session
        if session.keep:
            session.warnings.append("Worktree retained for audit; cleanup was skipped.")
            return session

        source = Path(session.source_path).resolve()
        repo_root = self._repo_root(source, session)
        if repo_root is None:
            session.status = "blocked"
            session.blockers.append(f"Cannot clean worktree because source repository is unavailable: {source}")
            return session

        remove_result = self._run(
            ["git", "worktree", "remove", "--force", session.worktree_path],
            cwd=repo_root,
            session=session,
        )
        if remove_result.returncode != 0:
            session.status = "blocked"
            session.blockers.append(remove_result.stderr.strip() or remove_result.stdout.strip() or "git worktree remove failed.")
            return session

        if remove_branch and session.branch:
            branch_result = self._run(["git", "branch", "-D", session.branch], cwd=repo_root, session=session)
            if branch_result.returncode != 0:
                session.status = "blocked"
                session.blockers.append(branch_result.stderr.strip() or branch_result.stdout.strip() or "git branch cleanup failed.")
                return session

        session.status = "cleaned"
        session.execution_path = session.source_path
        return session

    def _repo_root(self, path: Path, session: WorktreeSession) -> Path | None:
        result = self._run(["git", "rev-parse", "--show-toplevel"], cwd=path, session=session, allow_parent_discovery=True)
        if result.returncode != 0:
            return None
        return Path(result.stdout.strip()).resolve()

    def _dirty_paths(self, repository_path: Path, session: WorktreeSession) -> list[str]:
        result = self._run(["git", "status", "--porcelain", "-uall"], cwd=repository_path, session=session)
        if result.returncode != 0:
            return []
        return [_normalize_repo_path(line[3:].strip().strip('"')) for line in result.stdout.splitlines() if line.strip()]

    def _exclude_output_paths(self, dirty_paths: list[str], repo_root: Path, output_dir: Path) -> list[str]:
        try:
            output_relative = _normalize_repo_path(str(output_dir.relative_to(repo_root)))
        except ValueError:
            return dirty_paths
        if not output_relative or output_relative == ".":
            return dirty_paths
        return [path for path in dirty_paths if path != output_relative and not path.startswith(output_relative + "/")]

    def _unique_branch(self, repo_root: Path, base_branch: str, session: WorktreeSession) -> str:
        for index in range(100):
            candidate = base_branch if index == 0 else f"{base_branch}-{index}"
            result = self._run(["git", "rev-parse", "--verify", candidate], cwd=repo_root, session=session)
            if result.returncode != 0:
                return candidate
        return f"{base_branch}-{datetime.now(UTC).strftime('%H%M%S')}"

    def _run(
        self,
        args: list[str],
        *,
        cwd: str | Path,
        session: WorktreeSession,
        allow_parent_discovery: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        kwargs = {"cwd": cwd, "capture_output": True, "text": True, "check": False}
        if self.runner is subprocess.run:
            kwargs["env"] = clean_git_env(None if allow_parent_discovery else cwd)
            kwargs["timeout"] = 30
        try:
            result = run_hidden(self.runner, args, **kwargs)
        except subprocess.TimeoutExpired as exc:
            result = subprocess.CompletedProcess(
                args,
                124,
                stdout=str(exc.stdout or ""),
                stderr=f"Command timed out after {exc.timeout} seconds.",
            )
        session.commands_run.append(
            WorktreeCommand(
                command=list(args),
                cwd=str(Path(cwd).resolve()),
                exit_code=result.returncode,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
            )
        )
        return result


def _normalize_repo_path(path: str) -> str:
    raw_path = path
    if " -> " in raw_path:
        raw_path = raw_path.split(" -> ", 1)[1]
    return raw_path.replace("\\", "/").strip("/")


def _trim(value: str, limit: int = 2000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "...[truncated]"
