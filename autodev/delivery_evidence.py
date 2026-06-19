"""Build display-ready delivery evidence summaries."""

from __future__ import annotations

from typing import Any


def build_delivery_evidence(
    *,
    status: str,
    delivery_report: dict[str, Any],
    artifact_report: dict[str, Any],
    requirement_coverage: dict[str, Any],
    generated_ci: dict[str, Any],
    development_cycle: dict[str, Any],
    recovery_comparison: dict[str, Any] | None = None,
) -> dict[str, object]:
    artifact = delivery_report.get("artifact", {}) if isinstance(delivery_report.get("artifact", {}), dict) else {}
    final_gate = delivery_report.get("final_gate", {}) if isinstance(delivery_report.get("final_gate", {}), dict) else {}
    github = delivery_report.get("github", {}) if isinstance(delivery_report.get("github", {}), dict) else {}
    blockers = list(delivery_report.get("blockers", [])) if isinstance(delivery_report.get("blockers", []), list) else []
    next_actions = list(delivery_report.get("next_actions", [])) if isinstance(delivery_report.get("next_actions", []), list) else []
    requirements = requirement_summary(requirement_coverage)
    probes = probe_summary(artifact, artifact_report)
    native_tests = native_ui_summary(artifact)
    github_summary = github_evidence(github, generated_ci)
    cycle = development_cycle_summary(development_cycle)
    comparison = recovery_comparison_summary(recovery_comparison or {})
    repair_suggestions = list(comparison.get("repair_suggestions", [])) if isinstance(comparison.get("repair_suggestions", []), list) else []
    for suggestion in repair_suggestions:
        if not isinstance(suggestion, dict):
            continue
        title = str(suggestion.get("title", ""))
        if title and title not in next_actions:
            next_actions.append(title)
    ready = bool(delivery_report.get("ready_for_review", False))
    score = _number(final_gate.get("score"))
    evidence_status = "ready" if ready else "blocked" if blockers else status or "unknown"

    cards = [
        evidence_card(
            "Final Gate",
            "passed" if ready else "failed" if blockers else _status_from_score(score),
            _format_score(score),
            str(final_gate.get("reason", delivery_report.get("summary", ""))),
        ),
        evidence_card(
            "Requirements",
            "passed" if requirements["missing_must"] == 0 and requirements["partial_must"] == 0 else "failed",
            f"{requirements['covered']}/{requirements['total']} covered",
            f"coverage_score={requirements['coverage_score']}",
        ),
        evidence_card(
            "Artifact",
            _normalize_status(str(artifact.get("static_status", "") or artifact_report.get("static_verification", {}).get("status", ""))),
            str(artifact.get("profile", artifact_report.get("artifact_profile", {}).get("name", "unknown"))),
            "Static artifact evidence.",
        ),
        evidence_card(
            "Browser Probes",
            probes["overall_status"],
            probes["headline"],
            "semantic, scenario, and gameplay probe evidence",
        ),
        evidence_card(
            "Native UI Tests",
            _normalize_status(str(native_tests.get("status", ""))),
            str(native_tests.get("framework", "none")),
            str(native_tests.get("target_path", native_tests.get("summary", ""))),
        ),
        evidence_card(
            "CI",
            _normalize_status(str(github_summary.get("ci_status", generated_ci.get("status", "")))),
            str(github_summary.get("ci_status", generated_ci.get("status", "-"))),
            str(github_summary.get("summary", "")),
        ),
        evidence_card(
            "Development Cycle",
            str(cycle.get("status", "unknown")),
            f"{cycle.get('passed_steps', 0)}/{cycle.get('total_steps', 0)} steps",
            f"score={cycle.get('score', 0)}",
        ),
    ]
    if comparison:
        cards.append(
            evidence_card(
                "Repair Comparison",
                comparison_status_for_card(str(comparison.get("status", ""))),
                f"score delta {format_delta(comparison.get('score_delta', 0))}",
                str(comparison.get("summary", "")),
            )
        )

    return {
        "status": evidence_status,
        "ready_for_review": ready,
        "score": score,
        "summary": str(delivery_report.get("summary", "")),
        "cards": cards,
        "requirements": requirements,
        "probes": probes,
        "native_ui_tests": native_tests,
        "github": github_summary,
        "development_cycle": cycle,
        "recovery_comparison": comparison,
        "repair_suggestions": repair_suggestions,
        "blockers": blockers,
        "next_actions": next_actions,
    }


