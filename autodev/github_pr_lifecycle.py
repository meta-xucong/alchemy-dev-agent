"""Safe GitHub pull request lifecycle controls for validation/delivery PRs."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from intake.models import utc_now_iso


class CommandRunner(Protocol):
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
class PullRequestLifecycleReport:
    status: str
    action: str
    repository_path: str
    selector: str
    pull_request: dict[str, object] = field(default_factory=dict)
    checks: list[dict[str, object]] = field(default_factory=list)
    commands_run: list[dict[str, object]] = field(default_factory=list)
    blockers: list[dict[str, object]] = field(default_factory=list)
    warnings: list[dict[str, object]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "2.48",
            "status": self.status,
            "action": self.action,
            "repository_path": self.repository_path,
            "selector": self.selector,
            "pull_request": dict(self.pull_request),
            "checks": list(self.checks),
            "commands_run": list(self.commands_run),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "created_at": self.created_at,
        }


class GitHubPRLifecycle:
    """Inspect and safely transition validation/delivery PRs."""

    def __init__(
        self,
        *,
        runner: CommandRunner = subprocess.run,
        gh_executable: str = "gh",
        git_executable: str = "git",
    ) -> None:
        self.runner = runner
        self.gh_executable = gh_executable
        self.git_executable = git_executable

    def run(
        self,
        *,
        repository_path: str | Path = ".",
        selector: str,
        action: str = "inspect",
        delete_branch: bool = False,
        confirm: bool = False,
        output_dir: str | Path = ".alchemy/github_pr_lifecycle",
    ) -> PullRequestLifecycleReport:
        repo = Path(repository_path).resolve()
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        commands: list[dict[str, object]] = []
        warnings: list[dict[str, object]] = []
        blockers: list[dict[str, object]] = []

        if action not in {"inspect", "ready", "close"}:
            return self._write(
                output,
                PullRequestLifecycleReport(
                    status="blocked",
                    action=action,
                    repository_path=str(repo),
                    selector=selector,
                    blockers=[blocker("B-PR-LIFECYCLE-ACTION", f"Unsupported PR lifecycle action: {action}")],
                ),
            )

        pr = self._view_pr(repo, selector, commands)
        if not pr:
            return self._write(
                output,
                PullRequestLifecycleReport(
                    status="blocked",
                    action=action,
                    repository_path=str(repo),
                    selector=selector,
                    commands_run=commands,
                    blockers=[blocker("B-PR-LIFECYCLE-VIEW", "Could not inspect the selected pull request.")],
                ),
            )

        checks = self._checks(repo, selector, commands)
        if action == "inspect":
            return self._write(
                output,
                PullRequestLifecycleReport(
                    status="passed",
                    action=action,
                    repository_path=str(repo),
                    selector=selector,
                    pull_request=pr,
                    checks=checks,
                    commands_run=commands,
                    warnings=warnings,
                ),
            )

        if not confirm:
            warnings.append(
                {
                    "id": "W-PR-LIFECYCLE-CONFIRMATION-REQUIRED",
                    "type": "operator_confirmation",
                    "description": f"Action {action} was planned but not executed because confirm=false.",
                }
            )
            return self._write(
                output,
                PullRequestLifecycleReport(
                    status="planned",
                    action=action,
                    repository_path=str(repo),
                    selector=selector,
                    pull_request=pr,
                    checks=checks,
                    commands_run=commands,
                    warnings=warnings,
                ),
            )

        if action == "ready":
            ready = self._run([self.gh_executable, "pr", "ready", selector], repo, commands)
            if ready.returncode != 0:
                blockers.append(blocker("B-PR-LIFECYCLE-READY", "Could not mark the pull request ready for review."))
        elif action == "close":
            command = [self.gh_executable, "pr", "close", selector]
            if delete_branch:
                command.append("--delete-branch")
            closed = self._run(command, repo, commands)
            if closed.returncode != 0:
                blockers.append(blocker("B-PR-LIFECYCLE-CLOSE", "Could not close the pull request."))

        after = self._view_pr(repo, selector, commands) or pr
        status = "passed" if not blockers else "blocked"
        return self._write(
            output,
            PullRequestLifecycleReport(
                status=status,
                action=action,
                repository_path=str(repo),
                selector=selector,
                pull_request=after,
                checks=checks,
                commands_run=commands,
                blockers=blockers,
                warnings=warnings,
            ),
        )

    def _view_pr(self, repo: Path, selector: str, commands: list[dict[str, object]]) -> dict[str, object]:
        result = self._run(
            [
                self.gh_executable,
                "pr",
                "view",
                selector,
                "--json",
                "number,url,state,isDraft,headRefName,baseRefName,mergeStateStatus,statusCheckRollup",
            ],
            repo,
            commands,
        )
        if result.returncode != 0:
            return {}
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {}
        return dict(payload) if isinstance(payload, Mapping) else {}

    def _checks(self, repo: Path, selector: str, commands: list[dict[str, object]]) -> list[dict[str, object]]:
        result = self._run(
            [
                self.gh_executable,
                "pr",
                "checks",
                selector,
                "--json",
                "name,state,bucket,workflow,link,completedAt,startedAt",
            ],
            repo,
            commands,
        )
        if result.returncode != 0:
            return []
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []
        return [dict(item) for item in payload if isinstance(item, Mapping)] if isinstance(payload, list) else []

    def _run(
        self,
        args: list[str],
        repo: Path,
        commands: list[dict[str, object]],
    ) -> subprocess.CompletedProcess[str]:
        result = self.runner(args, cwd=repo, capture_output=True, text=True, check=False)
        commands.append(
            {
                "command": " ".join(args),
                "exit_code": result.returncode,
                "stdout": trim(result.stdout or ""),
                "stderr": trim(result.stderr or ""),
            }
        )
        return result

    def _write(self, output: Path, report: PullRequestLifecycleReport) -> PullRequestLifecycleReport:
        (output / "github_pr_lifecycle_report.json").write_text(
            json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return report


def blocker(blocker_id: str, description: str) -> dict[str, object]:
    return {
        "id": blocker_id,
        "type": "github_pr_lifecycle",
        "description": description,
        "required_resolution": "Inspect gh output and retry with a valid selector, repository, or explicit confirmation.",
        "can_continue_partially": False,
    }


def trim(value: str, limit: int = 12000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "...[truncated]"


def lifecycle_summary(report: Mapping[str, Any]) -> dict[str, object]:
    pr = report.get("pull_request", {})
    pr = pr if isinstance(pr, Mapping) else {}
    return {
        "status": report.get("status", ""),
        "action": report.get("action", ""),
        "selector": report.get("selector", ""),
        "number": pr.get("number", ""),
        "url": pr.get("url", ""),
        "state": pr.get("state", ""),
        "is_draft": pr.get("isDraft", ""),
        "head": pr.get("headRefName", ""),
        "base": pr.get("baseRefName", ""),
        "blocker_count": len(report.get("blockers", [])) if isinstance(report.get("blockers"), list) else 0,
        "warning_count": len(report.get("warnings", [])) if isinstance(report.get("warnings"), list) else 0,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect or safely transition a GitHub pull request.")
    parser.add_argument("--repository-path", default=".")
    parser.add_argument("--selector", required=True, help="PR number, URL, or branch selector accepted by gh pr view.")
    parser.add_argument("--action", choices=["inspect", "ready", "close"], default="inspect")
    parser.add_argument("--delete-branch", action="store_true", help="When closing, also ask GitHub to delete the remote branch.")
    parser.add_argument("--confirm", action="store_true", help="Required before mutating ready/close actions execute.")
    parser.add_argument("--output", default=".alchemy/github_pr_lifecycle")
    parser.add_argument("--summary", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = GitHubPRLifecycle().run(
        repository_path=args.repository_path,
        selector=args.selector,
        action=args.action,
        delete_branch=args.delete_branch,
        confirm=args.confirm,
        output_dir=args.output,
    )
    payload = report.to_dict()
    print(json.dumps(lifecycle_summary(payload) if args.summary else payload, indent=2, sort_keys=True))
    return 0 if report.status in {"passed", "planned"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
