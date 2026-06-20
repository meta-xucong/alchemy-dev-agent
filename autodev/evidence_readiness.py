"""Aggregate evidence reports into a final readiness decision."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from intake.models import utc_now_iso


@dataclass(slots=True)
class EvidenceReadinessReport:
    status: str
    output_dir: str
    inputs: dict[str, object] = field(default_factory=dict)
    checks: list[dict[str, object]] = field(default_factory=list)
    blockers: list[dict[str, object]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "2.54",
            "status": self.status,
            "output_dir": self.output_dir,
            "inputs": dict(self.inputs),
            "checks": list(self.checks),
            "blockers": list(self.blockers),
            "summary": {
                "check_count": len(self.checks),
                "passed_checks": sum(1 for item in self.checks if item.get("status") == "passed"),
                "failed_checks": [item.get("name", "") for item in self.checks if item.get("status") != "passed"],
                "blocker_count": len(self.blockers),
            },
            "created_at": self.created_at,
        }


class EvidenceReadinessGate:
    """Evaluate existing evidence reports without rerunning delivery work."""

    def evaluate(
        self,
        *,
        evidence_index: str | Path,
        evidence_package: str | Path,
        benchmark_regression: str | Path | None = None,
        output_dir: str | Path = ".alchemy/evidence_readiness",
    ) -> EvidenceReadinessReport:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        inputs = {
            "evidence_index": str(evidence_index),
            "evidence_package": str(evidence_package),
            "benchmark_regression": str(benchmark_regression or ""),
        }
        checks: list[dict[str, object]] = []
        blockers: list[dict[str, object]] = []

        index_payload = read_json_report(Path(evidence_index))
        package_payload = read_json_report(Path(evidence_package))
        regression_payload = read_json_report(Path(benchmark_regression)) if benchmark_regression else None

        checks.extend(evidence_index_checks(index_payload))
        checks.extend(evidence_package_checks(package_payload))
        if benchmark_regression:
            checks.extend(benchmark_regression_checks(regression_payload))

        for check in checks:
            if check.get("status") != "passed":
                blockers.append(
                    blocker(
                        "B-EVIDENCE-READINESS-CHECK",
                        str(check.get("message", "Evidence readiness check failed.")),
                        check=str(check.get("name", "")),
                    )
                )
        blockers.extend(input_blockers("evidence_index", index_payload))
        blockers.extend(input_blockers("evidence_package", package_payload))
        if benchmark_regression:
            blockers.extend(input_blockers("benchmark_regression", regression_payload))

        status = "ready" if not blockers and checks else "blocked"
        report = EvidenceReadinessReport(
            status=status,
            output_dir=str(output),
            inputs=inputs,
            checks=checks,
            blockers=dedupe_blockers(blockers),
        )
        payload = report.to_dict()
        (output / "evidence_readiness_report.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return report


def evidence_index_checks(payload: Mapping[str, Any] | None) -> list[dict[str, object]]:
    if payload is None:
        return [check("evidence_index_valid", False, "Evidence index is missing or invalid.")]
    summary = as_mapping(payload.get("summary", {}))
    total = int_or_zero(summary.get("total"))
    return [
        check("evidence_index_status", payload.get("status") == "passed", "Evidence index status must be passed."),
        check("evidence_index_entries", total > 0, "Evidence index must contain at least one entry."),
        check(
            "evidence_index_no_blocked_or_failed",
            int_or_zero(summary.get("blocked_or_failed")) == 0,
            "Evidence index contains blocked or failed entries.",
        ),
    ]


def evidence_package_checks(payload: Mapping[str, Any] | None) -> list[dict[str, object]]:
    if payload is None:
        return [check("evidence_package_valid", False, "Evidence package manifest is missing or invalid.")]
    summary = as_mapping(payload.get("summary", {}))
    return [
        check("evidence_package_status", payload.get("status") == "passed", "Evidence package status must be passed."),
        check("evidence_package_files", int_or_zero(summary.get("file_count")) > 0, "Evidence package must contain files."),
        check(
            "evidence_package_no_blockers",
            int_or_zero(summary.get("blocker_count")) == 0 and not payload.get("blockers", []),
            "Evidence package contains blockers.",
        ),
    ]


def benchmark_regression_checks(payload: Mapping[str, Any] | None) -> list[dict[str, object]]:
    if payload is None:
        return [check("benchmark_regression_valid", False, "Benchmark regression report is missing or invalid.")]
    return [
        check(
            "benchmark_regression_status",
            payload.get("status") == "passed",
            "Benchmark regression status must be passed.",
        ),
        check(
            "benchmark_regression_no_blockers",
            not payload.get("blockers", []),
            "Benchmark regression report contains blockers.",
        ),
    ]


def input_blockers(name: str, payload: Mapping[str, Any] | None) -> list[dict[str, object]]:
    if payload is None:
        return [blocker("B-EVIDENCE-READINESS-MISSING-INPUT", f"{name} report is missing or invalid.", check=name)]
    return [
        blocker("B-EVIDENCE-READINESS-INPUT-BLOCKER", f"{name} contains blocker: {item}", check=name)
        for item in payload.get("blockers", [])
        if item
    ]


def check(name: str, passed: bool, message: str) -> dict[str, object]:
    return {"name": name, "status": "passed" if passed else "failed", "message": message}


def blocker(blocker_id: str, description: str, *, check: str) -> dict[str, object]:
    return {
        "id": blocker_id,
        "type": "evidence_readiness",
        "check": check,
        "description": description,
        "required_resolution": "Fix or regenerate the referenced evidence and rerun the readiness gate.",
        "can_continue_partially": False,
    }


def dedupe_blockers(items: Sequence[Mapping[str, Any]]) -> list[dict[str, object]]:
    seen: set[tuple[str, str, str]] = set()
    result: list[dict[str, object]] = []
    for item in items:
        key = (str(item.get("id", "")), str(item.get("check", "")), str(item.get("description", "")))
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(item))
    return result


def read_json_report(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return dict(payload) if isinstance(payload, Mapping) else None


def as_mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def int_or_zero(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def readiness_summary(report: Mapping[str, Any]) -> dict[str, object]:
    return {
        "status": report.get("status", ""),
        "output_dir": report.get("output_dir", ""),
        "summary": report.get("summary", {}),
        "inputs": report.get("inputs", {}),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate final evidence readiness.")
    parser.add_argument("--evidence-index", required=True)
    parser.add_argument("--evidence-package", required=True)
    parser.add_argument("--benchmark-regression", default="")
    parser.add_argument("--output", default=".alchemy/evidence_readiness")
    parser.add_argument("--summary", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = EvidenceReadinessGate().evaluate(
        evidence_index=args.evidence_index,
        evidence_package=args.evidence_package,
        benchmark_regression=args.benchmark_regression or None,
        output_dir=args.output,
    )
    payload = report.to_dict()
    print(json.dumps(readiness_summary(payload) if args.summary else payload, indent=2, sort_keys=True))
    return 0 if report.status == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
