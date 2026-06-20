"""Controlled local smoke for a real Codex worker task."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from runtime import CodexWorkerAdapter, CodexWorkerInput, WorkerLifecycleRecorder

from .preflight import ExecutionPreflight


@dataclass(slots=True)
class RealWorkerSmokeReport:
    status: str
    preflight: dict[str, object]
    worker_result: dict[str, object]
    verification: dict[str, object]
    repository: dict[str, object]
    blockers: list[dict[str, object]] = field(default_factory=list)
    output_dir: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "2.43",
            "status": self.status,
            "preflight": dict(self.preflight),
            "worker_result": dict(self.worker_result),
            "verification": dict(self.verification),
            "repository": dict(self.repository),
            "blockers": list(self.blockers),
            "output_dir": self.output_dir,
        }


class RealWorkerSmoke:
    """Run one bounded worker task in a disposable local repository."""

    def __init__(self, *, runner: Any = subprocess.run) -> None:
        self.runner = runner

    def run(
        self,
        *,
        output_dir: str | Path = ".alchemy/real_worker_smoke",
        codex_executable: str = "codex",
        timeout_seconds: int = 300,
        dry_run_worker: bool = False,
        keep: bool = False,
    ) -> RealWorkerSmokeReport:
        output = Path(output_dir)
        if output.exists() and not keep:
            shutil.rmtree(output)
        output.mkdir(parents=True, exist_ok=True)
        repo = output / "repo"
        write_fixture_repo(repo)
        initialize_git(repo)

        preflight = ExecutionPreflight().check(
            repository_path=repo,
            real_codex=not dry_run_worker,
            real_github=False,
            codex_executable=codex_executable,
        ).to_dict()
        if preflight["status"] == "blocked":
            report = RealWorkerSmokeReport(
                status="blocked",
                preflight=preflight,
                worker_result={},
                verification={},
                repository=repository_report(repo),
                blockers=[
                    {
                        "id": "B-REAL-WORKER-PREFLIGHT",
                        "type": "environment",
                        "description": "Real worker smoke preflight failed.",
                        "required_resolution": "Install/configure Codex CLI or run with --dry-run-worker.",
                    }
                ],
                output_dir=str(output),
            )
            return write_report(output, report)

        worker = CodexWorkerAdapter(
            executable=codex_executable,
            dry_run=dry_run_worker,
            timeout_seconds=timeout_seconds,
            lifecycle_recorder=WorkerLifecycleRecorder(output / "workers") if not dry_run_worker else None,
            runner=self.runner,
        )
        worker_input = CodexWorkerInput(
            task_id="T-REAL-SMOKE-001",
            objective="Verify that a bounded real Codex worker can update a local fixture repository.",
            goal="Implement add(a, b) in app.py so it returns the numeric sum of the two inputs.",
            task_description="Replace the placeholder add implementation with a correct numeric addition function.",
            acceptance_criteria=["app.add(2, 3) returns 5.", "Only app.py is modified."],
            repository_path=str(repo),
            relevant_files=["app.py"],
            allowed_files=["app.py"],
            commands_to_run=[verification_command()],
        )
        worker_result = worker.execute(worker_input).to_dict()
        verification = verify_fixture(repo)
        blockers = []
        if worker_result.get("status") != "completed":
            blockers.append(
                {
                    "id": "B-REAL-WORKER-RESULT",
                    "type": "worker",
                    "description": str(worker_result.get("summary", "Worker did not complete.")),
                    "required_resolution": "Inspect worker raw output and lifecycle evidence.",
                }
            )
        if verification["status"] != "passed":
            blockers.append(
                {
                    "id": "B-REAL-WORKER-VERIFY",
                    "type": "verification",
                    "description": verification.get("summary", "Verification failed."),
                    "required_resolution": "Inspect app.py and worker result evidence.",
                }
            )
        status = "passed" if not blockers else "failed"
        report = RealWorkerSmokeReport(
            status=status,
            preflight=preflight,
            worker_result=worker_result,
            verification=verification,
            repository=repository_report(repo),
            blockers=blockers,
            output_dir=str(output),
        )
        return write_report(output, report)


def write_fixture_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "app.py").write_text(
        "\n".join(
            [
                '"""Tiny fixture module for the real worker smoke."""',
                "",
                "def add(a, b):",
                "    raise NotImplementedError('replace me')",
                "",
            ]
        ),
        encoding="utf-8",
    )


def initialize_git(repo: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, text=True, check=False)
    subprocess.run(["git", "config", "user.email", "alchemy@example.invalid"], cwd=repo, capture_output=True, text=True, check=False)
    subprocess.run(["git", "config", "user.name", "Alchemy Smoke"], cwd=repo, capture_output=True, text=True, check=False)
    subprocess.run(["git", "add", "app.py"], cwd=repo, capture_output=True, text=True, check=False)
    subprocess.run(["git", "commit", "-m", "Initial fixture"], cwd=repo, capture_output=True, text=True, check=False)


def verification_command() -> str:
    return "python -c \"import app; assert app.add(2, 3) == 5\""


def verify_fixture(repo: Path) -> dict[str, object]:
    result = subprocess.run(
        ["python", "-c", "import app; assert app.add(2, 3) == 5"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    source = (repo / "app.py").read_text(encoding="utf-8", errors="replace")
    status = "passed" if result.returncode == 0 else "failed"
    return {
        "status": status,
        "command": verification_command(),
        "exit_code": result.returncode,
        "summary": "Fixture add() verification passed." if status == "passed" else "Fixture add() verification failed.",
        "stdout": result.stdout,
        "stderr": result.stderr,
        "app_py_contains_placeholder": "NotImplementedError" in source,
    }


def repository_report(repo: Path) -> dict[str, object]:
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=False)
    diff = subprocess.run(["git", "diff", "--", "app.py"], cwd=repo, capture_output=True, text=True, check=False)
    return {
        "path": str(repo),
        "git_status": status.stdout.splitlines(),
        "app_py": (repo / "app.py").read_text(encoding="utf-8", errors="replace") if (repo / "app.py").exists() else "",
        "app_py_diff": diff.stdout,
    }


def write_report(output: Path, report: RealWorkerSmokeReport) -> RealWorkerSmokeReport:
    (output / "real_worker_smoke_report.json").write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def smoke_summary(report: dict[str, object]) -> dict[str, object]:
    return {
        "status": report.get("status", ""),
        "output_dir": report.get("output_dir", ""),
        "preflight_status": dict(report.get("preflight", {})).get("status", ""),
        "worker_status": dict(report.get("worker_result", {})).get("status", ""),
        "verification_status": dict(report.get("verification", {})).get("status", ""),
        "blocker_count": len(report.get("blockers", [])) if isinstance(report.get("blockers"), list) else 0,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a controlled local real Codex worker smoke.")
    parser.add_argument("--output", default=".alchemy/real_worker_smoke")
    parser.add_argument("--codex-executable", default="codex")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--dry-run-worker", action="store_true")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--summary", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = RealWorkerSmoke().run(
        output_dir=args.output,
        codex_executable=args.codex_executable,
        timeout_seconds=args.timeout_seconds,
        dry_run_worker=args.dry_run_worker,
        keep=args.keep,
    )
    payload = report.to_dict()
    print(json.dumps(smoke_summary(payload) if args.summary else payload, indent=2, sort_keys=True))
    return 0 if report.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
