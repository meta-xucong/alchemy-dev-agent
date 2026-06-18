"""Real-execution environment validation for external delivery readiness."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from intake.models import utc_now_iso


@dataclass(slots=True)
class EnvironmentCheck:
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
class EnvironmentReport:
    status: str
    checks: list[EnvironmentCheck] = field(default_factory=list)
    blockers: list[dict[str, object]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    output_dir: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "checks": [check.to_dict() for check in self.checks],
            "blockers": list(self.blockers),
            "created_at": self.created_at,
            "output_dir": self.output_dir,
        }


class RealEnvironmentCheck:
    """Check whether local real Codex/GitHub execution can start."""

    def run(self, *, output_dir: str | Path = ".alchemy/real_env_check") -> EnvironmentReport:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        checks = [
            self._command_check("git", ["git", "--version"]),
            self._command_check("gh", ["gh", "--version"]),
            self._command_check("gh_auth", ["gh", "auth", "status"]),
            self._command_check("codex", ["codex", "--version"]),
        ]
        blockers = []
        for check in checks:
            if check.required and check.status != "passed":
                blockers.append(
                    {
                        "id": f"B-ENV-{check.name.upper()}",
                        "type": "environment",
                        "description": check.summary,
                        "required_resolution": "Install, authenticate, or repair the required local tool before real execution validation.",
                        "can_continue_partially": check.name != "codex",
                    }
                )
        status = "ready" if not blockers else "blocked"
        report = EnvironmentReport(status=status, checks=checks, blockers=blockers, output_dir=str(output))
        (output / "real_environment_report.json").write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return report

    def _command_check(self, name: str, command: list[str]) -> EnvironmentCheck:
        executable = command[0]
        if shutil.which(executable) is None:
            return EnvironmentCheck(name, "failed", f"Executable not found on PATH: {executable}")
        try:
            result = subprocess.run(command, cwd=None, capture_output=True, text=False, check=False, timeout=30)
        except (OSError, subprocess.SubprocessError, UnicodeDecodeError) as exc:
            return EnvironmentCheck(name, "failed", redact(str(exc)))
        stdout = decode_output(result.stdout)
        stderr = decode_output(result.stderr)
        summary = first_line(redact(stdout + "\n" + stderr)) or f"{name} exited {result.returncode}"
        return EnvironmentCheck(name, "passed" if result.returncode == 0 else "failed", summary)


def first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


def decode_output(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return value
    return ""


def redact(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if "token:" in line.lower():
            lines.append("  - Token: [redacted]")
        else:
            lines.append(line)
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate local real-execution environment readiness.")
    parser.add_argument("--output", default=".alchemy/real_env_check")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = RealEnvironmentCheck().run(output_dir=args.output)
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.status == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
