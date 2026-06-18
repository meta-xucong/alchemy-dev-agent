"""GitHub execution flow adapter."""

from __future__ import annotations

import json
import subprocess
import time
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
    ci_details: list[dict] = field(default_factory=list)
    commands_run: list[dict] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "branch": self.branch,
            "commit": self.commit,
            "pull_request_url": self.pull_request_url,
            "ci_status": self.ci_status,
            "ci_details": list(self.ci_details),
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
        base_branch: str = "",
        draft: bool = False,
        collect_ci: bool = True,
        ci_wait_seconds: float = 0,
        ci_poll_interval_seconds: float = 5,
    ) -> GitHubExecutionResult:
        if self.dry_run:
            commit = f"dry-run:{'-'.join(task_ids) or 'runtime'}"
            return GitHubExecutionResult(
                status="recorded",
                branch=branch,
                commit=commit,
                pull_request_url=f"dry-run://pull-request/{branch}",
                ci_status="passed",
                ci_details=[],
                commands_run=[],
                summary="Dry-run GitHub execution evidence recorded.",
            )

        command_results: list[dict] = []
        pull_request_url = ""
        commit_sha = ""

        for command in [
            [self.git_executable, "checkout", "-B", branch],
            [self.git_executable, "add", "-A"],
        ]:
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

        status_result = self._run([self.git_executable, "status", "--short"], repository_path, command_results)
        if status_result.returncode != 0:
            return GitHubExecutionResult(
                status="failed",
                branch=branch,
                commands_run=command_results,
                summary="GitHub flow command failed: git status --short",
            )
        has_changes = bool(status_result.stdout.strip())

        if has_changes:
            commit_result = self._run([self.git_executable, "commit", "-m", title], repository_path, command_results)
            if commit_result.returncode != 0:
                return GitHubExecutionResult(
                    status="failed",
                    branch=branch,
                    commands_run=command_results,
                    summary="GitHub flow command failed: git commit",
                )

        push_result = self._run([self.git_executable, "push", "-u", "origin", branch], repository_path, command_results)
        if push_result.returncode != 0:
            return GitHubExecutionResult(
                status="failed",
                branch=branch,
                commands_run=command_results,
                summary="GitHub flow command failed: git push -u origin " + branch,
            )

        pull_request_url = self._ensure_pull_request(
            repository_path=repository_path,
            branch=branch,
            title=title,
            body=body,
            base_branch=base_branch,
            draft=draft,
            command_results=command_results,
        )
        if not pull_request_url:
            return GitHubExecutionResult(
                status="failed",
                branch=branch,
                commands_run=command_results,
                summary="GitHub flow failed to create or locate a pull request.",
            )

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

        ci_status = "unknown"
        ci_details: list[dict] = []
        if collect_ci:
            if ci_wait_seconds > 0:
                ci_status, ci_details = self.wait_for_ci_status(
                    repository_path=repository_path,
                    branch=branch,
                    timeout_seconds=ci_wait_seconds,
                    poll_interval_seconds=ci_poll_interval_seconds,
                    command_results=command_results,
                )
            else:
                ci_status, ci_details = self.collect_ci_status(
                    repository_path=repository_path,
                    branch=branch,
                    command_results=command_results,
                )

        return GitHubExecutionResult(
            status="pushed",
            branch=branch,
            commit=commit_sha,
            pull_request_url=pull_request_url,
            ci_status=ci_status,
            ci_details=ci_details,
            commands_run=command_results,
            summary=f"GitHub branch, commit, push, PR flow, and CI collection completed with CI status {ci_status}.",
        )

    def collect_ci_status(
        self,
        *,
        repository_path: str | Path,
        branch: str,
        command_results: list[dict] | None = None,
    ) -> tuple[str, list[dict]]:
        results = command_results if command_results is not None else []
        completed = self._run(
            [
                self.gh_executable,
                "pr",
                "checks",
                branch,
                "--json",
                "name,state,bucket,workflow,link,completedAt,startedAt",
            ],
            repository_path,
            results,
        )
        checks = self._parse_json_list(completed.stdout)
        if not checks:
            return "unknown", []
        buckets = {str(check.get("bucket", "")).lower() for check in checks}
        if buckets & {"fail", "cancel"}:
            return "failed", checks
        if buckets & {"pending"}:
            return "pending", checks
        if buckets <= {"pass", "skipping"}:
            return "passed", checks
        return "unknown", checks

    def wait_for_ci_status(
        self,
        *,
        repository_path: str | Path,
        branch: str,
        timeout_seconds: float,
        poll_interval_seconds: float = 5,
        command_results: list[dict] | None = None,
    ) -> tuple[str, list[dict]]:
        deadline = time.monotonic() + max(0, timeout_seconds)
        interval = max(0.1, poll_interval_seconds)
        latest_status = "unknown"
        latest_details: list[dict] = []

        while True:
            latest_status, latest_details = self.collect_ci_status(
                repository_path=repository_path,
                branch=branch,
                command_results=command_results,
            )
            if latest_status in {"passed", "failed"}:
                return latest_status, latest_details

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return latest_status, latest_details
            time.sleep(min(interval, remaining))

    def _ensure_pull_request(
        self,
        *,
        repository_path: str | Path,
        branch: str,
        title: str,
        body: str,
        base_branch: str,
        draft: bool,
        command_results: list[dict],
    ) -> str:
        existing = self._view_pull_request(repository_path, branch, command_results)
        if existing:
            return existing

        command = [self.gh_executable, "pr", "create", "--title", title, "--body", body, "--head", branch]
        if base_branch:
            command.extend(["--base", base_branch])
        if draft:
            command.append("--draft")
        created = self._run(command, repository_path, command_results)
        if created.returncode == 0:
            return _last_nonempty_line(created.stdout)

        return self._view_pull_request(repository_path, branch, command_results)

    def _view_pull_request(
        self,
        repository_path: str | Path,
        branch: str,
        command_results: list[dict],
    ) -> str:
        viewed = self._run(
            [self.gh_executable, "pr", "view", branch, "--json", "url,number,state"],
            repository_path,
            command_results,
        )
        if viewed.returncode != 0:
            return ""
        payload = self._parse_json_object(viewed.stdout)
        return str(payload.get("url", ""))

    def _parse_json_object(self, output: str) -> dict:
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _parse_json_list(self, output: str) -> list[dict]:
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    def _run(
        self,
        command: list[str],
        repository_path: str | Path,
        command_results: list[dict],
    ) -> subprocess.CompletedProcess[str]:
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
        return completed


def _last_nonempty_line(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return lines[-1] if lines else ""
