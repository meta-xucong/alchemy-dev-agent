"""Private GitHub source retrieval through local gh authentication."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, Sequence

from .gh_auth import GitHubAuthPreflight
from .github_source import parse_github_source
from .models import Blocker, RepositorySource


class PrivateGitRunner(Protocol):
    def __call__(self, args: list[str], *, cwd: str | None, capture_output: bool, text: bool, check: bool) -> subprocess.CompletedProcess:
        ...


@dataclass(slots=True)
class PrivateGitHubSourceResult:
    status: str
    repository: RepositorySource
    commands_run: list[list[str]] = field(default_factory=list)
    blockers: list[Blocker] = field(default_factory=list)
    summary: str = ""
    auth: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "repository": self.repository.to_dict(),
            "commands_run": [list(command) for command in self.commands_run],
            "blockers": [blocker.to_dict() for blocker in self.blockers],
            "summary": self.summary,
            "auth": dict(self.auth),
        }


class PrivateGitHubSourceRuntime:
    """Clone or update private GitHub sources using local gh credentials."""

    def __init__(self, runner: PrivateGitRunner = subprocess.run) -> None:
        self.runner = runner

    def prepare(self, repository: RepositorySource) -> PrivateGitHubSourceResult:
        auth = GitHubAuthPreflight(runner=self.runner).check(required=True)
        if auth.status != "passed":
            repository.access_status = "auth_required"
            return PrivateGitHubSourceResult(
                status="blocked",
                repository=repository,
                blockers=[
                    Blocker(
                        code="github_cli_auth_required",
                        message="Private repository access requires local GitHub CLI authentication.",
                        severity="hard",
                    )
                ],
                summary="GitHub CLI authentication is not ready.",
                auth=auth.to_dict(),
            )

        commands_run: list[list[str]] = []
        target = Path(repository.local_path)
        if target.exists() and (target / ".git").exists():
            return self._fetch_existing(repository, target, commands_run, auth.to_dict())
        if target.exists() and any(target.iterdir()):
            repository.access_status = "failed"
            return PrivateGitHubSourceResult(
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
                auth=auth.to_dict(),
            )
        return self._clone(repository, target, commands_run, auth.to_dict())

    def _clone(
        self,
        repository: RepositorySource,
        target: Path,
        commands_run: list[list[str]],
        auth: dict[str, object],
    ) -> PrivateGitHubSourceResult:
        target.parent.mkdir(parents=True, exist_ok=True)
        command = [
            "gh",
            "repo",
            "clone",
            f"{repository.owner}/{repository.name}",
            str(target),
            "--",
            "--branch",
            repository.target_branch,
            "--single-branch",
        ]
        commands_run.append(command)
        result = self._run(command, cwd=None)
        if result.returncode != 0:
            return self._failed(repository, commands_run, "private_repository_clone_failed", result.stderr or result.stdout, auth)
        repository.access_status = "available"
        repository.local_path = str(target)
        return PrivateGitHubSourceResult(
            status="available",
            repository=repository,
            commands_run=commands_run,
            summary="Private repository cloned through local GitHub CLI authentication.",
            auth=auth,
        )

    def _fetch_existing(
        self,
        repository: RepositorySource,
        target: Path,
        commands_run: list[list[str]],
        auth: dict[str, object],
    ) -> PrivateGitHubSourceResult:
        fetch = ["git", "fetch", "origin", repository.target_branch]
        checkout = ["git", "checkout", "-B", repository.target_branch, f"origin/{repository.target_branch}"]
        commands_run.extend([fetch, checkout])
        fetch_result = self._run(fetch, cwd=str(target))
        if fetch_result.returncode != 0:
            return self._failed(repository, commands_run, "private_repository_fetch_failed", fetch_result.stderr or fetch_result.stdout, auth)
        checkout_result = self._run(checkout, cwd=str(target))
        if checkout_result.returncode != 0:
            return self._failed(repository, commands_run, "private_repository_checkout_failed", checkout_result.stderr or checkout_result.stdout, auth)
        repository.access_status = "available"
        repository.local_path = str(target)
        return PrivateGitHubSourceResult(
            status="available",
            repository=repository,
            commands_run=commands_run,
            summary="Private repository fetched and checked out through local GitHub CLI authentication.",
            auth=auth,
        )

    def _run(self, command: list[str], *, cwd: str | None) -> subprocess.CompletedProcess:
        try:
            return self.runner(command, cwd=cwd, capture_output=True, text=True, check=False)
        except (OSError, UnicodeDecodeError) as exc:
            return subprocess.CompletedProcess(command, 1, "", str(exc))

    def _failed(
        self,
        repository: RepositorySource,
        commands_run: list[list[str]],
        code: str,
        output: str,
        auth: dict[str, object],
    ) -> PrivateGitHubSourceResult:
        repository.access_status = "failed"
        return PrivateGitHubSourceResult(
            status="failed",
            repository=repository,
            commands_run=commands_run,
            blockers=[
                Blocker(
                    code=code,
                    message=output.strip() or "Private GitHub source command failed.",
                    severity="hard",
                )
            ],
            summary="Private repository source preparation failed.",
            auth=auth,
        )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Clone or update a private GitHub repository through local gh authentication.")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--target-branch", default="main")
    parser.add_argument("--base-branch", default="")
    parser.add_argument("--local-path", default="")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    repository = parse_github_source(
        args.repository,
        project_id=args.project_id,
        target_branch=args.target_branch,
        base_branch=args.base_branch,
        visibility="private",
        local_path=args.local_path,
    )
    if repository is None:
        print(json.dumps({"status": "failed", "blockers": [{"code": "invalid_github_url"}]}, indent=2, sort_keys=True))
        return 1
    result = PrivateGitHubSourceRuntime().prepare(repository)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.status == "available" else 1


if __name__ == "__main__":
    raise SystemExit(main())
