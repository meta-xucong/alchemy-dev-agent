"""Phase promotion rules for full-roadmap mode."""

from __future__ import annotations

from typing import Any

from .roadmap_models import RoadmapExecutionPlan, RoadmapPhase


def phase_promotion_decision(phase: RoadmapPhase, result: dict[str, Any]) -> dict[str, object]:
    status = str(result.get("status", "") or "")
    delivery = result.get("delivery_report", {}) if isinstance(result.get("delivery_report"), dict) else {}
    final_gate = delivery.get("final_gate", {}) if isinstance(delivery.get("final_gate"), dict) else {}
    score = float(final_gate.get("score", final_gate.get("final_score", 0.0)) or 0.0)
    required_score = float(phase.promotion_gate.get("required_score", 0.85) or 0.85)
    blockers = result.get("blockers", [])
    runtime_state = result.get("runtime_state", {}) if isinstance(result.get("runtime_state"), dict) else {}
    if not blockers:
        blockers = runtime_state.get("blockers", []) if isinstance(runtime_state, dict) else []
    if phase.phase_type == "documentation" and status == "done" and not blockers and score > 0:
        score = max(score, required_score)
    reasons: list[str] = []
    preserved_gate_tasks = final_verification_preserved_gate_tasks(phase, runtime_state)
    if status != "done":
        reasons.append(f"Phase run status is {status or 'unknown'}.")
    if blockers:
        reasons.append("Phase has blockers.")
    if score and score < required_score:
        reasons.append(f"Phase score {score:.2f} is below required {required_score:.2f}.")
    if preserved_gate_tasks:
        reasons.append(
            "Final verification gate tasks must rerun after repair, not be preserved as completed: "
            + ", ".join(preserved_gate_tasks)
            + "."
        )
    can_promote = status == "done" and not blockers and not preserved_gate_tasks and (score == 0.0 or score >= required_score)
    return {
        "status": "passed" if can_promote else "blocked",
        "can_promote": can_promote,
        "phase_id": phase.phase_id,
        "required_score": required_score,
        "score": score,
        "reasons": reasons,
    }


def final_verification_preserved_gate_tasks(phase: RoadmapPhase, runtime_state: dict[str, Any]) -> list[str]:
    if phase.phase_id != "final_verification":
        return []
    task_graph = runtime_state.get("task_graph", {}) if isinstance(runtime_state, dict) else {}
    nodes = task_graph.get("nodes", []) if isinstance(task_graph, dict) else []
    gate_title_markers = (
        "audit final requirements",
        "run final simulation probes",
        "run final real repository checks",
        "review final handoff markers",
    )
    preserved: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        title = str(node.get("title", "") or "").lower()
        if not any(marker in title for marker in gate_title_markers):
            continue
        evidence = node.get("evidence", [])
        latest = evidence[-1] if isinstance(evidence, list) and evidence else {}
        if isinstance(latest, dict) and latest.get("type") == "focused_repair_preserved_task":
            preserved.append(str(node.get("id", "") or title))
    return preserved


def final_handoff_allowed(plan: RoadmapExecutionPlan) -> dict[str, object]:
    incomplete = [
        phase.phase_id
        for phase in plan.phases
        if not phase.optional and phase.status not in {"completed", "skipped"}
    ]
    return {
        "allowed": not incomplete,
        "status": "passed" if not incomplete else "blocked",
        "incomplete_phase_ids": incomplete,
        "reason": "All required phases are complete." if not incomplete else "Required roadmap phases remain.",
    }


def next_ready_phase(plan: RoadmapExecutionPlan) -> RoadmapPhase | None:
    completed = {phase.phase_id for phase in plan.phases if phase.status == "completed"}
    for phase in plan.phases:
        if phase.status != "pending":
            continue
        if phase.optional:
            continue
        if all(prereq in completed for prereq in phase.prerequisites):
            return phase
    return None
