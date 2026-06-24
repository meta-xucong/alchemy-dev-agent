"""Index real readiness and worker smoke evidence reports."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from intake.models import utc_now_iso


KNOWN_REPORTS = {
    "real_readiness_report.json": "real_readiness",
    "real_worker_smoke_report.json": "real_worker_smoke",
    "real_document_run_smoke_report.json": "real_document_run_smoke",
    "real_delivery_validation_report.json": "real_github_pr_probe",
    "real_unified_delivery_report.json": "real_unified_delivery",
    "github_pr_lifecycle_report.json": "github_pr_lifecycle",
    "evidence_package_manifest.json": "evidence_package",
    "benchmark_suite_report.json": "benchmark_suite",
    "benchmark_regression_report.json": "benchmark_regression",
    "evidence_readiness_report.json": "evidence_readiness",
    "real_worker_probe_report.json": "real_worker_probe",
}

DIAGNOSTIC_REPORT_TYPES = {"real_worker_probe"}


@dataclass(slots=True)
class RealProbeIndex:
    status: str
    entries: list[dict[str, object]] = field(default_factory=list)
    roots: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    output_path: str = ""

    def to_dict(self) -> dict[str, object]:
        blocking_entries = [entry for entry in self.entries if not entry_is_diagnostic(entry)]
        return {
            "schema_version": "2.47",
            "status": self.status,
            "entries": list(self.entries),
            "roots": list(self.roots),
            "created_at": self.created_at,
            "output_path": self.output_path,
            "summary": {
                "total": len(self.entries),
                "passed": sum(1 for entry in self.entries if entry.get("status") in {"ready", "passed"}),
                "diagnostic": sum(1 for entry in self.entries if entry_is_diagnostic(entry)),
                "blocking_total": len(blocking_entries),
                "blocked_or_failed": sum(
                    1 for entry in blocking_entries if entry.get("status") in {"blocked", "failed"}
                ),
            },
        }


class RealProbeIndexer:
    """Build a compact evidence index from known probe report files."""

    def build(self, *, roots: Sequence[str | Path], output_path: str | Path = ".alchemy/real_probe_index.json") -> RealProbeIndex:
        root_paths = [Path(root) for root in roots]
        entries: list[dict[str, object]] = []
        for root in root_paths:
            if not root.exists():
                continue
            for report_path in sorted(root.rglob("*.json")):
                report_type = KNOWN_REPORTS.get(report_path.name)
                if not report_type:
                    continue
                entry = self._entry(report_path, report_type)
                if entry:
                    entries.append(entry)
        entries = dedupe_entries(entries)
        blocking_entries = [entry for entry in entries if not entry_is_diagnostic(entry)]
        status = (
            "passed"
            if entries and all(entry.get("status") in {"ready", "passed"} for entry in blocking_entries)
            else "blocked"
        )
        index = RealProbeIndex(
            status=status,
            entries=entries,
            roots=[str(root) for root in root_paths],
            output_path=str(output_path),
        )
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(index.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return index

    def _entry(self, path: Path, report_type: str) -> dict[str, object] | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        status = str(payload.get("status", "unknown") or "unknown")
        entry: dict[str, object] = {
            "type": report_type,
            "status": status,
            "path": str(path),
            "schema_version": str(payload.get("schema_version", "")),
            "blocker_count": len(payload.get("blockers", [])) if isinstance(payload.get("blockers"), list) else 0,
        }
        if report_type == "real_readiness":
            entry.update(readiness_fields(payload))
        elif report_type == "real_worker_smoke":
            entry.update(worker_smoke_fields(payload))
        elif report_type == "real_document_run_smoke":
            entry.update(document_run_fields(payload))
        elif report_type == "real_github_pr_probe":
            entry.update(real_github_pr_fields(payload))
        elif report_type == "real_unified_delivery":
            entry.update(real_unified_delivery_fields(payload))
        elif report_type == "github_pr_lifecycle":
            entry.update(github_pr_lifecycle_fields(payload))
        elif report_type == "evidence_package":
            entry.update(evidence_package_fields(payload))
        elif report_type == "benchmark_suite":
            entry.update(benchmark_suite_fields(payload))
        elif report_type == "benchmark_regression":
            entry.update(benchmark_regression_fields(payload))
        elif report_type == "evidence_readiness":
            entry.update(evidence_readiness_fields(payload))
        elif report_type == "real_worker_probe":
            entry.update(real_worker_probe_fields(payload))
            entry["diagnostic"] = True
        return entry


def readiness_fields(payload: dict[str, Any]) -> dict[str, object]:
    return {
        "environment_status": as_dict(payload.get("environment")).get("status", ""),
        "request_preflights": [
            {
                "name": item.get("name", ""),
                "status": item.get("status", ""),
                "blocker_count": len(item.get("blockers", [])) if isinstance(item.get("blockers"), list) else 0,
            }
            for item in payload.get("request_preflights", [])
            if isinstance(item, dict)
        ],
    }


def worker_smoke_fields(payload: dict[str, Any]) -> dict[str, object]:
    worker = as_dict(payload.get("worker_result"))
    files_changed = worker.get("files_changed", [])
    return {
        "preflight_status": as_dict(payload.get("preflight")).get("status", ""),
        "worker_status": worker.get("status", ""),
        "verification_status": as_dict(payload.get("verification")).get("status", ""),
        "files_changed": list(files_changed) if isinstance(files_changed, list) else [],
    }


def document_run_fields(payload: dict[str, Any]) -> dict[str, object]:
    document_run = as_dict(payload.get("document_run"))
    return {
        "preflight_status": as_dict(payload.get("preflight")).get("status", ""),
        "document_run_status": document_run.get("status", ""),
        "worker_lifecycle_count": document_run.get("worker_lifecycle_count", 0),
        "verification_status": as_dict(payload.get("verification")).get("status", ""),
        "delivery_ready_for_review": document_run.get("delivery_ready_for_review", False),
    }


def real_github_pr_fields(payload: dict[str, Any]) -> dict[str, object]:
    github = as_dict(payload.get("github"))
    workspace = as_dict(payload.get("workspace"))
    merge = as_dict(github.get("merge"))
    return {
        "github_status": github.get("status", ""),
        "branch": payload.get("branch", github.get("branch", "")),
        "base_branch": payload.get("base_branch", ""),
        "commit": github.get("commit", ""),
        "pull_request_url": github.get("pull_request_url", ""),
        "ci_status": github.get("ci_status", ""),
        "merge_status": merge.get("status", ""),
        "workspace_status": workspace.get("status", ""),
    }


def real_unified_delivery_fields(payload: dict[str, Any]) -> dict[str, object]:
    request = as_dict(payload.get("request"))
    summary = as_dict(payload.get("summary"))
    gates = [
        {
            "name": item.get("name", ""),
            "status": item.get("status", ""),
            "required": item.get("required", False),
        }
        for item in payload.get("gates", [])
        if isinstance(item, dict)
    ]
    return {
        "route": request.get("route", ""),
        "execution_mode": request.get("execution_mode", ""),
        "delivery_mode": request.get("delivery_mode", ""),
        "required_gates": summary.get("required_gates", 0),
        "passed_required_gates": summary.get("passed_required_gates", 0),
        "failed_required_gates": list(summary.get("failed_required_gates", []))
        if isinstance(summary.get("failed_required_gates", []), list)
        else [],
        "gates": gates,
    }


def github_pr_lifecycle_fields(payload: dict[str, Any]) -> dict[str, object]:
    pull_request = as_dict(payload.get("pull_request"))
    return {
        "action": payload.get("action", ""),
        "selector": payload.get("selector", ""),
        "number": pull_request.get("number", ""),
        "url": pull_request.get("url", ""),
        "state": pull_request.get("state", ""),
        "is_draft": pull_request.get("isDraft", ""),
        "head": pull_request.get("headRefName", ""),
        "base": pull_request.get("baseRefName", ""),
        "check_count": len(payload.get("checks", [])) if isinstance(payload.get("checks"), list) else 0,
        "warning_count": len(payload.get("warnings", [])) if isinstance(payload.get("warnings"), list) else 0,
    }


def evidence_package_fields(payload: dict[str, Any]) -> dict[str, object]:
    summary = as_dict(payload.get("summary"))
    return {
        "output_dir": payload.get("output_dir", ""),
        "source_roots": list(payload.get("source_roots", [])) if isinstance(payload.get("source_roots", []), list) else [],
        "file_count": summary.get("file_count", 0),
        "package_blocker_count": summary.get("blocker_count", 0),
        "failed_required_gates": list(summary.get("failed_required_gates", []))
        if isinstance(summary.get("failed_required_gates", []), list)
        else [],
    }


def benchmark_suite_fields(payload: dict[str, Any]) -> dict[str, object]:
    summary = as_dict(payload.get("summary"))
    return {
        "output_dir": payload.get("output_dir", ""),
        "scenario_total": summary.get("total", 0),
        "scenario_passed": summary.get("passed", 0),
        "scenario_failed": summary.get("failed", 0),
        "failed_scenarios": list(summary.get("failed_scenarios", []))
        if isinstance(summary.get("failed_scenarios", []), list)
        else [],
    }


def benchmark_regression_fields(payload: dict[str, Any]) -> dict[str, object]:
    summary = as_dict(payload.get("summary"))
    return {
        "output_dir": payload.get("output_dir", ""),
        "baseline_path": payload.get("baseline_path", ""),
        "current_path": payload.get("current_path", ""),
        "baseline_total": summary.get("baseline_total", 0),
        "current_total": summary.get("current_total", 0),
        "new_failures": list(summary.get("new_failures", []))
        if isinstance(summary.get("new_failures", []), list)
        else [],
        "missing_baseline_passes": list(summary.get("missing_baseline_passes", []))
        if isinstance(summary.get("missing_baseline_passes", []), list)
        else [],
    }


def evidence_readiness_fields(payload: dict[str, Any]) -> dict[str, object]:
    summary = as_dict(payload.get("summary"))
    inputs = as_dict(payload.get("inputs"))
    return {
        "output_dir": payload.get("output_dir", ""),
        "evidence_index": inputs.get("evidence_index", ""),
        "evidence_package": inputs.get("evidence_package", ""),
        "benchmark_regression": inputs.get("benchmark_regression", ""),
        "check_count": summary.get("check_count", 0),
        "passed_checks": summary.get("passed_checks", 0),
        "failed_checks": list(summary.get("failed_checks", []))
        if isinstance(summary.get("failed_checks", []), list)
        else [],
    }


def real_worker_probe_fields(payload: dict[str, Any]) -> dict[str, object]:
    worker = as_dict(payload.get("worker_result"))
    runtime_state = as_dict(payload.get("runtime_state"))
    repository = as_dict(runtime_state.get("repository"))
    convergence = as_dict(repository.get("repair_convergence"))
    job = as_dict(payload.get("job"))
    return {
        "probe_name": payload.get("probe_name", ""),
        "purpose": payload.get("purpose", ""),
        "job_status": job.get("status", ""),
        "worker_status": worker.get("status", ""),
        "tests_passed": list(worker.get("tests_passed", [])) if isinstance(worker.get("tests_passed", []), list) else [],
        "files_changed": list(worker.get("files_changed", [])) if isinstance(worker.get("files_changed", []), list) else [],
        "repair_convergence_status": convergence.get("status", ""),
        "repair_target_files": list(convergence.get("target_files", []))
        if isinstance(convergence.get("target_files", []), list)
        else [],
    }


def as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def entry_is_diagnostic(entry: dict[str, object]) -> bool:
    return bool(entry.get("diagnostic")) or str(entry.get("type", "")) in DIAGNOSTIC_REPORT_TYPES


def dedupe_entries(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped: dict[tuple[str, str], dict[str, object]] = {}
    for entry in entries:
        deduped[(str(entry.get("type", "")), str(entry.get("path", "")))] = entry
    return list(deduped.values())


def index_summary(payload: dict[str, object]) -> dict[str, object]:
    return {
        "status": payload.get("status", ""),
        "output_path": payload.get("output_path", ""),
        "summary": payload.get("summary", {}),
        "entries": [
            {
                "type": entry.get("type", ""),
                "status": entry.get("status", ""),
                "path": entry.get("path", ""),
                "blocker_count": entry.get("blocker_count", 0),
                "diagnostic": bool(entry.get("diagnostic", False)),
            }
            for entry in payload.get("entries", [])
            if isinstance(entry, dict)
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Index real probe evidence reports.")
    parser.add_argument("--root", action="append", dest="roots", default=[])
    parser.add_argument("--output", default=".alchemy/real_probe_index.json")
    parser.add_argument("--summary", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    roots = args.roots or [".alchemy"]
    index = RealProbeIndexer().build(roots=roots, output_path=args.output)
    payload = index.to_dict()
    print(json.dumps(index_summary(payload) if args.summary else payload, indent=2, sort_keys=True))
    return 0 if index.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
