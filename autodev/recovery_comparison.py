"""Compare feedback or recovery runs against their source run."""

from __future__ import annotations

from typing import Any

from .repair_suggestions import build_repair_suggestions


PROBE_KEYS = ("static", "browser", "semantic", "scenario", "gameplay", "native_ui_tests", "ci")
STATUS_RANK = {
    "": 0,
    "unknown": 0,
    "missing": 0,
    "failed": 0,
    "blocked": 0,
    "error": 0,
    "skipped": 1,
    "waived": 1,
    "partial": 2,
    "in_progress": 2,
    "running": 2,
    "queued": 2,
    "generated": 3,
    "completed": 3,
    "passed": 3,
    "success": 3,
    "ready": 3,
    "done": 3,
    "merged": 3,
}


def build_recovery_comparison(
    *,
    source_run: dict[str, Any],
    current_run: dict[str, Any],
) -> dict[str, object]:
    """Build a machine-readable before/after report for repair iterations."""

    source = summarize_run(source_run)
    current = summarize_run(current_run)
    score_delta = _delta(current["final_gate_score"], source["final_gate_score"])
    coverage_delta = _delta(current["coverage_score"], source["coverage_score"])

    source_missing = set(source["missing_must_requirement_ids"])
    current_missing = set(current["missing_must_requirement_ids"])
    source_partial = set(source["partial_must_requirement_ids"])
    current_partial = set(current["partial_must_requirement_ids"])

    resolved_missing = sorted(source_missing - current_missing)
    new_missing = sorted(current_missing - source_missing)
    resolved_partial = sorted(source_partial - current_partial)
    new_partial = sorted(current_partial - source_partial)
    source_must = set(source["must_requirement_ids"])
    current_must = set(current["must_requirement_ids"])
    current_covered_must = set(current["covered_must_requirement_ids"])
    new_must = sorted(current_must - source_must)
    covered_new_must = sorted(current_covered_must.intersection(new_must))
    uncovered_new_must = sorted(set(new_must) - current_covered_must)
    blocker_delta = len(current["blockers"]) - len(source["blockers"])
    probe_changes = compare_probe_statuses(
        _dict(source["probes"]),
        _dict(current["probes"]),
    )
    status = classify_comparison(
        source=source,
        current=current,
        score_delta=score_delta,
        coverage_delta=coverage_delta,
        resolved_missing=resolved_missing,
        new_missing=new_missing,
        resolved_partial=resolved_partial,
        new_partial=new_partial,
        covered_new_must=covered_new_must,
        uncovered_new_must=uncovered_new_must,
        blocker_delta=blocker_delta,
        probe_changes=probe_changes,
    )

    comparison = {
        "status": status,
        "summary": summary_for(status),
        "source_run_id": str(source.get("run_id", "")),
        "current_run_id": str(current.get("run_id", "")),
        "source": source,
        "current": current,
        "score_delta": score_delta,
        "coverage_delta": coverage_delta,
        "blocker_delta": blocker_delta,
        "resolved_missing_must_requirement_ids": resolved_missing,
        "new_missing_must_requirement_ids": new_missing,
        "resolved_partial_must_requirement_ids": resolved_partial,
        "new_partial_must_requirement_ids": new_partial,
        "new_must_requirement_ids": new_must,
        "covered_new_must_requirement_ids": covered_new_must,
        "uncovered_new_must_requirement_ids": uncovered_new_must,
        "probe_changes": probe_changes,
    }
    comparison["repair_suggestions"] = build_repair_suggestions(comparison)
    return comparison


def summarize_run(run: dict[str, Any]) -> dict[str, object]:
    delivery_report = _dict(run.get("delivery_report"))
    artifact_report = _dict(run.get("artifact_report"))
    requirement_coverage = _dict(run.get("requirement_coverage"))
    runtime_state = _dict(run.get("runtime_state"))
    evaluation = _dict(runtime_state.get("evaluation") or runtime_state.get("evaluation_result"))
    final_gate = _dict(delivery_report.get("final_gate"))
    requirements = _dict(delivery_report.get("requirements"))
    artifact = _dict(delivery_report.get("artifact"))
    status = str(run.get("status", delivery_report.get("status", "")) or "")
    entries = requirement_coverage.get("entries", [])
    if not isinstance(entries, list):
        entries = []
    must_requirement_ids = sorted(
        str(entry.get("requirement_id", ""))
        for entry in entries
        if isinstance(entry, dict) and str(entry.get("priority", "")).lower() == "must" and str(entry.get("requirement_id", ""))
    )
    covered_must_requirement_ids = sorted(
        str(entry.get("requirement_id", ""))
        for entry in entries
        if (
            isinstance(entry, dict)
            and str(entry.get("priority", "")).lower() == "must"
            and str(entry.get("coverage_status", "")).lower() == "covered"
            and str(entry.get("requirement_id", ""))
        )
    )

    return {
        "run_id": str(run.get("run_id", "")),
        "status": status,
        "ready_for_review": bool(delivery_report.get("ready_for_review", False)),
        "final_gate_score": _number(
            final_gate.get("score", evaluation.get("final_gate_score", evaluation.get("final_score", 0)))
        ),
        "coverage_score": _number(requirement_coverage.get("coverage_score", requirements.get("coverage_score", 0))),
        "missing_must_requirement_ids": _string_list(
            requirement_coverage.get(
                "missing_must_requirement_ids",
                requirements.get("missing_must_requirement_ids", []),
            )
        ),
        "partial_must_requirement_ids": _string_list(
            requirement_coverage.get(
                "partial_must_requirement_ids",
                requirements.get("partial_must_requirement_ids", []),
            )
        ),
        "must_requirement_ids": must_requirement_ids,
        "covered_must_requirement_ids": covered_must_requirement_ids,
        "total_must_requirements": len(must_requirement_ids),
        "blockers": _compact_blockers(delivery_report.get("blockers", runtime_state.get("blockers", []))),
        "probes": summarize_probe_statuses(delivery_report, artifact, artifact_report, run),
    }


