"""Machine-checkable development-cycle report for autonomous runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CycleStep:
    name: str
    status: str
    evidence: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "evidence": list(self.evidence),
            "gaps": list(self.gaps),
        }


@dataclass(slots=True)
class DevelopmentCycleReport:
    status: str
    score: float
    steps: list[CycleStep]
    next_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "score": self.score,
            "steps": [step.to_dict() for step in self.steps],
            "next_actions": list(self.next_actions),
        }


def build_development_cycle_report(
    *,
    project_brief: dict[str, Any],
    context_bundle: dict[str, Any],
    task_graph: dict[str, Any],
    runtime_state: dict[str, Any],
    artifact_report: dict[str, Any],
    requirement_coverage: dict[str, Any],
    delivery_report: dict[str, Any],
) -> dict[str, object]:
    """Map the user's manual engineering loop into run-level evidence."""

    steps = [
        _step_long_task_state(runtime_state),
        _step_read_documents(project_brief, context_bundle),
        _step_brain_refinement(context_bundle, task_graph),
        _step_phase_planning(task_graph),
        _step_execution(runtime_state),
        _step_audit(runtime_state, requirement_coverage),
        _step_testing(runtime_state, artifact_report, delivery_report),
        _step_iteration(runtime_state),
        _step_full_review(runtime_state, delivery_report),
        _step_simulated_acceptance(runtime_state, delivery_report),
        _step_real_delivery(runtime_state, delivery_report),
        _step_merge(runtime_state),
    ]
    passed = sum(1 for step in steps if step.status in {"passed", "waived"})
    score = round(passed / len(steps), 4) if steps else 0.0
    blocking_gaps = [gap for step in steps if step.status == "missing" for gap in step.gaps]
    status = "passed" if score == 1.0 else "partial" if passed else "missing"
    return DevelopmentCycleReport(
        status=status,
        score=score,
        steps=steps,
        next_actions=blocking_gaps,
    ).to_dict()


def _step_long_task_state(runtime_state: dict[str, Any]) -> CycleStep:
    history = runtime_state.get("iteration_history", runtime_state.get("execution_history", []))
    if history:
        return CycleStep("long_task_state", "passed", [f"{len(history)} state/history event(s) recorded."])
    return CycleStep("long_task_state", "missing", gaps=["Persist iteration history before delivery."])


def _step_read_documents(project_brief: dict[str, Any], context_bundle: dict[str, Any]) -> CycleStep:
    documents = project_brief.get("documents", [])
    indexed = context_bundle.get("document_index", {}).get("documents", [])
    if documents and indexed:
        return CycleStep("read_documents", "passed", [f"{len(indexed)} document(s) indexed."])
    if project_brief.get("generated_from_one_liner"):
        return CycleStep("read_documents", "waived", ["One-line fallback run; no source document was supplied."])
    return CycleStep("read_documents", "missing", gaps=["No indexed development document evidence was found."])


def _step_brain_refinement(context_bundle: dict[str, Any], task_graph: dict[str, Any]) -> CycleStep:
    requirements = context_bundle.get("requirement_map", {}).get("requirements", [])
    nodes = task_graph.get("nodes", [])
    planned = [req for req in requirements if req.get("planned_task_ids")]
    if requirements and planned:
        return CycleStep(
            "brain_refinement",
            "passed",
            [f"{len(requirements)} requirement(s) normalized; {len(planned)} mapped to task graph nodes."],
        )
    if nodes:
        return CycleStep("brain_refinement", "partial", [f"{len(nodes)} task node(s) planned."], ["Requirement-to-task traceability is weak."])
    return CycleStep("brain_refinement", "missing", gaps=["No task graph refinement evidence was found."])


def _step_phase_planning(task_graph: dict[str, Any]) -> CycleStep:
    nodes = task_graph.get("nodes", [])
    types = {str(node.get("type", "")) for node in nodes}
    expected = {"architecture", "test", "review"}
    if nodes and expected <= types:
        return CycleStep("phase_planning", "passed", [f"{len(nodes)} task node(s) with architecture/test/review phases."])
    return CycleStep("phase_planning", "missing", gaps=["Task graph lacks required architecture, test, or review phase nodes."])


def _step_execution(runtime_state: dict[str, Any]) -> CycleStep:
    completed = runtime_state.get("completed_tasks", [])
    if completed:
        return CycleStep("execution", "passed", [f"{len(completed)} task(s) completed."])
    return CycleStep("execution", "missing", gaps=["No completed task evidence was found."])


def _step_audit(runtime_state: dict[str, Any], requirement_coverage: dict[str, Any]) -> CycleStep:
    review_nodes = [
        node
        for node in runtime_state.get("task_graph", {}).get("nodes", [])
        if node.get("type") == "review" and node.get("status") == "completed"
    ]
    coverage_status = str(requirement_coverage.get("status", ""))
    if review_nodes and coverage_status == "passed":
        return CycleStep("audit", "passed", ["Reviewer task completed and requirement coverage passed."])
    gaps: list[str] = []
    if not review_nodes:
        gaps.append("Reviewer approval evidence is missing.")
    if coverage_status != "passed":
        gaps.append("Requirement coverage did not pass.")
    return CycleStep("audit", "missing", gaps=gaps)


