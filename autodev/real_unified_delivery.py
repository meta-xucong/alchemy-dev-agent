"""Unified real-delivery validation harness.

This module validates the full user-facing run contract by driving the existing
unified CLI and then collecting the evidence into one reviewable report.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from intake.models import utc_now_iso

from .real_probe_index import RealProbeIndexer
from .unified_preflight import UnifiedRunPreflight, write_unified_preflight_report
from .unified_request import AutoDevRunRequest


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
class DeliveryGate:
    name: str
    status: str
    required: bool
    detail: object = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "required": self.required,
            "detail": self.detail,
        }


@dataclass(slots=True)
class RealUnifiedDeliveryReport:
    status: str
    request: dict[str, object]
    output_dir: str
    command: dict[str, object] = field(default_factory=dict)
    preflight: dict[str, object] = field(default_factory=dict)
    unified_run: dict[str, object] = field(default_factory=dict)
    document_run: dict[str, object] = field(default_factory=dict)
    real_probe_index: dict[str, object] = field(default_factory=dict)
    gates: list[dict[str, object]] = field(default_factory=list)
    blockers: list[dict[str, object]] = field(default_factory=list)
    report_paths: dict[str, str] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "2.47",
            "status": self.status,
            "request": dict(self.request),
            "output_dir": self.output_dir,
            "command": dict(self.command),
            "preflight": dict(self.preflight),
            "unified_run": dict(self.unified_run),
            "document_run": dict(self.document_run),
            "real_probe_index": dict(self.real_probe_index),
            "gates": list(self.gates),
            "blockers": list(self.blockers),
            "report_paths": dict(self.report_paths),
            "created_at": self.created_at,
            "summary": {
                "required_gates": sum(1 for gate in self.gates if gate.get("required")),
                "passed_required_gates": sum(
                    1 for gate in self.gates if gate.get("required") and gate.get("status") == "passed"
                ),
                "failed_required_gates": [
                    gate.get("name", "")
                    for gate in self.gates
                    if gate.get("required") and gate.get("status") != "passed"
                ],
                "blocker_count": len(self.blockers),
            },
        }


class RealUnifiedDeliveryHarness:
    """Run one unified request and evaluate whether the full delivery contract holds."""

    def __init__(self, *, runner: CommandRunner = subprocess.run) -> None:
        self.runner = runner

    def run(
        self,
        payload: Mapping[str, Any] | None = None,
        *,
        output_dir: str | Path | None = None,
        probe_index_root: str | Path = ".alchemy",
        include_probe_index: bool = True,
        require_probe_index: bool = False,
        clean_output: bool = True,
        cwd: str | Path | None = None,
    ) -> RealUnifiedDeliveryReport:
        payload_dict = dict(payload or {})
        if output_dir is not None:
            payload_dict["output_dir"] = str(output_dir)
        request = AutoDevRunRequest.from_mapping(payload_dict)
        output = Path(request.output_dir)
        if output.exists() and clean_output:
            shutil.rmtree(output)
        output.mkdir(parents=True, exist_ok=True)

        preflight = UnifiedRunPreflight().run(request).to_dict()
        write_unified_preflight_report(output, preflight)
        blockers = preflight_blockers(preflight)
        validation_errors = request.validate_paths()
        blockers.extend(path_blockers(validation_errors))

        command: dict[str, object] = {}
        if not blockers:
            command_args = build_unified_run_command(request)
            completed = self.runner(
                command_args,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
            )
            command = completed_to_dict(command_args, completed)
            if completed.returncode != 0:
                blockers.append(
                    {
                        "id": "B-V2-47-UNIFIED-COMMAND",
                        "type": "execution",
                        "description": "Unified CLI returned a non-zero exit code.",
                        "required_resolution": "Inspect command stdout/stderr and the related run reports.",
                        "can_continue_partially": False,
                    }
                )

        unified_run = read_json(output / "unified_run_report.json")
        document_run = read_json(output / "document_run_report.json")
        probe_index: dict[str, object] = {}
        if include_probe_index:
            probe_index = self._build_probe_index(
                root=Path(probe_index_root),
                output_path=output / "real_probe_index.json",
            )

        gates = build_delivery_gates(
            request=request,
            preflight=preflight,
            validation_errors=validation_errors,
            command=command,
            unified_run=unified_run,
            document_run=document_run,
            probe_index=probe_index,
            include_probe_index=include_probe_index,
            require_probe_index=require_probe_index,
        )
        blockers.extend(blockers_from_gates(gates))
        status = "passed" if not blockers and required_gates_passed(gates) else "blocked"
        report = RealUnifiedDeliveryReport(
            status=status,
            request=request.to_dict(),
            output_dir=str(output),
            command=command,
            preflight=preflight,
            unified_run=unified_run,
            document_run=document_run,
            real_probe_index=probe_index,
            gates=[gate.to_dict() for gate in gates],
            blockers=blockers,
            report_paths={
                "real_unified_delivery_report": str(output / "real_unified_delivery_report.json"),
                "unified_preflight_report": str(output / "unified_preflight_report.json"),
                "unified_run_report": str(output / "unified_run_report.json"),
                "document_run_report": str(output / "document_run_report.json"),
                "real_probe_index": str(output / "real_probe_index.json"),
            },
        )
        (output / "real_unified_delivery_report.json").write_text(
            json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return report

    def _build_probe_index(self, *, root: Path, output_path: Path) -> dict[str, object]:
        if not root.exists():
            return {
                "status": "skipped",
                "summary": "Probe index root does not exist.",
                "roots": [str(root)],
            }
        return RealProbeIndexer().build(roots=[root], output_path=output_path).to_dict()


def build_unified_run_command(request: AutoDevRunRequest) -> list[str]:
    command = [
        sys.executable,
        "-B",
        "-m",
        "autodev.run",
        "--objective",
        request.objective,
        "--output",
        request.output_dir,
        "--source-mode",
        request.source_mode,
        "--delivery-mode",
        request.delivery_mode,
        "--repository-visibility",
        request.repository_visibility,
        "--target-branch",
        request.target_branch,
        "--max-iterations",
        str(request.max_iterations),
        "--codex-executable",
        request.codex_executable,
        "--max-worker-seconds",
        str(request.max_worker_seconds),
        "--github-ci-wait-seconds",
        str(request.github_ci_wait_seconds),
        "--github-ci-poll-interval-seconds",
        str(request.github_ci_poll_interval_seconds),
        "--worktree-branch-prefix",
        request.worktree_branch_prefix,
    ]
    for path in request.documents:
        command.extend(["--document", path])
    for path in request.attachments:
        command.extend(["--attachment", path])
    if request.repository_url:
        command.extend(["--repository", request.repository_url])
    if request.repository_path:
        command.extend(["--repository-path", request.repository_path])
    if request.base_branch:
        command.extend(["--base-branch", request.base_branch])
    if request.prepare_repository:
        command.append("--prepare-repository")
    if request.real_codex:
        command.append("--real-codex")
    if request.real_github:
        command.append("--real-github")
    if request.legacy_unlocked:
        command.append("--legacy-unlocked")
    if not request.github_collect_ci:
        command.append("--no-github-ci")
    if not request.isolate_real_run:
        command.append("--no-isolated-worktree")
    if not request.keep_worktree:
        command.append("--cleanup-worktree")
    if request.resume_from:
        command.extend(["--resume-from", request.resume_from])
    for task_id in request.resume_tasks:
        command.extend(["--resume-task", task_id])
    for feedback in request.feedback_files:
        command.extend(["--feedback-file", feedback])
    if request.project_id:
        command.extend(["--project-id", request.project_id])
    if request.source_run_id:
        command.extend(["--source-run-id", request.source_run_id])
    if request.auto_browser_verify:
        command.append("--auto-browser-verify")
    if not request.generate_static_ci:
        command.append("--no-generate-static-ci")
    if request.write_native_ui_tests:
        command.append("--write-native-ui-tests")
    if request.auto_merge:
        command.append("--auto-merge")
    for constraint in request.constraints:
        command.extend(["--constraint", constraint])
    for acceptance in request.acceptance_criteria:
        command.extend(["--acceptance", acceptance])
    return command


def build_delivery_gates(
    *,
    request: AutoDevRunRequest,
    preflight: Mapping[str, Any],
    validation_errors: Sequence[str],
    command: Mapping[str, Any],
    unified_run: Mapping[str, Any],
    document_run: Mapping[str, Any],
    probe_index: Mapping[str, Any],
    include_probe_index: bool,
    require_probe_index: bool,
) -> list[DeliveryGate]:
    final_score = unified_run.get("final_gate_score")
    delivery = as_dict(unified_run.get("delivery"))
    delivery_report = as_dict(document_run.get("delivery_report"))
    artifact_report = as_dict(document_run.get("artifact_report"))
    gates = [
        DeliveryGate("preflight_passed", pass_fail(preflight.get("status") == "passed"), True, preflight.get("status", "")),
        DeliveryGate("path_validation", pass_fail(not validation_errors), True, list(validation_errors)),
        DeliveryGate("unified_command_exit_zero", command_status(command), bool(command), command.get("exit_code", "not_run")),
        DeliveryGate("unified_run_done", pass_fail(unified_run.get("status") == "done"), True, unified_run.get("status", "")),
        DeliveryGate(
            "delivery_ready_for_review",
            pass_fail(bool(unified_run.get("ready_for_review") or delivery.get("ready_for_review"))),
            True,
            {"ready_for_review": unified_run.get("ready_for_review", delivery.get("ready_for_review", False))},
        ),
        final_gate(final_score),
        DeliveryGate(
            "real_codex_worker_evidence",
            pass_fail(has_real_worker_evidence(document_run)) if request.real_codex else "skipped",
            request.real_codex,
            {"real_codex": request.real_codex},
        ),
        DeliveryGate(
            "real_github_pr_evidence",
            pass_fail(has_real_github_evidence(delivery_report)) if request.real_github else "skipped",
            request.real_github,
            as_dict(delivery_report.get("github")),
        ),
        DeliveryGate(
            "browser_verification_evidence",
            pass_fail(has_passing_browser_evidence(artifact_report)) if request.auto_browser_verify else "skipped",
            request.auto_browser_verify,
            as_dict(artifact_report.get("browser_verification")),
        ),
    ]
    if include_probe_index:
        gates.append(
            DeliveryGate(
                "real_probe_index_available",
                pass_fail(probe_index.get("status") == "passed") if require_probe_index else optional_probe_status(probe_index),
                require_probe_index,
                {
                    "status": probe_index.get("status", ""),
                    "summary": probe_index.get("summary", {}),
                },
            )
        )
    return gates


def final_gate(score: object) -> DeliveryGate:
    if score is None:
        return DeliveryGate("final_gate_score", "skipped", False, "No final gate score reported for this route.")
    try:
        value = float(score)
    except (TypeError, ValueError):
        return DeliveryGate("final_gate_score", "failed", True, score)
    return DeliveryGate("final_gate_score", pass_fail(value >= 0.85), True, value)


def command_status(command: Mapping[str, Any]) -> str:
    if not command:
        return "skipped"
    return pass_fail(command.get("exit_code") == 0)


def optional_probe_status(probe_index: Mapping[str, Any]) -> str:
    if not probe_index or probe_index.get("status") == "skipped":
        return "skipped"
    return pass_fail(probe_index.get("status") == "passed")


def has_real_worker_evidence(document_run: Mapping[str, Any]) -> bool:
    runtime_state = as_dict(document_run.get("runtime_state"))
    lifecycle = runtime_state.get("worker_lifecycle", [])
    if isinstance(lifecycle, list) and lifecycle:
        return True
    delivery_report = as_dict(document_run.get("delivery_report"))
    worker = as_dict(delivery_report.get("worker_lifecycle"))
    return bool(worker.get("records") or worker.get("count"))


def has_real_github_evidence(delivery_report: Mapping[str, Any]) -> bool:
    github = as_dict(delivery_report.get("github"))
    pr_url = str(github.get("pull_request_url", github.get("pr_url", "")) or "")
    ci_status = str(github.get("ci_status", "") or "")
    return pr_url.startswith("http") and ci_status in {"passed", "waived"}


def has_passing_browser_evidence(artifact_report: Mapping[str, Any]) -> bool:
    browser = as_dict(artifact_report.get("browser_verification"))
    if not browser:
        return False
    status = str(browser.get("status", "") or "")
    if status == "passed":
        return True
    if status != "completed":
        return False
    failures = browser.get("tests_failed")
    console_errors = browser.get("console_errors")
    if isinstance(failures, Sequence) and not isinstance(failures, (str, bytes)) and failures:
        return False
    if isinstance(console_errors, Sequence) and not isinstance(console_errors, (str, bytes)) and console_errors:
        return False
    return bool(browser.get("tests_passed") or browser.get("evidence") or browser.get("screenshots"))


def blockers_from_gates(gates: Sequence[DeliveryGate]) -> list[dict[str, object]]:
    blockers: list[dict[str, object]] = []
    for gate in gates:
        if gate.required and gate.status != "passed":
            blockers.append(
                {
                    "id": f"B-V2-47-{gate.name.upper()}",
                    "type": "quality_gate",
                    "description": f"Required unified delivery gate did not pass: {gate.name}.",
                    "required_resolution": "Inspect the V2.47 report and rerun after the failing gate has evidence.",
                    "can_continue_partially": False,
                }
            )
    return blockers


def required_gates_passed(gates: Sequence[DeliveryGate]) -> bool:
    return all(not gate.required or gate.status == "passed" for gate in gates)


def preflight_blockers(preflight: Mapping[str, Any]) -> list[dict[str, object]]:
    if preflight.get("status") != "blocked":
        return []
    return [
        {
            "id": f"B-V2-47-PREFLIGHT-{item.get('code', 'unknown')}",
            "type": "preflight",
            "description": str(item.get("message", "Unified preflight blocked the run.")),
            "required_resolution": str(item.get("required_resolution", "Resolve preflight blocker and retry.")),
            "can_continue_partially": False,
        }
        for item in preflight.get("blockers", [])
        if isinstance(item, Mapping)
    ] or [
        {
            "id": "B-V2-47-PREFLIGHT",
            "type": "preflight",
            "description": "Unified preflight blocked the run.",
            "required_resolution": "Resolve preflight blockers and retry.",
            "can_continue_partially": False,
        }
    ]


def path_blockers(errors: Sequence[str]) -> list[dict[str, object]]:
    return [
        {
            "id": "B-V2-47-PATH-VALIDATION",
            "type": "input",
            "description": error,
            "required_resolution": "Provide existing document, attachment, repository, feedback, and resume paths.",
            "can_continue_partially": False,
        }
        for error in errors
    ]


def completed_to_dict(args: Sequence[str], completed: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return {
        "command": list(args),
        "exit_code": completed.returncode,
        "stdout": trim(completed.stdout or ""),
        "stderr": trim(completed.stderr or ""),
    }


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def pass_fail(value: bool) -> str:
    return "passed" if value else "failed"


def as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def trim(value: str, limit: int = 12000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "...[truncated]"


def report_summary(report: Mapping[str, Any]) -> dict[str, object]:
    return {
        "status": report.get("status", ""),
        "output_dir": report.get("output_dir", ""),
        "route": as_dict(report.get("request")).get("route", ""),
        "execution_mode": as_dict(report.get("request")).get("execution_mode", ""),
        "delivery_mode": as_dict(report.get("request")).get("delivery_mode", ""),
        "summary": report.get("summary", {}),
        "failed_required_gates": as_dict(report.get("summary")).get("failed_required_gates", []),
        "report_path": as_dict(report.get("report_paths")).get("real_unified_delivery_report", ""),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the V2.47 unified real-delivery validation harness.")
    parser.add_argument("--objective", required=True)
    parser.add_argument("--document", action="append", dest="documents", default=[])
    parser.add_argument("--attachment", action="append", dest="attachments", default=[])
    parser.add_argument("--repository", "--repository-url", dest="repository_url", default="")
    parser.add_argument("--repository-path", default="")
    parser.add_argument("--repository-visibility", choices=["public", "private", "unknown"], default="public")
    parser.add_argument("--source-mode", choices=["auto", "none", "local", "github_public", "github_private"], default="auto")
    parser.add_argument("--delivery-mode", choices=["report_only", "local", "github_pr"], default="report_only")
    parser.add_argument("--output", "--output-dir", dest="output_dir", default=".alchemy/real_unified_delivery")
    parser.add_argument("--target-branch", default="main")
    parser.add_argument("--base-branch", default="")
    parser.add_argument("--prepare-repository", action="store_true")
    parser.add_argument("--max-iterations", type=int, default=50)
    parser.add_argument("--real-codex", action="store_true")
    parser.add_argument("--real-github", action="store_true")
    parser.add_argument("--legacy-unlocked", action="store_true")
    parser.add_argument("--codex-executable", default="codex")
    parser.add_argument("--max-worker-seconds", type=int, default=1800)
    parser.add_argument("--no-github-ci", action="store_true")
    parser.add_argument("--github-ci-wait-seconds", type=float, default=120.0)
    parser.add_argument("--github-ci-poll-interval-seconds", type=float, default=10.0)
    parser.add_argument("--no-isolated-worktree", action="store_true")
    parser.add_argument("--cleanup-worktree", action="store_true")
    parser.add_argument("--worktree-branch-prefix", default="agent/alchemy-real-run")
    parser.add_argument("--auto-browser-verify", action="store_true")
    parser.add_argument("--no-generate-static-ci", action="store_true")
    parser.add_argument("--write-native-ui-tests", action="store_true")
    parser.add_argument("--auto-merge", action="store_true")
    parser.add_argument("--constraint", action="append", dest="constraints", default=[])
    parser.add_argument("--acceptance", action="append", dest="acceptance_criteria", default=[])
    parser.add_argument("--probe-index-root", default=".alchemy")
    parser.add_argument("--no-probe-index", action="store_true")
    parser.add_argument("--require-probe-index", action="store_true")
    parser.add_argument("--keep-output", action="store_true")
    parser.add_argument("--summary", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = {
        "objective": args.objective,
        "documents": args.documents,
        "attachments": args.attachments,
        "repository_url": args.repository_url,
        "repository_path": args.repository_path,
        "repository_visibility": args.repository_visibility,
        "source_mode": args.source_mode,
        "delivery_mode": "github_pr" if args.real_github else args.delivery_mode,
        "output_dir": args.output_dir,
        "target_branch": args.target_branch,
        "base_branch": args.base_branch,
        "prepare_repository": args.prepare_repository,
        "max_iterations": args.max_iterations,
        "real_codex": args.real_codex,
        "real_github": args.real_github,
        "legacy_unlocked": args.legacy_unlocked,
        "codex_executable": args.codex_executable,
        "max_worker_seconds": args.max_worker_seconds,
        "github_collect_ci": not args.no_github_ci,
        "github_ci_wait_seconds": args.github_ci_wait_seconds,
        "github_ci_poll_interval_seconds": args.github_ci_poll_interval_seconds,
        "isolate_real_run": not args.no_isolated_worktree,
        "keep_worktree": not args.cleanup_worktree,
        "worktree_branch_prefix": args.worktree_branch_prefix,
        "auto_browser_verify": args.auto_browser_verify,
        "generate_static_ci": not args.no_generate_static_ci,
        "write_native_ui_tests": args.write_native_ui_tests,
        "auto_merge": args.auto_merge,
        "constraints": args.constraints,
        "acceptance_criteria": args.acceptance_criteria,
    }
    report = RealUnifiedDeliveryHarness().run(
        payload,
        probe_index_root=args.probe_index_root,
        include_probe_index=not args.no_probe_index,
        require_probe_index=args.require_probe_index,
        clean_output=not args.keep_output,
    )
    payload_out = report.to_dict()
    print(json.dumps(report_summary(payload_out) if args.summary else payload_out, indent=2, sort_keys=True))
    return 0 if report.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