def summarize_probe_statuses(
    delivery_report: dict[str, Any],
    artifact: dict[str, Any],
    artifact_report: dict[str, Any],
    run: dict[str, Any],
) -> dict[str, str]:
    browser = _dict(artifact_report.get("browser_verification"))
    static = _dict(artifact_report.get("static_verification"))
    native = _dict(artifact.get("native_ui_tests") or artifact_report.get("native_ui_tests"))
    github = _dict(delivery_report.get("github"))
    generated_ci = _dict(run.get("generated_ci"))
    probes = {
        "static": _normalize_status(str(artifact.get("static_status", static.get("status", "")) or "")),
        "browser": _normalize_status(str(artifact.get("browser_status", browser.get("status", "")) or "")),
        "semantic": _normalize_status(
            str(
                artifact.get(
                    "semantic_status",
                    _dict(artifact.get("semantic_probe") or browser.get("semantic_probe")).get("status", ""),
                )
                or ""
            )
        ),
        "scenario": _normalize_status(
            str(
                artifact.get(
                    "scenario_status",
                    _dict(artifact.get("scenario_probe") or browser.get("scenario_probe")).get("status", ""),
                )
                or ""
            )
        ),
        "gameplay": _normalize_status(
            str(
                artifact.get(
                    "gameplay_status",
                    _dict(artifact.get("gameplay_probe") or browser.get("gameplay_probe")).get("status", ""),
                )
                or ""
            )
        ),
        "native_ui_tests": _normalize_status(str(native.get("status", "") or "")),
        "ci": _normalize_status(str(github.get("ci_status", generated_ci.get("status", "")) or "")),
    }
    return {key: value for key, value in probes.items() if value}


def compare_probe_statuses(source: dict[str, Any], current: dict[str, Any]) -> list[dict[str, object]]:
    changes: list[dict[str, object]] = []
    for name in PROBE_KEYS:
        source_status = str(source.get(name, "") or "")
        current_status = str(current.get(name, "") or "")
        if not source_status and not current_status:
            continue
        source_rank = _status_rank(source_status)
        current_rank = _status_rank(current_status)
        if current_rank > source_rank:
            direction = "improved"
        elif current_rank < source_rank:
            direction = "regressed"
        else:
            direction = "unchanged"
        changes.append(
            {
                "name": name,
                "source_status": source_status or "unknown",
                "current_status": current_status or "unknown",
                "direction": direction,
            }
        )
    return changes


def classify_comparison(
    *,
    source: dict[str, object],
    current: dict[str, object],
    score_delta: float,
    coverage_delta: float,
    resolved_missing: list[str],
    new_missing: list[str],
    resolved_partial: list[str],
    new_partial: list[str],
    covered_new_must: list[str],
    uncovered_new_must: list[str],
    blocker_delta: int,
    probe_changes: list[dict[str, object]],
) -> str:
    status_delta = _status_rank(str(current.get("status", ""))) - _status_rank(str(source.get("status", "")))
    has_improvement = (
        status_delta > 0
        or score_delta > 0
        or coverage_delta > 0
        or bool(resolved_missing)
        or bool(resolved_partial)
        or bool(covered_new_must)
        or blocker_delta < 0
        or any(change.get("direction") == "improved" for change in probe_changes)
    )
    has_regression = (
        status_delta < 0
        or score_delta < 0
        or coverage_delta < 0
        or bool(new_missing)
        or bool(new_partial)
        or bool(uncovered_new_must)
        or blocker_delta > 0
        or any(change.get("direction") == "regressed" for change in probe_changes)
    )
    if has_improvement and has_regression:
        return "mixed"
    if has_regression:
        return "regressed"
    if has_improvement:
        return "improved"
    if source.get("status") == "done" and current.get("status") == "done":
        return "same_passed"
    return "unchanged"


def summary_for(status: str) -> str:
    if status == "improved":
        return "Repair run improved the source run evidence."
    if status == "mixed":
        return "Repair run improved some evidence but introduced at least one regression."
    if status == "regressed":
        return "Repair run regressed compared with the source run."
    if status == "same_passed":
        return "Source and repair runs both satisfy the delivery gate."
    return "No material evidence change was detected between the source and current run."


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _compact_blockers(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    blockers: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, dict):
            blocker_id = str(item.get("id", item.get("type", "blocker")) or "blocker")
            description = str(item.get("description", item.get("message", item)) or "")
        else:
            blocker_id = "blocker"
            description = str(item)
        blockers.append({"id": blocker_id, "description": description})
    return blockers


def _normalize_status(status: str) -> str:
    value = status.strip().lower()
    if value in {"completed", "passed", "success", "ready", "done", "merged"}:
        return "passed"
    if value in {"failed", "blocked", "error", "missing"}:
        return "failed"
    if value in {"partial", "in_progress", "running", "queued"}:
        return "partial"
    if value in {"skipped", "waived", ""}:
        return value
    return value


def _status_rank(status: str) -> int:
    return STATUS_RANK.get(_normalize_status(status), STATUS_RANK.get(status.strip().lower(), 0))


def _number(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _delta(current: object, source: object) -> float:
    return round(_number(current) - _number(source), 4)
