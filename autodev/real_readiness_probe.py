"""Non-mutating readiness probe for real Codex and GitHub execution."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, Sequence

from .preflight import ExecutionPreflight
from .real_env_check import RealEnvironmentCheck
from .unified_preflight import UnifiedRunPreflight
from .unified_request import AutoDevRunRequest


class EnvRunner(Protocol):
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


class PreflightRunner(Protocol):
    def __call__(self, args: list[str], *, cwd: str | None, capture_output: bool, text: bool, check: bool) -> subprocess.CompletedProcess:
        ...


@dataclass(slots=True)
class RealReadinessReport:
    status: str
    environment: dict[str, object]
    request_preflights: list[dict[str, object]] = field(default_factory=list)
    blockers: list[dict[str, object]] = field(default_factory=list)
    warnings: list[dict[str, object]] = field(default_factory=list)
    output_dir: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "2.42",
            "status": self.status,
            "environment": dict(self.environment),
            "request_preflights": list(self.request_preflights),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "output_dir": self.output_dir,
        }


class RealReadinessProbe:
    """Combine tool readiness and real-mode unified request preflights."""

    def __init__(
        self,
        *,
        env_runner: EnvRunner = subprocess.run,
        preflight_runner: PreflightRunner = subprocess.run,
    ) -> None:
        self.env_runner = env_runner
        self.preflight_runner = preflight_runner

    def run(
        self,
        *,
        output_dir: str | Path = ".alchemy/real_readiness",
        codex_executable: str = "codex",
        require_browser: bool = False,
        include_private_github: bool = False,
    ) -> RealReadinessReport:
        output = Path(output_dir)
        if output.exists():
            shutil.rmtree(output)
        output.mkdir(parents=True, exist_ok=True)
        fixtures = write_probe_fixtures(output / "fixtures")

        environment = RealEnvironmentCheck(runner=self.env_runner).run(
            output_dir=output / "environment",
            codex_executable=codex_executable,
            require_browser=require_browser,
        ).to_dict()

        preflight_engine = UnifiedRunPreflight(
            execution_preflight=ExecutionPreflight(runner=self.preflight_runner)
        )
        request_preflights = [
            self._run_preflight(
                preflight_engine,
                "local_real_pr",
                {
                    "objective": "Probe real local repository execution readiness",
                    "documents": [str(fixtures["spec"])],
                    "repository_path": str(fixtures["repo"]),
                    "real_codex": True,
                    "real_github": True,
                    "codex_executable": codex_executable,
                    "github_collect_ci": True,
                    "output_dir": str(output / "local_real_pr"),
                },
            )
        ]
        if include_private_github:
            request_preflights.append(
                self._run_preflight(
                    preflight_engine,
                    "private_github_prepared_real_pr",
                    {
                        "objective": "Probe private GitHub prepared-source readiness",
                        "documents": [str(fixtures["spec"])],
                        "repository_url": "https://github.com/example/private-project",
                        "repository_visibility": "private",
                        "source_mode": "github_private",
                        "prepare_repository": True,
                        "real_codex": True,
                        "real_github": True,
                        "codex_executable": codex_executable,
                        "github_collect_ci": True,
                        "output_dir": str(output / "private_github_real_pr"),
                    },
                )
            )

        blockers = list(environment.get("blockers", [])) if isinstance(environment.get("blockers"), list) else []
        warnings: list[dict[str, object]] = []
        for item in request_preflights:
            if item.get("status") == "blocked":
                for blocker in item.get("blockers", []):
                    if isinstance(blocker, dict):
                        blockers.append({"id": f"B-REQUEST-{item.get('name')}", **blocker})
            for warning in item.get("warnings", []):
                if isinstance(warning, dict):
                    warnings.append({"request": item.get("name", ""), **warning})
        status = "ready" if not blockers else "blocked"
        report = RealReadinessReport(
            status=status,
            environment=environment,
            request_preflights=request_preflights,
            blockers=blockers,
            warnings=warnings,
            output_dir=str(output),
        )
        (output / "real_readiness_report.json").write_text(
            json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return report

    def _run_preflight(self, engine: UnifiedRunPreflight, name: str, payload: dict[str, Any]) -> dict[str, object]:
        report = engine.run(AutoDevRunRequest.from_mapping(payload)).to_dict()
        report["name"] = name
        return report


def write_probe_fixtures(root: Path) -> dict[str, Path]:
    repo = root / "repo"
    spec = root / "spec.md"
    (repo / "src" / "api").mkdir(parents=True)
    (repo / "src" / "pages").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src" / "api" / "workspaces.ts").write_text("export const api = true;\n", encoding="utf-8")
    (repo / "src" / "pages" / "dashboard.tsx").write_text("export const ui = true;\n", encoding="utf-8")
    (repo / "tests" / "workspaces.test.ts").write_text("test('workspace', () => {});\n", encoding="utf-8")
    (repo / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
    spec.write_text(
        "\n".join(
            [
                "# Real Readiness Probe Spec",
                "",
                "## Requirements",
                "- Must verify real Codex worker readiness for a local repository package.",
                "- Must verify GitHub PR delivery readiness without creating a PR.",
                "",
                "## Acceptance Criteria",
                "- Preflight can find git, gh, Codex CLI, and a local repository.",
                "- Private GitHub readiness is checked only when explicitly requested.",
            ]
        ),
        encoding="utf-8",
    )
    return {"repo": repo, "spec": spec}


def readiness_summary(report: dict[str, object]) -> dict[str, object]:
    return {
        "status": report.get("status", ""),
        "output_dir": report.get("output_dir", ""),
        "environment_status": dict(report.get("environment", {})).get("status", ""),
        "request_preflights": [
            {
                "name": item.get("name", ""),
                "status": item.get("status", ""),
                "blocker_count": len(item.get("blockers", [])) if isinstance(item.get("blockers"), list) else 0,
                "warning_count": len(item.get("warnings", [])) if isinstance(item.get("warnings"), list) else 0,
            }
            for item in report.get("request_preflights", [])
            if isinstance(item, dict)
        ],
        "blocker_count": len(report.get("blockers", [])) if isinstance(report.get("blockers"), list) else 0,
        "warning_count": len(report.get("warnings", [])) if isinstance(report.get("warnings"), list) else 0,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run non-mutating real execution readiness probes.")
    parser.add_argument("--output", default=".alchemy/real_readiness")
    parser.add_argument("--codex-executable", default="codex")
    parser.add_argument("--require-browser", action="store_true")
    parser.add_argument("--include-private-github", action="store_true")
    parser.add_argument("--summary", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = RealReadinessProbe().run(
        output_dir=args.output,
        codex_executable=args.codex_executable,
        require_browser=args.require_browser,
        include_private_github=args.include_private_github,
    )
    payload = report.to_dict()
    print(json.dumps(readiness_summary(payload) if args.summary else payload, indent=2, sort_keys=True))
    return 0 if report.status == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
