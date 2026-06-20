"""Deterministic benchmark suite for Alchemy autonomous delivery paths."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from intake.models import utc_now_iso


class CommandRunner(Protocol):
    def __call__(
        self,
        args: list[str],
        *,
        cwd: str | Path | None,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        ...


@dataclass(slots=True)
class BenchmarkScenario:
    name: str
    status: str
    command: list[str]
    output_dir: str
    duration_seconds: float
    checks: list[dict[str, object]] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "command": list(self.command),
            "output_dir": self.output_dir,
            "duration_seconds": round(self.duration_seconds, 3),
            "checks": list(self.checks),
            "stdout": trim(self.stdout),
            "stderr": trim(self.stderr),
        }


@dataclass(slots=True)
class BenchmarkSuiteReport:
    status: str
    output_dir: str
    scenarios: list[BenchmarkScenario] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, object]:
        scenarios = [scenario.to_dict() for scenario in self.scenarios]
        return {
            "schema_version": "2.50",
            "status": self.status,
            "output_dir": self.output_dir,
            "scenarios": scenarios,
            "created_at": self.created_at,
            "summary": {
                "total": len(scenarios),
                "passed": sum(1 for item in scenarios if item.get("status") == "passed"),
                "failed": sum(1 for item in scenarios if item.get("status") != "passed"),
                "failed_scenarios": [item.get("name", "") for item in scenarios if item.get("status") != "passed"],
            },
        }


class BenchmarkSuite:
    """Run repeatable dry-run benchmarks through public CLI contracts."""

    def __init__(self, *, runner: CommandRunner = subprocess.run) -> None:
        self.runner = runner

    def run(
        self,
        *,
        output_dir: str | Path = ".alchemy/benchmark_suite",
        clean_output: bool = True,
        include_unified_acceptance: bool = True,
        cwd: str | Path | None = None,
    ) -> BenchmarkSuiteReport:
        output = Path(output_dir)
        if output.exists() and clean_output:
            shutil.rmtree(output)
        output.mkdir(parents=True, exist_ok=True)
        fixtures = write_fixtures(output / "fixtures")

        scenarios = [
            self._run_command(
                name="one_line_cli",
                command=[
                    sys.executable,
                    "-B",
                    "-m",
                    "autodev.run",
                    "--objective",
                    "Build a small retro platform game",
                    "--output",
                    str(output / "one_line_cli"),
                ],
                output_dir=output / "one_line_cli",
                checks=[
                    report_check("unified_run_report.json", "status", "done"),
                    file_exists_check("index.html"),
                ],
                cwd=cwd,
            ),
            self._run_command(
                name="document_only_cli",
                command=[
                    sys.executable,
                    "-B",
                    "-m",
                    "autodev.run",
                    "--objective",
                    "Build from this development document",
                    "--document",
                    str(fixtures["spec"]),
                    "--output",
                    str(output / "document_only_cli"),
                ],
                output_dir=output / "document_only_cli",
                checks=[
                    report_check("unified_run_report.json", "status", "done"),
                    report_check("document_run_report.json", "status", "done"),
                    file_exists_check("generated_repository/index.html"),
                ],
                cwd=cwd,
            ),
            self._run_command(
                name="local_repository_cli",
                command=[
                    sys.executable,
                    "-B",
                    "-m",
                    "autodev.run",
                    "--objective",
                    "Add workspace support",
                    "--document",
                    str(fixtures["spec"]),
                    "--repository-path",
                    str(fixtures["repo"]),
                    "--output",
                    str(output / "local_repository_cli"),
                ],
                output_dir=output / "local_repository_cli",
                checks=[
                    report_check("unified_run_report.json", "status", "done"),
                    report_check("document_run_report.json", "status", "done"),
                    report_check("unified_run_report.json", "source_mode", "local"),
                ],
                cwd=cwd,
            ),
            self._run_command(
                name="real_unified_delivery_dry_run",
                command=[
                    sys.executable,
                    "-B",
                    "-m",
                    "autodev.real_unified_delivery",
                    "--objective",
                    "Add workspace support",
                    "--document",
                    str(fixtures["spec"]),
                    "--repository-path",
                    str(fixtures["repo"]),
                    "--output",
                    str(output / "real_unified_delivery"),
                    "--no-probe-index",
                    "--summary",
                ],
                output_dir=output / "real_unified_delivery",
                checks=[
                    report_check("real_unified_delivery_report.json", "status", "passed"),
                    summary_check("real_unified_delivery_report.json", "failed_required_gates", []),
                ],
                cwd=cwd,
            ),
        ]
        if include_unified_acceptance:
            scenarios.append(
                self._run_command(
                    name="unified_acceptance_harness",
                    command=[
                        sys.executable,
                        "-B",
                        "-m",
                        "autodev.unified_acceptance",
                        "--output",
                        str(output / "unified_acceptance"),
                        "--summary",
                    ],
                    output_dir=output / "unified_acceptance",
                    checks=[report_check("unified_acceptance_report.json", "status", "passed")],
                    cwd=cwd,
                )
            )

        package_root = output / "evidence_package"
        scenarios.append(
            self._run_command(
                name="evidence_package_export",
                command=[
                    sys.executable,
                    "-B",
                    "-m",
                    "autodev.evidence_package",
                    "--root",
                    str(output / "real_unified_delivery"),
                    "--output",
                    str(package_root),
                    "--summary",
                ],
                output_dir=package_root,
                checks=[report_check("evidence_package_manifest.json", "status", "passed")],
                cwd=cwd,
            )
        )

        status = "passed" if all(scenario.status == "passed" for scenario in scenarios) else "failed"
        report = BenchmarkSuiteReport(status=status, output_dir=str(output), scenarios=scenarios)
        (output / "benchmark_suite_report.json").write_text(
            json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return report

    def _run_command(
        self,
        *,
        name: str,
        command: list[str],
        output_dir: Path,
        checks: Sequence[dict[str, object]],
        cwd: str | Path | None,
    ) -> BenchmarkScenario:
        start = time.monotonic()
        completed = self.runner(command, cwd=cwd, capture_output=True, text=True, check=False)
        duration = time.monotonic() - start
        evaluated = [evaluate_check(output_dir, item) for item in checks]
        if completed.returncode != 0:
            evaluated.append(
                {
                    "name": "command_exit_zero",
                    "passed": False,
                    "detail": completed.returncode,
                }
            )
        status = "passed" if completed.returncode == 0 and all(item["passed"] for item in evaluated) else "failed"
        return BenchmarkScenario(
            name=name,
            status=status,
            command=command,
            output_dir=str(output_dir),
            duration_seconds=duration,
            checks=evaluated,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )


def report_check(report_name: str, key: str, expected: object) -> dict[str, object]:
    return {"type": "report_value", "report": report_name, "key": key, "expected": expected}


def summary_check(report_name: str, key: str, expected: object) -> dict[str, object]:
    return {"type": "summary_value", "report": report_name, "key": key, "expected": expected}


def file_exists_check(relative_path: str) -> dict[str, object]:
    return {"type": "file_exists", "path": relative_path}


def evaluate_check(output_dir: Path, check: Mapping[str, object]) -> dict[str, object]:
    kind = check.get("type")
    if kind == "file_exists":
        path = output_dir / str(check.get("path", ""))
        return {"name": f"file_exists:{check.get('path', '')}", "passed": path.exists(), "detail": str(path)}
    report = output_dir / str(check.get("report", ""))
    payload = read_json(report)
    if kind == "report_value":
        key = str(check.get("key", ""))
        actual = payload.get(key, None)
        return {
            "name": f"{report.name}:{key}",
            "passed": actual == check.get("expected"),
            "detail": {"actual": actual, "expected": check.get("expected")},
        }
    if kind == "summary_value":
        key = str(check.get("key", ""))
        summary = payload.get("summary", {})
        actual = summary.get(key, None) if isinstance(summary, Mapping) else None
        return {
            "name": f"{report.name}:summary.{key}",
            "passed": actual == check.get("expected"),
            "detail": {"actual": actual, "expected": check.get("expected")},
        }
    return {"name": "unknown_check", "passed": False, "detail": dict(check)}


def write_fixtures(root: Path) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
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
                "# Benchmark Development Spec",
                "",
                "## Objective",
                "Add workspace support.",
                "",
                "## Requirements",
                "- Must add workspace API support in src/api/workspaces.ts.",
                "- Must add dashboard workspace switching in src/pages/dashboard.tsx.",
                "- Must keep delivery evidence reviewable.",
                "",
                "## Acceptance Criteria",
                "- Users can create a workspace.",
                "- Users can switch active workspace.",
            ]
        ),
        encoding="utf-8",
    )
    return {"repo": repo, "spec": spec}


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def trim(value: str, limit: int = 12000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "...[truncated]"


def benchmark_summary(report: Mapping[str, Any]) -> dict[str, object]:
    return {
        "status": report.get("status", ""),
        "output_dir": report.get("output_dir", ""),
        "summary": report.get("summary", {}),
        "scenarios": [
            {
                "name": item.get("name", ""),
                "status": item.get("status", ""),
                "failed_checks": [
                    check.get("name", "")
                    for check in item.get("checks", [])
                    if isinstance(check, Mapping) and not check.get("passed", False)
                ],
            }
            for item in report.get("scenarios", [])
            if isinstance(item, Mapping)
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deterministic Alchemy benchmark scenarios.")
    parser.add_argument("--output", default=".alchemy/benchmark_suite")
    parser.add_argument("--keep-output", action="store_true")
    parser.add_argument("--skip-unified-acceptance", action="store_true")
    parser.add_argument("--summary", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = BenchmarkSuite().run(
        output_dir=args.output,
        clean_output=not args.keep_output,
        include_unified_acceptance=not args.skip_unified_acceptance,
    )
    payload = report.to_dict()
    print(json.dumps(benchmark_summary(payload) if args.summary else payload, indent=2, sort_keys=True))
    return 0 if report.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
