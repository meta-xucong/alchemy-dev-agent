"""Unified autonomous development CLI entrypoint."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .document_run import DocumentRunPipeline
from .pipeline import AutoDevPipeline
from .unified_preflight import UnifiedRunPreflight, unified_preflight_summary, write_unified_preflight_report
from .unified_request import AutoDevRunRequest, unified_run_summary, write_unified_run_outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Alchemy Dev Agent through one unified CLI contract.")
    parser.add_argument("--objective", default="")
    parser.add_argument("--document", action="append", dest="documents", default=[])
    parser.add_argument("--attachment", action="append", dest="attachments", default=[])
    parser.add_argument("--repository", "--repository-url", dest="repository_url", default="")
    parser.add_argument("--repository-path", default="")
    parser.add_argument("--repository-visibility", choices=["public", "private", "unknown"], default="public")
    parser.add_argument("--source-mode", choices=["auto", "none", "local", "github_public", "github_private"], default="auto")
    parser.add_argument("--execution-mode", choices=["dry_run", "real_codex"], default="dry_run")
    parser.add_argument("--delivery-mode", choices=["report_only", "local", "github_pr"], default="report_only")
    parser.add_argument("--output", "--output-dir", dest="output_dir", default=".alchemy/unified_run")
    parser.add_argument("--target-branch", default="main")
    parser.add_argument("--base-branch", default="")
    parser.add_argument("--prepare-repository", action="store_true")
    parser.add_argument("--max-iterations", type=int, default=50)
    parser.add_argument("--real-codex", action="store_true")
    parser.add_argument("--real-github", action="store_true")
    parser.add_argument("--codex-executable", default="codex")
    parser.add_argument("--max-worker-seconds", type=int, default=1800)
    parser.add_argument("--no-github-ci", action="store_true")
    parser.add_argument("--github-ci-wait-seconds", type=float, default=120.0)
    parser.add_argument("--github-ci-poll-interval-seconds", type=float, default=10.0)
    parser.add_argument("--no-isolated-worktree", action="store_true")
    parser.add_argument("--cleanup-worktree", action="store_true")
    parser.add_argument("--worktree-branch-prefix", default="agent/alchemy-real-run")
    parser.add_argument("--resume-from", default="")
    parser.add_argument("--resume-task", action="append", dest="resume_tasks", default=[])
    parser.add_argument("--feedback-file", action="append", dest="feedback_files", default=[])
    parser.add_argument("--project-id", default="")
    parser.add_argument("--source-run-id", default="")
    parser.add_argument("--auto-browser-verify", action="store_true")
    parser.add_argument("--no-generate-static-ci", action="store_true")
    parser.add_argument("--write-native-ui-tests", action="store_true")
    parser.add_argument("--auto-merge", action="store_true")
    parser.add_argument("--preflight-only", action="store_true", help="Validate the unified run request without creating or executing a project.")
    parser.add_argument("--constraint", action="append", dest="constraints", default=[])
    parser.add_argument("--acceptance", action="append", dest="acceptance_criteria", default=[])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    request = AutoDevRunRequest.from_mapping(
        {
            "objective": args.objective,
            "documents": args.documents,
            "attachments": args.attachments,
            "repository_url": args.repository_url,
            "repository_path": args.repository_path,
            "repository_visibility": args.repository_visibility,
            "source_mode": args.source_mode,
            "execution_mode": "real_codex" if args.real_codex else args.execution_mode,
            "delivery_mode": "github_pr" if args.real_github else args.delivery_mode,
            "output_dir": args.output_dir,
            "target_branch": args.target_branch,
            "base_branch": args.base_branch,
            "prepare_repository": args.prepare_repository,
            "max_iterations": args.max_iterations,
            "codex_executable": args.codex_executable,
            "max_worker_seconds": args.max_worker_seconds,
            "github_collect_ci": not args.no_github_ci,
            "github_ci_wait_seconds": args.github_ci_wait_seconds,
            "github_ci_poll_interval_seconds": args.github_ci_poll_interval_seconds,
            "isolate_real_run": not args.no_isolated_worktree,
            "keep_worktree": not args.cleanup_worktree,
            "worktree_branch_prefix": args.worktree_branch_prefix,
            "resume_from": args.resume_from,
            "resume_tasks": args.resume_tasks,
            "feedback_files": args.feedback_files,
            "project_id": args.project_id,
            "source_run_id": args.source_run_id,
            "auto_browser_verify": args.auto_browser_verify,
            "generate_static_ci": not args.no_generate_static_ci,
            "write_native_ui_tests": args.write_native_ui_tests,
            "auto_merge": args.auto_merge,
            "constraints": args.constraints,
            "acceptance_criteria": args.acceptance_criteria,
        }
    )
    preflight_report = UnifiedRunPreflight().run(request).to_dict()
    write_unified_preflight_report(request.output_dir, preflight_report)
    if args.preflight_only:
        print(json.dumps(unified_preflight_summary(preflight_report), indent=2, sort_keys=True))
        return 0 if preflight_report["status"] == "passed" else 1
    if preflight_report["status"] == "blocked":
        report = write_unified_run_outputs(
            request.output_dir,
            request=request,
            result_payload={
                "status": "blocked",
                "validation_errors": [str(item.get("message", "")) for item in preflight_report.get("blockers", [])],
                "unified_preflight": preflight_report,
            },
        )
        summary = unified_run_summary(report)
        summary["preflight_status"] = preflight_report["status"]
        summary["validation_errors"] = report["validation_errors"]
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 1
    validation_errors = request.validate_paths()
    if validation_errors:
        report = write_unified_run_outputs(
            request.output_dir,
            request=request,
            result_payload={"status": "blocked", "validation_errors": validation_errors, "unified_preflight": preflight_report},
        )
        summary = unified_run_summary(report)
        summary["validation_errors"] = validation_errors
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 1

    if request.route == "feedback_reopen":
        report = write_unified_run_outputs(
            request.output_dir,
            request=request,
            result_payload={
                "status": "blocked",
                "validation_errors": [
                    "CLI feedback reopen requires the API service because it needs an existing stored project/run."
                ],
                "unified_preflight": preflight_report,
            },
        )
        summary = unified_run_summary(report)
        summary["validation_errors"] = report["validation_errors"]
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 1

    if request.route == "one_line_fallback":
        result = AutoDevPipeline().run(request.objective, Path(request.output_dir))
        related_report = str(Path(request.output_dir) / "autodev_report.json")
        result_payload = result.to_dict()
    else:
        result = DocumentRunPipeline().run(**request.to_document_run_kwargs())
        related_report = str(Path(request.output_dir) / "document_run_report.json")
        result_payload = result.to_dict()
        write_document_run_report(Path(request.output_dir), result_payload)

    report = write_unified_run_outputs(
        request.output_dir,
        request=request,
        result_payload={**result_payload, "unified_preflight": preflight_report},
        related_report=related_report,
    )
    print(json.dumps(unified_run_summary(report), indent=2, sort_keys=True))
    return 0 if report["status"] == "done" else 1


def write_document_run_report(output_dir: Path, payload: dict[str, object]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "document_run_report.json"
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report_path


if __name__ == "__main__":
    raise SystemExit(main())
