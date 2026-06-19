"""Build Debug Agent repair suggestions from recovery comparison evidence."""

from __future__ import annotations

from typing import Any


def build_repair_suggestions(comparison: dict[str, Any]) -> list[dict[str, object]]:
    """Convert source-vs-current comparison gaps into Debug Agent task seeds."""

    suggestions: list[dict[str, object]] = []
    current = _dict(comparison.get("current"))
    current_score = _number(current.get("final_gate_score"))
    current_ready = bool(current.get("ready_for_review", False))

    new_missing = _string_list(comparison.get("new_missing_must_requirement_ids"))
    if new_missing:
        _add_requirement_suggestion(
            suggestions,
            title="Cover newly missing must requirements",
            reason="The repair run introduced must requirements with no coverage.",
            requirement_ids=new_missing,
        )

    new_partial = _string_list(comparison.get("new_partial_must_requirement_ids"))
    if new_partial:
        _add_requirement_suggestion(
            suggestions,
            title="Complete newly partial must requirements",
            reason="The repair run left must requirements only partially covered.",
            requirement_ids=new_partial,
        )

    requirement_gap_ids = set(new_missing + new_partial)
    uncovered_new = [
        requirement_id
        for requirement_id in _string_list(comparison.get("uncovered_new_must_requirement_ids"))
        if requirement_id not in requirement_gap_ids
    ]
    if uncovered_new:
        _add_requirement_suggestion(
            suggestions,
            title="Cover new feedback must requirements",
            reason="Feedback introduced new must requirements that are not covered yet.",
            requirement_ids=uncovered_new,
        )

    if _number(comparison.get("coverage_delta")) < 0:
        suggestions.append(
            _suggestion(
                suggestions,
                title="Recover requirement coverage regression",
                priority="must",
                reason="Requirement coverage decreased compared with the source run.",
                worker_goal="Audit changed implementation and tests, then restore or improve requirement coverage.",
            )
        )

    if _number(comparison.get("score_delta")) < 0:
        suggestions.append(
            _suggestion(
                suggestions,
                title="Recover final gate score regression",
                priority="must" if current_score < 0.85 else "should",
                reason="The final gate score decreased compared with the source run.",
                worker_goal="Inspect final gate failures and repair the implementation until the score no longer regresses.",
            )
        )

    if _number(comparison.get("blocker_delta")) > 0:
        blockers = _dict_list(current.get("blockers"))
        suggestions.append(
            _suggestion(
                suggestions,
                title="Resolve new repair blockers",
                priority="must",
                reason="The repair run has more blockers than the source run.",
                blocker_ids=[str(item.get("id", "blocker")) for item in blockers],
                worker_goal="Remove or resolve the new blockers and rerun the affected checks.",
            )
        )

    for change in _dict_list(comparison.get("probe_changes")):
        if str(change.get("direction", "")) != "regressed":
            continue
        probe = str(change.get("name", "probe") or "probe")
        suggestions.append(
            _suggestion(
                suggestions,
                title=f"Repair {probe} probe regression",
                priority="must",
                reason=f"{probe} probe changed from {change.get('source_status', 'unknown')} to {change.get('current_status', 'unknown')}.",
                probe=probe,
                worker_goal=f"Reproduce the {probe} probe regression, patch the app or tests, and rerun the probe until it passes.",
            )
        )

    if not suggestions and not current_ready and str(comparison.get("status", "")) in {"unchanged", "regressed", "mixed"}:
        suggestions.append(
            _suggestion(
                suggestions,
                title="Run focused Debug Agent repair audit",
                priority="should",
                reason="The repair run is still not ready for review but no specific regression bucket was detected.",
                worker_goal="Compare source and current evidence, identify the remaining delivery blocker, and create a focused repair patch.",
            )
        )

    return suggestions


def _add_requirement_suggestion(
    suggestions: list[dict[str, object]],
    *,
    title: str,
    reason: str,
    requirement_ids: list[str],
) -> None:
    suggestions.append(
        _suggestion(
            suggestions,
            title=title,
            priority="must",
            reason=reason,
            requirement_ids=requirement_ids,
            worker_goal="Implement or fix the linked must requirements, add verification evidence, and rerun coverage.",
        )
    )


def _suggestion(
    existing: list[dict[str, object]],
    *,
    title: str,
    priority: str,
    reason: str,
    worker_goal: str,
    requirement_ids: list[str] | None = None,
    probe: str = "",
    blocker_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": f"RS-{len(existing) + 1:03d}",
        "agent": "debug",
        "task_type": "debug",
        "priority": priority,
        "title": title,
        "reason": reason,
        "requirement_ids": list(requirement_ids or []),
        "probe": probe,
        "blocker_ids": list(blocker_ids or []),
        "worker_goal": worker_goal,
    }


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_list(value: object) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _string_list(value: object) -> list[str]:
    return [str(item) for item in value if str(item)] if isinstance(value, list) else []


def _number(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
