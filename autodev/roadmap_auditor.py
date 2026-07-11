"""Audit and lightly repair roadmap execution plans."""

from __future__ import annotations

from .roadmap_models import RoadmapAuditResult, RoadmapExecutionPlan, RoadmapPhase


class RoadmapAuditor:
    """Validate that a roadmap can drive full autonomous execution."""

    def audit_and_repair(self, plan: RoadmapExecutionPlan) -> tuple[RoadmapExecutionPlan, RoadmapAuditResult]:
        issues: list[str] = []
        warnings: list[str] = []
        repaired = False
        if not plan.root_objective.strip():
            issues.append("Root objective is empty.")
        if plan.completion_policy not in {"full_roadmap", "goal_locked_full_roadmap"}:
            plan.completion_policy = "full_roadmap"
            repaired = True
        if not plan.phases:
            plan.phases.append(
                RoadmapPhase(
                    phase_id="phase_001",
                    title="Complete root objective",
                    requirements=[plan.root_objective or "Complete requested work."],
                )
            )
            repaired = True
        seen_ids: set[str] = set()
        for index, phase in enumerate(plan.phases, start=1):
            if not phase.phase_id or phase.phase_id in seen_ids:
                phase.phase_id = f"phase_{index:03d}"
                repaired = True
            seen_ids.add(phase.phase_id)
            if not phase.title.strip():
                phase.title = f"Phase {index}"
                repaired = True
            if not phase.requirements:
                phase.requirements = [phase.title]
                warnings.append(f"{phase.phase_id} had no requirements; title was used as fallback.")
                repaired = True
            if not phase.promotion_gate:
                phase.promotion_gate = {
                    "required_score": 0.85,
                    "required_tests_pass": True,
                    "central_review_decision": "handoff_for_phase",
                }
                repaired = True
        if not plan.final_acceptance:
            plan.final_acceptance = {
                "all_required_phases_complete": True,
                "final_system_audit_passes": True,
                "no_hard_blockers": True,
            }
            repaired = True
        if not plan.delivery_policy:
            plan.delivery_policy = {
                "mode": "local",
                "requires_user_approval_for_merge": True,
                "allow_public_repository": True,
                "allow_destructive_actions": False,
            }
            repaired = True
        status = "failed" if issues else "passed"
        return plan, RoadmapAuditResult(status=status, issues=issues, warnings=warnings, repaired=repaired)
