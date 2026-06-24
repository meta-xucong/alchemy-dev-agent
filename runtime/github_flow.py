"""GitHub execution flow adapter."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .models import utc_now_iso
from .subprocess_utils import clean_git_env, run_hidden


@dataclass(slots=True)
class GitHubExecutionResult:
    status: str
    branch: str
    commit: str = ""
    pull_request_url: str = ""
    ci_status: str = "unknown"
    ci_details: list[dict] = field(default_factory=list)
    merge: dict = field(default_factory=dict)
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
            "merge": dict(self.merge),
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
        auto_merge: bool = False,
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
                merge=_merge_skipped("Auto-merge is unavailable in dry-run mode."),
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
            kwargs = {"cwd": repository_path, "capture_output": True, "text": True, "check": False}
            if self.runner is subprocess.run:
                kwargs["env"] = clean_git_env(repository_path)
            completed = run_hidden(self.runner, command, **kwargs)
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

        self._ensure_commit_identity(repository_path, command_results)
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

        kwargs = {"cwd": repository_path, "capture_output": True, "text": True, "check": False}
        if self.runner is subprocess.run:
            kwargs["env"] = clean_git_env(repository_path)
        rev_parse = run_hidden(self.runner, [self.git_executable, "rev-parse", "HEAD"], **kwargs)
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
        else:
            ci_status = "waived"
            ci_details = [
                {
                    "name": "github-ci",
                    "state": "skipped",
                    "bucket": "waived",
                    "summary": "PR check collection was explicitly disabled for this run.",
                }
            ]

        merge_result = _merge_skipped("Auto-merge was not requested for this run.")
        if auto_merge:
            merge_result = self.merge_pull_request(
                repository_path=repository_path,
                branch=branch,
                ci_status=ci_status,
                command_results=command_results,
            )

        return GitHubExecutionResult(
            status="pushed",
            branch=branch,
            commit=commit_sha,
            pull_request_url=pull_request_url,
            ci_status=ci_status,
            ci_details=ci_details,
            merge=merge_result,
            commands_run=command_results,
            summary=f"GitHub branch, commit, push, PR flow, CI evidence, and merge policy completed with CI status {ci_status}.",
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

    def merge_pull_request(
        self,
        *,
        repository_path: str | Path,
        branch: str,
        ci_status: str,
        command_results: list[dict],
    ) -> dict[str, object]:
        if ci_status != "passed":
            return {
                "status": "skipped",
                "summary": f"Auto-merge skipped because CI status is {ci_status}.",
            }
        merged = self._run(
            [self.gh_executable, "pr", "merge", branch, "--squash", "--delete-branch", "--auto"],
            repository_path,
            command_results,
        )
        if merged.returncode == 0:
            merge_state = self._view_pull_request_merge_state(repository_path, branch, command_results)
            if merge_state.get("state") == "MERGED" or merge_state.get("mergedAt"):
                return {
                    "status": "merged",
                    "summary": "Pull request was merged.",
                    "stdout": merged.stdout,
                    "stderr": merged.stderr,
                    "remote_state": merge_state,
                }
            return {
                "status": "auto_merge_enabled",
                "summary": "GitHub auto-merge was enabled for the pull request.",
                "stdout": merged.stdout,
                "stderr": merged.stderr,
            }
        direct = self._run(
            [self.gh_executable, "pr", "merge", branch, "--squash", "--delete-branch"],
            repository_path,
            command_results,
        )
        if direct.returncode == 0:
            return {
                "status": "merged",
                "summary": "Pull request was merged.",
                "stdout": direct.stdout,
                "stderr": direct.stderr,
            }
        merge_state = self._view_pull_request_merge_state(repository_path, branch, command_results)
        if merge_state.get("state") == "MERGED" or merge_state.get("mergedAt"):
            return {
                "status": "merged",
                "summary": "Pull request was merged, but the local gh merge command returned a cleanup error.",
                "stdout": direct.stdout,
                "stderr": direct.stderr,
                "remote_state": merge_state,
            }
        return {
            "status": "failed",
            "summary": "Auto-merge and direct merge commands failed.",
            "stdout": direct.stdout,
            "stderr": direct.stderr,
        }

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

    def _view_pull_request_merge_state(
        self,
        repository_path: str | Path,
        branch: str,
        command_results: list[dict],
    ) -> dict:
        viewed = self._run(
            [self.gh_executable, "pr", "view", branch, "--json", "url,number,state,mergedAt"],
            repository_path,
            command_results,
        )
        if viewed.returncode != 0:
            return {}
        return self._parse_json_object(viewed.stdout)

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
        kwargs = {"cwd": repository_path, "capture_output": True, "text": True, "check": False}
        if self.runner is subprocess.run:
            kwargs["env"] = clean_git_env(repository_path)
        completed = run_hidden(self.runner, command, **kwargs)
        command_results.append(
            {
                "command": " ".join(command),
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        )
        return completed

    def _ensure_commit_identity(self, repository_path: str | Path, command_results: list[dict]) -> None:
        name = self._config_value(repository_path, "user.name", command_results)
        email = self._config_value(repository_path, "user.email", command_results)
        if not name:
            self._run([self.git_executable, "config", "user.name", "Alchemy Dev Agent"], repository_path, command_results)
        if not email:
            self._run([self.git_executable, "config", "user.email", "alchemy-dev-agent@users.noreply.github.com"], repository_path, command_results)

    def _config_value(self, repository_path: str | Path, key: str, command_results: list[dict]) -> str:
        completed = self._run([self.git_executable, "config", "--get", key], repository_path, command_results)
        return completed.stdout.strip() if completed.returncode == 0 else ""


def _last_nonempty_line(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _merge_skipped(summary: str) -> dict[str, object]:
    return {"status": "skipped", "summary": summary}
