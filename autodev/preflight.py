"""Preflight checks for document-driven execution."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from intake.gh_auth import GitHubAuthPreflight


class CommandRunner(Protocol):
    def __call__(self, args: list[str], *, cwd: str | None, capture_output: bool, text: bool, check: bool) -> subprocess.CompletedProcess:
        ...


@dataclass(slots=True)
class PreflightCheck:
    name: str
    status: str
    summary: str
    required: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "summary": self.summary,
            "required": self.required,
        }


@dataclass(slots=True)
class PreflightResult:
    status: str
    checks: list[PreflightCheck] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "checks": [check.to_dict() for check in self.checks],
        }


class ExecutionPreflight:
    """Check whether requested execution mode can start locally."""

    def __init__(self, runner: CommandRunner = subprocess.run) -> None:
        self.runner = runner

    def check(
        self,
        *,
        repository_path: str | Path,
        real_codex: bool = False,
        real_github: bool = False,
        codex_executable: str = "codex",
        private_repository: bool = False,
    ) -> PreflightResult:
        checks: list[PreflightCheck] = []
        repo = Path(repository_path)
        checks.append(self._repository_check(repo))
        checks.append(self._command_check("git", required=real_github or real_codex))
        if real_codex:
            checks.append(self._command_check(codex_executable, required=True, display_name="codex"))
        else:
            checks.append(PreflightCheck("codex", "skipped", "Dry-run mode does not require Codex CLI.", required=False))
        if real_github and not private_repository:
            checks.append(self._command_check("gh", required=True))
        elif not private_repository:
            checks.append(PreflightCheck("gh", "skipped", "Dry-run GitHub mode does not require gh.", required=False))
        if private_repository:
            auth_result = GitHubAuthPreflight(runner=self.runner).check(required=True)
            for check in auth_result.checks:
                checks.append(PreflightCheck(check.name, check.status, check.summary, check.required))
        else:
            checks.append(PreflightCheck("gh_auth", "skipped", "Public repository mode does not require GitHub CLI authentication.", required=False))

        blocking = [check for check in checks if check.required and check.status != "passed"]
        return PreflightResult(status="blocked" if blocking else "passed", checks=checks)

    def _repository_check(self, path: Path) -> PreflightCheck:
        if not path.exists():
            return PreflightCheck("repository_path", "failed", f"Repository path does not exist: {path}")
        if not path.is_dir():
            return PreflightCheck("repository_path", "failed", f"Repository path is not a directory: {path}")
        return PreflightCheck("repository_path", "passed", f"Repository path is available: {path}")

    def _command_check(self, executable: str, *, required: bool, display_name: str | None = None) -> PreflightCheck:
        name = display_name or executable
        resolved = shutil.which(executable) or (executable if Path(executable).is_file() else "")
        if not resolved:
            return PreflightCheck(name, "failed", f"Executable not found on PATH: {executable}", required=required)
        try:
            result = self.runner([executable, "--version"], cwd=None, capture_output=True, text=True, check=False)
        except OSError as exc:
            return PreflightCheck(name, "failed", f"Executable is not launchable: {exc}", required=required)
        summary = (result.stdout or result.stderr or resolved).strip().splitlines()[0]
        status = "passed" if result.returncode == 0 else "failed"
        return PreflightCheck(name, status, summary, required=required)
