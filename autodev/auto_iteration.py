"""Central auto-iteration repair plan generation."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any


MAX_AUTO_ITERATIONS_PER_PROJECT = 3
MAX_DUPLICATE_REPAIR_SIGNATURE_COUNT = 1
PATH_PATTERN = re.compile(
    r"(?P<path>[\w./-]+\.(?:tsx|jsx|yaml|yml|py|js|ts|go|rs|java|cs|rb|php|html|css|sql|md|json))(?![\w/-])"
)


def build_auto_iteration_preview(
    *,
    project_id: str,
    source_run_id: str,
    central_review: dict[str, Any],
    run: dict[str, Any],
    delivery_report: dict[str, Any] | None = None,
    artifact_report: dict[str, Any] | None = None,
    requirement_coverage: dict[str, Any] | None = None,
    development_cycle: dict[str, Any] | None = None,
    previous_reports: list[dict[str, Any]] | None = None,
    max_iterations: int = MAX_AUTO_ITERATIONS_PER_PROJECT,
    max_duplicate_signature_count: int = MAX_DUPLICATE_REPAIR_SIGNATURE_COUNT,
) -> dict[str, Any]:
    """Build a non-mutating auto-iteration preview."""

    delivery_report = _dict(delivery_report or run.get("delivery_report"))
    artifact_report = _dict(artifact_report or run.get("artifact_report"))
    requirement_coverage = _dict(requirement_coverage or run.get("requirement_coverage"))
    development_cycle = _dict(development_cycle or run.get("development_cycle"))
    previous_reports = list(previous_reports or [])

    repair_plan = build_repair_plan(
        project_id=project_id,
        source_run_id=source_run_id,
        central_review=central_review,
        run=run,
        delivery_report=delivery_report,
        artifact_report=artifact_report,
        requirement_coverage=requirement_coverage,
        development_cycle=development_cycle,
        previous_reports=previous_reports,
        max_iterations=max_iterations,
        max_duplicate_signature_count=max_duplicate_signature_count,
    )
    report = build_auto_iteration_report(
        project_id=project_id,
        source_run_id=source_run_id,
        central_review=central_review,
        repair_plan=repair_plan,
        preview=True,
    )
    return {
        "project_id": project_id,
        "source_run_id": source_run_id,
        "status": report["status"],
        "central_review": central_review,
        "repair_plan": repair_plan,
        "auto_iteration_report": report,
        "auto_execution_available": bool(repair_plan["auto_execution"]["allowed"]),
    }


def build_repair_plan(
    *,
    project_id: str,
    source_run_id: str,
    central_review: dict[str, Any],
    run: dict[str, Any],
    delivery_report: dict[str, Any],
    artifact_report: dict[str, Any],
    requirement_coverage: dict[str, Any],
    development_cycle: dict[str, Any],
    previous_reports: list[dict[str, Any]],
    max_iterations: int,
    max_duplicate_signature_count: int,
) -> dict[str, Any]:
    """Convert review and delivery gaps into a concrete repair plan."""

    decision = str(central_review.get("decision", "") or "")
    status = str(central_review.get("status", "") or "")
    items = repair_items_from_evidence(
        central_review=central_review,
        run=run,
        delivery_report=delivery_report,
        artifact_report=artifact_report,
        requirement_coverage=requirement_coverage,
        development_cycle=development_cycle,
    )
    signature = repair_signature(source_run_id, items)
    duplicate_count = duplicate_signature_count(previous_reports, signature)
    current_iteration = count_started_iterations(previous_reports)
    blockers = guardrail_blockers(
        decision=decision,
        central_status=status,
        items=items,
        duplicate_count=duplicate_count,
        current_iteration=current_iteration,
        max_iterations=max_iterations,
        max_duplicate_signature_count=max_duplicate_signature_count,
    )
    allowed = decision == "iterate" and bool(items) and not blockers
    plan_status = "ready" if allowed else "blocked"
    if decision == "handoff":
        plan_status = "superseded"
    elif decision not in {"iterate", "blocked"}:
        plan_status = "draft"
    if decision == "blocked" or blockers:
        plan_status = "blocked"

    return {
        "schema_version": "1.0",
        "repair_plan_id": f"rp_{source_run_id}_{signature[-12:]}",
        "project_id": project_id,
        "source_run_id": source_run_id,
        "trigger": "central_review_iterate" if decision == "iterate" else "delivery_gate_failed",
        "status": plan_status,
        "summary": repair_summary(decision=decision, items=items, blockers=blockers),
        "repair_signature": signature,
        "items": items,
        "guardrails": {
            "safe_to_execute": allowed,
            "max_iterations": max_iterations,
            "current_iteration": current_iteration,
            "duplicate_signature_count": duplicate_count,
            "requires_user_approval": False,
            "blockers": blockers,
        },
        "auto_execution": {
            "allowed": allowed,
            "mode": "feedback_reopen" if allowed else "none",
        },
        "created_at": utc_now_iso(),
    }


def repair_items_from_evidence(
    *,
    central_review: dict[str, Any],
    run: dict[str, Any],
    delivery_report: dict[str, Any],
    artifact_report: dict[str, Any],
    requirement_coverage: dict[str, Any],
    development_cycle: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for index, blocker in enumerate(_blockers(run, delivery_report), start=1):
        items.append(
            repair_item(
                index=index,
                priority="must",
                source="hard_blocker",
                summary=_text(blocker) or "Resolve hard blocker before continuing.",
                target_agent="debug",
                required_evidence=["Blocker is resolved and no hard fail remains."],
                acceptance_check="blockers == []",
                target_files=target_files_from_text(_text(blocker)),
            )
        )

    final_gate = _dict(delivery_report.get("final_gate"))
    for text in _list(final_gate.get("hard_failures")):
        items.append(
            repair_item(
                index=len(items) + 1,
                priority="must",
                source="test_failure",
                summary=_text(text) or "Resolve final gate hard failure.",
                target_agent="debug",
                required_evidence=["Final gate hard failures are empty."],
                acceptance_check="delivery_report.final_gate.hard_failures == []",
                target_files=target_files_from_text(_text(text)),
            )
        )
    for text in _list(final_gate.get("required_changes")):
        items.append(
            repair_item(
                index=len(items) + 1,
                priority="must",
                source="reviewer_change",
                summary=_text(text) or "Implement reviewer required change.",
                target_agent="debug",
                required_evidence=["Reviewer required changes are resolved."],
                acceptance_check="delivery_report.final_gate.required_changes == []",
                target_files=target_files_from_text(_text(text)),
            )
        )

    add_probe_items(items, artifact_report)
    add_requirement_items(items, requirement_coverage)
    add_development_cycle_items(items, development_cycle)
    add_central_review_items(items, central_review)
    add_score_dimension_items(items, final_gate)
    return dedupe_repair_items(items)


def add_probe_items(items: list[dict[str, Any]], artifact_report: dict[str, Any]) -> None:
    probes = [
        ("browser_verification", "browser_probe", "Browser verification failed or is blocked."),
        ("semantic_probe", "browser_probe", "Semantic browser probe failed or is blocked."),
        ("scenario_probe", "scenario_probe", "Acceptance scenario probe failed or is blocked."),
        ("gameplay_probe", "gameplay_probe", "Gameplay probe failed or is blocked."),
    ]
    artifact = _dict(artifact_report.get("artifact"))
    for key, source, fallback in probes:
        probe = _dict(artifact_report.get(key)) or _dict(artifact.get(key))
        status = str(probe.get("status", "") or "").lower()
        if status not in {"failed", "blocked"}:
            continue
        summary = str(probe.get("summary") or probe.get("message") or fallback)
        items.append(
            repair_item(
                index=len(items) + 1,
                priority="must",
                source=source,
                summary=summary,
                target_agent="debug",
                required_evidence=[f"{key}.status == passed"],
                acceptance_check=f"artifact_report.{key}.status == passed",
            )
        )


def add_requirement_items(items: list[dict[str, Any]], coverage: dict[str, Any]) -> None:
    requirement_targets = requirement_target_files_by_id(coverage)
    for key, label in (
        ("missing_must_requirement_ids", "Implement missing must requirement"),
        ("partial_must_requirement_ids", "Complete partial must requirement"),
    ):
        for req_id in _list(coverage.get(key)):
            text = str(req_id)
            target_files = requirement_targets.get(text, [])
            items.append(
                repair_item(
                    index=len(items) + 1,
                    priority="must",
                    source="requirement_coverage",
                    summary=f"{label}: {text}",
                    target_agent=infer_agent_for_text(" ".join([text, *target_files])),
                    required_evidence=[f"Requirement {text} is covered."],
                    acceptance_check=f"requirement_coverage.{key} does not include {text}",
                    target_files=target_files,
                )
            )

    for req in _list(_dict(coverage.get("requirement_map")).get("requirements")):
        if not isinstance(req, dict):
            continue
        priority = str(req.get("priority", "") or "").lower()
        status = str(req.get("status", "") or req.get("coverage_status", "") or "").lower()
        if priority != "must" or status not in {"missing", "partial", "failed"}:
            continue
        req_id = str(req.get("id") or req.get("requirement_id") or req.get("title") or "")
        summary = str(req.get("summary") or req.get("description") or req_id or "Must requirement is not covered.")
        target_files = target_files_for_requirement(req)
        items.append(
            repair_item(
                index=len(items) + 1,
                priority="must",
                source="requirement_coverage",
                summary=summary,
                target_agent=infer_agent_for_text(" ".join([summary, *target_files])),
                required_evidence=[f"Must requirement {req_id or summary} is covered."],
                acceptance_check="requirement_coverage must gap is resolved",
                target_files=target_files,
            )
        )


def add_development_cycle_items(items: list[dict[str, Any]], development_cycle: dict[str, Any]) -> None:
    for step in _list(development_cycle.get("steps")):
        if not isinstance(step, dict):
            continue
        status = str(step.get("status", "") or "").lower()
        if status not in {"failed", "blocked"}:
            continue
        name = str(step.get("name") or "development_cycle")
        items.append(
            repair_item(
                index=len(items) + 1,
                priority="must",
                source="central_review_missing_step",
                summary=f"Repair failed development-cycle step: {name}",
                target_agent=agent_for_loop_step(name),
                required_evidence=[f"Development-cycle step {name} passes or is explicitly waived."],
                acceptance_check=f"development_cycle.steps[{name}].status in passed|waived",
                target_files=target_files_from_text(name),
            )
        )


def add_central_review_items(items: list[dict[str, Any]], central_review: dict[str, Any]) -> None:
    decision = str(central_review.get("decision", "") or "")
    if decision != "iterate":
        return
    for step in _list(central_review.get("missing_loop_steps")):
        text = str(step)
        if text in {"final_review", "reviewable_artifact"}:
            priority = "must"
        else:
            priority = "should"
        items.append(
            repair_item(
                index=len(items) + 1,
                priority=priority,
                source="central_review_missing_step",
                summary=f"Complete missing development loop step: {text}",
                target_agent=agent_for_loop_step(text),
                required_evidence=[f"Central review no longer reports missing step {text}."],
                acceptance_check=f"central_review.missing_loop_steps does not include {text}",
                target_files=target_files_from_text(text),
            )
        )


def add_score_dimension_items(items: list[dict[str, Any]], final_gate: dict[str, Any]) -> None:
    scores = _dict(final_gate.get("dimension_scores"))
    for name, value in scores.items():
        score = _float(value)
        if score <= 0 or score >= 0.85:
            continue
        items.append(
            repair_item(
                index=len(items) + 1,
                priority="should",
                source="score_dimension",
                summary=f"Improve low final gate dimension {name}: {score:.2f}",
                target_agent=agent_for_score_dimension(str(name)),
                required_evidence=[f"Final gate dimension {name} improves or is justified."],
                acceptance_check=f"final_gate.dimension_scores.{name} >= 0.85 or explicitly justified",
                target_files=target_files_from_text(str(name)),
            )
        )


def repair_item(
    *,
    index: int,
    priority: str,
    source: str,
    summary: str,
    target_agent: str,
    required_evidence: list[str],
    acceptance_check: str,
    target_files: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": f"repair_{index:03d}",
        "priority": priority,
        "source": source,
        "summary": summary.strip(),
        "target_agent": target_agent,
        "target_files": dedupe_strings(list(target_files or [])),
        "required_evidence": required_evidence,
        "acceptance_check": acceptance_check,
    }


def build_auto_iteration_report(
    *,
    project_id: str,
    source_run_id: str,
    central_review: dict[str, Any],
    repair_plan: dict[str, Any],
    preview: bool = False,
    repair_run_id: str | None = None,
    repair_plan_path: str | None = None,
) -> dict[str, Any]:
    decision = str(central_review.get("decision", "") or "wait_for_input")
    guardrails = _list(_dict(repair_plan.get("guardrails")).get("blockers"))
    allowed = bool(_dict(repair_plan.get("auto_execution")).get("allowed"))
    if repair_run_id:
        status = "started"
        reason = "Started a repair run from central auto-iteration."
    elif decision == "handoff":
        status = "handoff"
        reason = "Central review says the result is ready for handoff."
    elif decision == "blocked" or guardrails:
        status = "blocked"
        reason = guardrails[0] if guardrails else "Central review is blocked."
    else:
        status = "skipped"
        reason = "Preview only. Automatic iteration can be started." if preview and allowed else "Automatic iteration is not available."

    return {
        "schema_version": "1.0",
        "project_id": project_id,
        "source_run_id": source_run_id,
        "repair_run_id": repair_run_id,
        "status": status,
        "central_review_decision": decision,
        "repair_plan_path": repair_plan_path,
        "reason": reason,
        "guardrails": [str(item) for item in guardrails],
        "next_actions": next_actions_for_report(status=status, repair_plan=repair_plan),
        "created_at": utc_now_iso(),
    }


def repair_plan_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# Repair Plan",
        "",
        f"Project: {plan.get('project_id', '')}",
        f"Source run: {plan.get('source_run_id', '')}",
        f"Status: {plan.get('status', '')}",
        "",
        "## Summary",
        "",
        str(plan.get("summary", "")),
        "",
        "## Required Repairs",
        "",
    ]
    items = _list(plan.get("items"))
    if not items:
        lines.append("- No concrete repair item was generated.")
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        lines.append(f"{index}. [{item.get('priority', '')}] {item.get('summary', '')}")
        lines.append(f"   - Agent: {item.get('target_agent', '')}")
        lines.append(f"   - Source: {item.get('source', '')}")
        target_files = _list(item.get("target_files"))
        if target_files:
            lines.append(f"   - Target files: {', '.join(str(path) for path in target_files)}")
        lines.append(f"   - Acceptance: {item.get('acceptance_check', '')}")
    lines.extend(["", "## Guardrails", ""])
    guardrails = _dict(plan.get("guardrails"))
    blockers = _list(guardrails.get("blockers"))
    lines.append(f"- Safe to execute: {guardrails.get('safe_to_execute', False)}")
    lines.append(f"- Current iteration: {guardrails.get('current_iteration', 0)} / {guardrails.get('max_iterations', 0)}")
    lines.append(f"- Duplicate signature count: {guardrails.get('duplicate_signature_count', 0)}")
    lines.append(f"- Blockers: {', '.join(str(item) for item in blockers) if blockers else 'none'}")
    lines.append("")
    return "\n".join(lines)


def auto_feedback_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# Auto Feedback",
        "",
        f"Source run: {plan.get('source_run_id', '')}",
        "Reason: central review requested another iteration.",
        "",
        "## Required Repairs",
        "",
    ]
    items = _list(plan.get("items"))
    if not items:
        lines.append("- No concrete repair item was generated.")
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        lines.append(f"{index}. {item.get('summary', '')}")
        target_files = _list(item.get("target_files"))
        if target_files:
            lines.append(f"   - Target files: {', '.join(str(path) for path in target_files)}")
    lines.extend(["", "## Acceptance Evidence Required", ""])
    evidence: list[str] = []
    for item in items:
        if isinstance(item, dict):
            evidence.extend(str(value) for value in _list(item.get("required_evidence")))
    for item in dedupe_strings(evidence):
        lines.append(f"- {item}")
    lines.append("- Final gate score is at least 0.85.")
    lines.append("- Central review decision becomes handoff or reports only accepted blockers.")
    lines.append("")
    return "\n".join(lines)


def repair_signature(source_run_id: str, items: list[dict[str, Any]]) -> str:
    payload = {
        "source_run_id": source_run_id,
        "items": [
            {
                "source": item.get("source", ""),
                "summary": item.get("summary", ""),
                "target_agent": item.get("target_agent", ""),
                "required_evidence": item.get("required_evidence", []),
            }
            for item in sorted(items, key=lambda value: str(value.get("summary", "")))
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def duplicate_signature_count(reports: list[dict[str, Any]], signature: str) -> int:
    count = 0
    for report in reports:
        plan = _dict(report.get("repair_plan"))
        if plan.get("repair_signature") == signature:
            count += 1
            continue
        metadata = _dict(report.get("metadata"))
        if metadata.get("repair_signature") == signature:
            count += 1
    return count


def count_started_iterations(reports: list[dict[str, Any]]) -> int:
    return sum(1 for report in reports if str(report.get("status", "")) == "started")


def guardrail_blockers(
    *,
    decision: str,
    central_status: str,
    items: list[dict[str, Any]],
    duplicate_count: int,
    current_iteration: int,
    max_iterations: int,
    max_duplicate_signature_count: int,
) -> list[str]:
    blockers: list[str] = []
    if decision != "iterate":
        if decision == "handoff":
            blockers.append("Central review is ready for handoff; no repair run is needed.")
        elif decision == "blocked" or central_status == "blocked":
            blockers.append("Central review is blocked and needs human help.")
        else:
            blockers.append("Central review is not asking for iteration.")
    if not items:
        blockers.append("No concrete repair item was generated.")
    if current_iteration >= max_iterations:
        blockers.append("Auto-iteration limit reached for this project.")
    if duplicate_count >= max_duplicate_signature_count:
        blockers.append("Duplicate repair plan already attempted.")
    return dedupe_strings(blockers)


def next_actions_for_report(*, status: str, repair_plan: dict[str, Any]) -> list[str]:
    if status == "started":
        return ["Monitor the repair run.", "Review recovery comparison after completion."]
    if status == "handoff":
        return ["Open the result and inspect it manually."]
    blockers = _list(_dict(repair_plan.get("guardrails")).get("blockers"))
    if status == "blocked":
        return [str(item) for item in blockers] or ["Resolve the blocker, then retry."]
    if bool(_dict(repair_plan.get("auto_execution")).get("allowed")):
        return ["Start auto-iteration to continue optimizing."]
    return ["Review repair plan details."]


def requirement_target_files_by_id(coverage: dict[str, Any]) -> dict[str, list[str]]:
    targets: dict[str, list[str]] = {}
    for req in _list(_dict(coverage.get("requirement_map")).get("requirements")):
        if not isinstance(req, dict):
            continue
        for key in (
            str(req.get("id", "") or ""),
            str(req.get("requirement_id", "") or ""),
            str(req.get("title", "") or ""),
        ):
            if key:
                targets[key] = target_files_for_requirement(req)
    return targets


def target_files_for_requirement(requirement: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("related_files", "implementation_files", "files", "target_files"):
        values.extend(str(item) for item in _list(requirement.get(key)))
    values.extend(target_files_from_text(str(requirement.get("summary", "") or "")))
    values.extend(target_files_from_text(str(requirement.get("description", "") or "")))
    values.extend(target_files_from_text(str(requirement.get("text", "") or "")))
    return dedupe_strings(values)


def target_files_from_text(text: str) -> list[str]:
    return dedupe_strings([match.group("path") for match in PATH_PATTERN.finditer(str(text or ""))])


def repair_summary(*, decision: str, items: list[dict[str, Any]], blockers: list[str]) -> str:
    if decision == "handoff":
        return "Central review says the result is ready for handoff."
    if blockers:
        return "Automatic repair is blocked: " + blockers[0]
    if not items:
        return "No concrete repair item was generated."
    must_count = sum(1 for item in items if item.get("priority") == "must")
    return f"Repair {len(items)} evidence gap(s), including {must_count} must-fix item(s)."


def dedupe_repair_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = (str(item.get("source", "")), str(item.get("summary", "")))
        if key in seen:
            continue
        seen.add(key)
        copied = dict(item)
        copied["id"] = f"repair_{len(result) + 1:03d}"
        result.append(copied)
    return result


def dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def infer_agent_for_text(text: str) -> str:
    lower = text.lower()
    if any(token in lower for token in ("ui", "frontend", "browser", "page", "screen", "canvas", "game", "css")):
        return "frontend"
    if any(token in lower for token in ("api", "server", "database", "backend", "auth", "endpoint")):
        return "backend"
    if any(token in lower for token in ("test", "ci", "probe", "verify")):
        return "test"
    return "debug"


def agent_for_loop_step(step: str) -> str:
    lower = step.lower()
    if any(token in lower for token in ("test", "probe", "verification", "testing")):
        return "test"
    if any(token in lower for token in ("review", "handoff", "audit")):
        return "reviewer"
    if any(token in lower for token in ("plan", "document", "brain")):
        return "architect"
    return "debug"


def agent_for_score_dimension(dimension: str) -> str:
    lower = dimension.lower()
    if "test" in lower:
        return "test"
    if "review" in lower or "risk" in lower:
        return "reviewer"
    if "graph" in lower or "spec" in lower:
        return "architect"
    return "debug"


def _blockers(run: dict[str, Any], delivery_report: dict[str, Any]) -> list[Any]:
    runtime_state = _dict(run.get("runtime_state"))
    blockers: list[Any] = []
    blockers.extend(_list(run.get("blockers")))
    blockers.extend(_list(runtime_state.get("blockers")))
    blockers.extend(_list(delivery_report.get("blockers")))
    return blockers


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("summary") or value.get("message") or value.get("description") or value.get("id") or "")
    return str(value or "")


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
