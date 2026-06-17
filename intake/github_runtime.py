"""Public GitHub source retrieval for project intake."""

from __future__ import annotations

import subprocess
import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, Sequence

from .models import Blocker, RepositorySource
from .github_source import parse_github_source


class GitRunner(Protocol):
    def __call__(self, args: list[str], *, cwd: str | None, capture_output: bool, text: bool, check: bool) -> subprocess.CompletedProcess:
        ...


@dataclass(slots=True)
class GitHubSourceResult:
    status: str
    repository: RepositorySource
    commands_run: list[list[str]] = field(default_factory=list)
    blockers: list[Blocker] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "repository": self.repository.to_dict(),
            "commands_run": [list(command) for command in self.commands_run],
            "blockers": [blocker.to_dict() for blocker in self.blockers],
            "summary": self.summary,
        }


class GitHubSourceRuntime:
    """Clone or update public GitHub sources with local git.

    Public repositories are the primary path. Private repositories remain
    represented in ProjectBrief metadata, but this runtime does not require
    local gh authentication or tokens for the public path.
    """

    def __init__(self, runner: GitRunner | None = None) -> None:
        self.runner = runner or subprocess.run

    def prepare(self, repository: RepositorySource) -> GitHubSourceResult:
        commands_run: list[list[str]] = []
        if repository.visibility == "private" or repository.gh_auth_required:
            repository.access_status = "auth_required"
            return GitHubSourceResult(
                status="blocked",
                repository=repository,
                blockers=[
                    Blocker(
                        code="private_repository_not_supported_in_public_runtime",
                        message="Private repository retrieval is optional and not part of the public repository runtime path.",
                        severity="hard",
                    )
                ],
                summary="Private repository retrieval requires a later authenticated source adapter.",
            )

        target = Path(repository.local_path)
        if target.exists() and (target / ".git").exists():
            return self._fetch_existing(repository, target, commands_run)
        if target.exists() and any(target.iterdir()):
            return GitHubSourceResult(
                status="blocked",
                repository=repository,
                blockers=[
                    Blocker(
                        code="repository_path_not_empty",
                        message=f"Repository local_path exists and is not an empty git checkout: {target}",
                        severity="hard",
                    )
                ],
                summary="Cannot clone into a non-empty non-git directory.",
            )
        return self._clone(repository, target, commands_run)

    def _clone(self, repository: RepositorySource, target: Path, commands_run: list[list[str]]) -> GitHubSourceResult:
        target.parent.mkdir(parents=True, exist_ok=True)
        command = ["git", "clone", "--branch", repository.target_branch, "--single-branch", repository.url, str(target)]
        commands_run.append(command)
        result = self._run(command, cwd=None)
        if result.returncode != 0:
            return self._failed(repository, commands_run, "repository_clone_failed", result.stderr or result.stdout)
        repository.access_status = "available"
        repository.local_path = str(target)
        return GitHubSourceResult(
            status="available",
            repository=repository,
            commands_run=commands_run,
            summary="Repository cloned for public source intake.",
        )

    def _fetch_existing(self, repository: RepositorySource, target: Path, commands_run: list[list[str]]) -> GitHubSourceResult:
        fetch = ["git", "fetch", "origin", repository.target_branch]
        checkout = ["git", "checkout", "-B", repository.target_branch, f"origin/{repository.target_branch}"]
        commands_run.extend([fetch, checkout])
        fetch_result = self._run(fetch, cwd=str(target))
        if fetch_result.returncode != 0:
            return self._failed(repository, commands_run, "repository_fetch_failed", fetch_result.stderr or fetch_result.stdout)
        checkout_result = self._run(checkout, cwd=str(target))
        if checkout_result.returncode != 0:
            return self._failed(repository, commands_run, "repository_checkout_failed", checkout_result.stderr or checkout_result.stdout)
        repository.access_status = "available"
        repository.local_path = str(target)
        return GitHubSourceResult(
            status="available",
            repository=repository,
            commands_run=commands_run,
            summary="Repository fetched and checked out for public source intake.",
        )

    def _run(self, command: list[str], *, cwd: str | None) -> subprocess.CompletedProcess:
        return self.runner(command, cwd=cwd, capture_output=True, text=True, check=False)

    def _failed(
        self,
        repository: RepositorySource,
        commands_run: list[list[str]],
        code: str,
        output: str,
    ) -> GitHubSourceResult:
        repository.access_status = "failed"
        return GitHubSourceResult(
            status="failed",
            repository=repository,
            commands_run=commands_run,
            blockers=[
                Blocker(
                    code=code,
                    message=output.strip() or "Git command failed.",
                    severity="hard",
                )
            ],
            summary="Repository source preparation failed.",
        )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Clone or update a public GitHub repository source.")
    parser.add_argument("--repository", required=True, help="GitHub repository URL.")
    parser.add_argument("--project-id", required=True, help="Project ID used for the default local checkout path.")
    parser.add_argument("--target-branch", default="main")
    parser.add_argument("--base-branch", default="")
    parser.add_argument("--local-path", default="")
    parser.add_argument("--visibility", choices=["public", "private", "unknown"], default="public")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    repository = parse_github_source(
        args.repository,
        project_id=args.project_id,
        target_branch=args.target_branch,
        base_branch=args.base_branch,
        visibility=args.visibility,
        local_path=args.local_path,
    )
    if repository is None:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "blockers": [
                        {
                            "code": "invalid_github_url",
                            "message": f"Repository URL is not a supported GitHub URL: {args.repository}",
                            "severity": "hard",
                        }
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    result = GitHubSourceRuntime().prepare(repository)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.status == "available" else 1


if __name__ == "__main__":
    raise SystemExit(main())
