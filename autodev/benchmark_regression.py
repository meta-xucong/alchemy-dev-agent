"""Compare benchmark suite reports and block regressions."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from intake.models import utc_now_iso


@dataclass(slots=True)
class BenchmarkRegressionReport:
    status: str
    baseline_path: str
    current_path: str
    output_dir: str
    scenario_changes: list[dict[str, object]] = field(default_factory=list)
    summary: dict[str, object] = field(default_factory=dict)
    blockers: list[dict[str, object]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "2.52",
            "status": self.status,
            "baseline_path": self.baseline_path,
            "current_path": self.current_path,
            "output_dir": self.output_dir,
            "scenario_changes": list(self.scenario_changes),
            "summary": dict(self.summary),
            "blockers": list(self.blockers),
            "created_at": self.created_at,
        }


class BenchmarkRegressionGate:
    """Compare two benchmark reports without rerunning benchmark scenarios."""

    def compare(
        self,
        *,
        baseline: str | Path,
        current: str | Path,
        output_dir: str | Path = ".alchemy/benchmark_regression",
    ) -> BenchmarkRegressionReport:
        baseline_path = Path(baseline)
        current_path = Path(current)
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)

        blockers: list[dict[str, object]] = []
        baseline_report = read_json_report(baseline_path)
        current_report = read_json_report(current_path)
        if baseline_report is None:
            blockers.append(blocker("B-BENCHMARK-BASELINE-MISSING", f"Baseline benchmark report is missing or invalid: {baseline_path}"))
            baseline_report = {}
        if current_report is None:
            blockers.append(blocker("B-BENCHMARK-CURRENT-MISSING", f"Current benchmark report is missing or invalid: {current_path}"))
            current_report = {}

        baseline_scenarios = scenario_map(baseline_report)
        current_scenarios = scenario_map(current_report)
        scenario_changes = compare_scenarios(baseline_scenarios, current_scenarios)
        summary = build_summary(baseline_report, current_report, scenario_changes)
        blockers.extend(regression_blockers(current_report, summary))
        status = "passed" if not blockers else "blocked"

        report = BenchmarkRegressionReport(
            status=status,
            baseline_path=str(baseline_path),
            current_path=str(current_path),
            output_dir=str(output),
            scenario_changes=scenario_changes,
            summary=summary,
            blockers=blockers,
        )
        payload = report.to_dict()
        (output / "benchmark_regression_report.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return report


def compare_scenarios(
    baseline: Mapping[str, Mapping[str, Any]],
    current: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, object]]:
    changes: list[dict[str, object]] = []
    for name in sorted(set(baseline) | set(current)):
        before = baseline.get(name)
        after = current.get(name)
        before_status = str(before.get("status", "")) if before else ""
        after_status = str(after.get("status", "")) if after else ""
        if before is None:
            direction = "added"
        elif after is None:
            direction = "missing"
        elif before_status == after_status:
            direction = "unchanged"
        elif before_status == "passed" and after_status != "passed":
            direction = "regressed"
        elif before_status != "passed" and after_status == "passed":
            direction = "resolved"
        else:
            direction = "changed"
        changes.append(
            {
                "name": name,
                "baseline_status": before_status,
                "current_status": after_status,
                "direction": direction,
            }
        )
    return changes


def build_summary(
    baseline_report: Mapping[str, Any],
    current_report: Mapping[str, Any],
    scenario_changes: Sequence[Mapping[str, Any]],
) -> dict[str, object]:
    baseline_summary = as_mapping(baseline_report.get("summary", {}))
    current_summary = as_mapping(current_report.get("summary", {}))
    return {
        "baseline_status": str(baseline_report.get("status", "")),
        "current_status": str(current_report.get("status", "")),
        "baseline_total": int_or_zero(baseline_summary.get("total")),
        "current_total": int_or_zero(current_summary.get("total")),
        "baseline_failed": int_or_zero(baseline_summary.get("failed")),
        "current_failed": int_or_zero(current_summary.get("failed")),
        "resolved_failures": names_with_direction(scenario_changes, "resolved"),
        "new_failures": names_with_direction(scenario_changes, "regressed"),
        "missing_baseline_passes": [
            str(item.get("name", ""))
            for item in scenario_changes
            if item.get("direction") == "missing" and item.get("baseline_status") == "passed"
        ],
        "added_scenarios": names_with_direction(scenario_changes, "added"),
    }


def regression_blockers(current_report: Mapping[str, Any], summary: Mapping[str, Any]) -> list[dict[str, object]]:
    blockers: list[dict[str, object]] = []
    if str(current_report.get("status", "")) != "passed":
        blockers.append(blocker("B-BENCHMARK-CURRENT-FAILED", "Current benchmark suite status is not passed."))
    for name in string_list(summary.get("new_failures")):
        blockers.append(blocker("B-BENCHMARK-SCENARIO-REGRESSED", f"Benchmark scenario regressed: {name}", scenario=name))
    for name in string_list(summary.get("missing_baseline_passes")):
        blockers.append(blocker("B-BENCHMARK-SCENARIO-MISSING", f"Baseline-passed benchmark scenario is missing: {name}", scenario=name))
    if int_or_zero(summary.get("current_failed")) > int_or_zero(summary.get("baseline_failed")):
        blockers.append(blocker("B-BENCHMARK-FAILED-COUNT-INCREASED", "Current benchmark has more failed scenarios than baseline."))
    return blockers


def scenario_map(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    scenarios: dict[str, Mapping[str, Any]] = {}
    for item in report.get("scenarios", []):
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name", "") or "")
        if name:
            scenarios[name] = item
    return scenarios


def read_json_report(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return dict(payload) if isinstance(payload, Mapping) else None


def blocker(blocker_id: str, description: str, *, scenario: str = "") -> dict[str, object]:
    payload: dict[str, object] = {
        "id": blocker_id,
        "type": "benchmark_regression",
        "description": description,
        "required_resolution": "Fix the regression, rerun the benchmark suite, and compare again.",
        "can_continue_partially": False,
    }
    if scenario:
        payload["scenario"] = scenario
    return payload


def as_mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def int_or_zero(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def string_list(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def names_with_direction(items: Sequence[Mapping[str, Any]], direction: str) -> list[str]:
    return [str(item.get("name", "")) for item in items if item.get("direction") == direction]


def regression_summary(report: Mapping[str, Any]) -> dict[str, object]:
    return {
        "status": report.get("status", ""),
        "baseline_path": report.get("baseline_path", ""),
        "current_path": report.get("current_path", ""),
        "output_dir": report.get("output_dir", ""),
        "summary": report.get("summary", {}),
        "blocker_count": len(report.get("blockers", [])) if isinstance(report.get("blockers"), list) else 0,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare benchmark reports and block regressions.")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--current", required=True)
    parser.add_argument("--output", default=".alchemy/benchmark_regression")
    parser.add_argument("--summary", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = BenchmarkRegressionGate().compare(
        baseline=args.baseline,
        current=args.current,
        output_dir=args.output,
    )
    payload = report.to_dict()
    print(json.dumps(regression_summary(payload) if args.summary else payload, indent=2, sort_keys=True))
    return 0 if report.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
