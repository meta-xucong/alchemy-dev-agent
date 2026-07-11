"""Coherent delivery ledger for V2.188 handoff."""

from __future__ import annotations

from dataclasses import dataclass, field
import subprocess
from pathlib import Path
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
            "schema_version": "2.188",
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
    if ledger.handoff_decision == "approved" and (not ledger.branch or not ledger.commit):
        errors.append("Approved delivery lacks coherent Git branch and commit identity.")
    if ledger.handoff_decision == "approved" and ledger.commit and not _looks_like_commit(ledger.commit):
        errors.append("Approved delivery commit identity is not a valid commit hash.")
    return errors


def git_identity(repository_path: str | Path) -> dict[str, str]:
    root = Path(repository_path)
    return {
        "branch": _git(root, "branch", "--show-current"),
        "commit": _git(root, "rev-parse", "HEAD"),
        "worktree": _git(root, "rev-parse", "--show-toplevel"),
    }


def _git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(root),
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _looks_like_commit(value: str) -> bool:
    return len(value) >= 7 and all(char in "0123456789abcdefABCDEF" for char in value)
