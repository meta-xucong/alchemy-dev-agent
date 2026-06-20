"""Export reviewable evidence packages from Alchemy run/probe reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from intake.models import utc_now_iso


KNOWN_REPORT_NAMES = {
    "unified_run_report.json",
    "document_run_report.json",
    "delivery_report.json",
    "development_cycle.json",
    "real_unified_delivery_report.json",
    "real_probe_index.json",
    "github_pr_lifecycle_report.json",
    "real_delivery_validation_report.json",
    "real_readiness_report.json",
    "real_worker_smoke_report.json",
    "real_document_run_smoke_report.json",
    "benchmark_suite_report.json",
}


@dataclass(slots=True)
class EvidencePackageReport:
    status: str
    output_dir: str
    source_roots: list[str] = field(default_factory=list)
    files: list[dict[str, object]] = field(default_factory=list)
    summary: dict[str, object] = field(default_factory=dict)
    blockers: list[dict[str, object]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "2.49",
            "status": self.status,
            "output_dir": self.output_dir,
            "source_roots": list(self.source_roots),
            "files": list(self.files),
            "summary": dict(self.summary),
            "blockers": list(self.blockers),
            "created_at": self.created_at,
        }


class EvidencePackageExporter:
    """Copy known JSON reports into a compact review package."""

    def export(
        self,
        *,
        roots: Sequence[str | Path],
        output_dir: str | Path = ".alchemy/evidence_package",
        include_unknown_json: bool = False,
        clean_output: bool = True,
    ) -> EvidencePackageReport:
        output = Path(output_dir)
        if output.exists() and clean_output:
            shutil.rmtree(output)
        reports_dir = output / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        source_roots = [Path(root) for root in roots]
        blockers: list[dict[str, object]] = []
        files: list[dict[str, object]] = []
        for root in source_roots:
            if not root.exists():
                blockers.append(blocker("B-EVIDENCE-PACKAGE-MISSING-ROOT", f"Evidence root does not exist: {root}"))
                continue
            for path in sorted(root.rglob("*.json")):
                if not include_unknown_json and path.name not in KNOWN_REPORT_NAMES:
                    continue
                payload = read_json(path)
                if payload is None:
                    blockers.append(blocker("B-EVIDENCE-PACKAGE-INVALID-JSON", f"Invalid JSON report: {path}"))
                    continue
                relative = safe_relative_name(path, root)
                target = reports_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                files.append(file_entry(source=path, target=target, payload=payload))

        summary = build_summary(files)
        status = "passed" if files and not blockers else "blocked"
        report = EvidencePackageReport(
            status=status,
            output_dir=str(output),
            source_roots=[str(root) for root in source_roots],
            files=files,
            summary=summary,
            blockers=blockers,
        )
        payload = report.to_dict()
        (output / "evidence_package_manifest.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (output / "summary.md").write_text(summary_markdown(payload), encoding="utf-8")
        return report


def file_entry(*, source: Path, target: Path, payload: Mapping[str, Any]) -> dict[str, object]:
    data = target.read_bytes()
    return {
        "source_path": str(source),
        "package_path": str(target),
        "name": source.name,
        "status": str(payload.get("status", "")),
        "schema_version": str(payload.get("schema_version", "")),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "summary": compact_report_summary(payload),
    }


def compact_report_summary(payload: Mapping[str, Any]) -> dict[str, object]:
    summary = payload.get("summary", {})
    summary = summary if isinstance(summary, Mapping) else {}
    request = payload.get("request", {})
    request = request if isinstance(request, Mapping) else {}
    pr = payload.get("pull_request", {})
    pr = pr if isinstance(pr, Mapping) else {}
    github = payload.get("github", {})
    github = github if isinstance(github, Mapping) else {}
    delivery = payload.get("delivery", {})
    delivery = delivery if isinstance(delivery, Mapping) else {}
    return {
        "route": request.get("route", payload.get("route", "")),
        "execution_mode": request.get("execution_mode", payload.get("execution_mode", "")),
        "delivery_mode": request.get("delivery_mode", payload.get("delivery_mode", "")),
        "ready_for_review": payload.get("ready_for_review", delivery.get("ready_for_review", "")),
        "failed_required_gates": list(summary.get("failed_required_gates", []))
        if isinstance(summary.get("failed_required_gates", []), list)
        else [],
        "blocker_count": len(payload.get("blockers", [])) if isinstance(payload.get("blockers"), list) else 0,
        "pr_url": pr.get("url", github.get("pull_request_url", "")),
        "ci_status": github.get("ci_status", ""),
    }


def build_summary(files: Sequence[Mapping[str, Any]]) -> dict[str, object]:
    statuses: dict[str, int] = {}
    blockers = 0
    failed_gates: list[str] = []
    for item in files:
        status = str(item.get("status", "") or "unknown")
        statuses[status] = statuses.get(status, 0) + 1
        summary = item.get("summary", {})
        if isinstance(summary, Mapping):
            blockers += int(summary.get("blocker_count", 0) or 0)
            for gate in summary.get("failed_required_gates", []):
                failed_gates.append(str(gate))
    return {
        "file_count": len(files),
        "statuses": statuses,
        "blocker_count": blockers,
        "failed_required_gates": sorted(set(failed_gates)),
    }


def summary_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary", {})
    summary = summary if isinstance(summary, Mapping) else {}
    lines = [
        "# Alchemy Evidence Package",
        "",
        f"- Status: {payload.get('status', '')}",
        f"- Files: {summary.get('file_count', 0)}",
        f"- Blockers: {summary.get('blocker_count', 0)}",
        f"- Failed required gates: {', '.join(summary.get('failed_required_gates', []) or []) or 'none'}",
        "",
        "## Files",
        "",
    ]
    for item in payload.get("files", []):
        if not isinstance(item, Mapping):
            continue
        lines.append(f"- `{item.get('name', '')}`: status `{item.get('status', '')}`, sha256 `{item.get('sha256', '')}`")
    lines.append("")
    return "\n".join(lines)


def safe_relative_name(path: Path, root: Path) -> Path:
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = Path(path.name)
    parts = [part for part in relative.parts if part not in {"", ".", ".."}]
    return Path(*parts) if parts else Path(path.name)


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return dict(payload) if isinstance(payload, Mapping) else None


def blocker(blocker_id: str, description: str) -> dict[str, object]:
    return {
        "id": blocker_id,
        "type": "evidence_package",
        "description": description,
        "required_resolution": "Provide valid evidence roots and rerun the package export.",
        "can_continue_partially": False,
    }


def package_summary(report: Mapping[str, Any]) -> dict[str, object]:
    return {
        "status": report.get("status", ""),
        "output_dir": report.get("output_dir", ""),
        "summary": report.get("summary", {}),
        "manifest": str(Path(str(report.get("output_dir", ""))) / "evidence_package_manifest.json"),
        "summary_markdown": str(Path(str(report.get("output_dir", ""))) / "summary.md"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export an Alchemy evidence package from known JSON reports.")
    parser.add_argument("--root", action="append", dest="roots", default=[])
    parser.add_argument("--output", default=".alchemy/evidence_package")
    parser.add_argument("--include-unknown-json", action="store_true")
    parser.add_argument("--keep-output", action="store_true")
    parser.add_argument("--summary", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    roots = args.roots or [".alchemy"]
    report = EvidencePackageExporter().export(
        roots=roots,
        output_dir=args.output,
        include_unknown_json=args.include_unknown_json,
        clean_output=not args.keep_output,
    )
    payload = report.to_dict()
    print(json.dumps(package_summary(payload) if args.summary else payload, indent=2, sort_keys=True))
    return 0 if report.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
