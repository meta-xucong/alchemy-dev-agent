"""Optional GitHub CLI authentication preflight for private repositories."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Protocol, Sequence


class GhRunner(Protocol):
    def __call__(self, args: list[str], *, cwd: str | None, capture_output: bool, text: bool, check: bool) -> subprocess.CompletedProcess:
        ...


@dataclass(slots=True)
class GitHubAuthCheck:
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
class GitHubAuthResult:
    status: str
    checks: list[GitHubAuthCheck] = field(default_factory=list)
    account: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "checks": [check.to_dict() for check in self.checks],
            "account": self.account,
        }


class GitHubAuthPreflight:
    """Check local gh readiness without reading or storing tokens."""

    def __init__(self, runner: GhRunner = subprocess.run) -> None:
        self.runner = runner

    def check(self, *, required: bool = True) -> GitHubAuthResult:
        checks: list[GitHubAuthCheck] = []
        resolved = shutil.which("gh")
        if not resolved:
            checks.append(GitHubAuthCheck("gh", "failed", "GitHub CLI executable not found on PATH.", required=required))
            return GitHubAuthResult(status="blocked" if required else "skipped", checks=checks)

        version = self._run(["gh", "--version"])
        checks.append(
            GitHubAuthCheck(
                "gh",
                "passed" if version.returncode == 0 else "failed",
                first_line(version.stdout or version.stderr or resolved),
                required=required,
            )
        )

        auth = self._run(["gh", "auth", "status"])
        auth_output = safe_text(auth.stdout) + "\n" + safe_text(auth.stderr)
        account = account_from_auth_status(auth_output)
        checks.append(
            GitHubAuthCheck(
                "gh_auth",
                "passed" if auth.returncode == 0 else "failed",
                auth_summary(auth_output),
                required=required,
            )
        )

        blocking = [check for check in checks if check.required and check.status != "passed"]
        return GitHubAuthResult(status="blocked" if blocking else "passed", checks=checks, account=account)

    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        try:
            return self.runner(args, cwd=None, capture_output=True, text=True, check=False)
        except (OSError, UnicodeDecodeError) as exc:
            return subprocess.CompletedProcess(args, 1, "", str(exc))


def first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


def safe_text(value: object) -> str:
    return value if isinstance(value, str) else ""


def auth_summary(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    safe_lines = [line for line in lines if "token" not in line.lower()]
    return safe_lines[0] if safe_lines else "GitHub CLI auth status unavailable."


def account_from_auth_status(text: str) -> str:
    for line in text.splitlines():
        clean = line.strip()
        marker = "Logged in to github.com account "
        if marker in clean:
            account = clean.split(marker, 1)[1].split()[0]
            return account.strip("()")
    return ""


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check local GitHub CLI authentication for optional private repository access.")
    parser.add_argument("--optional", action="store_true", help="Return skipped instead of blocked when gh is unavailable.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = GitHubAuthPreflight().check(required=not args.optional)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.status in {"passed", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