def evidence_card(label: str, status: str, value: str, detail: str = "") -> dict[str, object]:
    return {
        "label": label,
        "status": status or "unknown",
        "value": value or "-",
        "detail": detail or "",
    }


def requirement_summary(requirement_coverage: dict[str, Any]) -> dict[str, object]:
    entries = requirement_coverage.get("entries", [])
    if not isinstance(entries, list):
        entries = []
    counts = {"covered": 0, "partial": 0, "missing": 0}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("coverage_status", "missing"))
        if status in counts:
            counts[status] += 1
    missing_must = list(requirement_coverage.get("missing_must_requirement_ids", []))
    partial_must = list(requirement_coverage.get("partial_must_requirement_ids", []))
    return {
        "status": requirement_coverage.get("status", ""),
        "coverage_score": requirement_coverage.get("coverage_score", 0),
        "total": len(entries),
        **counts,
        "missing_must": len(missing_must),
        "partial_must": len(partial_must),
        "missing_must_requirement_ids": missing_must,
        "partial_must_requirement_ids": partial_must,
    }


def probe_summary(artifact: dict[str, Any], artifact_report: dict[str, Any]) -> dict[str, object]:
    browser = artifact_report.get("browser_verification", {})
    if not isinstance(browser, dict):
        browser = {}
    semantic = _probe_detail("Semantic", artifact.get("semantic_probe", browser.get("semantic_probe", {})))
    scenario = _probe_detail("Scenario", artifact.get("scenario_probe", browser.get("scenario_probe", {})))
    gameplay = _probe_detail("Gameplay", artifact.get("gameplay_probe", browser.get("gameplay_probe", {})))
    browser_status = str(artifact.get("browser_status", browser.get("status", "")) or "")
    statuses = [semantic["status"], scenario["status"], gameplay["status"], browser_status]
    normalized = [_normalize_status(str(status)) for status in statuses if status]
    if any(status == "failed" for status in normalized):
        overall = "failed"
    elif any(status == "passed" for status in normalized):
        overall = "passed"
    elif browser_status:
        overall = _normalize_status(browser_status)
    else:
        overall = "skipped"
    headline = ", ".join(
        f"{item['label']}={item['status']}"
        for item in (semantic, scenario, gameplay)
        if item["status"]
    ) or browser_status or "no browser probe"
    return {
        "overall_status": overall,
        "browser_status": browser_status,
        "headline": headline,
        "semantic": semantic,
        "scenario": scenario,
        "gameplay": gameplay,
        "screenshots": dict(artifact.get("screenshots", browser.get("screenshots", {})) or {}),
        "pixel_diff": dict(artifact.get("pixel_diff", browser.get("pixel_diff", {})) or {}),
    }


def native_ui_summary(artifact: dict[str, Any]) -> dict[str, object]:
    native = artifact.get("native_ui_tests", {})
    if not isinstance(native, dict):
        native = {}
    return {
        "status": str(native.get("status", "")),
        "framework": str(native.get("framework", "none")),
        "write_mode": str(native.get("write_mode", "")),
        "target_path": str(native.get("target_path", "")),
        "summary": str(native.get("summary", "")),
        "files": list(native.get("files", [])) if isinstance(native.get("files", []), list) else [],
        "evidence": list(native.get("evidence", [])) if isinstance(native.get("evidence", []), list) else [],
    }


def github_evidence(github: dict[str, Any], generated_ci: dict[str, Any]) -> dict[str, object]:
    merge = github.get("merge", {}) if isinstance(github.get("merge", {}), dict) else {}
    return {
        "pull_request_url": str(github.get("pull_request_url", "")),
        "branch": str(github.get("branch", "")),
        "commit": str(github.get("commit", "")),
        "ci_status": str(github.get("ci_status", generated_ci.get("status", ""))),
        "merge_status": str(merge.get("status", "")),
        "generated_ci_status": str(generated_ci.get("status", "")),
        "summary": str(merge.get("summary", "")),
    }


def development_cycle_summary(development_cycle: dict[str, Any]) -> dict[str, object]:
    steps = development_cycle.get("steps", [])
    if not isinstance(steps, list):
        steps = []
    passed = 0
    partial = 0
    missing = 0
    compact_steps: list[dict[str, object]] = []
    for item in steps:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "unknown"))
        if status in {"passed", "waived"}:
            passed += 1
        elif status == "partial":
            partial += 1
        elif status in {"missing", "failed"}:
            missing += 1
        compact_steps.append(
            {
                "name": str(item.get("name", "")),
                "status": status,
                "gaps": list(item.get("gaps", [])) if isinstance(item.get("gaps", []), list) else [],
            }
        )
    return {
        "status": str(development_cycle.get("status", "")),
        "score": development_cycle.get("score", 0),
        "total_steps": len(compact_steps),
        "passed_steps": passed,
        "partial_steps": partial,
        "missing_steps": missing,
        "steps": compact_steps,
        "next_actions": list(development_cycle.get("next_actions", []))
        if isinstance(development_cycle.get("next_actions", []), list)
        else [],
    }


