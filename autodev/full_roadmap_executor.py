"""Full-roadmap execution loop built on top of existing document runs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Sequence

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
    "live worker process",
    "preflight",
    "recovery",
    "operator",
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
                if not should_auto_repair_phase(promotion, phase_payload):
                    phase.status = "blocked"
                    blockers.extend(str(item) for item in promotion.get("reasons", []) or [])
                    break
                repair_attempt_index = len(repair_documents) + 1
                if repair_attempt_index > max_phase_repair_attempts:
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

        if phase_count >= max_phases:
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
        repair_documents: list[str] = []
        max_attempts = max(1, int(run_payload.get("max_final_verification_attempts", 2) or 2))
        payload: dict[str, object] = {}
        promotion: dict[str, object] = {}
        for attempt_index in range(1, max_attempts + 1):
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
                repository_path=repository_path,
                repository_visibility=repository_visibility,
                output_dir=attempt_dir,
                run_payload=run_payload,
            )
            payload = payload_result.to_dict() if hasattr(payload_result, "to_dict") else dict(payload_result)
            promotion = phase_promotion_decision(final_phase, payload)
            attempt_record = {
                "attempt": attempt_index,
                "output_dir": str(attempt_dir),
                "promotion": promotion,
                "status": "done" if promotion["can_promote"] else "blocked",
            }
            attempts.append(attempt_record)
            write_json(output_dir / f"attempt_{attempt_index:03d}.json", attempt_record)
            if promotion["can_promote"]:
                break
            if attempt_index >= max_attempts or not should_auto_repair_phase(promotion, payload):
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

    if max_repair_documents <= 0 or previous_record is None:
        return []
    if str(previous_record.status).lower() not in {"blocked", "failed"}:
        return []
    if not should_auto_repair_phase(previous_record.promotion, previous_record.result):
        return []
    path = next_phase_repair_resume_path(phase_dir)
    return [
        write_phase_repair_document(
            path,
            phase=phase,
            result=previous_record.result,
            promotion=previous_record.promotion,
            attempt_index=1,
        )
    ]


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
    attempt_index: int,
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


def phase_focused_repair_lines(result: dict[str, object], blockers: Sequence[object]) -> list[str]:
    runtime_state = _dict(result.get("runtime_state"))
    task_graph = _dict(runtime_state.get("task_graph"))
    nodes = [dict(item) for item in _list(task_graph.get("nodes")) if isinstance(item, dict)]
    nodes_by_id = {str(node.get("id", "")): node for node in nodes if str(node.get("id", ""))}
    focus_task_ids = repair_focus_task_ids(blockers, nodes)
    completed_task_ids = repair_completed_task_ids(runtime_state, nodes)
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
    task_ids: list[str] = []
    for blocker in blockers:
        if not isinstance(blocker, dict):
            continue
        task_ids.extend(str(item) for item in _list(blocker.get("task_ids")))
    if task_ids:
        return dedupe_strings(task_ids)
    failed_statuses = {"failed", "blocked", "timed_out", "cancelled"}
    return dedupe_strings(
        str(node.get("id", ""))
        for node in nodes
        if str(node.get("status", "")).lower() in failed_statuses
    )


def repair_completed_task_ids(runtime_state: dict[str, Any], nodes: Sequence[dict[str, object]]) -> list[str]:
    completed = [str(item) for item in _list(runtime_state.get("completed_tasks"))]
    completed.extend(
        str(node.get("id", ""))
        for node in nodes
        if str(node.get("status", "")).lower() in {"done", "completed"}
    )
    return dedupe_strings(completed)


def repair_task_focus_lines(task_id: str, task: dict[str, object]) -> list[str]:
    title = str(task.get("title", "") or "").strip()
    status = str(task.get("status", "") or "").strip()
    result = latest_worker_result_from_task(task)
    lines = ["", f"### Task {task_id}{f' - {title}' if title else ''}", ""]
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
    runtime_state = _dict(result.get("runtime_state"))
    blockers = [*(_list(result.get("blockers"))), *(_list(runtime_state.get("blockers")))]
    if blockers:
        return status == "blocked" and blockers_are_auto_repairable(blockers)
    delivery = _dict(result.get("delivery_report"))
    final_gate = _dict(delivery.get("final_gate"))
    score = float_or_zero(promotion.get("score", final_gate.get("score", final_gate.get("final_score"))))
    required_score = float_or_zero(promotion.get("required_score", 0.85))
    hard_failures = _list(final_gate.get("hard_failures"))
    required_changes = _list(final_gate.get("required_changes"))
    dimensions = _dict(final_gate.get("dimension_scores"))
    has_low_dimension = any(float_or_zero(value) < required_score for value in dimensions.values())
    return status == "done" and (
        (score > 0 and score < required_score)
        or bool(required_changes)
        or bool(hard_failures)
        or has_low_dimension
    )


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
