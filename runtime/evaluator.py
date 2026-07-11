"""Runtime evaluation gate."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .models import RuntimeState, TaskNode, utc_now_iso

SPEC_ALIGNMENT_EVIDENCE_TYPES = {
    "worker_result",
    "focused_repair_preserved_task",
    "focused_repair_preserved_coverage",
    "ci_result",
}


@dataclass(slots=True)
class EvaluationResult:
    done: bool
    final_gate_score: float
    dimension_scores: dict[str, float]
    reviewer_decision: str
    hard_failures: list[str] = field(default_factory=list)
    required_changes: list[str] = field(default_factory=list)
    evidence_summary: list[str] = field(default_factory=list)
    reason: str = ""

    @property
    def final_score(self) -> float:
        return self.final_gate_score

    @property
    def test_pass_rate(self) -> float:
        return self.dimension_scores.get("test_health", 0.0)

    @property
    def spec_alignment(self) -> float:
        return self.dimension_scores.get("spec_alignment", 0.0)

    @property
    def reviewer_score(self) -> float:
        return self.dimension_scores.get("reviewer_approval", 0.0)

    def to_dict(self) -> dict:
        status = "passed" if self.done else "failed" if self.hard_failures else "in_progress"
        return {
            "status": status,
            "done": self.done,
            "final_gate_score": self.final_gate_score,
            "final_score": self.final_gate_score,
            "dimension_scores": dict(self.dimension_scores),
            "test_pass_rate": self.test_pass_rate,
            "spec_alignment": self.spec_alignment,
            "reviewer_score": self.reviewer_score,
            "reviewer_decision": self.reviewer_decision,
            "hard_failures": list(self.hard_failures),
            "required_changes": list(self.required_changes),
            "evidence_summary": list(self.evidence_summary),
            "reason": self.reason,
            "last_evaluated_at": utc_now_iso(),
        }


class Evaluator:
    """Compute DONE using the documented weighted final gate."""

    done_threshold = 0.85
    weights = {
        "test_health": 0.25,
        "spec_alignment": 0.30,
        "graph_completion": 0.20,
        "reviewer_approval": 0.15,
        "risk_quality": 0.10,
    }

    def evaluate(self, state: RuntimeState) -> EvaluationResult:
        nodes = state.task_graph.nodes
        if not nodes:
            return EvaluationResult(
                done=False,
                final_gate_score=0.0,
                dimension_scores={name: 0.0 for name in self.weights},
                reviewer_decision="not_reviewed",
                hard_failures=["No task graph nodes exist."],
                reason="No task graph nodes exist.",
            )

        hard_failures: list[str] = []
        required_changes: list[str] = []
        evidence_summary: list[str] = []

        test_health = self._test_health(nodes)
        spec_alignment = self._spec_alignment(nodes)
        coverage_score = self._requirement_coverage_score(state)
        if coverage_score is not None:
            spec_alignment = min(spec_alignment, coverage_score)
        graph_completion = self._graph_completion(nodes)
        reviewer_decision = self._reviewer_decision(nodes)
        reviewer_approval = 1.0 if reviewer_decision == "approved" else 0.0
        risk_quality = self._risk_quality(nodes, state)

        if any(node.status in {"failed", "blocked"} for node in nodes):
            hard_failures.append("One or more required tasks failed or are blocked.")
        unfinished = [node.id for node in nodes if node.status not in {"completed", "skipped"}]
        if unfinished:
            hard_failures.append(f"Required tasks are unfinished: {', '.join(unfinished)}.")
        if self._has_failed_tests(nodes):
            hard_failures.append("Required tests are failing.")
        if reviewer_decision != "approved":
            hard_failures.append("Reviewer approval is not recorded.")
        if not state.github.get("commit") and not state.github.get("pull_request_url"):
            hard_failures.append("GitHub execution evidence is not recorded.")
        if state.blockers:
            hard_failures.append("Unresolved blockers exist.")
        coverage = state.repository.get("requirement_coverage", {})
        if isinstance(coverage, dict):
            missing_must = [str(item) for item in coverage.get("missing_must_requirement_ids", [])]
            partial_must = [str(item) for item in coverage.get("partial_must_requirement_ids", [])]
            if missing_must:
                hard_failures.append("Must requirements are missing coverage: " + ", ".join(missing_must) + ".")
            if partial_must:
                hard_failures.append("Must requirements have only partial coverage: " + ", ".join(partial_must) + ".")
        verification_matrix = state.repository.get("verification_matrix", {})
        if isinstance(verification_matrix, dict):
            hard_failures.extend(_verification_matrix_hard_failures(verification_matrix))
        artifact_report = state.repository.get("artifact_report", {})
        if isinstance(artifact_report, dict):
            hard_failures.extend(_artifact_hard_failures(artifact_report))
        hard_failures.extend(_final_gate_marker_hard_failures(nodes))

        for node in nodes:
            if node.status == "completed":
                evidence_summary.append(f"{node.id} completed with {len(node.evidence)} evidence record(s).")
            if node.status in {"failed", "blocked"}:
                required_changes.append(f"{node.id}: resolve {node.status} task.")

        dimension_scores = {
            "test_health": round(test_health, 4),
            "spec_alignment": round(spec_alignment, 4),
            "graph_completion": round(graph_completion, 4),
            "reviewer_approval": round(reviewer_approval, 4),
            "risk_quality": round(risk_quality, 4),
        }
        final_gate_score = round(
            sum(dimension_scores[name] * weight for name, weight in self.weights.items()),
            4,
        )
        done = final_gate_score >= self.done_threshold and not hard_failures

        if done:
            reason = "DONE condition met."
        elif hard_failures:
            reason = hard_failures[0]
        else:
            reason = f"Final gate score {final_gate_score:.2f} is below {self.done_threshold:.2f}."

        return EvaluationResult(
            done=done,
            final_gate_score=final_gate_score,
            dimension_scores=dimension_scores,
            reviewer_decision=reviewer_decision,
            hard_failures=hard_failures,
            required_changes=required_changes,
            evidence_summary=evidence_summary,
            reason=reason,
        )

    def _test_health(self, nodes: list[TaskNode]) -> float:
        test_nodes = [node for node in nodes if node.type == "test"]
        if test_nodes:
            return self._ratio_with_passing_worker_results(test_nodes)
        return self._ratio_with_passing_worker_results(nodes)

    def _spec_alignment(self, nodes: list[TaskNode]) -> float:
        completed = [node for node in nodes if node.status in {"completed", "skipped"}]
        with_criteria = [
            node
            for node in completed
            if node.completion_criteria
            and any(str(item.get("type", "")) in SPEC_ALIGNMENT_EVIDENCE_TYPES for item in node.evidence)
        ]
        return len(with_criteria) / len(nodes)

    def _graph_completion(self, nodes: list[TaskNode]) -> float:
        return len([node for node in nodes if node.status in {"completed", "skipped"}]) / len(nodes)

    def _reviewer_decision(self, nodes: list[TaskNode]) -> str:
        review_nodes = [node for node in nodes if node.type == "review"]
        if not review_nodes:
            return "not_reviewed"
        if all(node.status == "completed" for node in review_nodes):
            return "approved"
        if any(node.status == "failed" for node in review_nodes):
            return "changes_requested"
        if any(node.status == "blocked" for node in review_nodes):
            return "rejected"
        return "not_reviewed"

    def _risk_quality(self, nodes: list[TaskNode], state: RuntimeState) -> float:
        if state.blockers:
            return 0.0
        failed_or_blocked = [node for node in nodes if node.status in {"failed", "blocked"}]
        if failed_or_blocked:
            return 0.0
        issues = 0
        for node in nodes:
            if node.type in {"architecture", "documentation", "release"} and node.status == "completed":
                continue
            for evidence in node.evidence:
                result = evidence.get("result", {})
                if not isinstance(result, dict):
                    continue
                status = str(result.get("status", ""))
                if status in {"failed", "blocked"}:
                    issues += len(result.get("known_issues", []))
                    continue
                issues += sum(
                    1
                    for issue in result.get("known_issues", [])
                    if _is_risk_relevant_known_issue(str(issue))
                )
        if issues == 0:
            return 1.0
        return max(0.0, 1.0 - issues * 0.2)

    def _requirement_coverage_score(self, state: RuntimeState) -> float | None:
        coverage = state.repository.get("requirement_coverage", {})
        if not isinstance(coverage, dict):
            return None
        score = coverage.get("coverage_score")
        if score is None:
            return None
        try:
            return max(0.0, min(1.0, float(score)))
        except (TypeError, ValueError):
            return None

    def _ratio_with_passing_worker_results(self, nodes: list[TaskNode]) -> float:
        if not nodes:
            return 0.0
        passing = 0
        for node in nodes:
            if node.status not in {"completed", "skipped"}:
                continue
            if not self._node_has_failed_worker_result(node):
                passing += 1
        return passing / len(nodes)

    def _has_failed_tests(self, nodes: list[TaskNode]) -> bool:
        for node in nodes:
            if self._node_has_failed_worker_result(node):
                return True
        return False

    def _node_has_failed_worker_result(self, node: TaskNode) -> bool:
        if node.type in {"debug", "release"} and node.status == "completed":
            return False
        latest_result = self._latest_worker_result(node)
        if latest_result is None:
            return False
        status = latest_result.get("status")
        tests_failed = latest_result.get("tests_failed", [])
        return bool(status in {"failed", "blocked"} or tests_failed)

    def _latest_worker_result(self, node: TaskNode) -> dict | None:
        for evidence in reversed(node.evidence):
            result = evidence.get("result", {})
            if isinstance(result, dict):
                return result
        return None


def _artifact_hard_failures(artifact_report: dict) -> list[str]:
    failures: list[str] = []
    static = artifact_report.get("static_verification", {})
    browser = artifact_report.get("browser_verification", {})
    profile = artifact_report.get("artifact_profile", {})
    profile_name = str(profile.get("name", "")) if isinstance(profile, dict) else ""
    if profile_name in {"canvas_game", "static_web_app"} and isinstance(static, dict) and static.get("status") == "failed":
        failures.append("Static artifact verification failed.")
    if not isinstance(browser, dict) or not browser:
        return failures
    if browser.get("status") == "failed":
        failures.append("Browser artifact verification failed.")
    semantic = browser.get("semantic_probe", {})
    if isinstance(semantic, dict) and semantic.get("status") == "failed":
        failures.append("Semantic browser probe failed.")
    scenario = browser.get("scenario_probe", {})
    if isinstance(scenario, dict) and scenario.get("status") == "failed":
        failures.append("Acceptance scenario browser probe failed.")
    gameplay = browser.get("gameplay_probe", {})
    gameplay_status = str(gameplay.get("status", "")) if isinstance(gameplay, dict) else ""
    if profile_name == "canvas_game" and gameplay_status != "completed":
        failures.append("Canvas gameplay probe did not complete.")
    elif gameplay_status == "failed":
        failures.append("Gameplay browser probe failed.")
    return failures


def _verification_matrix_hard_failures(matrix: dict) -> list[str]:
    failures: list[str] = []
    hard_failures = [str(item) for item in matrix.get("hard_failures", []) if str(item)]
    failures.extend(hard_failures)
    for item in matrix.get("items", []):
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "")).lower()
        requirement_id = str(item.get("requirement_id", "unknown"))
        obligation = str(item.get("obligation", "unknown"))
        if status in {"failed", "stale", "unproven", "blocked"}:
            failures.append(f"Verification matrix item {requirement_id}/{obligation} is {status}.")
    return failures


FINAL_GATE_STATUS_MARKERS = {
    "audit final requirements": "FINAL_AUDIT_STATUS",
    "run final simulation probes": "SIMULATION_TEST_STATUS",
    "run final real repository checks": "REAL_TEST_STATUS",
}


def _final_gate_marker_hard_failures(nodes: list[TaskNode]) -> list[str]:
    failures: list[str] = []
    for node in nodes:
        marker = _final_gate_marker_for_node(node)
        if not marker:
            continue
        status = _latest_final_gate_marker_status(node, marker)
        if status in {"failed", "blocked"}:
            failures.append(f"{marker} is {status}.")
    return failures


def _final_gate_marker_for_node(node: TaskNode) -> str:
    title = node.title.lower()
    for title_marker, status_marker in FINAL_GATE_STATUS_MARKERS.items():
        if title_marker in title:
            return status_marker
    return ""


def _latest_final_gate_marker_status(node: TaskNode, marker: str) -> str:
    if not node.evidence:
        return ""
    latest = node.evidence[-1]
    result = latest.get("result", latest) if isinstance(latest, dict) else latest
    text = json.dumps(result, ensure_ascii=False)
    label = re.escape(marker).replace("_", r"[_\s-]?")
    pattern = rf"['\"]?{label}['\"]?\s*[:=]\s*['\"]?(pass|passed|fail|failed|block|blocked)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return ""
    return _normalize_final_gate_marker_status(match.group(1))


def _normalize_final_gate_marker_status(value: object) -> str:
    text = str(value).strip().lower()
    if text in {"pass", "passed", "ok", "success", "successful"}:
        return "passed"
    if text in {"block", "blocked"}:
        return "blocked"
    if text in {"fail", "failed", "failure"}:
        return "failed"
    return text


def _is_risk_relevant_known_issue(issue: str) -> bool:
    lowered = issue.lower()
    benign_markers = (
        "allowed_files is empty",
        "implementation directory does not appear to exist yet",
        "branch names differ",
        "root legacy test command",
        "authoritative verification",
        "runtime data",
        "pytest emitted",
        "cache",
        "permissionerror",
        "winerror 5",
        "compileall",
        "non-required",
        "tests still passed",
        "required verification command",
        "later roadmap phase",
        "later phases",
        "later implementation",
        "later roadmap phases",
        "后续阶段",
        "后续开发",
        "后续实现",
        "later-phase",
        "explicitly out of scope for phase",
        "out of scope for phase",
        "out of scope for this phase",
        "non-blocking",
        "not a requested verification command",
        "telemetry",
        "upload-token",
        "upload.token",
        "go cache",
        "go telemetry",
        "workspace-local",
        "host go cache",
        "scratch artifacts",
        ".go.",
        "did not affect",
        "documentation intentionally",
        "active git branch",
        "not the task package branch",
        "worktree is already very dirty",
        "pre-existing changes",
        "temporary copy",
        "empty allowed_files/no-repository-edits",
        "non-fatal",
        "vue-i18n",
        "vite dynamic",
        "eslint --fix",
    )
    return not any(marker in lowered for marker in benign_markers)
