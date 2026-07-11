"""Coherent delivery ledger for V2.187 handoff."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from runtime.accepted_checkpoint import AcceptedCheckpoint, validate_accepted_checkpoint


@dataclass(slots=True)
class DeliveryLedger:
    baseline: str
    target_worktree: str
    final_fingerprint: str
    verification_matrix_revision: str
    verification_repository_fingerprint: str = ""
    branch: str = ""
    commit: str = ""
    delivery_diff: list[str] = field(default_factory=list)
    checkpoints: list[AcceptedCheckpoint] = field(default_factory=list)
    waivers: list[dict[str, Any]] = field(default_factory=list)
    unresolved_non_required_issues: list[str] = field(default_factory=list)
    handoff_decision: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "2.187",
            "baseline": self.baseline,
            "target_worktree": self.target_worktree,
            "final_fingerprint": self.final_fingerprint,
            "verification_matrix_revision": self.verification_matrix_revision,
            "verification_repository_fingerprint": self.verification_repository_fingerprint,
            "branch": self.branch,
            "commit": self.commit,
            "delivery_diff": list(self.delivery_diff),
            "accepted_checkpoints": [checkpoint.to_dict() for checkpoint in self.checkpoints],
            "waivers": list(self.waivers),
            "unresolved_non_required_issues": list(self.unresolved_non_required_issues),
            "handoff_decision": self.handoff_decision,
        }


def validate_delivery_ledger(ledger: DeliveryLedger) -> list[str]:
    errors: list[str] = []
    for checkpoint in ledger.checkpoints:
        errors.extend(validate_accepted_checkpoint(checkpoint))
    if any(checkpoint.worktree != ledger.target_worktree for checkpoint in ledger.checkpoints):
        errors.append("Accepted checkpoints reference more than one worktree.")
    if ledger.handoff_decision == "approved" and not ledger.final_fingerprint:
        errors.append("Approved delivery lacks a final fingerprint.")
    if ledger.handoff_decision == "approved" and not ledger.verification_matrix_revision:
        errors.append("Approved delivery lacks verification matrix identity.")
    if (
        ledger.handoff_decision == "approved"
        and ledger.verification_repository_fingerprint
        and ledger.verification_repository_fingerprint != ledger.final_fingerprint
    ):
        errors.append("Approved delivery verification belongs to a different repository fingerprint.")
    return errors
