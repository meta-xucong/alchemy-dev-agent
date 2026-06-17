"""GitHub execution flow adapter."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .models import utc_now_iso


@dataclass(slots=True)
class GitHubExecutionResult:
    status: str
    branch: str
    commit: str = ""
    pull_request_url: str = ""
    ci_status: str = "unknown"
    commands_run: list[dict] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "branch": self.branch,
            "commit": self.commit,
            "pull_request_url": self.pull_request_url,
            "ci_status": self.ci_status,
            "commands_run": list(self.commands_run),
            "summary": self.summary,
            "created_at": utc_now_iso(),
        }


class GitRunner(Protocol):
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


class GitHubFlow:
    """Record or execute branch, commit, push, PR, and CI check flow."""

    def __init__(
        self,
        *,
        dry_run: bool = True,
        git_executable: str = "git",
        gh_executable: str = "gh",
        runner: GitRunner = subprocess.run,
    ) -> None:
        self.dry_run = dry_run
        self.git_executable = git_executable
        self.gh_executable = gh_executable
        self.runner = runner

    def record_execution(
        self,
        *,
        repository_path: str | Path,
        branch: str,
        task_ids: list[str],
        title: str,
        body: str,
    ) -> GitHubExecutionResult:
        if self.dry_run:
            commit = f"dry-run:{'-'.join(task_ids) or 'runtime'}"
            return GitHubExecutionResult(
                status="recorded",
                branch=branch,
                commit=commit,
                pull_request_url=f"dry-run://pull-request/{branch}",
                ci_status="passed",
                commands_run=[],
                summary="Dry-run GitHub execution evidence recorded.",
            )

        commands = [
            [self.git_executable, "checkout", "-B", branch],
            [self.git_executable, "status", "--short"],
            [self.git_executable, "add", "-A"],
            [self.git_executable, "commit", "-m", title],
            [self.git_executable, "push", "-u", "origin", branch],
            [self.gh_executable, "pr", "create", "--title", title, "--body", body],
        ]
        command_results: list[dict] = []
        pull_request_url = ""
        commit_sha = ""

        for command in commands:
            completed = self.runner(
                command,
                cwd=repository_path,
                capture_output=True,
                text=True,
                check=False,
            )
            command_results.append(
                {
                    "command": " ".join(command),
                    "exit_code": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                }
            )
            if completed.returncode != 0:
                return GitHubExecutionResult(
                    status="failed",
                    branch=branch,
                    commands_run=command_results,
                    summary=f"GitHub flow command failed: {' '.join(command)}",
                )
            if command[:3] == [self.gh_executable, "pr", "create"]:
                pull_request_url = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""

        rev_parse = self.runner(
            [self.git_executable, "rev-parse", "HEAD"],
            cwd=repository_path,
            capture_output=True,
            text=True,
            check=False,
        )
        command_results.append(
            {
                "command": f"{self.git_executable} rev-parse HEAD",
                "exit_code": rev_parse.returncode,
                "stdout": rev_parse.stdout,
                "stderr": rev_parse.stderr,
            }
        )
        if rev_parse.returncode == 0:
            commit_sha = rev_parse.stdout.strip()

        return GitHubExecutionResult(
            status="pushed",
            branch=branch,
            commit=commit_sha,
            pull_request_url=pull_request_url,
            ci_status="unknown",
            commands_run=command_results,
            summary="GitHub branch, commit, push, and PR flow completed.",
        )