def recovery_comparison_summary(recovery_comparison: dict[str, Any]) -> dict[str, object]:
    if not recovery_comparison:
        return {}
    return {
        "status": str(recovery_comparison.get("status", "")),
        "summary": str(recovery_comparison.get("summary", "")),
        "source_run_id": str(recovery_comparison.get("source_run_id", "")),
        "current_run_id": str(recovery_comparison.get("current_run_id", "")),
        "score_delta": recovery_comparison.get("score_delta", 0),
        "coverage_delta": recovery_comparison.get("coverage_delta", 0),
        "blocker_delta": recovery_comparison.get("blocker_delta", 0),
        "resolved_missing_must_requirement_ids": list(
            recovery_comparison.get("resolved_missing_must_requirement_ids", [])
        )
        if isinstance(recovery_comparison.get("resolved_missing_must_requirement_ids", []), list)
        else [],
        "new_missing_must_requirement_ids": list(recovery_comparison.get("new_missing_must_requirement_ids", []))
        if isinstance(recovery_comparison.get("new_missing_must_requirement_ids", []), list)
        else [],
        "resolved_partial_must_requirement_ids": list(
            recovery_comparison.get("resolved_partial_must_requirement_ids", [])
        )
        if isinstance(recovery_comparison.get("resolved_partial_must_requirement_ids", []), list)
        else [],
        "new_partial_must_requirement_ids": list(recovery_comparison.get("new_partial_must_requirement_ids", []))
        if isinstance(recovery_comparison.get("new_partial_must_requirement_ids", []), list)
        else [],
        "new_must_requirement_ids": list(recovery_comparison.get("new_must_requirement_ids", []))
        if isinstance(recovery_comparison.get("new_must_requirement_ids", []), list)
        else [],
        "covered_new_must_requirement_ids": list(recovery_comparison.get("covered_new_must_requirement_ids", []))
        if isinstance(recovery_comparison.get("covered_new_must_requirement_ids", []), list)
        else [],
        "uncovered_new_must_requirement_ids": list(recovery_comparison.get("uncovered_new_must_requirement_ids", []))
        if isinstance(recovery_comparison.get("uncovered_new_must_requirement_ids", []), list)
        else [],
        "probe_changes": list(recovery_comparison.get("probe_changes", []))
        if isinstance(recovery_comparison.get("probe_changes", []), list)
        else [],
        "repair_suggestions": list(recovery_comparison.get("repair_suggestions", []))
        if isinstance(recovery_comparison.get("repair_suggestions", []), list)
        else [],
    }


def comparison_status_for_card(status: str) -> str:
    if status in {"improved", "same_passed"}:
        return "passed"
    if status == "mixed":
        return "partial"
    if status == "regressed":
        return "failed"
    return "skipped"


def _probe_detail(label: str, payload: object) -> dict[str, object]:
    data = payload if isinstance(payload, dict) else {}
    return {
        "label": label,
        "status": str(data.get("status", "")),
        "tests_passed": list(data.get("tests_passed", [])) if isinstance(data.get("tests_passed", []), list) else [],
        "tests_failed": list(data.get("tests_failed", [])) if isinstance(data.get("tests_failed", []), list) else [],
        "evidence": list(data.get("evidence", [])) if isinstance(data.get("evidence", []), list) else [],
    }


def _normalize_status(status: str) -> str:
    value = status.strip().lower()
    if value in {"completed", "passed", "success", "ready", "done", "merged"}:
        return "passed"
    if value in {"failed", "blocked", "error", "missing"}:
        return "failed"
    if value in {"partial", "in_progress", "running", "queued"}:
        return "partial"
    if value in {"skipped", "waived", ""}:
        return "skipped"
    return value


def _status_from_score(score: float) -> str:
    if score >= 0.85:
        return "passed"
    if score > 0:
        return "partial"
    return "unknown"


def _number(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _format_score(score: float) -> str:
    return f"{score:.2f}" if score else "-"


def format_delta(value: object) -> str:
    delta = _number(value)
    return f"{delta:+.2f}"
