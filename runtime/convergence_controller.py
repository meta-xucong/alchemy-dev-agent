"""Strategy-aware convergence recovery decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from runtime.failure_fingerprint import failure_fingerprint


@dataclass(slots=True)
class ConvergenceDecision:
    action: str
    reason: str
    fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, "reason": self.reason, "fingerprint": self.fingerprint}


def diagnose_convergence(
    *,
    requirement_gaps: list[str],
    inventory_counts: dict[str, int],
    previous_fingerprints: list[str],
    failure_kind: str,
) -> ConvergenceDecision:
    fingerprint = failure_fingerprint(requirement_gaps, inventory_counts, failure_kind)
    repeats = previous_fingerprints.count(fingerprint)
    if failure_kind == "environment":
        return ConvergenceDecision(
            action="environment_repair",
            reason="The failure is environmental; repair toolchain, permissions, cache, or credentials without editing product code.",
            fingerprint=fingerprint,
        )
    if repeats >= 2:
        return ConvergenceDecision(
            action="strategy_backtrack",
            reason="Repeated failure has unchanged requirement gaps and inventory counts; stop leaf splitting and replan from objective/reference evidence.",
            fingerprint=fingerprint,
        )
    if failure_kind in {"timeout", "test_failure"} and requirement_gaps:
        return ConvergenceDecision(action="refresh_inventory_and_replan", reason="Failure affects objective proof gaps.", fingerprint=fingerprint)
    return ConvergenceDecision(action="continue", reason="No repeated semantic loop detected.", fingerprint=fingerprint)
