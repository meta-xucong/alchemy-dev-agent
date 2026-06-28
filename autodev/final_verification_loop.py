"""Final audit and test convergence for full-roadmap execution."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .roadmap_models import PhaseExecutionRecord, RoadmapExecutionPlan


AUDIT_DIMENSIONS = [
    ("roadmap_completion", "Did every required roadmap phase finish?"),
    ("phase_gate_quality", "Did every phase pass its promotion gate?"),
    ("blocker_cleanliness", "Are blockers, hard failures, and required changes empty?"),
    ("requirement_traceability", "Can requirements be traced to implementation or evidence?"),
    ("scope_boundary", "Did implementation stay inside allowed/protected boundaries?"),
    ("known_audit_findings", "Were known suspicious findings challenged and resolved?"),
    ("adversarial_review", "Did the system challenge the result before final handoff?"),
]

TEST_STAGES = [
    ("deterministic_tests", "Were deterministic tests or equivalent gate scores recorded?"),
    ("simulation_tests", "Were simulation, scenario, browser, static, or golden-case probes considered?"),
    ("real_tests", "Were real-environment checks run when the run used real workers or GitHub?"),
]

FINAL_WORKER_STATUS_MARKERS = {
    "final_audit_status": "FINAL_AUDIT_STATUS",
    "simulation_test_status": "SIMULATION_TEST_STATUS",
    "real_test_status": "REAL_TEST_STATUS",
}


@dataclass(slots=True)
class FinalVerificationReport:
    status: str
    ready_for_final_handoff: bool
    audit_status: str
    test_status: str
    dimensions: list[dict[str, object]] = field(default_factory=list)
    test_stages: list[dict[str, object]] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    required_actions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    worker_verification: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "ready_for_final_handoff": self.ready_for_final_handoff,
            "audit_status": self.audit_status,
            "test_status": self.test_status,
            "dimensions": [dict(item) for item in self.dimensions],
            "test_stages": [dict(item) for item in self.test_stages],
            "blockers": list(self.blockers),
            "required_actions": list(self.required_actions),
            "warnings": list(self.warnings),
            "worker_verification": dict(self.worker_verification),
        }


class FinalVerificationLoop:
    """Challenge a completed roadmap before final handoff."""

    def audit(
        self,
        plan: RoadmapExecutionPlan,
        phase_records: Sequence[PhaseExecutionRecord],
        *,
        worker_verification: dict[str, object] | None = None,
        run_payload: dict[str, Any] | None = None,
    ) -> FinalVerificationReport:
        worker_verification = dict(worker_verification or {})
        run_payload = dict(run_payload or {})
        dimensions = self._audit_dimensions(plan, phase_records, worker_verification, run_payload)
        test_stages = self._test_stages(phase_records, worker_verification, run_payload)
        blockers = [
            str(item.get("required_action", ""))
            for item in [*dimensions, *test_stages]
            if item.get("status") == "failed" and str(item.get("required_action", "")).strip()
        ]
        required_actions = [
            str(item.get("required_action", ""))
            for item in [*dimensions, *test_stages]
            if item.get("status") in {"failed", "warning"} and str(item.get("required_action", "")).strip()
        ]
        warnings = [
            str(item.get("summary", ""))
            for item in [*dimensions, *test_stages]
            if item.get("status") == "warning" and str(item.get("summary", "")).strip()
        ]
        audit_status = "passed" if not any(item.get("status") == "failed" for item in dimensions) else "iterate"
        test_status = "passed" if not any(item.get("status") == "failed" for item in test_stages) else "iterate"
        status = "passed" if audit_status == "passed" and test_status == "passed" else "iterate"
        return FinalVerificationReport(
            status=status,
            ready_for_final_handoff=status == "passed",
            audit_status=audit_status,
            test_status=test_status,
            dimensions=dimensions,
            test_stages=test_stages,
            blockers=[] if status == "passed" else blockers,
            required_actions=required_actions,
            warnings=warnings,
            worker_verification=worker_verification,
        )

    def _audit_dimensions(
        self,
        plan: RoadmapExecutionPlan,
        phase_records: Sequence[PhaseExecutionRecord],
        worker_verification: dict[str, object],
        run_payload: dict[str, Any],
    ) -> list[dict[str, object]]:
        records_by_phase = {record.phase_id: record for record in phase_records}
        required_phases = [phase for phase in plan.phases if not phase.optional]
        incomplete = [phase.phase_id for phase in required_phases if phase.status not in {"completed", "skipped"}]
        missing_records = [phase.phase_id for phase in required_phases if phase.phase_id not in records_by_phase]
        failed_records = [record.phase_id for record in phase_records if record.status not in {"done", "completed"}]
        low_scores = low_score_phase_ids(phase_records)
        hard_failures = hard_failure_summaries(phase_records)
        traceability_warnings = traceability_gaps(plan, phase_records)
        boundary_warnings = boundary_evidence_gaps(phase_records)
        worker_status = str(worker_verification.get("status", "") or "")
        marker_statuses = final_worker_marker_statuses(worker_verification)
        strict_worker_evidence = strict_final_verification_required(run_payload)
        worker_required_actions = [
            str(item) for item in _list(worker_verification.get("required_actions")) if str(item).strip()
        ]
        worker_blockers = [str(item) for item in _list(worker_verification.get("blockers")) if str(item).strip()]
        known_findings = [str(item) for item in _list(run_payload.get("known_final_audit_findings")) if str(item).strip()]
        dimensions: list[dict[str, object]] = []
        dimensions.append(
            dimension(
                "roadmap_completion",
                "failed" if incomplete or missing_records or failed_records else "passed",
                evidence=[
                    f"required_phases={len(required_phases)}",
                    f"phase_records={len(phase_records)}",
                    f"incomplete={','.join(incomplete) or 'none'}",
                    f"missing_records={','.join(missing_records) or 'none'}",
                    f"failed_records={','.join(failed_records) or 'none'}",
                ],
                required_action="Complete every required phase and persist a done phase record.",
            )
        )
        dimensions.append(
            dimension(
                "phase_gate_quality",
                "failed" if low_scores else "passed",
                evidence=[f"low_score_phases={','.join(low_scores) or 'none'}"],
                required_action="Repair phases whose promotion or final gate score is below the required threshold.",
            )
        )
        dimensions.append(
            dimension(
                "blocker_cleanliness",
                "failed" if hard_failures else "passed",
                evidence=hard_failures or ["No blockers, hard failures, or required changes were found in phase evidence."],
                required_action="Resolve blockers, hard failures, and required changes before final handoff.",
            )
        )
        dimensions.append(
            dimension(
                "requirement_traceability",
                "warning" if traceability_warnings else "passed",
                evidence=traceability_warnings or ["Phase requirements have corresponding phase records."],
                required_action="Add explicit requirement coverage or reviewer evidence for weakly traced phases.",
            )
        )
        dimensions.append(
            dimension(
                "scope_boundary",
                "warning" if boundary_warnings else "passed",
                evidence=boundary_warnings or ["No scope-boundary failures were reported by phase evidence."],
                required_action="Record boundary audit evidence, especially for protected legacy paths.",
            )
        )
        known_status = "passed"
        known_action = ""
        known_evidence = ["No known suspicious findings were supplied."]
        if known_findings:
            known_evidence = known_findings
            if not worker_verification or worker_status not in {"passed", "done"}:
                known_status = "failed"
                known_action = "Resolve supplied suspicious findings and add regression evidence before final handoff."
            else:
                known_evidence = [*known_findings, f"worker_status={worker_status}"]
        dimensions.append(
            dimension(
                "known_audit_findings",
                known_status,
                evidence=known_evidence,
                required_action=known_action,
            )
        )
        adversarial_status = "passed"
        adversarial_evidence = ["Evidence-only final verification completed."]
        adversarial_action = ""
        if worker_verification:
            if worker_status not in {"passed", "done"} or worker_required_actions or worker_blockers:
                adversarial_status = "failed"
                adversarial_action = "Apply the final adversarial review findings and rerun final verification."
            adversarial_evidence = [
                f"worker_status={worker_status or 'unknown'}",
                *marker_status_evidence(marker_statuses),
                *worker_required_actions,
                *worker_blockers,
            ]
            if strict_worker_evidence:
                marker_failures = failed_or_missing_worker_markers(marker_statuses, ["final_audit_status"])
                if marker_failures:
                    adversarial_status = "failed"
                    adversarial_action = (
                        "Final verification worker must report FINAL_AUDIT_STATUS: PASS with evidence before handoff."
                    )
                    adversarial_evidence.extend(marker_failures)
        elif strict_worker_evidence:
            adversarial_status = "failed"
            adversarial_evidence = ["Strict final verification requires a final worker report."]
            adversarial_action = "Run the final full-system audit worker before handoff."
        dimensions.append(
            dimension(
                "adversarial_review",
                adversarial_status,
                evidence=adversarial_evidence,
                required_action=adversarial_action,
            )
        )
        return dimensions

    def _test_stages(
        self,
        phase_records: Sequence[PhaseExecutionRecord],
        worker_verification: dict[str, object],
        run_payload: dict[str, Any],
    ) -> list[dict[str, object]]:
        evidence_text = "\n".join(json.dumps(record.to_dict(), ensure_ascii=False) for record in phase_records)
        worker_text = json.dumps(worker_verification, ensure_ascii=False)
        combined = f"{evidence_text}\n{worker_text}".lower()
        strict_worker_evidence = strict_final_verification_required(run_payload)
        marker_statuses = final_worker_marker_statuses(worker_verification)
        deterministic = "passed" if deterministic_test_evidence_present(phase_records) else ("failed" if strict_worker_evidence else "warning")
        simulation_marker = marker_statuses.get("simulation_test_status", "")
        real_marker = marker_statuses.get("real_test_status", "")
        simulation = explicit_or_evidence_status(
            simulation_marker,
            evidence_present=any(token in combined for token in ["scenario", "browser", "static", "golden", "simulation"]),
            strict=strict_worker_evidence,
        )
        expects_real = bool(run_payload.get("real_codex") or run_payload.get("real_github"))
        real = explicit_or_evidence_status(
            real_marker,
            evidence_present=not expects_real
            or any(token in combined for token in ["real_codex", "real worker", "real-github", "github", "legacy"]),
            strict=strict_worker_evidence and expects_real,
        )
        return [
            test_stage(
                "deterministic_tests",
                deterministic,
                evidence="Deterministic phase gate or test evidence found." if deterministic == "passed" else "No explicit deterministic test evidence found in phase records.",
                required_action="Run and record deterministic tests before final handoff.",
            ),
            test_stage(
                "simulation_tests",
                simulation,
                evidence=(
                    f"Final worker reported SIMULATION_TEST_STATUS={simulation_marker}."
                    if simulation_marker
                    else (
                        "Simulation/scenario/browser/static/golden evidence found."
                        if simulation == "passed"
                        else "No explicit simulation or scenario evidence found."
                    )
                ),
                required_action="Run scenario, browser, golden-case, or static simulation probes for user-facing behavior.",
            ),
            test_stage(
                "real_tests",
                real,
                evidence=(
                    f"Final worker reported REAL_TEST_STATUS={real_marker}."
                    if real_marker
                    else (
                        "Real-worker/GitHub/legacy evidence found or not required for this run."
                        if real == "passed"
                        else "Real execution was requested but no real-test evidence was found."
                    )
                ),
                required_action="Run real-environment tests or record a precise blocker/waiver.",
            ),
        ]


def worker_final_verification_enabled(run_payload: dict[str, Any]) -> bool:
    if "final_verification_worker" in run_payload:
        return bool(run_payload.get("final_verification_worker"))
    return bool(run_payload.get("real_codex") and run_payload.get("full_roadmap", True))


def strict_final_verification_required(run_payload: dict[str, Any]) -> bool:
    if "strict_final_verification" in run_payload:
        return bool(run_payload.get("strict_final_verification"))
    return worker_final_verification_enabled(run_payload)


def write_final_verification_document(
    path: Path,
    *,
    plan: RoadmapExecutionPlan,
    phase_records: Sequence[PhaseExecutionRecord],
    evidence_report: FinalVerificationReport,
) -> str:
    lines = [
        "# Final Full-System Audit And Testing",
        "",
        "You are the central brain performing the final challenge pass before user handoff.",
        "Do not treat prior green checks as sufficient. Act like a careful human operator after the code is complete.",
        "",
        "## Required Workflow",
        "",
        "1. Read the original development documents and generated implementation evidence.",
        "2. Challenge the result from multiple angles: requirements, architecture, runtime behavior, edge cases, UX, tests, safety, delivery, and regression risk.",
        "3. If an audit angle fails, repair the implementation or tests, then rerun the relevant verification.",
        "4. Only after all major audit angles pass, run broad simulation tests and real tests available in this repository.",
        "5. Report exact evidence. Do not hide warnings as success.",
        "",
        "## Root Objective",
        "",
        plan.root_objective,
        "",
        "## Audit Dimensions To Challenge",
        "",
    ]
    for dimension_id, question in AUDIT_DIMENSIONS:
        lines.append(f"- {dimension_id}: {question}")
    lines.extend(["", "## Test Stages To Run Or Justify", ""])
    for stage_id, question in TEST_STAGES:
        lines.append(f"- {stage_id}: {question}")
    lines.extend(["", "## Roadmap Phases", ""])
    for phase in plan.phases:
        lines.append(f"- {phase.phase_id} [{phase.status}] {phase.title}")
    lines.extend(["", "## Current Evidence-Only Final Verification", ""])
    lines.append("```json")
    lines.append(json.dumps(evidence_report.to_dict(), indent=2, sort_keys=True))
    lines.append("```")
    if evidence_report.to_dict().get("required_actions"):
        lines.extend(["", "## Required Actions From Evidence Audit", ""])
        for action in evidence_report.required_actions:
            lines.append(f"- {action}")
    known_dimension = next((item for item in evidence_report.dimensions if item.get("id") == "known_audit_findings"), {})
    known_evidence = [str(item) for item in known_dimension.get("evidence", [])] if isinstance(known_dimension, dict) else []
    if known_evidence and known_evidence != ["No known suspicious findings were supplied."]:
        lines.extend(["", "## Known Suspicious Findings To Resolve", ""])
        for finding in known_evidence:
            lines.append(f"- {finding}")
    lines.extend(["", "## Required Output", ""])
    lines.extend(
        [
            "Return structured evidence in your worker result:",
            "- FINAL_AUDIT_STATUS: PASS or FAIL",
            "- SIMULATION_TEST_STATUS: PASS or FAIL",
            "- REAL_TEST_STATUS: PASS or FAIL",
            "- REQUIRED_ACTIONS: empty if none",
            "- BLOCKERS: empty if none",
            "",
            "These exact status markers are machine-read by the parent roadmap executor.",
            "A high score without the explicit PASS markers is not enough for final handoff.",
            "",
            "If you find a defect, fix it within the repository scope and include the tests you ran.",
            "Do not only rerun existing tests. Derive fresh semantic probes from the source documents, especially",
            "for rules whose implementation could pass tests while still violating the product contract.",
            "Compare paired concepts such as requirement classification versus selected agent/module, source mode",
            "versus delivery action, protected scope versus changed files, and generated output versus user-facing",
            "acceptance examples.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path.resolve())


def dimension(dimension_id: str, status: str, *, evidence: list[str], required_action: str = "") -> dict[str, object]:
    question = dict(AUDIT_DIMENSIONS).get(dimension_id, dimension_id)
    return {
        "id": dimension_id,
        "question": question,
        "status": status,
        "summary": "; ".join(evidence[:3]),
        "evidence": list(evidence),
        "required_action": required_action if status in {"failed", "warning"} else "",
    }


def test_stage(stage_id: str, status: str, *, evidence: str, required_action: str = "") -> dict[str, object]:
    question = dict(TEST_STAGES).get(stage_id, stage_id)
    return {
        "id": stage_id,
        "question": question,
        "status": status,
        "summary": evidence,
        "evidence": [evidence],
        "required_action": required_action if status in {"failed", "warning"} else "",
    }


def low_score_phase_ids(phase_records: Sequence[PhaseExecutionRecord]) -> list[str]:
    low: list[str] = []
    for record in phase_records:
        promotion = record.promotion
        score = float_or_zero(promotion.get("score"))
        required = float_or_zero(promotion.get("required_score", 0.85)) or 0.85
        can_promote = bool(promotion.get("can_promote", record.status in {"done", "completed"}))
        if (score and score < required) or not can_promote:
            low.append(record.phase_id)
    return low


def hard_failure_summaries(phase_records: Sequence[PhaseExecutionRecord]) -> list[str]:
    failures: list[str] = []
    for record in phase_records:
        payload = record.result
        delivery = _dict(payload.get("delivery_report"))
        gate = _dict(delivery.get("final_gate"))
        runtime = _dict(payload.get("runtime_state"))
        evaluation = _dict(runtime.get("evaluation"))
        promoted = phase_record_cleanly_promoted(record)
        for key in ("blockers", "hard_failures", "required_changes"):
            current_items = [*_list(payload.get(key)), *_list(runtime.get(key))]
            stale_gate_items = [] if promoted else [*_list(gate.get(key)), *_list(evaluation.get(key))]
            for item in [*current_items, *stale_gate_items]:
                text = str(item).strip()
                if text:
                    failures.append(f"{record.phase_id}: {text}")
    return dedupe(failures)


def phase_record_cleanly_promoted(record: PhaseExecutionRecord) -> bool:
    promotion = record.promotion
    score = float_or_zero(promotion.get("score"))
    required = float_or_zero(promotion.get("required_score", 0.85)) or 0.85
    can_promote = bool(promotion.get("can_promote", False))
    reasons = [str(item).strip() for item in _list(promotion.get("reasons")) if str(item).strip()]
    return (
        record.status in {"done", "completed"}
        and can_promote
        and not reasons
        and (not score or score >= required)
    )


def traceability_gaps(plan: RoadmapExecutionPlan, phase_records: Sequence[PhaseExecutionRecord]) -> list[str]:
    records_by_phase = {record.phase_id: record for record in phase_records}
    gaps: list[str] = []
    for phase in plan.phases:
        if phase.optional:
            continue
        record = records_by_phase.get(phase.phase_id)
        if not record:
            continue
        payload = json.dumps(record.result, ensure_ascii=False).lower()
        if phase.requirements and not any(token in payload for token in ["requirement_coverage", "coverage", "review", "evidence"]):
            gaps.append(f"{phase.phase_id}: requirement coverage evidence is implicit rather than explicit.")
    return gaps


def boundary_evidence_gaps(phase_records: Sequence[PhaseExecutionRecord]) -> list[str]:
    gaps: list[str] = []
    for record in phase_records:
        payload = json.dumps(record.result, ensure_ascii=False).lower()
        if "boundary" not in payload and "scope" not in payload and "protected" not in payload:
            gaps.append(f"{record.phase_id}: no explicit scope/boundary evidence found.")
        if scope_violation_mentioned(payload):
            gaps.append(f"{record.phase_id}: possible scope violation mentioned in evidence.")
    return gaps


def scope_violation_mentioned(payload: str) -> bool:
    if "scope violation" in payload or "protected path violation" in payload:
        return True
    for match in re.finditer(r"\bout[- ]of[- ]scope\b", payload):
        snippet = payload[max(0, match.start() - 50) : match.end() + 80]
        if re.search(r"\b(no|without|avoid|prevent|convert|converted|turn)\b.{0,45}\bout[- ]of[- ]scope\b", snippet):
            continue
        if re.search(
            r"\bout[- ]of[- ]scope\b.{0,70}\b(change|changes|edit|edits|modification|write|writes|path|file|files|violation|touch|touched)\b",
            snippet,
        ):
            return True
    return False


def deterministic_test_evidence_present(phase_records: Sequence[PhaseExecutionRecord]) -> bool:
    for record in phase_records:
        payload = json.dumps(record.result, ensure_ascii=False).lower()
        if any(token in payload for token in ["tests_passed", "test_health", "pytest", "unittest", "npm test", "passed"]):
            return True
    return False


def final_worker_marker_statuses(worker_verification: dict[str, object]) -> dict[str, str]:
    if not worker_verification:
        return {}
    text = json.dumps(worker_verification, ensure_ascii=False)
    statuses: dict[str, str] = {}
    for marker_id, marker_label in FINAL_WORKER_STATUS_MARKERS.items():
        direct = _find_status_value(worker_verification, marker_id)
        if direct:
            statuses[marker_id] = normalize_marker_status(direct)
            continue
        label = re.escape(marker_label).replace("_", r"[_\s-]?")
        pattern = rf"['\"]?{label}['\"]?\s*[:=]\s*['\"]?(pass|passed|fail|failed|block|blocked)"
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            statuses[marker_id] = normalize_marker_status(match.group(1))
    return statuses


def explicit_or_evidence_status(marker_status: str, *, evidence_present: bool, strict: bool) -> str:
    if marker_status == "passed":
        return "passed"
    if marker_status in {"failed", "blocked"}:
        return "failed"
    if evidence_present:
        return "passed"
    return "failed" if strict else "warning"


def failed_or_missing_worker_markers(marker_statuses: dict[str, str], required_marker_ids: Sequence[str]) -> list[str]:
    failures: list[str] = []
    for marker_id in required_marker_ids:
        status = marker_statuses.get(marker_id, "")
        label = FINAL_WORKER_STATUS_MARKERS.get(marker_id, marker_id)
        if not status:
            failures.append(f"{label} is missing.")
        elif status != "passed":
            failures.append(f"{label} is {status}.")
    return failures


def marker_status_evidence(marker_statuses: dict[str, str]) -> list[str]:
    evidence: list[str] = []
    for marker_id, label in FINAL_WORKER_STATUS_MARKERS.items():
        status = marker_statuses.get(marker_id, "missing")
        evidence.append(f"{label}={status}")
    return evidence


def normalize_marker_status(value: object) -> str:
    text = str(value).strip().lower()
    if text in {"pass", "passed", "ok", "success", "successful"}:
        return "passed"
    if text in {"block", "blocked"}:
        return "blocked"
    if text in {"fail", "failed", "failure"}:
        return "failed"
    return text


def _find_status_value(payload: object, key: str) -> object:
    if isinstance(payload, dict):
        for item_key, item_value in payload.items():
            normalized_key = re.sub(r"[^a-z0-9]+", "_", str(item_key).strip().lower()).strip("_")
            if normalized_key == key:
                return item_value
            nested = _find_status_value(item_value, key)
            if nested:
                return nested
    if isinstance(payload, list):
        for item in payload:
            nested = _find_status_value(item, key)
            if nested:
                return nested
    return ""


def float_or_zero(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []
