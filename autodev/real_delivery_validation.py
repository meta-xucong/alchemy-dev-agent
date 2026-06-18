"""Controlled real GitHub delivery validation harness."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, Sequence

from intake.models import utc_now_iso
from runtime.github_flow import GitHubExecutionResult, GitHubFlow
from runtime.worktree import RealRunWorkspace, WorktreeSession


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
class DeliveryValidationReport:
    status: str
    repository_path: str
    output_dir: str
    branch: str
    base_branch: str
    github: dict[str, object] = field(default_factory=dict)
    workspace: dict[str, object] = field(default_factory=dict)
    checks: list[dict[str, object]] = field(default_factory=list)
    blockers: list[dict[str, object]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "repository_path": self.repository_path,
            "output_dir": self.output_dir,
            "branch": self.branch,
            "base_branch": self.base_branch,
            "github": dict(self.github),
            "workspace": dict(self.workspace),
            "checks": list(self.checks),
            "blockers": list(self.blockers),
            "created_at": self.created_at,
        }


class RealDeliveryValidation:
    """Create a small real PR and collect GitHub/CI evidence."""

    def __init__(
        self,
        *,
        runner: CommandRunner = subprocess.run,
        git_executable: str = "git",
        gh_executable: str = "gh",
    ) -> None:
        self.runner = runner
        self.git_executable = git_executable
        self.gh_executable = gh_executable

    def run(
        self,
        *,
        repository_path: str | Path = ".",
        output_dir: str | Path = ".alchemy/real_delivery_validation",
        branch: str = "agent/alchemy-real-delivery-validation",
        base_branch: str = "master",
        marker_path: str = ".alchemy-real-delivery-validation.md",
        draft: bool = True,
        collect_ci: bool = True,
        ci_wait_seconds: float = 0,
        ci_poll_interval_seconds: float = 5,
        isolate: bool = True,
        keep_worktree: bool = True,
    ) -> DeliveryValidationReport:
        source_repo = Path(repository_path).resolve()
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        blockers: list[dict[str, object]] = []
        checks: list[dict[str, object]] = []
        workspace = RealRunWorkspace(runner=self._workspace_runner()).prepare(
            source_path=source_repo,
            output_dir=output,
            enabled=isolate,
            keep=keep_worktree,
            branch_prefix=branch,
        )
        repo = Path(workspace.execution_path).resolve()
        delivery_branch = str(workspace.branch or branch)
        checks.extend(command.to_dict() for command in workspace.commands_run)
        if workspace.blockers:
            report = DeliveryValidationReport(
                status="blocked",
                repository_path=str(source_repo),
                output_dir=str(output),
                branch=delivery_branch,
                base_branch=base_branch,
                workspace=workspace.to_dict(),
                checks=checks,
                blockers=[
                    {
                        "id": "B-REAL-DELIVERY-WORKSPACE",
                        "type": "environment",
                        "description": "; ".join(workspace.blockers),
                        "required_resolution": "Resolve source repository cleanliness or worktree setup before validation.",
                        "can_continue_partially": False,
                    }
                ],
            )
            self._write_report(output, report)
            return report

        git_root = self._git(["rev-parse", "--show-toplevel"], repo, checks)
        if git_root.returncode != 0:
            return self._blocked(source_repo, output, delivery_branch, base_branch, checks, workspace, "repository_not_git", "Repository is not a git checkout.")
        if Path(git_root.stdout.strip()).resolve() != repo:
            return self._blocked(source_repo, output, delivery_branch, base_branch, checks, workspace, "repository_not_root", "Repository path must be the git root.")

        dirty = self._git(["status", "--porcelain", "-uall"], repo, checks)
        if dirty.returncode != 0:
            return self._blocked(source_repo, output, delivery_branch, base_branch, checks, workspace, "git_status_failed", "Could not read repository status.")
        if dirty.stdout.strip():
            return self._blocked(source_repo, output, delivery_branch, base_branch, checks, workspace, "dirty_repository", "Repository has uncommitted changes.")

        marker = repo / marker_path
        marker.write_text(
            "\n".join(
                [
                    "# Alchemy Real Delivery Validation",
                    "",
                    f"- Created at: {utc_now_iso()}",
                    "- Purpose: verify real GitHub branch, PR, and CI evidence collection.",
                    "- Scope: validation artifact only.",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        flow = GitHubFlow(
            dry_run=False,
            git_executable=self.git_executable,
            gh_executable=self.gh_executable,
            runner=self.runner,
        )
        result = flow.record_execution(
            repository_path=repo,
            branch=delivery_branch,
            task_ids=["V2.18"],
            title="Validate Alchemy real delivery flow",
            body="Controlled V2.18 validation PR generated by Alchemy Dev Agent. This PR verifies branch, PR, and CI evidence collection.",
            base_branch=base_branch,
            draft=draft,
            collect_ci=collect_ci,
            ci_wait_seconds=ci_wait_seconds,
            ci_poll_interval_seconds=ci_poll_interval_seconds,
        )
        checks.extend(result.commands_run)
        if result.status != "pushed":
            blockers.append(
                {
                    "id": "B-REAL-DELIVERY-GITHUB",
                    "type": "external_service",
                    "description": result.summary,
                    "required_resolution": "Inspect git/gh output and rerun once GitHub delivery prerequisites are fixed.",
                    "can_continue_partially": False,
                }
            )

        status = "passed" if result.status == "pushed" and result.pull_request_url and not blockers else "blocked"
        report = DeliveryValidationReport(
            status=status,
            repository_path=str(repo),
            output_dir=str(output),
            branch=delivery_branch,
            base_branch=base_branch,
            github=result.to_dict(),
            workspace=workspace.to_dict(),
            checks=checks,
            blockers=blockers,
        )
        self._write_report(output, report)
        return report

    def _git(self, args: list[str], repo: Path, checks: list[dict[str, object]]) -> subprocess.CompletedProcess[str]:
        command = [self.git_executable, *args]
        result = self.runner(command, cwd=repo, capture_output=True, text=True, check=False)
        checks.append(
            {
                "command": " ".join(command),
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        return result

    def _blocked(
        self,
        repo: Path,
        output: Path,
        branch: str,
        base_branch: str,
        checks: list[dict[str, object]],
        workspace: WorktreeSession,
        blocker_id: str,
        description: str,
    ) -> DeliveryValidationReport:
        report = DeliveryValidationReport(
            status="blocked",
            repository_path=str(repo),
            output_dir=str(output),
            branch=branch,
            base_branch=base_branch,
            workspace=workspace.to_dict(),
            checks=checks,
            blockers=[
                {
                    "id": f"B-REAL-DELIVERY-{blocker_id.upper()}",
                    "type": "environment",
                    "description": description,
                    "required_resolution": "Resolve the repository state and rerun validation.",
                    "can_continue_partially": False,
                }
            ],
        )
        self._write_report(output, report)
        return report

    def _write_report(self, output: Path, report: DeliveryValidationReport) -> None:
        (output / "real_delivery_validation_report.json").write_text(
            json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _workspace_runner(self):
        def run(args, *, cwd, capture_output, text, check):
            return self.runner(args, cwd=cwd, capture_output=capture_output, text=text, check=check)

        return run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run controlled real GitHub delivery validation.")
    parser.add_argument("--repository-path", default=".")
    parser.add_argument("--output", default=".alchemy/real_delivery_validation")
    parser.add_argument("--branch", default="agent/alchemy-real-delivery-validation")
    parser.add_argument("--base-branch", default="master")
    parser.add_argument("--marker-path", default=".alchemy-real-delivery-validation.md")
    parser.add_argument("--ready-pr", action="store_true", help="Create a ready-for-review PR instead of a draft PR.")
    parser.add_argument("--no-ci", action="store_true", help="Skip PR check collection.")
    parser.add_argument("--ci-wait-seconds", type=float, default=120, help="Wait this long for PR checks to finish.")
    parser.add_argument("--ci-poll-interval-seconds", type=float, default=10, help="PR check polling interval.")
    parser.add_argument("--no-isolated-worktree", action="store_true", help="Run validation directly in the repository path.")
    parser.add_argument("--cleanup-worktree", action="store_true", help="Remove the validation worktree and branch after setup cleanup is possible.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = RealDeliveryValidation().run(
        repository_path=args.repository_path,
        output_dir=args.output,
        branch=args.branch,
        base_branch=args.base_branch,
        marker_path=args.marker_path,
        draft=not args.ready_pr,
        collect_ci=not args.no_ci,
        ci_wait_seconds=0 if args.no_ci else args.ci_wait_seconds,
        ci_poll_interval_seconds=args.ci_poll_interval_seconds,
        isolate=not args.no_isolated_worktree,
        keep_worktree=not args.cleanup_worktree,
    )
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
