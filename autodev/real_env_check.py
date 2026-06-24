"""Real-execution environment validation for external delivery readiness."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, Sequence

from intake.models import utc_now_iso


class CommandRunner(Protocol):
    def __call__(
        self,
        args: list[str],
        *,
        cwd: str | None,
        capture_output: bool,
        text: bool,
        check: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess:
        ...


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

    def __init__(self, runner: CommandRunner = subprocess.run) -> None:
        self.runner = runner

    def run(
        self,
        *,
        output_dir: str | Path = ".alchemy/real_env_check",
        codex_executable: str = "codex",
        require_browser: bool = False,
        model_provider: str = "codex_cli",
        model_api_key_env: str = "",
        model_base_url: str = "",
    ) -> EnvironmentReport:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        checks = [
            self._command_check("git", ["git", "--version"]),
            self._command_check("gh", ["gh", "--version"]),
            self._command_check("gh_auth", ["gh", "auth", "status"]),
            self._command_check("codex", [codex_executable, "--version"]),
        ]
        checks.append(
            self._model_check(
                provider=model_provider,
                api_key_env=model_api_key_env,
                base_url=model_base_url,
            )
        )
        checks.append(self._browser_check(required=require_browser))
        blockers = []
        for check in checks:
            if check.required and check.status != "passed":
                blockers.append(
                    {
                        "id": f"B-ENV-{check.name.upper()}",
                        "type": "environment",
                        "description": check.summary,
                        "required_resolution": "Install, authenticate, or repair the required local tool before real execution validation.",
                        "can_continue_partially": check.name not in {"codex", "model_access"},
                    }
                )
        status = "ready" if not blockers else "blocked"
        report = EnvironmentReport(status=status, checks=checks, blockers=blockers, output_dir=str(output))
        (output / "real_environment_report.json").write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return report

    def _command_check(self, name: str, command: list[str]) -> EnvironmentCheck:
        executable = command[0]
        if not is_launchable_reference(executable):
            return EnvironmentCheck(name, "failed", f"Executable not found on PATH: {executable}")
        try:
            result = self.runner(command, cwd=None, capture_output=True, text=False, check=False, timeout=30)
        except (OSError, subprocess.SubprocessError, UnicodeDecodeError) as exc:
            return EnvironmentCheck(name, "failed", redact(str(exc)))
        stdout = decode_output(result.stdout)
        stderr = decode_output(result.stderr)
        summary = first_line(redact(stdout + "\n" + stderr)) or f"{name} exited {result.returncode}"
        return EnvironmentCheck(name, "passed" if result.returncode == 0 else "failed", summary)

    def _browser_check(self, *, required: bool) -> EnvironmentCheck:
        try:
            import playwright.sync_api  # type: ignore[import-not-found]  # noqa: F401
        except ImportError:
            return EnvironmentCheck(
                "browser_automation",
                "failed" if required else "skipped",
                "Playwright is not installed; automatic browser artifact verification is unavailable.",
                required=required,
            )
        return EnvironmentCheck(
            "browser_automation",
            "passed",
            "Playwright package is importable for automatic browser artifact verification.",
            required=required,
        )

    def _model_check(self, *, provider: str, api_key_env: str, base_url: str) -> EnvironmentCheck:
        normalized = provider.strip().lower().replace("-", "_") or "codex_cli"
        env_name = api_key_env.strip()
        endpoint = base_url.strip()
        if normalized in {"codex", "codex_cli", "codex_worker"}:
            return EnvironmentCheck(
                "model_access",
                "passed",
                "Model access is delegated to the configured Codex CLI worker.",
                required=True,
            )
        if normalized == "openai":
            return self._api_key_check(env_name or "OPENAI_API_KEY", "OpenAI")
        if normalized in {"anthropic", "claude"}:
            return self._api_key_check(env_name or "ANTHROPIC_API_KEY", "Anthropic")
        if normalized == "custom":
            env_name = env_name or "CUSTOM_LLM_API_KEY"
            missing = []
            if not endpoint:
                missing.append("custom model base URL")
            if not os.environ.get(env_name):
                missing.append(f"{env_name} environment variable")
            if missing:
                return EnvironmentCheck(
                    "model_access",
                    "failed",
                    f"Missing {', '.join(missing)} for custom model access.",
                    required=True,
                )
            return EnvironmentCheck(
                "model_access",
                "passed",
                f"Custom model endpoint and {env_name} are configured.",
                required=True,
            )
        return EnvironmentCheck(
            "model_access",
            "failed",
            f"Unsupported model provider: {provider}",
            required=True,
        )

    def _api_key_check(self, env_name: str, label: str) -> EnvironmentCheck:
        if os.environ.get(env_name):
            return EnvironmentCheck(
                "model_access",
                "passed",
                f"{env_name} is configured for {label} model access.",
                required=True,
            )
        return EnvironmentCheck(
            "model_access",
            "failed",
            f"{env_name} is not set for {label} model access.",
            required=True,
        )


def detect_environment_defaults() -> dict[str, object]:
    """Return safe local defaults that the browser console can prefill."""

    codex_path = shutil.which("codex") or "codex"
    gh_path = shutil.which("gh") or ""
    return {
        "schema_version": "2.56",
        "codex_executable": codex_path,
        "github_cli": gh_path,
        "model_provider": "codex_cli",
        "orchestrator_model": "codex-cli",
        "document_expansion_model": "codex-cli",
        "reviewer_model": "codex-cli",
        "model_api_key_env": "",
        "model_base_url": "",
        "openai_api_key_configured": bool(os.environ.get("OPENAI_API_KEY")),
        "anthropic_api_key_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "recommended_mode": "codex_cli",
    }


def first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


def decode_output(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return value
    return ""


def is_launchable_reference(executable: str) -> bool:
    return shutil.which(executable) is not None or Path(executable).is_file()


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
    parser.add_argument("--codex-executable", default="codex")
    parser.add_argument("--require-browser", action="store_true", help="Treat browser automation readiness as required.")
    parser.add_argument("--model-provider", default="codex_cli")
    parser.add_argument("--model-api-key-env", default="")
    parser.add_argument("--model-base-url", default="")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = RealEnvironmentCheck().run(
        output_dir=args.output,
        codex_executable=args.codex_executable,
        require_browser=args.require_browser,
        model_provider=args.model_provider,
        model_api_key_env=args.model_api_key_env,
        model_base_url=args.model_base_url,
    )
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.status == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
