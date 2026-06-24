"""Central review decision for the autonomous development loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CentralReview:
    status: str
    decision: str
    confidence: float
    summary: str
    completed_loop_steps: list[str] = field(default_factory=list)
    missing_loop_steps: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    human_help_needed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "decision": self.decision,
            "confidence": round(self.confidence, 4),
            "summary": self.summary,
            "completed_loop_steps": list(self.completed_loop_steps),
            "missing_loop_steps": list(self.missing_loop_steps),
            "next_actions": list(self.next_actions),
            "human_help_needed": self.human_help_needed,
        }


def build_central_review(
    *,
    status: str,
    run: dict[str, Any] | None = None,
    job: dict[str, Any] | None = None,
    delivery_report: dict[str, Any] | None = None,
    artifact_report: dict[str, Any] | None = None,
    requirement_coverage: dict[str, Any] | None = None,
    development_cycle: dict[str, Any] | None = None,
    artifact_manifest: dict[str, Any] | None = None,
    delivery_actions: list[dict[str, Any]] | None = None,
    is_stalled: bool = False,
) -> dict[str, object]:
    """Summarize run evidence into one human-style phase decision."""

    run = run or {}
    job = job or {}
    delivery_report = delivery_report or _dict(run.get("delivery_report"))
    artifact_report = artifact_report or _dict(run.get("artifact_report"))
    requirement_coverage = requirement_coverage or _dict(run.get("requirement_coverage"))
    development_cycle = development_cycle or _dict(run.get("development_cycle"))
    artifact_manifest = artifact_manifest or {"items": []}
    delivery_actions = list(delivery_actions or [])
    runtime_state = _dict(run.get("runtime_state"))

    normalized_status = str(status or job.get("status") or run.get("status") or "unknown").lower()
    completed_steps, missing_steps = _loop_steps(
        runtime_state=runtime_state,
        delivery_report=delivery_report,
        artifact_report=artifact_report,
        requirement_coverage=requirement_coverage,
        development_cycle=development_cycle,
    )
    next_actions = _next_actions(
        delivery_report=delivery_report,
        requirement_coverage=requirement_coverage,
        artifact_report=artifact_report,
        development_cycle=development_cycle,
    )
    blockers = _blockers(run, delivery_report, runtime_state)

    if not run and normalized_status in {"queued", "running", "paused"}:
        return CentralReview(
            status="running",
            decision="continue",
            confidence=0.55,
            summary="Development is running. Keep waiting for task evidence.",
            completed_loop_steps=completed_steps,
            missing_loop_steps=missing_steps,
            next_actions=["Continue monitoring the current run."],
        ).to_dict()

    if not run:
        return CentralReview(
            status="waiting",
            decision="wait_for_input",
            confidence=0.0,
            summary="No run evidence exists yet.",
            missing_loop_steps=["execution"],
            next_actions=["Choose a source and start development."],
            human_help_needed=True,
        ).to_dict()

    if normalized_status in {"queued", "running", "paused"}:
        summary = "Development is running. Keep waiting for task evidence."
        if is_stalled:
            summary = "Development appears stalled. Check the current worker or stop and resume the run."
            next_actions.insert(0, "Check worker activity because the run appears stalled.")
        return CentralReview(
            status="running",
            decision="continue",
            confidence=0.65 if not is_stalled else 0.35,
            summary=summary,
            completed_loop_steps=completed_steps,
            missing_loop_steps=missing_steps,
            next_actions=next_actions or ["Continue monitoring the current run."],
            human_help_needed=is_stalled,
        ).to_dict()

    if normalized_status in {"failed", "blocked"} or blockers:
        return CentralReview(
            status="blocked",
            decision="blocked",
            confidence=0.9,
            summary=_first_text(blockers) or "The run is blocked and needs attention before continuing.",
            completed_loop_steps=completed_steps,
            missing_loop_steps=missing_steps,
            next_actions=next_actions or ["Resolve the reported blocker, then reopen with feedback."],
            human_help_needed=True,
        ).to_dict()

    ready = bool(delivery_report.get("ready_for_review")) or str(delivery_report.get("status", "")).lower() == "done"
    has_result_action = any(str(action.get("id", "")) == "open_result" and bool(action.get("enabled")) for action in delivery_actions)
    has_artifact = bool(_list(artifact_manifest.get("items"))) or bool(_list(artifact_report.get("artifact_files")))
    final_gate = _dict(delivery_report.get("final_gate"))
    score = _float(final_gate.get("score", 0.0))
    hard_failures = _list(final_gate.get("hard_failures"))
    required_changes = _list(final_gate.get("required_changes"))

    if ready and has_artifact and not hard_failures and not required_changes and score >= 0.85:
        return CentralReview(
            status="ready",
            decision="handoff",
            confidence=max(0.85, min(1.0, score)),
            summary="Ready to review. Open the generated result and inspect it.",
            completed_loop_steps=completed_steps,
            missing_loop_steps=missing_steps,
            next_actions=["Open the result and verify it manually.", *next_actions[:2]],
            human_help_needed=False,
        ).to_dict()

    if normalized_status in {"done", "needs_iteration", "partial"} or run:
        gaps = list(missing_steps)
        if not ready:
            gaps.append("final_review")
        if not has_result_action and not has_artifact:
            gaps.append("reviewable_artifact")
        if score and score < 0.85:
            gaps.append("final_gate_score")
        return CentralReview(
            status="needs_iteration",
            decision="iterate",
            confidence=0.7 if gaps else 0.5,
            summary="A result exists, but the central review found gaps before handoff.",
            completed_loop_steps=completed_steps,
            missing_loop_steps=_dedupe(gaps),
            next_actions=next_actions or ["Run another iteration with feedback or stronger verification enabled."],
            human_help_needed=False,
        ).to_dict()

    return CentralReview(
        status="waiting",
        decision="wait_for_input",
        confidence=0.0,
        summary="No actionable run state is available yet.",
        missing_loop_steps=missing_steps or ["execution"],
        next_actions=["Start development or reopen an existing run."],
        human_help_needed=True,
    ).to_dict()


def _loop_steps(
    *,
    runtime_state: dict[str, Any],
    delivery_report: dict[str, Any],
    artifact_report: dict[str, Any],
    requirement_coverage: dict[str, Any],
    development_cycle: dict[str, Any],
) -> tuple[list[str], list[str]]:
    completed: list[str] = []
    missing: list[str] = []
    cycle_steps = _list(development_cycle.get("steps"))
    if cycle_steps:
        for step in cycle_steps:
            if not isinstance(step, dict):
                continue
            name = str(step.get("name", ""))
            step_status = str(step.get("status", ""))
            if not name:
                continue
            if step_status in {"passed", "waived"}:
                completed.append(name)
            elif step_status in {"missing", "failed", "blocked", "partial"}:
                missing.append(name)
    else:
        if _list(runtime_state.get("iteration_history") or runtime_state.get("execution_history")):
            completed.append("long_task_state")
        else:
            missing.append("long_task_state")
        if _dict(runtime_state.get("task_graph")).get("nodes"):
            completed.append("phase_planning")
        else:
            missing.append("phase_planning")
        if _list(runtime_state.get("completed_tasks")):
            completed.append("execution")
        else:
            missing.append("execution")
        if str(requirement_coverage.get("status", "")).lower() == "passed":
            completed.append("audit")
        else:
            missing.append("audit")
        static = _dict(artifact_report.get("static_verification"))
        browser = _dict(artifact_report.get("browser_verification"))
        if str(static.get("status", "")).lower() in {"passed", "completed", "skipped"} and str(browser.get("status", "")).lower() not in {"failed", "blocked"}:
            completed.append("testing")
        else:
            missing.append("testing")
        if delivery_report.get("ready_for_review"):
            completed.append("full_review")
        else:
            missing.append("full_review")
    return _dedupe(completed), _dedupe(missing)


def _next_actions(
    *,
    delivery_report: dict[str, Any],
    requirement_coverage: dict[str, Any],
    artifact_report: dict[str, Any],
    development_cycle: dict[str, Any],
) -> list[str]:
    actions = [str(item) for item in _list(delivery_report.get("next_actions")) if str(item).strip()]
    actions.extend(str(item) for item in _list(development_cycle.get("next_actions")) if str(item).strip())
    missing_must = _list(requirement_coverage.get("missing_must_requirement_ids"))
    partial_must = _list(requirement_coverage.get("partial_must_requirement_ids"))
    if missing_must:
        actions.append("Implement missing must requirements: " + ", ".join(str(item) for item in missing_must[:5]))
    if partial_must:
        actions.append("Complete partial must requirements: " + ", ".join(str(item) for item in partial_must[:5]))
    browser = _dict(artifact_report.get("browser_verification"))
    if str(browser.get("status", "")).lower() in {"failed", "blocked"}:
        actions.append("Fix browser verification failures and rerun.")
    if not browser:
        actions.append("Run browser verification when a visual or interactive artifact is expected.")
    return _dedupe(actions)[:6]


def _blockers(run: dict[str, Any], delivery_report: dict[str, Any], runtime_state: dict[str, Any]) -> list[Any]:
    blockers: list[Any] = []
    blockers.extend(_list(run.get("blockers")))
    blockers.extend(_list(delivery_report.get("blockers")))
    blockers.extend(_list(runtime_state.get("blockers")))
    final_gate = _dict(delivery_report.get("final_gate"))
    blockers.extend(_list(final_gate.get("hard_failures")))
    return blockers


def _first_text(items: list[Any]) -> str:
    for item in items:
        if isinstance(item, dict):
            text = str(item.get("message") or item.get("description") or item.get("summary") or "")
        else:
            text = str(item)
        if text.strip():
            return text.strip()
    return ""


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
