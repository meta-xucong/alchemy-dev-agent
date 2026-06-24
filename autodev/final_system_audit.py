"""Final full-system audit for roadmap execution."""

from __future__ import annotations

from typing import Any

from .final_verification_loop import FinalVerificationLoop
from .phase_promotion import final_handoff_allowed
from .roadmap_models import PhaseExecutionRecord, RoadmapExecutionPlan


class FinalSystemAudit:
    """Prevent final handoff while roadmap work remains."""

    def audit(
        self,
        plan: RoadmapExecutionPlan,
        phase_records: list[PhaseExecutionRecord],
        *,
        worker_verification: dict[str, object] | None = None,
        run_payload: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        handoff = final_handoff_allowed(plan)
        failed_records = [record.phase_id for record in phase_records if record.status not in {"done", "completed"}]
        final_verification = FinalVerificationLoop().audit(
            plan,
            phase_records,
            worker_verification=worker_verification,
            run_payload=run_payload,
        )
        final_verification_payload = final_verification.to_dict()
        blockers: list[str] = []
        if not handoff["allowed"]:
            blockers.append(str(handoff["reason"]))
        if failed_records:
            blockers.append("One or more phase execution records are not complete.")
        if not final_verification.ready_for_final_handoff:
            blockers.append("Final audit/test convergence did not pass.")
            blockers.extend(final_verification_blockers(final_verification_payload))
        return {
            "status": "passed" if not blockers else "blocked",
            "ready_for_final_handoff": not blockers,
            "handoff": handoff,
            "failed_phase_records": failed_records,
            "final_verification": final_verification_payload,
            "blockers": dedupe_strings(blockers),
        }


def final_verification_blockers(payload: dict[str, object]) -> list[str]:
    """Return concrete final-verification blockers for parent reports."""

    blockers: list[str] = []
    for key in ("blockers", "required_actions"):
        value = payload.get(key, [])
        if not isinstance(value, list):
            continue
        blockers.extend(str(item) for item in value if str(item).strip())
    for key in ("dimensions", "test_stages"):
        value = payload.get(key, [])
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, dict) or item.get("status") != "failed":
                continue
            blockers.append(str(item.get("summary", "")))
            evidence = item.get("evidence", [])
            if isinstance(evidence, list):
                blockers.extend(str(entry) for entry in evidence if str(entry).strip())
    return dedupe_strings(blockers)


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