def _step_testing(runtime_state: dict[str, Any], artifact_report: dict[str, Any], delivery_report: dict[str, Any]) -> CycleStep:
    evaluation = runtime_state.get("evaluation", runtime_state.get("evaluation_result", {}))
    profile_name = str(artifact_report.get("artifact_profile", {}).get("name", ""))
    static_status = artifact_report.get("static_verification", {}).get("status", "")
    browser = artifact_report.get("browser_verification", {})
    browser_status = browser.get("status", "") if isinstance(browser, dict) else ""
    gameplay_probe = browser.get("gameplay_probe", {}) if isinstance(browser, dict) else {}
    gameplay_status = gameplay_probe.get("status", "") if isinstance(gameplay_probe, dict) else ""
    semantic_probe = browser.get("semantic_probe", {}) if isinstance(browser, dict) else {}
    semantic_status = semantic_probe.get("status", "") if isinstance(semantic_probe, dict) else ""
    scenario_probe = browser.get("scenario_probe", {}) if isinstance(browser, dict) else {}
    scenario_status = scenario_probe.get("status", "") if isinstance(scenario_probe, dict) else ""
    ci_status = delivery_report.get("github", {}).get("ci_status", runtime_state.get("github", {}).get("ci_status", ""))
    artifact_ok = static_status in {"passed", "completed", "skipped", ""}
    browser_ok = browser_status in {"completed", "passed", "skipped", ""}
    gameplay_ok = profile_name != "canvas_game" or gameplay_status == "completed"
    semantic_ok = semantic_status not in {"failed"}
    scenario_ok = scenario_status not in {"failed"}
    passed = evaluation.get("test_pass_rate", 0) and artifact_ok and browser_ok and gameplay_ok and semantic_ok and scenario_ok
    if passed and ci_status in {"passed", "waived", ""}:
        evidence = [f"test_pass_rate={evaluation.get('test_pass_rate')}", f"ci_status={ci_status or 'n/a'}"]
        if browser_status:
            evidence.append(f"browser_status={browser_status}")
        if gameplay_status:
            evidence.append(f"gameplay_status={gameplay_status}")
        if semantic_status and semantic_status != gameplay_status:
            evidence.append(f"semantic_status={semantic_status}")
        if scenario_status and scenario_status != "skipped":
            evidence.append(f"scenario_status={scenario_status}")
        return CycleStep("testing", "passed", evidence)
    gaps: list[str] = []
    if not evaluation.get("test_pass_rate", 0):
        gaps.append("Evaluator test health is zero or missing.")
    if static_status == "failed":
        gaps.append("Static artifact verification failed.")
    if browser_status == "failed":
        gaps.append("Browser artifact verification failed.")
    if profile_name == "canvas_game" and gameplay_status != "completed":
        gaps.append("Canvas gameplay probe did not complete.")
    if semantic_status == "failed":
        gaps.append("Semantic browser probe failed.")
    if scenario_status == "failed":
        gaps.append("Acceptance scenario browser probe failed.")
    if ci_status in {"failed", "pending", "unknown"}:
        gaps.append(f"GitHub CI status is {ci_status}.")
    return CycleStep("testing", "missing", gaps=gaps)


def _step_iteration(runtime_state: dict[str, Any]) -> CycleStep:
    history = runtime_state.get("iteration_history", runtime_state.get("execution_history", []))
    retries = [event for event in history if str(event.get("type", "")).startswith("debug") or "retry" in str(event.get("summary", "")).lower()]
    if retries:
        return CycleStep("iteration", "passed", [f"{len(retries)} debug/retry event(s) recorded."])
    failed = runtime_state.get("failed_tasks", [])
    blockers = runtime_state.get("blockers", [])
    if not failed and not blockers:
        return CycleStep("iteration", "waived", ["No retry was needed because the run completed cleanly."])
    return CycleStep("iteration", "missing", gaps=["Failures or blockers exist without successful retry/iteration evidence."])


def _step_full_review(runtime_state: dict[str, Any], delivery_report: dict[str, Any]) -> CycleStep:
    evaluation = runtime_state.get("evaluation", runtime_state.get("evaluation_result", {}))
    if delivery_report.get("ready_for_review") and evaluation.get("done"):
        return CycleStep("full_review", "passed", ["Final gate done and delivery is ready for review."])
    return CycleStep("full_review", "missing", gaps=["Final gate or delivery readiness did not pass."])


def _step_simulated_acceptance(runtime_state: dict[str, Any], delivery_report: dict[str, Any]) -> CycleStep:
    github = runtime_state.get("github", {})
    if str(github.get("pull_request_url", "")).startswith("dry-run://"):
        return CycleStep("simulated_acceptance", "passed", ["Dry-run GitHub evidence recorded."])
    if delivery_report.get("status") == "done":
        return CycleStep("simulated_acceptance", "waived", ["Real delivery run reached done; dry-run simulation is not required."])
    return CycleStep("simulated_acceptance", "missing", gaps=["No dry-run or completed real delivery evidence was found."])


def _step_real_delivery(runtime_state: dict[str, Any], delivery_report: dict[str, Any]) -> CycleStep:
    github = runtime_state.get("github", {})
    pr = str(github.get("pull_request_url", ""))
    if pr and not pr.startswith("dry-run://"):
        return CycleStep("real_delivery", "passed", [pr])
    if delivery_report.get("status") == "done":
        return CycleStep("real_delivery", "waived", ["Run completed in dry-run mode; real GitHub delivery was not requested."])
    return CycleStep("real_delivery", "missing", gaps=["No real pull request evidence was found."])


def _step_merge(runtime_state: dict[str, Any]) -> CycleStep:
    github = runtime_state.get("github", {})
    merge = github.get("merge", {})
    if isinstance(merge, dict) and merge.get("status") in {"merged", "auto_merge_enabled"}:
        return CycleStep("merge", "passed", [str(merge.get("summary", "Merge evidence recorded."))])
    if github.get("status") in {"recorded", "pushed"}:
        return CycleStep("merge", "waived", ["Merge was not requested for this run."])
    return CycleStep("merge", "missing", gaps=["Merge or explicit merge waiver evidence is missing."])
