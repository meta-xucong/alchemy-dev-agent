"""Controlled local smoke for a real Codex document-run pipeline."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from .document_run import DocumentRunPipeline
from .preflight import ExecutionPreflight


@dataclass(slots=True)
class RealDocumentRunSmokeReport:
    status: str
    preflight: dict[str, object]
    document_run: dict[str, object]
    verification: dict[str, object]
    repository: dict[str, object]
    blockers: list[dict[str, object]] = field(default_factory=list)
    output_dir: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "2.44",
            "status": self.status,
            "preflight": dict(self.preflight),
            "document_run": dict(self.document_run),
            "verification": dict(self.verification),
            "repository": dict(self.repository),
            "blockers": list(self.blockers),
            "output_dir": self.output_dir,
        }


class RealDocumentRunSmoke:
    """Run a minimal document-driven pipeline with real Codex enabled."""

    def __init__(self, *, pipeline_factory: Callable[[], Any] = DocumentRunPipeline) -> None:
        self.pipeline_factory = pipeline_factory

    def run(
        self,
        *,
        output_dir: str | Path = ".alchemy/real_document_run_smoke",
        codex_executable: str = "codex",
        timeout_seconds: int = 300,
        keep: bool = False,
        real_codex: bool = True,
    ) -> RealDocumentRunSmokeReport:
        output = Path(output_dir)
        if output.exists() and not keep:
            shutil.rmtree(output)
        output.mkdir(parents=True, exist_ok=True)
        repo = output / "repo"
        spec = output / "spec.md"
        write_fixture_repo(repo)
        write_spec(spec)
        initialize_git(repo)

        preflight = ExecutionPreflight().check(
            repository_path=repo,
            real_codex=real_codex,
            real_github=False,
            codex_executable=codex_executable,
        ).to_dict()
        if preflight["status"] == "blocked":
            report = RealDocumentRunSmokeReport(
                status="blocked",
                preflight=preflight,
                document_run={},
                verification={},
                repository=repository_report(repo, repo),
                blockers=[
                    {
                        "id": "B-REAL-DOCUMENT-RUN-PREFLIGHT",
                        "type": "environment",
                        "description": "Real document-run smoke preflight failed.",
                        "required_resolution": "Install/configure Codex CLI or run a dry/fake test path.",
                    }
                ],
                output_dir=str(output),
            )
            return write_report(output, report)

        result = self.pipeline_factory().run(
            objective="Implement the add function from the supplied development document.",
            documents=[spec],
            repository_path=repo,
            output_dir=output / "run",
            real_codex=real_codex,
            real_github=False,
            codex_executable=codex_executable,
            max_worker_seconds=timeout_seconds,
            isolate_real_run=real_codex,
            keep_worktree=True,
            max_iterations=20,
        )
        payload = result.to_dict()
        execution_repo = execution_repository_path(payload, fallback=repo)
        verification = verify_fixture(execution_repo)
        repository = repository_report(repo, execution_repo)
        blockers = smoke_blockers(payload, verification, require_worker_lifecycle=real_codex)
        status = "passed" if not blockers else "failed"
        report = RealDocumentRunSmokeReport(
            status=status,
            preflight=preflight,
            document_run=summarize_document_run(payload),
            verification=verification,
            repository=repository,
            blockers=blockers,
            output_dir=str(output),
        )
        return write_report(output, report)


def write_fixture_repo(repo: Path) -> None:
    (repo / "tests").mkdir(parents=True, exist_ok=True)
    (repo / "app.py").write_text(
        "\n".join(
            [
                '"""Tiny fixture module for a real document-run smoke."""',
                "",
                "def add(a, b):",
                "    raise NotImplementedError('replace me')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo / "tests" / "test_app.py").write_text(
        "\n".join(
            [
                "import unittest",
                "",
                "import app",
                "",
                "",
                "class AddTests(unittest.TestCase):",
                "    def test_adds_numbers(self):",
                "        self.assertEqual(app.add(2, 3), 5)",
                "",
                "",
                "if __name__ == '__main__':",
                "    unittest.main()",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo / "requirements.txt").write_text("# standard-library fixture\n", encoding="utf-8")


def write_spec(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# Add Function Development Spec",
                "",
                "## Requirements",
                "- Must implement add(a, b) in app.py.",
                "",
                "## Acceptance Criteria",
                "- app.add(2, 3) returns 5.",
                "- python -m unittest discover -s tests passes.",
                "- Only app.py is modified for implementation.",
            ]
        ),
        encoding="utf-8",
    )


def initialize_git(repo: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, text=True, check=False)
    subprocess.run(["git", "config", "user.email", "alchemy@example.invalid"], cwd=repo, capture_output=True, text=True, check=False)
    subprocess.run(["git", "config", "user.name", "Alchemy Smoke"], cwd=repo, capture_output=True, text=True, check=False)
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, text=True, check=False)
    subprocess.run(["git", "commit", "-m", "Initial fixture"], cwd=repo, capture_output=True, text=True, check=False)


def execution_repository_path(payload: dict[str, object], *, fallback: Path) -> Path:
    workspace = payload.get("workspace", {})
    if isinstance(workspace, dict):
        for key in ("execution_path", "worktree_path", "source_path"):
            value = str(workspace.get(key, "") or "")
            if value and Path(value).exists():
                return Path(value)
    runtime = payload.get("runtime_state", {})
    repository = runtime.get("repository", {}) if isinstance(runtime, dict) else {}
    if isinstance(repository, dict):
        value = str(repository.get("path", "") or "")
        if value and Path(value).exists():
            return Path(value)
    return fallback


def verify_fixture(repo: Path) -> dict[str, object]:
    result = subprocess.run(
        ["python", "-m", "unittest", "discover", "-s", "tests"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    source = (repo / "app.py").read_text(encoding="utf-8", errors="replace") if (repo / "app.py").exists() else ""
    status = "passed" if result.returncode == 0 else "failed"
    return {
        "status": status,
        "command": "python -m unittest discover -s tests",
        "exit_code": result.returncode,
        "summary": "Document-run fixture tests passed." if status == "passed" else "Document-run fixture tests failed.",
        "stdout": result.stdout,
        "stderr": result.stderr,
        "app_py_contains_placeholder": "NotImplementedError" in source,
    }


def repository_report(source_repo: Path, execution_repo: Path) -> dict[str, object]:
    status = subprocess.run(["git", "status", "--porcelain"], cwd=execution_repo, capture_output=True, text=True, check=False)
    diff = subprocess.run(["git", "diff", "--", "app.py"], cwd=execution_repo, capture_output=True, text=True, check=False)
    return {
        "source_path": str(source_repo),
        "execution_path": str(execution_repo),
        "git_status": status.stdout.splitlines(),
        "app_py": (execution_repo / "app.py").read_text(encoding="utf-8", errors="replace")
        if (execution_repo / "app.py").exists()
        else "",
        "app_py_diff": diff.stdout,
    }


def smoke_blockers(payload: dict[str, object], verification: dict[str, object], *, require_worker_lifecycle: bool) -> list[dict[str, object]]:
    blockers: list[dict[str, object]] = []
    if payload.get("status") != "done":
        blockers.append(
            {
                "id": "B-REAL-DOCUMENT-RUN-STATUS",
                "type": "runtime",
                "description": f"DocumentRunPipeline status was {payload.get('status')}.",
                "required_resolution": "Inspect runtime_state blockers and worker output.",
            }
        )
    if verification.get("status") != "passed":
        blockers.append(
            {
                "id": "B-REAL-DOCUMENT-RUN-VERIFY",
                "type": "verification",
                "description": str(verification.get("summary", "Verification failed.")),
                "required_resolution": "Inspect app.py, tests, and worker evidence.",
            }
        )
    runtime = payload.get("runtime_state", {})
    worker_lifecycle = runtime.get("worker_lifecycle", []) if isinstance(runtime, dict) else []
    if require_worker_lifecycle and not worker_lifecycle:
        blockers.append(
            {
                "id": "B-REAL-DOCUMENT-RUN-LIFECYCLE",
                "type": "worker",
                "description": "No real worker lifecycle evidence was recorded.",
                "required_resolution": "Ensure real_codex=true and worker lifecycle recorder is enabled.",
            }
        )
    return blockers


def summarize_document_run(payload: dict[str, object]) -> dict[str, object]:
    runtime = payload.get("runtime_state", {})
    worker_lifecycle = runtime.get("worker_lifecycle", []) if isinstance(runtime, dict) else []
    delivery_report = payload.get("delivery_report", {})
    return {
        "status": payload.get("status", ""),
        "output_dir": payload.get("output_dir", ""),
        "preflight_status": dict(payload.get("preflight", {})).get("status", ""),
        "workspace": payload.get("workspace", {}),
        "worker_lifecycle": worker_lifecycle,
        "worker_lifecycle_count": len(worker_lifecycle) if isinstance(worker_lifecycle, list) else 0,
        "delivery_ready_for_review": dict(delivery_report).get("ready_for_review", False)
        if isinstance(delivery_report, dict)
        else False,
        "final_gate": dict(delivery_report).get("final_gate", {}) if isinstance(delivery_report, dict) else {},
    }


def write_report(output: Path, report: RealDocumentRunSmokeReport) -> RealDocumentRunSmokeReport:
    (output / "real_document_run_smoke_report.json").write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def smoke_summary(report: dict[str, object]) -> dict[str, object]:
    return {
        "status": report.get("status", ""),
        "output_dir": report.get("output_dir", ""),
        "preflight_status": dict(report.get("preflight", {})).get("status", ""),
        "document_run_status": dict(report.get("document_run", {})).get("status", ""),
        "worker_lifecycle_count": dict(report.get("document_run", {})).get("worker_lifecycle_count", 0),
        "verification_status": dict(report.get("verification", {})).get("status", ""),
        "blocker_count": len(report.get("blockers", [])) if isinstance(report.get("blockers"), list) else 0,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a controlled local real document-run smoke.")
    parser.add_argument("--output", default=".alchemy/real_document_run_smoke")
    parser.add_argument("--codex-executable", default="codex")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--dry-run-codex", action="store_true")
    parser.add_argument("--summary", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = RealDocumentRunSmoke().run(
        output_dir=args.output,
        codex_executable=args.codex_executable,
        timeout_seconds=args.timeout_seconds,
        keep=args.keep,
        real_codex=not args.dry_run_codex,
    )
    payload = report.to_dict()
    print(json.dumps(smoke_summary(payload) if args.summary else payload, indent=2, sort_keys=True))
    return 0 if report.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
