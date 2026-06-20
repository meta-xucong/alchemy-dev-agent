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
}


@dataclass(slots=True)
class RealProbeIndex:
    status: str
    entries: list[dict[str, object]] = field(default_factory=list)
    roots: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    output_path: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "2.45",
            "status": self.status,
            "entries": list(self.entries),
            "roots": list(self.roots),
            "created_at": self.created_at,
            "output_path": self.output_path,
            "summary": {
                "total": len(self.entries),
                "passed": sum(1 for entry in self.entries if entry.get("status") in {"ready", "passed"}),
                "blocked_or_failed": sum(1 for entry in self.entries if entry.get("status") in {"blocked", "failed"}),
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
        status = "passed" if entries and all(entry.get("status") in {"ready", "passed"} for entry in entries) else "blocked"
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


def as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


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
