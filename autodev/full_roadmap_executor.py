"""Full-roadmap execution loop built on top of existing document runs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Sequence

from runtime.evaluator import Evaluator
from runtime.models import RuntimeState
from runtime.worker_lifecycle import process_exists

from .document_reference_expander import expand_development_documents
from .document_run import DocumentRunPipeline
from .final_system_audit import FinalSystemAudit
from .final_verification_loop import (
    FinalVerificationLoop,
    worker_final_verification_enabled,
    write_final_verification_document,
)
from .generated_development_package import GeneratedDevelopmentPackage
from .phase_promotion import next_ready_phase, phase_promotion_decision
from .project_analysis_gate import ProjectAnalysisGate, write_project_analysis_report
from .roadmap_auditor import RoadmapAuditor
from .roadmap_extractor import RoadmapExtractor
from .roadmap_models import PhaseExecutionRecord, RoadmapExecutionPlan, RoadmapPhase


DocumentRunner = Callable[..., Any]

NON_REPAIRABLE_BLOCKER_MARKERS = (
    "credential",
    "missing api key",
    "api key required",
    "requires api key",
    "invalid api key",
    "provider api key",
    "auth required",
    "authentication required",
    "unauthenticated",
    "not logged in",
    "permission",
    "approval",
    "external",
    "you've hit your usage limit",
    "you have hit your usage limit",
    "usage limit reached",
    "purchase more credits",
    "local codex cli usage limit",
    "codex cli usage limit",
    "live worker process",
    "preflight",
    "recovery",
    "operator",
)

REPAIR_EVIDENCE_PATH_PATTERN = re.compile(
    r"(?P<path>[\w./-]+\.(?:vue|tsx|jsx|yaml|yml|py|js|ts|go|rs|java|cs|rb|php|html|css|sql|md|json))(?![\w/-])"
)
SUCCESSFUL_WORKER_STATUSES = {"completed", "done", "passed", "success", "successful", "ok"}
REPAIR_WORKER_STATUSES = {"failed", "partial", "blocked", "timed_out"}
WORKER_TIMEOUT_STOP_MARKERS = (
    "exceeded the codex worker timeout",
    "codex worker timeout",
    "worker timeout",
    "timed out after",
)


@dataclass(slots=True)
class FullRoadmapExecutionResult:
    status: str
    roadmap: dict[str, object]
    roadmap_audit: dict[str, object]
    project_analysis: dict[str, object] = field(default_factory=dict)
    document_expansion: dict[str, object] = field(default_factory=dict)
    phase_records: list[dict[str, object]] = field(default_factory=list)
    final_audit: dict[str, object] = field(default_factory=dict)
    final_verification_worker: dict[str, object] = field(default_factory=dict)
    generated_development_package: dict[str, object] = field(default_factory=dict)
    output_dir: str = ""
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "roadmap": self.roadmap,
            "roadmap_audit": self.roadmap_audit,
            "project_analysis": dict(self.project_analysis),
            "document_expansion": dict(self.document_expansion),
            "phase_records": list(self.phase_records),
            "final_audit": dict(self.final_audit),
            "final_verification_worker": dict(self.final_verification_worker),
            "generated_development_package": dict(self.generated_development_package),
            "output_dir": self.output_dir,
            "blockers": list(self.blockers),
        }


@dataclass(slots=True)
class InterruptedPhaseResume:
    resume_from: Path | None = None
    active_run_dir: Path | None = None
    blockers: list[str] = field(default_factory=list)


class FullRoadmapExecutor:
    """Execute every required roadmap phase without stopping at phase boundaries."""

    def __init__(self, document_runner: DocumentRunner | None = None) -> None:
        self.document_runner = document_runner or DocumentRunPipeline().run

    def run(
        self,
        *,
        objective: str,
        documents: Sequence[str | Path] = (),
        attachments: Sequence[str | Path] = (),
        primary_input_mode: str = "document_driven",
        repository_url: str = "",
        repository_path: str | Path | None = None,
        repository_visibility: str = "public",
        output_dir: str | Path = ".alchemy/full_roadmap_run",
        max_phases: int = 50,
        run_payload: dict[str, Any] | None = None,
    ) -> FullRoadmapExecutionResult:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        run_payload = dict(run_payload or {})
        max_phase_repair_attempts = max(0, int(run_payload.get("max_phase_repair_attempts", 2) or 0))
        generated_package: dict[str, object] = {}
        source_mode = source_mode_for(primary_input_mode, repository_url=repository_url, repository_path=repository_path)
        resume_state = load_resume_state(output)
        if resume_state:
            plan = resume_state.plan
            audit_payload = resume_state.roadmap_audit
            analysis_payload = resume_state.project_analysis
            document_expansion_payload = resume_state.document_expansion
            generated_package = resume_state.generated_development_package
            roadmap_documents = list(resume_state.documents or documents)
            phase_records = list(resume_state.phase_records)
            sync_plan_status_from_records(plan, phase_records)
            write_json(output / "roadmap_execution_plan.json", plan.to_dict())
            write_running_report(
                output / "full_roadmap_report.json",
                plan=plan,
                roadmap_audit=audit_payload,
                project_analysis=analysis_payload,
                document_expansion=document_expansion_payload,
                generated_development_package=generated_package,
                phase_records=phase_records,
                active_phase=None,
            )
        else:
            roadmap_documents = list(documents)
            if not roadmap_documents and primary_input_mode in {"one_line_fallback", "document_driven"}:
                package_dir = output / "generated_development_package"
                generated_package = GeneratedDevelopmentPackage().write(objective=objective, output_dir=package_dir)
                roadmap_documents = [
                    str(path)
                    for path in generated_package.get("documents", [])
                    if str(path).endswith((".md", ".txt", ".json", ".yaml", ".yml"))
                ]
                source_mode = "one_sentence"
            document_expansion = expand_development_documents(
                roadmap_documents,
                repository_path=repository_path,
            )
            if document_expansion.documents:
                roadmap_documents = list(document_expansion.documents)
            document_expansion_payload = document_expansion.to_dict()
            write_json(output / "expanded_document_index.json", document_expansion_payload)

            plan = RoadmapExtractor().extract(
                objective=objective,
                documents=roadmap_documents,
                attachments=attachments,
                source_mode=source_mode,
                delivery_policy={
                    "mode": "github_pr" if run_payload.get("real_github") else "local",
                    "requires_user_approval_for_merge": not bool(run_payload.get("auto_merge", False)),
                    "allow_public_repository": True,
                    "allow_destructive_actions": False,
                },
            )
            plan, audit = RoadmapAuditor().audit_and_repair(plan)
            audit_payload = audit.to_dict()
            write_json(output / "roadmap_execution_plan.json", plan.to_dict())
            write_json(output / "roadmap_audit.json", audit_payload)
            analysis_payload = {}
            phase_records = []
        if audit_payload.get("status") != "passed":
            result = FullRoadmapExecutionResult(
                status="blocked",
                roadmap=plan.to_dict(),
                roadmap_audit=audit_payload,
                project_analysis={},
                document_expansion=document_expansion_payload,
                generated_development_package=generated_package,
                output_dir=str(output),
                blockers=[str(item) for item in audit_payload.get("issues", [])],
            )
            write_json(output / "full_roadmap_report.json", result.to_dict())
            return result
        if not analysis_payload:
            analysis_report = ProjectAnalysisGate().analyze(
                plan=plan,
                documents=roadmap_documents,
                attachments=attachments,
            )
            analysis_payload = analysis_report.to_dict()
            write_project_analysis_report(output / "project_analysis_report.json", analysis_report)
        if not bool(analysis_payload.get("ready_to_start")):
            blockers = [
                *[str(item) for item in analysis_payload.get("required_human_actions", [])],
                *[str(item) for item in analysis_payload.get("external_blockers", [])],
            ]
            result = FullRoadmapExecutionResult(
                status="blocked",
                roadmap=plan.to_dict(),
                roadmap_audit=audit_payload,
                project_analysis=analysis_payload,
                document_expansion=document_expansion_payload,
                generated_development_package=generated_package,
                output_dir=str(output),
                blockers=blockers or ["Project analysis gate did not allow development to start."],
            )
            write_json(output / "full_roadmap_report.json", result.to_dict())
            return result

        blockers: list[str] = []
        phase_count = 0
        while phase_count < max_phases:
            phase = next_ready_phase(plan)
            if phase is None:
                break
            phase_count += 1
            phase.status = "running"
            previous_phase_record = next(
                (record for record in reversed(phase_records) if record.phase_id == phase.phase_id),
                None,
            )
            phase_records = [record for record in phase_records if record.phase_id != phase.phase_id]
            phase_dir = output / "phases" / phase.phase_id
            phase_dir.mkdir(parents=True, exist_ok=True)
            revalidated_record = revalidated_promotable_phase_record(phase_dir, phase)
            if revalidated_record is not None:
                phase.status = "completed"
                phase_records.append(revalidated_record)
                write_json(phase_dir / "phase_record.json", revalidated_record.to_dict())
                write_json(output / "roadmap_execution_plan.json", plan.to_dict())
                write_running_report(
                    output / "full_roadmap_report.json",
                    plan=plan,
                    roadmap_audit=audit_payload,
                    project_analysis=analysis_payload,
                    document_expansion=document_expansion_payload,
                    generated_development_package=generated_package,
                    phase_records=phase_records,
                    active_phase=None,
                )
                continue
            write_running_report(
                output / "full_roadmap_report.json",
                plan=plan,
                roadmap_audit=audit_payload,
                project_analysis=analysis_payload,
                document_expansion=document_expansion_payload,
                generated_development_package=generated_package,
                phase_records=phase_records,
                active_phase=phase,
            )
            phase_document = write_phase_document(
                phase_dir / "phase_requirements.md",
                root_objective=objective,
                phase=phase,
                plan=plan,
            )
            repair_documents = bootstrap_phase_repair_documents(
                phase_dir,
                phase=phase,
                previous_record=previous_phase_record,
                max_repair_documents=max_phase_repair_attempts,
            )
            new_repair_documents_written = 0
            attempt_records: list[dict[str, object]] = []
            phase_payload: dict[str, object] = {}
            promotion: dict[str, object] = {}
            record_status = "blocked"
            while True:
                attempt_index = len(attempt_records) + 1
                interrupted_resume = interrupted_phase_resume_source(phase_dir)
                if interrupted_resume.blockers:
                    phase.status = "blocked"
                    blockers.extend(interrupted_resume.blockers)
                    phase_run_dir = interrupted_resume.active_run_dir or phase_dir
                    phase_payload = {
                        "status": "blocked",
                        "blockers": list(interrupted_resume.blockers),
                        "runtime_state": {"done": False, "blockers": list(interrupted_resume.blockers)},
                    }
                    promotion = {
                        "can_promote": False,
                        "status": "blocked",
                        "reasons": list(interrupted_resume.blockers),
                    }
                    break
                phase_run_dir = next_phase_run_dir(phase_dir)
                effective_repository_path = phase_repository_path(
                    repository_path,
                    phase_records,
                    run_payload=run_payload,
                )
                phase_result = self._run_phase(
                    objective=phase_objective(objective, phase),
                    documents=[phase_document, *repair_documents],
                    attachments=attachments,
                    repository_url=repository_url,
                    repository_path=effective_repository_path,
                    repository_visibility=repository_visibility,
                    output_dir=phase_run_dir,
                    resume_from=interrupted_resume.resume_from,
                    run_payload=phase_run_payload(
                        run_payload,
                        phase,
                        inherited_repository_path=effective_repository_path if effective_repository_path != repository_path else None,
                    ),
                )
                phase_payload = phase_result.to_dict() if hasattr(phase_result, "to_dict") else dict(phase_result)
                promotion = phase_promotion_decision(phase, phase_payload)
                attempt_record = {
                    "attempt": attempt_index,
                    "output_dir": str(phase_run_dir),
                    "promotion": promotion,
                    "status": "done" if promotion["can_promote"] else "blocked",
                }
                if interrupted_resume.resume_from is not None:
                    attempt_record["resume_from"] = str(interrupted_resume.resume_from)
                attempt_records.append(attempt_record)
                write_json(phase_dir / f"attempt_{attempt_index:03d}.json", attempt_record)
                if promotion["can_promote"]:
                    phase.status = "completed"
                    record_status = "done"
                    break
                if phase_has_worker_timeout_stop_boundary(phase_payload):
                    phase.status = "blocked"
                    blockers.extend(str(item) for item in promotion.get("reasons", []) or [])
                    blockers.append(
                        f"Phase stopped at a non-partial worker-timeout blocker for {phase.phase_id}; "
                        "a supervisor must inspect or split the scope before another attempt."
                    )
                    if new_repair_documents_written < max_phase_repair_attempts:
                        repair_document = write_phase_repair_document(
                            next_phase_repair_path(phase_dir),
                            phase=phase,
                            result=phase_payload,
                            promotion=promotion,
                            attempt_index=len(repair_documents) + 1,
                        )
                        repair_documents.append(repair_document)
                        new_repair_documents_written += 1
                    break
                if not should_auto_repair_phase(promotion, phase_payload):
                    phase.status = "blocked"
                    blockers.extend(str(item) for item in promotion.get("reasons", []) or [])
                    break
                repair_attempt_index = len(repair_documents) + 1
                if new_repair_documents_written >= max_phase_repair_attempts:
                    phase.status = "blocked"
                    blockers.extend(str(item) for item in promotion.get("reasons", []) or [])
                    blockers.append(
                        f"Phase auto-repair limit reached for {phase.phase_id}: "
                        f"{max_phase_repair_attempts} repair attempt(s)."
                    )
                    break
                repair_document = write_phase_repair_document(
                    next_phase_repair_path(phase_dir),
                    phase=phase,
                    result=phase_payload,
                    promotion=promotion,
                    attempt_index=repair_attempt_index,
                )
                repair_documents.append(repair_document)
                new_repair_documents_written += 1
            record = PhaseExecutionRecord(
                phase_id=phase.phase_id,
                title=phase.title,
                status=record_status,
                output_dir=str(phase_run_dir),
                result=phase_payload,
                promotion={
                    **promotion,
                    "attempts": attempt_records,
                    "auto_repair_documents": list(repair_documents),
                },
            )
            phase_records.append(record)
            write_json(phase_dir / "phase_record.json", record.to_dict())
            write_json(output / "roadmap_execution_plan.json", plan.to_dict())
            write_running_report(
                output / "full_roadmap_report.json",
                plan=plan,
                roadmap_audit=audit_payload,
                project_analysis=analysis_payload,
                document_expansion=document_expansion_payload,
                generated_development_package=generated_package,
                phase_records=phase_records,
                active_phase=None,
            )
            if record_status != "done":
                break

        if phase_count >= max_phases and next_ready_phase(plan) is not None:
            blockers.append("Maximum roadmap phase count reached.")

        final_verification_worker: dict[str, object] = {}
        if not blockers and worker_final_verification_enabled(run_payload):
            final_verification_worker = self._run_final_verification_worker(
                objective=objective,
                plan=plan,
                phase_records=phase_records,
                documents=roadmap_documents,
                attachments=attachments,
                repository_url=repository_url,
                repository_path=repository_path,
                repository_visibility=repository_visibility,
                output_dir=output / "final_verification",
                run_payload=run_payload,
            )

        final_audit = FinalSystemAudit().audit(
            plan,
            phase_records,
            worker_verification=final_verification_worker,
            run_payload=run_payload,
        )
        result_blockers = dedupe_strings(
            [
                *blockers,
                *[
                    str(item)
                    for item in final_audit.get("blockers", [])
                    if str(item).strip()
                ],
            ]
        )
        status = "done" if final_audit["ready_for_final_handoff"] and not result_blockers else "blocked"
        result = FullRoadmapExecutionResult(
            status=status,
            roadmap=plan.to_dict(),
            roadmap_audit=audit_payload,
            project_analysis=analysis_payload,
            document_expansion=document_expansion_payload,
            phase_records=[record.to_dict() for record in phase_records],
            final_audit=final_audit,
            final_verification_worker=final_verification_worker,
            generated_development_package=generated_package,
            output_dir=str(output),
            blockers=result_blockers,
        )
        write_json(output / "full_roadmap_report.json", result.to_dict())
        return result

    def _run_phase(
        self,
        *,
        objective: str,
        documents: Sequence[str | Path],
        attachments: Sequence[str | Path],
        repository_url: str,
        repository_path: str | Path | None,
        repository_visibility: str,
        output_dir: Path,
        resume_from: str | Path | None = None,
        run_payload: dict[str, Any],
    ) -> Any:
        return self.document_runner(
            objective=objective,
            documents=documents,
            attachments=attachments,
            primary_input_mode="document_driven",
            repository_url=repository_url,
            repository_path=repository_path,
            repository_visibility=repository_visibility,
            output_dir=output_dir,
            resume_from=resume_from,
            max_iterations=int(run_payload.get("max_iterations", 50)),
            prepare_repository=bool(run_payload.get("prepare_repository", False)),
            real_codex=bool(run_payload.get("real_codex", False)),
            real_github=bool(run_payload.get("real_github", False)),
            codex_executable=str(run_payload.get("codex_executable", "codex")),
            max_worker_seconds=int(run_payload.get("max_worker_seconds", 0) or 0),
            github_collect_ci=bool(run_payload.get("github_collect_ci", True)),
            github_ci_wait_seconds=float(run_payload.get("github_ci_wait_seconds", 120)),
            github_ci_poll_interval_seconds=float(run_payload.get("github_ci_poll_interval_seconds", 10)),
            isolate_real_run=bool(run_payload.get("isolate_real_run", True)),
            keep_worktree=bool(run_payload.get("keep_worktree", True)),
            worktree_branch_prefix=str(run_payload.get("worktree_branch_prefix", "agent/alchemy-real-run")),
            auto_browser_verify=bool(run_payload.get("auto_browser_verify", False)),
            generate_static_ci=bool(run_payload.get("generate_static_ci", True)),
            write_native_ui_tests=bool(run_payload.get("write_native_ui_tests", False)),
            auto_merge=bool(run_payload.get("auto_merge", False)),
            constraints=[str(item) for item in run_payload.get("constraints", []) or []],
        )

    def _run_final_verification_worker(
        self,
        *,
        objective: str,
        plan: RoadmapExecutionPlan,
        phase_records: Sequence[PhaseExecutionRecord],
        documents: Sequence[str | Path],
        attachments: Sequence[str | Path],
        repository_url: str,
        repository_path: str | Path | None,
        repository_visibility: str,
        output_dir: Path,
        run_payload: dict[str, Any],
    ) -> dict[str, object]:
        output_dir.mkdir(parents=True, exist_ok=True)
        evidence_report = FinalVerificationLoop().audit(plan, phase_records, run_payload=run_payload)
        verification_doc = write_final_verification_document(
            output_dir / "final_verification_requirements.md",
            plan=plan,
            phase_records=phase_records,
            evidence_report=evidence_report,
        )
        final_phase = RoadmapPhase(
            phase_id="final_verification",
            title="Final Full-System Audit And Testing",
            requirements=[
                "Challenge the completed code against the full development documents from multiple audit angles.",
                "Run broad simulation tests and real tests available in the repository.",
                "Repair any defect found before reporting PASS.",
            ],
            promotion_gate={"required_score": float(run_payload.get("final_verification_required_score", 0.85) or 0.85)},
        )
        attempts: list[dict[str, object]] = []
        repair_documents: list[str] = final_verification_resume_repair_documents(output_dir)
        max_attempts = max(1, int(run_payload.get("max_final_verification_attempts", 2) or 2))
        payload: dict[str, object] = {}
        promotion: dict[str, object] = {}
        effective_repository_path = phase_repository_path(
            repository_path,
            phase_records,
            run_payload=run_payload,
        )
        final_run_payload = phase_run_payload(
            run_payload,
            final_phase,
            inherited_repository_path=(
                effective_repository_path if effective_repository_path != repository_path else None
            ),
        )
        final_run_payload["max_iterations"] = max(int(final_run_payload.get("max_iterations", 0) or 0), 24)
        first_attempt_index = next_final_verification_attempt_index(output_dir)
        for attempt_offset in range(max_attempts):
            attempt_index = first_attempt_index + attempt_offset
            attempt_dir = output_dir / f"run_attempt_{attempt_index:03d}"
            payload_result = self._run_phase(
                objective=(
                    f"{objective}\n\n"
                    "Final verification phase: audit the complete system, run simulation and real tests, "
                    "repair defects if found, and return evidence. This is the last gate before handoff."
                ),
                documents=[*documents, verification_doc, *repair_documents],
                attachments=attachments,
                repository_url=repository_url,
                repository_path=effective_repository_path,
                repository_visibility=repository_visibility,
                output_dir=attempt_dir,
                run_payload=final_run_payload,
            )
            payload = payload_result.to_dict() if hasattr(payload_result, "to_dict") else dict(payload_result)
            promotion = phase_promotion_decision(final_phase, payload)
            non_partial_stop = phase_has_non_partial_stop_boundary(payload)
            attempt_record = {
                "attempt": attempt_index,
                "output_dir": str(attempt_dir),
                "promotion": promotion,
                "status": "done" if promotion["can_promote"] else "blocked",
            }
            if non_partial_stop:
                attempt_record["stop_boundary"] = "non_partial_blocker"
            attempts.append(attempt_record)
            write_json(output_dir / f"attempt_{attempt_index:03d}.json", attempt_record)
            if promotion["can_promote"]:
                break
            if non_partial_stop:
                break
            if attempt_offset + 1 >= max_attempts or not should_auto_repair_phase(promotion, payload):
                break
            repair_documents.append(
                write_phase_repair_document(
                    output_dir / f"final_verification_repair_{attempt_index:03d}.md",
                    phase=final_phase,
                    result=payload,
                    promotion=promotion,
                    attempt_index=attempt_index,
                )
            )
        worker_report = {
            "status": "passed" if promotion.get("can_promote") else "failed",
            "promotion": promotion,
            "attempts": attempts,
            "auto_repair_documents": list(repair_documents),
            "output_dir": str(output_dir),
            "result": payload,
            "required_actions": [str(item) for item in promotion.get("reasons", []) or []],
            "blockers": [str(item) for item in payload.get("blockers", [])] if isinstance(payload.get("blockers", []), list) else [],
        }
        write_json(output_dir / "final_verification_worker_report.json", worker_report)
        return worker_report


def write_phase_document(path: Path, *, root_objective: str, phase: RoadmapPhase, plan: RoadmapExecutionPlan) -> str:
    scope_payload = documentation_phase_scope_controls(phase) if is_documentation_phase(phase) else phase.scope_controls
    lines = [
        f"# {phase.title}",
        "",
        "## Root Objective",
        "",
        root_objective,
        "",
        "## Phase Requirements",
        "",
    ]
    lines.extend(f"- {item}" for item in phase.requirements)
    if is_documentation_phase(phase):
        lines.extend(
            [
                "",
                "## Global Constraints Reference",
                "",
                "Global implementation constraints stay frozen in the parent roadmap for later implementation phases. Phase acceptance is limited to the phase requirements above and the documentation-only verification below.",
            ]
        )
    else:
        lines.extend(["", "## Global Constraints", ""])
        lines.extend(f"- {item}" for item in plan.global_constraints)
    lines.extend(["", "## Phase-Local Constraints", ""])
    if phase.phase_local_constraints:
        lines.extend(f"- {item}" for item in phase.phase_local_constraints)
    else:
        lines.append("- No additional phase-local constraints.")
    scope_controls = normalized_scope_controls(scope_payload)
    if scope_controls["allowed_prefixes"] or scope_controls["protected_prefixes"] or scope_controls["target_files"]:
        lines.extend(["", "## Scope Controls", ""])
        if scope_controls["allowed_prefixes"]:
            lines.extend(["Allowed implementation scope:", ""])
            lines.append("```text")
            lines.extend(str(item) for item in scope_controls["allowed_prefixes"])
            lines.append("```")
            lines.append("")
        if scope_controls["target_files"]:
            lines.extend(["Target files:", ""])
            lines.append("```text")
            lines.extend(str(item) for item in scope_controls["target_files"])
            lines.append("```")
            lines.append("")
        if scope_controls["protected_prefixes"]:
            lines.extend(["Protected paths:", ""])
            lines.append("```text")
            lines.extend(str(item) for item in scope_controls["protected_prefixes"])
            lines.append("```")
            lines.append("")
        lines.extend(
            [
                "- Do not edit protected paths.",
                "- Treat files outside the allowed implementation scope as read-only reference material.",
            ]
        )
    if scope_controls["boundary_mode"] and scope_controls["boundary_mode"][0] == "large_refactor":
        lines.extend(
            [
                "",
                "## Boundary Mode",
                "",
                "Scope boundary mode: large_refactor",
                "Plan implementation as a bounded product-scale vertical slice for this phase only.",
                "If the phase has several independent acceptance bullets, finish the smallest coherent subset that proves this phase's contract before expanding scope.",
                "Do not pull requirements from later roadmap phases into this worker attempt.",
            ]
        )
    if is_documentation_phase(phase):
        lines.extend(
            [
                "",
                "## Documentation Phase Verification",
                "",
                "- This phase is documentation-only; do not run full backend/frontend builds unless a document explicitly requires them.",
                "- Record deterministic evidence with lightweight document checks such as `git diff --check -- docs`.",
                "- Do not edit backend, frontend, deployment, generated schema, or runtime files in this phase.",
            ]
        )
    lines.extend(
        [
            "",
            "## Full-Roadmap Execution Rule",
            "",
            "- Completion of this phase is not final project delivery if later roadmap phases remain.",
            "- The parent roadmap executor handles promotion after this phase passes.",
            "",
            "## Acceptance Criteria",
            "",
            "- This phase satisfies every phase requirement.",
            "- Tests, probes, or deterministic verification evidence are recorded.",
            "- No global constraint is violated.",
        ]
    )
    path = path.resolve()
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def is_documentation_phase(phase: RoadmapPhase) -> bool:
    title = phase.title.lower()
    return phase.phase_type == "documentation" or any(
        token in title for token in ("documentation", "document", "docs", "freeze", "文档", "冻结")
    )


def documentation_phase_scope_controls(phase: RoadmapPhase) -> dict[str, object]:
    controls = dict(phase.scope_controls or {})
    allowed = [str(item) for item in controls.get("allowed_prefixes", []) or []]
    protected = [str(item) for item in controls.get("protected_prefixes", []) or []]
    targets = [str(item) for item in controls.get("target_files", []) or []]
    return {
        "allowed_prefixes": dedupe_strings([*allowed, "docs/"]),
        "protected_prefixes": dedupe_strings(
            [
                *protected,
                ".github/",
                "backend/",
                "cmd/",
                "deploy/",
                "deployment/",
                "docker/",
                "ent/",
                "frontend/",
                "internal/",
                "migrations/",
                "pkg/",
                "runtime/",
                "scripts/",
                "src/",
                "web/",
            ]
        ),
        "target_files": dedupe_strings(targets),
        "boundary_mode": "strict",
    }


def phase_run_payload(
    run_payload: dict[str, Any],
    phase: RoadmapPhase,
    *,
    inherited_repository_path: str | Path | None = None,
) -> dict[str, Any]:
    payload = dict(run_payload)
    constraints = list(payload.get("constraints", []) or [])
    boundary_mode = str(payload.get("boundary_mode", "auto") or "auto")
    if is_schema_build_phase(phase):
        payload["max_iterations"] = max(int(payload.get("max_iterations", 50) or 0), 8)
    if inherited_repository_path:
        payload["isolate_real_run"] = False
        constraints.append(
            "Continue in the inherited full-roadmap worktree from the previous phase; do not create a fresh isolated worktree for this phase."
        )
    if is_documentation_phase(phase):
        payload["boundary_mode"] = "strict"
        constraints = [
            item
            for item in constraints
            if "scope boundary mode:" not in str(item).lower()
        ]
        constraints.extend(
            [
                "Scope boundary mode: strict",
                "Allowed paths: docs/",
                "Protected paths: backend/, frontend/, deploy/, .github/, ent/, runtime/, scripts/, src/, web/",
                "Documentation-only phase: run lightweight document checks instead of full backend/frontend builds.",
            ]
        )
    elif boundary_mode in {"strict", "large_refactor"} and not any(
        "scope boundary mode:" in str(item).lower() for item in constraints
    ):
        constraints.append(f"Scope boundary mode: {boundary_mode}")
    payload["constraints"] = dedupe_strings([str(item) for item in constraints if str(item).strip()])
    return payload


def is_schema_build_phase(phase: RoadmapPhase) -> bool:
    text = " ".join([phase.title, *phase.requirements]).lower()
    return any(marker in text for marker in ("schema", "ent", "migration", "migrate", "fresh db"))


def phase_repository_path(
    default_repository_path: str | Path | None,
    phase_records: Sequence[PhaseExecutionRecord],
    *,
    run_payload: dict[str, Any] | None = None,
) -> str | Path | None:
    """Return the repository path that should receive the next roadmap phase.

    Real full-roadmap execution is cumulative. Once a phase succeeds in an
    isolated worktree, later phases must continue in that same worktree instead
    of starting again from the original checkout.
    """

    if not bool((run_payload or {}).get("real_codex", False)):
        return default_repository_path
    for record in reversed(list(phase_records)):
        if record.status not in {"done", "completed"}:
            continue
        path = result_repository_path(record.result)
        if path:
            return path
    return default_repository_path


def result_repository_path(result: dict[str, object]) -> str:
    runtime_state = _dict(result.get("runtime_state"))
    repository = _dict(runtime_state.get("repository"))
    path = str(repository.get("path", "") or "").strip()
    if path:
        return path
    workspace = _dict(result.get("workspace"))
    for key in ("execution_path", "worktree_path"):
        value = str(workspace.get(key, "") or "").strip()
        if value:
            return value
    return ""


def bootstrap_phase_repair_documents(
    phase_dir: Path,
    *,
    phase: RoadmapPhase,
    previous_record: PhaseExecutionRecord | None,
    max_repair_documents: int,
) -> list[str]:
    """Seed a resumed blocked phase with the previous blocker evidence."""

    if max_repair_documents <= 0:
        return []
    repair_context_limit = cumulative_repair_document_limit(phase, max_repair_documents)
    if previous_record is None:
        return latest_existing_phase_repair_documents(phase_dir, max_repair_documents=repair_context_limit)
    previous_record = effective_previous_repair_record(phase_dir, phase=phase, previous_record=previous_record)
    existing_documents = latest_existing_phase_repair_documents(
        phase_dir,
        max_repair_documents=repair_context_limit,
    )
    if existing_documents:
        return existing_documents
    context_documents = latest_existing_phase_repair_documents(
        phase_dir,
        max_repair_documents=repair_context_limit,
        require_newer_than_phase_record=False,
    )
    iteration_limit_context = latest_iteration_limit_context_document(
        phase_dir,
        phase=phase,
    )
    if iteration_limit_context:
        return dedupe_strings([*context_documents, iteration_limit_context])
    previous_output_dir = Path(previous_record.output_dir)
    if previous_output_dir.exists() and supervisor_stop_marker_exists(previous_output_dir):
        stopped_attempt_context = latest_supervisor_stopped_attempt_context_document(
            phase_dir,
            phase=phase,
        )
        if stopped_attempt_context:
            return dedupe_strings([*context_documents, stopped_attempt_context])
        if context_documents:
            return context_documents
    if str(previous_record.status).lower() not in {"blocked", "failed"}:
        return []
    if context_documents and phase_has_worker_timeout_stop_boundary(previous_record.result):
        return context_documents
    if not should_auto_repair_phase(previous_record.promotion, previous_record.result):
        return []
    stopped_attempt_context = latest_supervisor_stopped_attempt_context_document(
        phase_dir,
        phase=phase,
    )
    if stopped_attempt_context:
        return dedupe_strings([*context_documents, stopped_attempt_context])
    verification_issue_context = latest_verification_issue_context_document(
        phase_dir,
        phase=phase,
    )
    if verification_issue_context:
        return dedupe_strings([*context_documents, verification_issue_context])
    path = next_phase_repair_resume_path(phase_dir)
    return dedupe_strings(
        [
            *context_documents,
            write_phase_repair_document(
                path,
                phase=phase,
                result=previous_record.result,
                promotion=previous_record.promotion,
                attempt_index=1,
            ),
        ]
    )


def cumulative_repair_document_limit(phase: RoadmapPhase, max_repair_documents: int) -> int:
    if is_schema_build_phase(phase):
        return max(max_repair_documents, 14)
    return max_repair_documents


def revalidated_promotable_phase_record(phase_dir: Path, phase: RoadmapPhase) -> PhaseExecutionRecord | None:
    for run_dir in reversed(list_phase_run_dirs(phase_dir)):
        payload = read_optional_json(run_dir / "document_run_report.json")
        if not payload:
            continue
        refreshed = result_with_current_evaluation(payload)
        promotion = phase_promotion_decision(phase, refreshed)
        if not bool(promotion.get("can_promote")):
            continue
        return PhaseExecutionRecord(
            phase_id=phase.phase_id,
            title=phase.title,
            status="done",
            output_dir=str(run_dir),
            result=refreshed,
            promotion=promotion,
        )
    return None


def result_with_current_evaluation(result: dict[str, object]) -> dict[str, object]:
    runtime_state = _dict(result.get("runtime_state"))
    if not runtime_state:
        return result
    try:
        evaluation = Evaluator().evaluate(RuntimeState.from_dict(runtime_state)).to_dict()
    except (KeyError, TypeError, ValueError):
        return result
    refreshed = dict(result)
    delivery = _dict(refreshed.get("delivery_report"))
    final_gate = _dict(delivery.get("final_gate"))
    final_gate.update(
        {
            "score": evaluation.get("final_gate_score", evaluation.get("final_score", 0.0)),
            "final_score": evaluation.get("final_score", evaluation.get("final_gate_score", 0.0)),
            "dimension_scores": evaluation.get("dimension_scores", {}),
            "hard_failures": evaluation.get("hard_failures", []),
            "required_changes": evaluation.get("required_changes", []),
            "reason": evaluation.get("reason", ""),
        }
    )
    delivery["final_gate"] = final_gate
    delivery["ready_for_review"] = bool(evaluation.get("done"))
    refreshed["delivery_report"] = delivery
    if bool(evaluation.get("done")) and str(refreshed.get("status", "")) == "done":
        refreshed["status"] = "done"
    return refreshed


def effective_previous_repair_record(
    phase_dir: Path,
    *,
    phase: RoadmapPhase,
    previous_record: PhaseExecutionRecord,
) -> PhaseExecutionRecord:
    """Skip empty supervisor-stopped attempts when selecting repair context."""

    if not empty_supervisor_stopped_phase_record(previous_record):
        return previous_record
    previous_output = Path(previous_record.output_dir)
    previous_key = _phase_run_sort_key(previous_output)
    previous_resolved = str(previous_output.resolve())
    for run_dir in reversed(list_phase_run_dirs(phase_dir)):
        if str(run_dir.resolve()) == previous_resolved:
            continue
        if _phase_run_sort_key(run_dir) >= previous_key:
            continue
        payload = read_optional_json(run_dir / "document_run_report.json")
        if not payload:
            continue
        promotion = phase_promotion_decision(phase, payload)
        candidate = PhaseExecutionRecord(
            phase_id=phase.phase_id,
            title=phase.title,
            status="done" if bool(promotion.get("can_promote")) else "blocked",
            output_dir=str(run_dir),
            result=payload,
            promotion=promotion,
        )
        if should_auto_repair_phase(candidate.promotion, candidate.result):
            return candidate
    return previous_record


def empty_supervisor_stopped_phase_record(record: PhaseExecutionRecord) -> bool:
    output_dir = Path(record.output_dir)
    if not output_dir.exists() or not supervisor_stop_marker_exists(output_dir):
        return False
    runtime_state = _dict(record.result.get("runtime_state"))
    return not completed_task_ids_from_state(runtime_state)


def latest_existing_phase_repair_documents(
    phase_dir: Path,
    *,
    max_repair_documents: int,
    require_newer_than_phase_record: bool = True,
) -> list[str]:
    """Return recent on-disk repair briefs when they are newer than the phase record.

    A supervisor may stop a parent run after it writes ``phase_repair_NNN.md``
    but before it refreshes ``phase_record.json``. On the next full-roadmap
    launch, the stale phase record cannot carry the fresh blocker evidence, so
    recent ordinary repair briefs must be handed to the document runner.
    """

    if max_repair_documents <= 0:
        return []
    record_path = phase_dir / "phase_record.json"
    record_mtime = record_path.stat().st_mtime if record_path.exists() else 0.0
    candidates: list[Path] = []
    for candidate in phase_dir.glob("phase_repair_*.md"):
        if candidate.name.startswith("phase_repair_resume_"):
            continue
        try:
            candidate_mtime = candidate.stat().st_mtime
        except OSError:
            continue
        if require_newer_than_phase_record and record_mtime and candidate_mtime <= record_mtime:
            continue
        candidates.append(candidate)
    if not candidates:
        return []
    latest_candidates = sorted(candidates, key=lambda path: (path.stat().st_mtime, path.name))[-max_repair_documents:]
    return [str(path.resolve()) for path in latest_candidates]


def latest_supervisor_stopped_attempt_context_document(
    phase_dir: Path,
    *,
    phase: RoadmapPhase,
) -> str:
    """Write repair context from a newer supervisor-stopped attempt.

    A live supervisor stop can intentionally terminate a parent after some tasks
    complete but before ``phase_record.json`` is refreshed. The next launch must
    not resume that active attempt, but it should preserve completed task IDs
    from its state to avoid replaying successful work.
    """

    record_path = phase_dir / "phase_record.json"
    record_mtime = record_path.stat().st_mtime if record_path.exists() else 0.0
    for run_dir in reversed(list_phase_run_dirs(phase_dir)):
        if not supervisor_stop_marker_exists(run_dir):
            continue
        state_path = run_dir / "state.json"
        try:
            state_mtime = state_path.stat().st_mtime
        except OSError:
            continue
        if record_mtime and state_mtime <= record_mtime:
            continue
        state = read_optional_json(state_path)
        completed_task_ids = completed_task_ids_from_state(state)
        if not completed_task_ids:
            continue
        active_task_ids = active_task_ids_from_state(state)
        existing_context = existing_supervisor_stopped_attempt_context_document(phase_dir, run_dir)
        if existing_context:
            return existing_context
        return write_supervisor_stopped_attempt_context_document(
            next_phase_repair_resume_path(phase_dir),
            phase=phase,
            run_dir=run_dir,
            completed_task_ids=completed_task_ids,
            active_task_ids=active_task_ids,
        )
    return ""


def existing_supervisor_stopped_attempt_context_document(phase_dir: Path, run_dir: Path) -> str:
    marker = f"Supervisor-stopped run directory: {run_dir}"
    for candidate in sorted(phase_dir.glob("phase_repair_resume_*.md"), reverse=True):
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        if "Repair attempt: supervisor-stopped context" in text and marker in text:
            return str(candidate.resolve())
    return ""


def latest_verification_issue_context_document(
    phase_dir: Path,
    *,
    phase: RoadmapPhase,
) -> str:
    """Recover concrete failed verification evidence from older phase attempts."""

    for run_dir in reversed(list_phase_run_dirs(phase_dir)):
        state = read_optional_json(run_dir / "state.json")
        if not state:
            continue
        result = verification_issue_result_from_state(state)
        verification_issue_lines = phase_verification_issue_lines(result)
        if not verification_issue_lines:
            if state_has_clean_test_verification(state):
                return ""
            continue
        existing_context = existing_verification_issue_context_document(phase_dir, run_dir)
        if existing_context:
            return existing_context
        return write_verification_issue_context_document(
            next_phase_repair_resume_path(phase_dir),
            phase=phase,
            run_dir=run_dir,
            result=result,
        )
    return ""


def existing_verification_issue_context_document(phase_dir: Path, run_dir: Path) -> str:
    marker = f"Verification issue run directory: {run_dir}"
    for candidate in sorted(phase_dir.glob("phase_repair_resume_*.md"), reverse=True):
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        if "Repair attempt: verification-issue context" in text and marker in text:
            return str(candidate.resolve())
    return ""


def latest_iteration_limit_context_document(
    phase_dir: Path,
    *,
    phase: RoadmapPhase,
) -> str:
    """Recover completed task evidence from a clean iteration-limit stop."""

    for run_dir in reversed(list_phase_run_dirs(phase_dir)):
        if supervisor_stop_marker_exists(run_dir):
            continue
        state = read_optional_json(run_dir / "state.json")
        if not state_has_clean_iteration_limit_continuation(state):
            continue
        completed_task_ids = completed_task_ids_from_state(state)
        pending_task_ids = pending_task_ids_from_state(state)
        if not completed_task_ids or not pending_task_ids:
            continue
        existing_context = existing_iteration_limit_context_document(phase_dir, run_dir)
        if existing_context:
            return existing_context
        return write_iteration_limit_context_document(
            next_phase_repair_resume_path(phase_dir),
            phase=phase,
            run_dir=run_dir,
            completed_task_ids=completed_task_ids,
            pending_task_ids=pending_task_ids,
        )
    return ""


def existing_iteration_limit_context_document(phase_dir: Path, run_dir: Path) -> str:
    marker = f"Iteration-limit run directory: {run_dir}"
    for candidate in sorted(phase_dir.glob("phase_repair_resume_*.md"), reverse=True):
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        if "Repair attempt: iteration-limit context" in text and marker in text:
            return str(candidate.resolve())
    return ""


def state_has_clean_iteration_limit_continuation(state: dict[str, object]) -> bool:
    if not state:
        return False
    if bool(state.get("done")):
        return False
    if _list(state.get("blockers")) or _list(state.get("active_tasks")) or _list(state.get("failed_tasks")):
        return False
    history = _list(state.get("execution_history"))
    has_iteration_limit = any(
        isinstance(item, dict)
        and (
            str(item.get("type", "")).lower() == "iteration_limit"
            or "stopped after" in str(item.get("summary", "")).lower()
        )
        for item in history
    )
    return has_iteration_limit and bool(completed_task_ids_from_state(state)) and bool(pending_task_ids_from_state(state))


def write_iteration_limit_context_document(
    path: Path,
    *,
    phase: RoadmapPhase,
    run_dir: Path,
    completed_task_ids: Sequence[str],
    pending_task_ids: Sequence[str],
) -> str:
    lines = [
        f"# Auto Repair For {phase.title}",
        "",
        "Repair attempt: iteration-limit context",
        "",
        "## Why This Repair Exists",
        "",
        "A phase attempt stopped at its document-run iteration limit after completing tasks cleanly.",
        "Do not restart the phase from scratch; preserve the completed task evidence and continue the pending review or delivery tasks.",
        "",
        "## Focused Repair Scope",
        "",
        f"- Primary failed task IDs: {', '.join(pending_task_ids)}.",
        f"- Completed tasks to preserve: {', '.join(completed_task_ids)}.",
        f"- Iteration-limit run directory: {run_dir}",
        "- Continue from the next incomplete task after the preserved completed task IDs.",
        "- Keep prior timeout split context active so task IDs do not drift when preserving completed verification tasks.",
        "",
        "## Repair Instructions",
        "",
        "- Do not restart the phase from scratch.",
        "- Preserve all completed work from previous roadmap phases.",
        "- Preserve completed tasks from this iteration-limit attempt unless a focused failed-task dependency requires a scoped edit.",
        "- Continue from the pending review or delivery-evidence tasks before creating new implementation work.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path.resolve())


def write_verification_issue_context_document(
    path: Path,
    *,
    phase: RoadmapPhase,
    run_dir: Path,
    result: dict[str, object],
) -> str:
    state = _dict(result.get("runtime_state"))
    evaluation = _dict(state.get("evaluation"))
    promotion = {
        "required_score": 0.85,
        "score": evaluation.get("final_gate_score", evaluation.get("score", 0.0)),
        "reasons": evaluation.get("hard_failures", ["Recovered failed verification evidence from prior attempt."]),
    }
    resolved = Path(
        write_phase_repair_document(
            path,
            phase=phase,
            result=result,
            promotion=promotion,
            attempt_index="verification-issue context",
        )
    )
    with resolved.open("a", encoding="utf-8") as handle:
        handle.write("\n## Recovery Source\n\n")
        handle.write(f"- Verification issue run directory: {run_dir}\n")
    return str(resolved)


def verification_issue_result_from_state(state: dict[str, object]) -> dict[str, object]:
    evaluation = _dict(state.get("evaluation"))
    return {
        "status": "done",
        "delivery_report": {"final_gate": evaluation},
        "runtime_state": state,
    }


def write_supervisor_stopped_attempt_context_document(
    path: Path,
    *,
    phase: RoadmapPhase,
    run_dir: Path,
    completed_task_ids: Sequence[str],
    active_task_ids: Sequence[str],
) -> str:
    split_task_ids = {"T010", "T011", "T012", "T013"}
    needs_t010_split_context = any(
        str(task_id).upper() in split_task_ids for task_id in [*completed_task_ids, *active_task_ids]
    )
    primary_ids = dedupe_strings([*active_task_ids, *(["T010"] if needs_t010_split_context else [])])
    lines = [
        f"# Auto Repair For {phase.title}",
        "",
        "Repair attempt: supervisor-stopped context",
        "",
        "## Why This Repair Exists",
        "",
        "A newer phase attempt was stopped by the supervisor before the parent phase record was refreshed.",
        "Do not resume that active attempt directly, but preserve its completed task evidence.",
        "",
        "## Focused Repair Scope",
        "",
        f"- Primary failed task IDs: {', '.join(primary_ids) if primary_ids else 'none'}.",
        f"- Completed tasks to preserve: {', '.join(completed_task_ids)}.",
        f"- Supervisor-stopped run directory: {run_dir}",
        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
        "- Keep prior timeout split context active so task IDs do not drift when preserving completed tasks.",
    ]
    if active_task_ids:
        lines.append(f"- Active tasks at supervisor stop: {', '.join(active_task_ids)}.")
    if needs_t010_split_context:
        lines.extend(
            [
                "",
                "### Prior Timeout Split Context",
                "",
                "- Primary failed task IDs: T010.",
                "- Task T010 previously exceeded the Codex worker timeout and must remain split/checkpointed.",
                "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
            ]
        )
    lines.extend(
        [
            "",
            "## Repair Instructions",
            "",
            "- Do not restart the phase from scratch.",
            "- Preserve all completed work from previous roadmap phases.",
            "- Preserve completed tasks from this stopped attempt unless a focused failed-task dependency requires a scoped edit.",
            "- Continue from the next incomplete task after the preserved completed task IDs.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path.resolve())


def completed_task_ids_from_state(state: dict[str, object]) -> list[str]:
    task_ids = [str(item) for item in _list(state.get("completed_tasks"))]
    task_graph = _dict(state.get("task_graph"))
    nodes = _list(task_graph.get("nodes"))
    task_ids.extend(
        str(node.get("id", ""))
        for node in nodes
        if isinstance(node, dict) and str(node.get("status", "")).lower() == "completed"
    )
    return dedupe_strings(task_ids)


def pending_task_ids_from_state(state: dict[str, object]) -> list[str]:
    task_graph = _dict(state.get("task_graph"))
    nodes = _list(task_graph.get("nodes"))
    return dedupe_strings(
        str(node.get("id", ""))
        for node in nodes
        if isinstance(node, dict) and str(node.get("status", "")).lower() in {"pending", "ready", "active"}
    )


def next_phase_repair_resume_path(phase_dir: Path) -> Path:
    for index in range(1, 1000):
        candidate = phase_dir / f"phase_repair_resume_{index:03d}.md"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Too many phase repair resume documents for {phase_dir}")


def next_phase_repair_path(phase_dir: Path) -> Path:
    for index in range(1, 1000):
        candidate = phase_dir / f"phase_repair_{index:03d}.md"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Too many phase repair documents for {phase_dir}")


def write_phase_repair_document(
    path: Path,
    *,
    phase: RoadmapPhase,
    result: dict[str, object],
    promotion: dict[str, object],
    attempt_index: int | str,
) -> str:
    """Write a machine-actionable repair brief for a failed phase gate."""

    delivery = _dict(result.get("delivery_report"))
    final_gate = _dict(delivery.get("final_gate"))
    runtime_state = _dict(result.get("runtime_state"))
    evaluation = _dict(runtime_state.get("evaluation"))
    dimension_scores = _dict(final_gate.get("dimension_scores")) or _dict(evaluation.get("dimension_scores"))
    low_dimensions = [
        f"{name}: {float_or_zero(score):.2f}"
        for name, score in dimension_scores.items()
        if float_or_zero(score) < float_or_zero(promotion.get("required_score", 0.85))
    ]
    required_changes = [
        *[str(item) for item in _list(final_gate.get("required_changes"))],
        *[str(item) for item in _list(evaluation.get("required_changes"))],
    ]
    blockers = [*(_list(result.get("blockers"))), *(_list(runtime_state.get("blockers")))]
    verification_issue_lines = phase_verification_issue_lines(result)
    focused_repair_lines = phase_focused_repair_lines(result, blockers)
    hard_failures = [
        *[str(item) for item in _list(final_gate.get("hard_failures"))],
        *[str(item) for item in _list(evaluation.get("hard_failures"))],
    ]
    reasons = [str(item) for item in _list(promotion.get("reasons"))]
    lines = [
        f"# Auto Repair For {phase.title}",
        "",
        f"Repair attempt: {attempt_index}",
        "",
        "## Why This Repair Exists",
        "",
        "The phase implementation ran, but the parent roadmap promotion gate did not pass.",
        "Continue from the current repository state and repair only the remaining evidence or implementation gaps.",
        "",
        "## Promotion Gate Result",
        "",
        f"- Required score: {promotion.get('required_score', 0.85)}",
        f"- Current score: {promotion.get('score', final_gate.get('score', final_gate.get('final_score', 0.0)))}",
        f"- Reasons: {', '.join(reasons) if reasons else 'none recorded'}",
        "",
        "## Low Score Dimensions",
        "",
    ]
    if low_dimensions:
        lines.extend(f"- {item}" for item in low_dimensions)
    else:
        lines.append("- No low score dimension was reported; inspect final gate evidence and close the promotion gap.")
    lines.extend(["", "## Hard Failures", ""])
    if hard_failures:
        lines.extend(f"- {item}" for item in dedupe_strings(hard_failures))
    else:
        lines.append("- None recorded.")
    lines.extend(["", "## Repairable Blockers", ""])
    blocker_summaries = repairable_blocker_summaries(blockers)
    if blocker_summaries:
        lines.extend(f"- {item}" for item in blocker_summaries)
    else:
        lines.append("- None recorded.")
    lines.extend(["", "## Required Changes", ""])
    if required_changes:
        lines.extend(f"- {item}" for item in dedupe_strings(required_changes))
    else:
        lines.append("- Improve the low gate dimensions with concrete implementation, tests, or review evidence.")
    if verification_issue_lines:
        lines.extend(["", "## Failing Verification Issues", ""])
        lines.extend(verification_issue_lines)
    lines.extend(focused_repair_lines)
    lines.extend(
        [
            "",
            "## Repair Instructions",
            "",
            "- Do not restart the phase from scratch.",
            "- Preserve all completed work from previous roadmap phases.",
            "- Preserve completed tasks from this phase unless a focused failed-task dependency requires a scoped edit.",
            "- Prefer a narrow follow-up graph around the failed task IDs and failing tests listed above.",
            "- Keep the phase scope controls and protected paths unchanged.",
            "- If full-suite failures are outside the previous task allowed_files, create a focused repair task with those files in scope instead of retrying the same narrow task unchanged.",
            "- If retry exhaustion or timeout repeats, split the task by failing workflow or test file before launching another large worker.",
            "- Add or update implementation, tests, and reviewer evidence so the promotion gate reaches at least 0.85.",
            "- If a low score is caused by missing evidence rather than missing code, add deterministic verification evidence.",
            "- Stop only if a real external blocker exists.",
            "",
            "## Original Phase Requirements",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in phase.requirements)
    path = path.resolve()
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def phase_verification_issue_lines(result: dict[str, object]) -> list[str]:
    runtime_state = _dict(result.get("runtime_state"))
    task_graph = _dict(runtime_state.get("task_graph"))
    nodes = [dict(item) for item in _list(task_graph.get("nodes")) if isinstance(item, dict)]
    lines: list[str] = []
    for node in nodes:
        if str(node.get("type", "")).lower() not in {"test", "review"}:
            continue
        worker_result = latest_worker_result_from_task(node)
        if not worker_result_has_repair_issue(worker_result):
            continue
        task_id = str(node.get("id", "") or "unknown")
        title = str(node.get("title", "") or "").strip()
        heading = f"- Must repair {task_id} verification issue"
        if title:
            heading += f" ({title})"
        summary = str(worker_result.get("summary", "") or "").strip()
        if summary:
            heading += f": {summary}"
        else:
            heading += "."
        lines.append(heading)
        failed_commands = failed_command_summaries(worker_result)
        if failed_commands:
            lines.append(f"- Failed commands: {'; '.join(failed_commands)}.")
        for label, key in (
            ("Tests failed", "tests_failed"),
            ("Known issues", "known_issues"),
            ("Follow-up tasks", "follow_up_tasks"),
        ):
            values = dedupe_strings(str(item) for item in _list(worker_result.get(key)))[:6]
            if values:
                lines.append(f"- {label}: {'; '.join(values)}.")
        target_paths = repair_issue_target_paths(node, worker_result)
        if target_paths:
            lines.append(f"- Target files: {', '.join(target_paths)}.")
    return dedupe_strings(lines)


def worker_result_has_repair_issue(worker_result: dict[str, object]) -> bool:
    if not worker_result:
        return False
    if _list(worker_result.get("tests_failed")):
        return True
    for command in _list(worker_result.get("commands_run")):
        if isinstance(command, dict) and int_or_zero(command.get("exit_code")) != 0:
            return True
    status = str(worker_result.get("status", "")).lower()
    if status in REPAIR_WORKER_STATUSES:
        return True
    if status not in SUCCESSFUL_WORKER_STATUSES and (
        _list(worker_result.get("known_issues")) or _list(worker_result.get("follow_up_tasks"))
    ):
        return True
    return False


def state_has_clean_test_verification(state: dict[str, object]) -> bool:
    task_graph = _dict(state.get("task_graph"))
    nodes = [dict(item) for item in _list(task_graph.get("nodes")) if isinstance(item, dict)]
    for node in nodes:
        if str(node.get("type", "")).lower() != "test":
            continue
        worker_result = latest_worker_result_from_task(node)
        if not worker_result:
            continue
        if worker_result_has_repair_issue(worker_result):
            continue
        if str(worker_result.get("status", "")).lower() in SUCCESSFUL_WORKER_STATUSES:
            return True
    return False


def failed_command_summaries(worker_result: dict[str, object]) -> list[str]:
    summaries: list[str] = []
    for command in _list(worker_result.get("commands_run")):
        if not isinstance(command, dict):
            continue
        if int_or_zero(command.get("exit_code")) == 0:
            continue
        command_text = str(command.get("command", "") or "").strip()
        details = " ".join(
            str(command.get(key, "") or "").strip()
            for key in ("summary", "stderr", "stdout")
            if str(command.get(key, "") or "").strip()
        )
        text = command_text
        if details:
            text = f"{text}: {short_repair_text(details)}" if text else short_repair_text(details)
        if text:
            summaries.append(text)
    return dedupe_strings(summaries)[:4]


def repair_issue_target_paths(node: dict[str, object], worker_result: dict[str, object]) -> list[str]:
    texts: list[str] = []
    for key in ("summary", "tests_failed", "known_issues", "follow_up_tasks", "evidence"):
        value = worker_result.get(key)
        if isinstance(value, str):
            texts.append(value)
        else:
            texts.extend(str(item) for item in _list(value))
    for command in _list(worker_result.get("commands_run")):
        if not isinstance(command, dict):
            continue
        texts.extend(
            str(command.get(key, "") or "")
            for key in ("command", "summary", "stderr", "stdout")
            if str(command.get(key, "") or "")
        )
    texts.extend(str(item) for item in _list(node.get("relevant_files")))
    return dedupe_strings(
        normalize_repair_path(match.group("path"))
        for text in texts
        for match in REPAIR_EVIDENCE_PATH_PATTERN.finditer(text)
    )[:12]


def normalize_repair_path(path: str) -> str:
    return str(path).replace("\\", "/").strip().strip("`").strip().strip(".").strip("/")


def short_repair_text(text: str, *, limit: int = 240) -> str:
    clean = " ".join(text.split())
    return clean if len(clean) <= limit else clean[: limit - 3].rstrip() + "..."


def phase_focused_repair_lines(result: dict[str, object], blockers: Sequence[object]) -> list[str]:
    runtime_state = _dict(result.get("runtime_state"))
    task_graph = _dict(runtime_state.get("task_graph"))
    nodes = [dict(item) for item in _list(task_graph.get("nodes")) if isinstance(item, dict)]
    nodes_by_id = {str(node.get("id", "")): node for node in nodes if str(node.get("id", ""))}
    focus_task_ids = repair_focus_task_ids(blockers, nodes)
    debug_parent_focus_ids = repair_debug_parent_focus_task_ids(blockers, nodes_by_id)
    completed_task_ids = repair_completed_task_ids(
        runtime_state,
        nodes,
        focus_task_ids,
        protected_dependency_focus_task_ids=debug_parent_focus_ids,
    )
    lines = ["", "## Focused Repair Scope", ""]
    if focus_task_ids:
        lines.append(f"- Primary failed task IDs: {', '.join(focus_task_ids)}.")
    else:
        lines.append("- Primary failed task IDs: none reported; infer the narrowest failing task from the gate evidence.")
    if completed_task_ids:
        lines.append(f"- Completed tasks to preserve: {', '.join(completed_task_ids)}.")
    lines.extend(
        [
            "- Do not regenerate a broad phase graph when blocker task IDs identify a specific failed task.",
            "- Convert out-of-scope full-suite failures into focused follow-up tasks with expanded allowed files.",
            "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
        ]
    )
    for task_id in focus_task_ids:
        task = nodes_by_id.get(task_id, {"id": task_id})
        lines.extend(repair_task_focus_lines(task_id, task))
    return lines


def repair_focus_task_ids(blockers: Sequence[object], nodes: Sequence[dict[str, object]]) -> list[str]:
    nodes_by_id = {str(node.get("id", "")): node for node in nodes if str(node.get("id", ""))}
    task_ids: list[str] = []
    for blocker in blockers:
        if not isinstance(blocker, dict):
            continue
        task_ids.extend(str(item) for item in _list(blocker.get("task_ids")))
    if task_ids:
        return normalize_repair_focus_task_ids(task_ids, nodes_by_id)
    failed_statuses = {"failed", "blocked", "timed_out", "cancelled"}
    return normalize_repair_focus_task_ids(
        [
            str(node.get("id", ""))
            for node in nodes
            if str(node.get("status", "")).lower() in failed_statuses
        ],
        nodes_by_id,
    )


def normalize_repair_focus_task_ids(task_ids: Sequence[str], nodes_by_id: dict[str, dict[str, object]]) -> list[str]:
    normalized: list[str] = []
    for task_id in task_ids:
        clean = str(task_id or "").strip()
        if not clean:
            continue
        normalized.append(repair_focus_root_task_id(clean, nodes_by_id))
    return dedupe_strings(normalized)


def repair_debug_parent_focus_task_ids(
    blockers: Sequence[object],
    nodes_by_id: dict[str, dict[str, object]],
) -> list[str]:
    mapped: list[str] = []
    for blocker in blockers:
        if not isinstance(blocker, dict):
            continue
        for item in _list(blocker.get("task_ids")):
            task_id = str(item or "").strip()
            if not task_id:
                continue
            root_id = repair_focus_root_task_id(task_id, nodes_by_id)
            if root_id != task_id:
                mapped.append(root_id)
    return dedupe_strings(mapped)


def repair_focus_root_task_id(task_id: str, nodes_by_id: dict[str, dict[str, object]]) -> str:
    node = nodes_by_id.get(task_id)
    if node and str(node.get("type", "")).lower() != "debug":
        return task_id
    current = task_id
    while "-DEBUG-" in current:
        current = current.rsplit("-DEBUG-", 1)[0]
        parent = nodes_by_id.get(current)
        if not parent or str(parent.get("type", "")).lower() != "debug":
            return current
    return task_id


def task_dependency_closure(task_ids: Sequence[str], nodes_by_id: dict[str, dict[str, object]]) -> list[str]:
    seen: list[str] = []

    def visit(task_id: str) -> None:
        for dependency in _list(nodes_by_id.get(task_id, {}).get("dependencies")):
            dep_id = str(dependency or "").strip()
            if dep_id and dep_id not in seen:
                visit(dep_id)
                seen.append(dep_id)

    for task_id in task_ids:
        visit(task_id)
    return seen


def repair_preserve_dependency_completed_task_ids(
    focus_task_ids: Sequence[str],
    nodes_by_id: dict[str, dict[str, object]],
) -> list[str]:
    return [
        task_id
        for task_id in task_dependency_closure(focus_task_ids, nodes_by_id)
        if str(nodes_by_id.get(task_id, {}).get("status", "")).lower() in {"done", "completed"}
    ]


def repair_completed_task_ids(
    runtime_state: dict[str, Any],
    nodes: Sequence[dict[str, object]],
    focus_task_ids: Sequence[str] = (),
    *,
    protected_dependency_focus_task_ids: Sequence[str] = (),
) -> list[str]:
    nodes_by_id = {str(node.get("id", "")): node for node in nodes if str(node.get("id", ""))}
    completed = repair_preserve_dependency_completed_task_ids(focus_task_ids, nodes_by_id)
    completed.extend(str(item) for item in _list(runtime_state.get("completed_tasks")))
    completed.extend(
        str(node.get("id", ""))
        for node in nodes
        if str(node.get("status", "")).lower() in {"done", "completed"}
    )
    completed.extend(partial_downstream_handoff_completed_task_ids(nodes))
    completed_ids = dedupe_strings(completed)
    reopen_ids = repair_completed_task_ids_to_reopen(nodes, completed_ids)
    if reopen_ids and protected_dependency_focus_task_ids:
        protected_ids = set(repair_preserve_dependency_completed_task_ids(protected_dependency_focus_task_ids, nodes_by_id))
        reopen_ids = {task_id for task_id in reopen_ids if task_id not in protected_ids}
    if reopen_ids:
        completed_ids = [task_id for task_id in completed_ids if task_id not in reopen_ids]
    return completed_ids


def partial_downstream_handoff_completed_task_ids(nodes: Sequence[dict[str, object]]) -> list[str]:
    task_nodes = [dict(node) for node in nodes]
    completed: list[str] = []
    for node in task_nodes:
        task_id = str(node.get("id", "") or "").strip()
        if not task_id or str(node.get("type", "")).lower() == "debug":
            continue
        worker_result = latest_worker_result_from_task(node)
        if str(worker_result.get("status", "")).lower() != "partial":
            continue
        if not worker_result_has_scoped_progress(worker_result):
            continue
        target_paths = repair_result_target_paths(worker_result)
        if not target_paths:
            continue
        downstream = [
            candidate
            for candidate in task_nodes
            if task_id in [str(item) for item in _list(candidate.get("dependencies"))]
            and str(candidate.get("type", "")).lower() != "debug"
        ]
        if any(task_scope_matches_paths(candidate, target_paths) for candidate in downstream):
            completed.append(task_id)
    return dedupe_strings(completed)


def worker_result_has_scoped_progress(worker_result: dict[str, object]) -> bool:
    if _list(worker_result.get("files_changed")) or _list(worker_result.get("tests_passed")):
        return True
    for command in _list(worker_result.get("commands_run")):
        if isinstance(command, dict) and int_or_zero(command.get("exit_code")) == 0:
            return True
    return False


def repair_completed_task_ids_to_reopen(
    nodes: Sequence[dict[str, object]],
    completed_task_ids: Sequence[str],
) -> set[str]:
    if not completed_task_ids:
        return set()
    task_nodes = [dict(node) for node in nodes]
    nodes_by_id = {str(node.get("id", "") or ""): node for node in task_nodes}
    target_paths = unresolved_repair_target_paths(task_nodes)
    if not target_paths:
        return set()
    reopen_ids: set[str] = set()
    for task_id in completed_task_ids:
        task = nodes_by_id.get(str(task_id))
        if not task:
            continue
        if task_scope_matches_paths(task, target_paths):
            reopen_ids.add(str(task_id))
    return reopen_ids


def unresolved_repair_target_paths(nodes: Sequence[dict[str, object]]) -> list[str]:
    target_paths: list[str] = []
    unresolved_statuses = {"failed", "blocked", "timed_out", "cancelled"}
    for node in nodes:
        status = str(node.get("status", "") or "").lower()
        worker_result = latest_worker_result_from_task(node)
        if not worker_result:
            continue
        worker_status = str(worker_result.get("status", "") or "").lower()
        if status not in unresolved_statuses and worker_status not in REPAIR_WORKER_STATUSES:
            continue
        target_paths.extend(repair_result_target_paths(worker_result, include_raw_output=False))
    return dedupe_strings(target_paths)


def repair_result_target_paths(worker_result: dict[str, object], *, include_raw_output: bool = True) -> list[str]:
    texts: list[str] = []
    keys = ["tests_failed", "known_issues", "follow_up_tasks", "evidence"]
    summary = str(worker_result.get("summary", "") or "")
    if not summary.lower().startswith("codex cli usage limit reached:"):
        keys.insert(0, "summary")
    if include_raw_output:
        keys.append("raw_output")
    for key in keys:
        value = worker_result.get(key)
        if isinstance(value, str):
            texts.append(value)
        else:
            texts.extend(str(item) for item in _list(value))
    if include_raw_output:
        for command in _list(worker_result.get("commands_run")):
            if not isinstance(command, dict):
                continue
            texts.extend(
                str(command.get(key, "") or "")
                for key in ("command", "summary", "stderr", "stdout")
                if str(command.get(key, "") or "")
            )
    return dedupe_strings(
        normalize_repair_path(match.group("path"))
        for text in texts
        for match in REPAIR_EVIDENCE_PATH_PATTERN.finditer(text)
    )[:12]


def task_scope_matches_paths(task: dict[str, object], paths: Sequence[str]) -> bool:
    scope_patterns = [normalize_repair_path(str(item)) for item in _list(task.get("relevant_files"))]
    if not scope_patterns:
        return False
    for path in paths:
        for variant in repair_path_variants(path):
            if any(repair_path_matches_pattern(variant, pattern) for pattern in scope_patterns):
                return True
    return False


def repair_path_variants(path: str) -> list[str]:
    normalized = normalize_repair_path(path)
    if not normalized:
        return []
    variants = {normalized}
    if normalized.startswith("internal/") or normalized.startswith("cmd/") or normalized.startswith("ent/"):
        variants.add(f"backend/{normalized}")
    if normalized.startswith("src/"):
        variants.add(f"frontend/{normalized}")
    return sorted(variants)


def repair_path_matches_pattern(path: str, pattern: str) -> bool:
    normalized = normalize_repair_path(path).lower()
    clean = normalize_repair_path(pattern).lower()
    if not normalized or not clean:
        return False
    if clean.endswith("/**"):
        prefix = clean[:-3].rstrip("/")
        return normalized == prefix or normalized.startswith(prefix + "/")
    if clean.endswith("/*"):
        prefix = clean[:-2].rstrip("/")
        if not normalized.startswith(prefix + "/"):
            return False
        return "/" not in normalized[len(prefix) + 1 :]
    if clean.endswith("/"):
        return normalized.startswith(clean)
    if any(char in clean for char in "*?["):
        return PurePosixPath(normalized).match(clean)
    return normalized == clean


def repair_task_focus_lines(task_id: str, task: dict[str, object]) -> list[str]:
    title = str(task.get("title", "") or "").strip()
    status = str(task.get("status", "") or "").strip()
    result = latest_worker_result_from_task(task)
    lines = ["", f"### Task {task_id}{f' - {title}' if title else ''}", ""]
    if title:
        lines.append(f"- Must continue focused task {task_id}: {title}.")
    if status:
        lines.append(f"- Last task status: {status}.")
    relevant_files = dedupe_strings(str(item) for item in _list(task.get("relevant_files")))
    if relevant_files:
        lines.append(f"- Previous relevant files: {', '.join(relevant_files)}.")
    retry_count = task.get("retry_count")
    retry_policy = _dict(task.get("retry_policy"))
    if retry_count is not None or retry_policy:
        max_attempts = retry_policy.get("max_attempts", retry_policy.get("attempts", "unknown"))
        lines.append(f"- Retry state: {retry_count if retry_count is not None else 'unknown'} of {max_attempts} attempts used.")
    if result:
        summary = str(result.get("summary", "") or "").strip()
        if summary:
            lines.append(f"- Worker summary: {summary}")
        for label, key in (
            ("Tests passed", "tests_passed"),
            ("Tests failed", "tests_failed"),
            ("Known issues", "known_issues"),
            ("Follow-up tasks", "follow_up_tasks"),
            ("Files changed", "files_changed"),
        ):
            values = dedupe_strings(str(item) for item in _list(result.get(key)))
            if values:
                lines.append(f"- {label}:")
                lines.extend(f"  - {item}" for item in values)
        lifecycle = _dict(result.get("worker_lifecycle"))
        timeout_seconds = lifecycle.get("timeout_seconds")
        timed_out_at = str(lifecycle.get("timed_out_at", "") or "").strip()
        if timeout_seconds or timed_out_at or str(result.get("status", "")).lower() == "timed_out":
            lines.append(
                "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout."
            )
    else:
        lines.append("- Worker result: none recorded for this task; inspect task evidence before widening scope.")
    return lines


def latest_worker_result_from_task(task: dict[str, object]) -> dict[str, object]:
    for evidence in reversed(_list(task.get("evidence"))):
        if not isinstance(evidence, dict):
            continue
        if str(evidence.get("type", "")) != "worker_result":
            continue
        result = _dict(evidence.get("result"))
        if result:
            return result
    return {}


def should_auto_repair_phase(promotion: dict[str, object], result: dict[str, object]) -> bool:
    """Return true when another autonomous phase attempt is useful and safe."""

    if bool(promotion.get("can_promote")):
        return False
    status = str(result.get("status", "") or "")
    blockers = phase_result_blockers(result)
    if blockers:
        if phase_has_worker_timeout_stop_boundary(result):
            return False
        return status == "blocked" and blockers_are_auto_repairable(blockers)
    delivery = _dict(result.get("delivery_report"))
    final_gate = _dict(delivery.get("final_gate"))
    score = float_or_zero(promotion.get("score", final_gate.get("score", final_gate.get("final_score"))))
    required_score = float_or_zero(promotion.get("required_score", 0.85))
    hard_failures = _list(final_gate.get("hard_failures"))
    required_changes = _list(final_gate.get("required_changes"))
    dimensions = _dict(final_gate.get("dimension_scores"))
    has_low_dimension = any(float_or_zero(value) < required_score for value in dimensions.values())
    repair_texts = [*hard_failures, *required_changes]
    if repair_texts and not blockers_are_auto_repairable(repair_texts):
        return False
    return status in {"done", "blocked"} and (
        (score > 0 and score < required_score)
        or bool(required_changes)
        or bool(hard_failures)
        or has_low_dimension
    )


def phase_has_worker_timeout_stop_boundary(result: dict[str, object]) -> bool:
    for blocker in phase_result_blockers(result):
        if not isinstance(blocker, dict):
            continue
        if blocker.get("can_continue_partially") is not False:
            continue
        description = str(blocker.get("description", blocker.get("summary", "")) or "").lower()
        if any(marker in description for marker in WORKER_TIMEOUT_STOP_MARKERS):
            return True
    return False


def phase_has_non_partial_stop_boundary(result: dict[str, object]) -> bool:
    for blocker in phase_result_blockers(result):
        if isinstance(blocker, dict) and blocker.get("can_continue_partially") is False:
            return True
    return False


def phase_result_blockers(result: dict[str, object]) -> list[object]:
    runtime_state = _dict(result.get("runtime_state"))
    return [*(_list(result.get("blockers"))), *(_list(runtime_state.get("blockers")))]


def blockers_are_auto_repairable(blockers: Sequence[object]) -> bool:
    if not blockers:
        return False
    return all(blocker_is_auto_repairable(blocker) for blocker in blockers)


def blocker_is_auto_repairable(blocker: object) -> bool:
    if isinstance(blocker, str):
        text = blocker.lower()
        return bool(text.strip()) and not any(marker in text for marker in NON_REPAIRABLE_BLOCKER_MARKERS)
    if not isinstance(blocker, dict):
        return False
    blocker_type = str(blocker.get("type", "") or "").lower()
    blocker_id = str(blocker.get("id", "") or "").upper()
    description = str(blocker.get("description", blocker.get("summary", "")) or "").lower()
    if blocker_id in {"B-PREFLIGHT", "B-RECOVERY", "B-RUN-STOPPED"}:
        return False
    if blocker_type in {"environment", "operator_control", "credentials", "external_dependency", "policy"}:
        return False
    if any(marker in description for marker in NON_REPAIRABLE_BLOCKER_MARKERS):
        return False
    return blocker_type in {"", "technical_limit", "quality_gate", "test_failure", "implementation"}


def repairable_blocker_summaries(blockers: Sequence[object]) -> list[str]:
    summaries: list[str] = []
    for blocker in blockers:
        if isinstance(blocker, str):
            if blocker.strip():
                summaries.append(blocker.strip())
            continue
        if not isinstance(blocker, dict):
            continue
        blocker_id = str(blocker.get("id", "blocker") or "blocker")
        description = str(blocker.get("description", blocker.get("summary", "")) or "").strip()
        task_ids = ", ".join(str(item) for item in _list(blocker.get("task_ids")) if str(item).strip())
        suffix = f" (tasks: {task_ids})" if task_ids else ""
        summaries.append(f"{blocker_id}: {description}{suffix}".strip())
    return dedupe_strings(summaries)


def normalized_scope_controls(payload: dict[str, object] | None) -> dict[str, list[str]]:
    payload = dict(payload or {})
    return {
        "allowed_prefixes": [str(item) for item in payload.get("allowed_prefixes", []) or []],
        "protected_prefixes": [str(item) for item in payload.get("protected_prefixes", []) or []],
        "target_files": [str(item) for item in payload.get("target_files", []) or []],
        "boundary_mode": [str(payload.get("boundary_mode", "strict") or "strict")],
    }


def phase_objective(root_objective: str, phase: RoadmapPhase) -> str:
    return (
        f"{root_objective}\n\n"
        f"Current full-roadmap phase: {phase.phase_id} {phase.title}. "
        "Complete this phase only, then return evidence for central promotion. "
        "Do not treat this phase as final delivery if later required phases remain."
    )


def next_phase_run_dir(phase_dir: Path) -> Path:
    """Return a clean run directory while preserving interrupted attempts."""

    default = phase_dir / "run"
    if not default.exists():
        return default
    record_path = phase_dir / "phase_record.json"
    if record_path.exists():
        record = read_json(record_path)
        if isinstance(record, dict) and str(record.get("status", "")).lower() in {"done", "completed"}:
            return default
        # Blocked/failed phase records are resume checkpoints. Keep the old run
        # directory intact and put the retried phase attempt in a fresh output.
        for index in range(2, 1000):
            candidate = phase_dir / f"run_attempt_{index:03d}"
            if not candidate.exists():
                return candidate
        raise RuntimeError(f"Too many interrupted attempts for {phase_dir}")
    for index in range(2, 1000):
        candidate = phase_dir / f"run_attempt_{index:03d}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Too many interrupted attempts for {phase_dir}")


def next_final_verification_attempt_index(output_dir: Path) -> int:
    existing: list[int] = []
    for path in output_dir.glob("run_attempt_*"):
        if not path.is_dir():
            continue
        try:
            existing.append(int(path.name.rsplit("_", 1)[-1]))
        except ValueError:
            continue
    return max(existing, default=0) + 1


def next_final_verification_repair_resume_path(output_dir: Path) -> Path:
    for index in range(1, 1000):
        candidate = output_dir / f"final_verification_repair_resume_{index:03d}.md"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Too many final verification repair resume documents for {output_dir}")


def final_verification_resume_repair_documents(output_dir: Path) -> list[str]:
    existing = sorted(output_dir.glob("final_verification_repair_resume_*.md"))
    report = read_optional_json(output_dir / "final_verification_worker_report.json")
    if str(report.get("status", "")).lower() != "failed":
        return [str(existing[-1].resolve())] if existing else []
    report_text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    lowered = report_text.lower()
    repair_markers = [
        "final_audit_status=fail",
        "source-boundary",
        "allowed_files",
        "worker timeout",
        "timed out",
        "exceeded the codex worker timeout",
        "operator stop request",
        "supervisor",
        "outside the task boundary",
        "out-of-scope",
    ]
    if not any(token in lowered for token in repair_markers):
        return [str(existing[-1].resolve())] if existing else []
    attempt_marker = final_verification_report_attempt_marker(report)
    result = _dict(report.get("result"))
    runtime_state = _dict(result.get("runtime_state"))
    blockers = [*(_list(result.get("blockers"))), *(_list(runtime_state.get("blockers")))]
    focused_lines = phase_focused_repair_lines(result, blockers)
    if existing and (
        not attempt_marker
        or final_verification_repair_resume_matches_focus(existing[-1], attempt_marker, focused_lines)
    ):
        return [str(existing[-1].resolve())]
    path = next_final_verification_repair_resume_path(output_dir)
    lines = [
        "# Final Verification Repair Resume",
        "",
        f"Repair attempt: {attempt_marker or 'latest failed final verification attempt'}",
        "",
        "## Requirements",
        "",
        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
        "- Must preserve completed final-verification tasks from the failed attempt unless a focused failed-task dependency requires a scoped edit.",
        "- Must grant the repair worker edit access to backend migrations, Ent schema/generated files, backend domain/repository/service/handler/server contracts, and backend command wiring when those surfaces contain residual relay-era product concepts.",
        "- Must split backend schema/domain repair by Ent schema, domain/repository, and service/handler/server wiring instead of replaying one broad worker.",
        "- Must grant the repair worker edit access to frontend API, i18n, router, view, component, composable, constants, type, store, and test files when those surfaces contain upstream account, proxy, channel, channel-monitor, model-routing, or subscription-plan behavior.",
        "- Implementation repair tasks must use narrow static or package-level checks; broad Go/frontend verification is reserved for final real repository checks.",
        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
        "- Must report FINAL_AUDIT_STATUS, SIMULATION_TEST_STATUS, REAL_TEST_STATUS, REQUIRED_ACTIONS, and BLOCKERS after repair.",
        *focused_lines,
        "",
        "## Previous Final Verification Failure",
        "",
        "```json",
        report_text[:12000],
        "```",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return [str(path.resolve())]


def final_verification_report_attempt_marker(report: dict[str, object]) -> str:
    attempts = [item for item in _list(report.get("attempts")) if isinstance(item, dict)]
    if not attempts:
        return ""
    latest = attempts[-1]
    attempt = latest.get("attempt")
    output_dir = str(latest.get("output_dir", "") or "")
    if attempt is None:
        return Path(output_dir).name if output_dir else ""
    try:
        return f"run_attempt_{int(attempt):03d}"
    except (TypeError, ValueError):
        return str(attempt)


def final_verification_repair_resume_mentions(path: Path, marker: str) -> bool:
    if not marker:
        return False
    try:
        return marker in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def final_verification_repair_resume_matches_focus(path: Path, marker: str, focused_lines: Sequence[str]) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if marker not in text:
        return False
    focus_requirements = [line for line in focused_lines if line.startswith("- Primary failed task IDs:")]
    return all(line in text for line in focus_requirements)


def interrupted_phase_resume_source(phase_dir: Path) -> InterruptedPhaseResume:
    """Find the newest interrupted active attempt that can be resumed safely."""

    for run_dir in reversed(list_phase_run_dirs(phase_dir)):
        if supervisor_stop_marker_exists(run_dir):
            return InterruptedPhaseResume()
        state = read_optional_json(run_dir / "state.json")
        active_task_ids = active_task_ids_from_state(state)
        if not active_task_ids:
            if state:
                return InterruptedPhaseResume()
            continue
        lifecycle_records = worker_lifecycle_records_for(run_dir, state, active_task_ids)
        live_records = [
            record
            for record in lifecycle_records
            if str(record.get("status", "")).lower() == "running" and process_exists(_int_or_none(record.get("worker_pid")))
        ]
        if live_records:
            descriptions = [
                f"{record.get('task_id', 'unknown')} pid={record.get('worker_pid')}"
                for record in live_records
            ]
            return InterruptedPhaseResume(
                active_run_dir=run_dir,
                blockers=[
                    "Previous phase attempt still has live worker process(es): "
                    + ", ".join(descriptions)
                    + ". Stop or wait for those workers before starting another resume."
                ],
            )
        if active_tasks_have_terminal_lifecycle(active_task_ids, lifecycle_records):
            return InterruptedPhaseResume()
        if active_debug_tasks_have_dead_running_lifecycle(active_task_ids, lifecycle_records):
            return InterruptedPhaseResume()
        return InterruptedPhaseResume(resume_from=run_dir, active_run_dir=run_dir)
    return InterruptedPhaseResume()


def list_phase_run_dirs(phase_dir: Path) -> list[Path]:
    candidates: list[Path] = []
    default = phase_dir / "run"
    if default.exists():
        candidates.append(default)
    candidates.extend(sorted(phase_dir.glob("run_attempt_*"), key=_phase_run_sort_key))
    return candidates


def supervisor_stop_marker_exists(run_dir: Path) -> bool:
    return any((run_dir / name).exists() for name in ("supervisor_stop.json", "operator_stop.json"))


def active_task_ids_from_state(state: dict[str, object]) -> list[str]:
    active_ids = dedupe_strings(str(item.get("task_id", "")) if isinstance(item, dict) else str(item) for item in _list(state.get("active_tasks", [])))
    if active_ids:
        return active_ids
    task_graph = _dict(state.get("task_graph"))
    nodes = _list(task_graph.get("nodes"))
    return dedupe_strings(
        str(node.get("id", ""))
        for node in nodes
        if isinstance(node, dict) and str(node.get("status", "")).lower() == "active"
    )


def worker_lifecycle_records_for(run_dir: Path, state: dict[str, object], task_ids: Sequence[str]) -> list[dict[str, object]]:
    wanted = {str(task_id) for task_id in task_ids}
    records: list[dict[str, object]] = []
    for record in _list(state.get("worker_lifecycle", [])):
        if isinstance(record, dict) and str(record.get("task_id", "")) in wanted:
            records.append(dict(record))
    workers_dir = run_dir / "workers"
    if workers_dir.exists():
        for path in sorted(workers_dir.glob("*.json")):
            payload = read_optional_json(path)
            if str(payload.get("task_id", "")) in wanted:
                records.append(payload)
    return records


def active_tasks_have_terminal_lifecycle(task_ids: Sequence[str], records: Sequence[dict[str, object]]) -> bool:
    terminal_task_ids = {
        str(record.get("task_id", ""))
        for record in records
        if str(record.get("status", "")).lower() in {"completed", "failed", "timed_out", "cancelled"}
    }
    return bool(task_ids) and all(str(task_id) in terminal_task_ids for task_id in task_ids)


def active_debug_tasks_have_dead_running_lifecycle(task_ids: Sequence[str], records: Sequence[dict[str, object]]) -> bool:
    wanted = {str(task_id) for task_id in task_ids if str(task_id)}
    if not wanted or not all(_is_debug_task_id(task_id) for task_id in wanted):
        return False

    running_task_ids: set[str] = set()
    for record in records:
        task_id = str(record.get("task_id", ""))
        if task_id not in wanted or str(record.get("status", "")).lower() != "running":
            continue
        running_task_ids.add(task_id)
        if process_exists(_int_or_none(record.get("worker_pid"))):
            return False
    return running_task_ids == wanted


def _is_debug_task_id(task_id: str) -> bool:
    return "-DEBUG-" in task_id or task_id.endswith("-DEBUG")


def _phase_run_sort_key(path: Path) -> tuple[int, str]:
    if path.name == "run":
        return (1, path.name)
    suffix = path.name.removeprefix("run_attempt_")
    try:
        return (int(suffix), path.name)
    except ValueError:
        return (999_999, path.name)


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def source_mode_for(primary_input_mode: str, *, repository_url: str, repository_path: str | Path | None) -> str:
    if repository_url:
        return "github_repo"
    if repository_path:
        return "local_repo"
    if primary_input_mode == "one_line_fallback":
        return "one_sentence"
    return "uploaded_docs"


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_running_report(
    path: Path,
    *,
    plan: RoadmapExecutionPlan,
    roadmap_audit: dict[str, object],
    project_analysis: dict[str, object],
    document_expansion: dict[str, object],
    generated_development_package: dict[str, object],
    phase_records: Sequence[PhaseExecutionRecord],
    active_phase: RoadmapPhase | None,
) -> None:
    """Persist a live full-roadmap snapshot so monitors do not show stale blockers."""

    active = (
        {
            "phase_id": active_phase.phase_id,
            "title": active_phase.title,
            "status": active_phase.status,
        }
        if active_phase is not None
        else {}
    )
    payload = FullRoadmapExecutionResult(
        status="running",
        roadmap=plan.to_dict(),
        roadmap_audit=roadmap_audit,
        project_analysis=project_analysis,
        document_expansion=document_expansion,
        phase_records=[record.to_dict() for record in phase_records],
        generated_development_package=generated_development_package,
        output_dir=str(path.parent),
    ).to_dict()
    payload["active_phase"] = active
    payload["updated_at"] = datetime.now(UTC).isoformat()
    write_json(path, payload)


@dataclass(slots=True)
class ResumeState:
    plan: RoadmapExecutionPlan
    roadmap_audit: dict[str, object]
    project_analysis: dict[str, object]
    document_expansion: dict[str, object]
    generated_development_package: dict[str, object]
    phase_records: list[PhaseExecutionRecord]
    documents: list[str]


def load_resume_state(output: Path) -> ResumeState | None:
    plan_path = output / "roadmap_execution_plan.json"
    final_report_path = output / "full_roadmap_report.json"
    if not plan_path.exists():
        return None
    if final_report_path.exists() and _final_report_is_complete(final_report_path):
        return None
    payload = read_json(plan_path)
    if not isinstance(payload, dict):
        return None
    plan = RoadmapExecutionPlan.from_dict(payload)
    records = load_phase_records(output)
    if not records and not any(phase.status in {"completed", "running"} for phase in plan.phases):
        return None
    expansion = read_optional_json(output / "expanded_document_index.json")
    documents = [str(item) for item in expansion.get("documents", [])] if isinstance(expansion.get("documents"), list) else []
    return ResumeState(
        plan=plan,
        roadmap_audit=read_optional_json(output / "roadmap_audit.json") or {"status": "passed", "issues": []},
        project_analysis=read_optional_json(output / "project_analysis_report.json"),
        document_expansion=expansion,
        generated_development_package=read_optional_json(output / "generated_development_package" / "development_package.json"),
        phase_records=records,
        documents=documents,
    )


def _final_report_is_complete(final_report_path: Path) -> bool:
    payload = read_json(final_report_path)
    if not isinstance(payload, dict):
        return False
    return str(payload.get("status", "")).lower() == "done"


def load_phase_records(output: Path) -> list[PhaseExecutionRecord]:
    records: list[PhaseExecutionRecord] = []
    phases_dir = output / "phases"
    if not phases_dir.exists():
        return records
    for record_path in sorted(phases_dir.glob("phase_*/phase_record.json")):
        payload = read_json(record_path)
        if not isinstance(payload, dict):
            continue
        records.append(
            PhaseExecutionRecord(
                phase_id=str(payload.get("phase_id", "")),
                title=str(payload.get("title", "")),
                status=str(payload.get("status", "")),
                output_dir=str(payload.get("output_dir", record_path.parent)),
                result=dict(payload.get("result", {}) if isinstance(payload.get("result"), dict) else {}),
                promotion=dict(payload.get("promotion", {}) if isinstance(payload.get("promotion"), dict) else {}),
            )
        )
    return records


def sync_plan_status_from_records(plan: RoadmapExecutionPlan, records: Sequence[PhaseExecutionRecord]) -> None:
    status_by_phase = {record.phase_id: record.status for record in records}
    for phase in plan.phases:
        record_status = status_by_phase.get(phase.phase_id)
        if record_status in {"done", "completed"}:
            phase.status = "completed"
        elif record_status in {"blocked", "failed"}:
            phase.status = "pending"
        elif phase.status == "running":
            phase.status = "pending"


def read_optional_json(path: Path) -> dict[str, object]:
    payload = read_json(path)
    return dict(payload) if isinstance(payload, dict) else {}


def read_json(path: Path) -> object:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def float_or_zero(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def int_or_zero(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def dedupe_strings(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
