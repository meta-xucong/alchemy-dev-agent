"""Accepted checkpoint records for verified transformation waves."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AcceptedCheckpoint:
    id: str
    worktree: str
    target_fingerprint: str
    changed_files: list[str]
    requirement_ids: list[str]
    transformation_ids: list[str]
    evidence_ids: list[str] = field(default_factory=list)
    invalidated_evidence_ids: list[str] = field(default_factory=list)
    rollback: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "worktree": self.worktree,
            "target_fingerprint": self.target_fingerprint,
            "changed_files": list(self.changed_files),
            "requirement_ids": list(self.requirement_ids),
            "transformation_ids": list(self.transformation_ids),
            "evidence_ids": list(self.evidence_ids),
            "invalidated_evidence_ids": list(self.invalidated_evidence_ids),
            "rollback": dict(self.rollback),
        }


def validate_accepted_checkpoint(checkpoint: AcceptedCheckpoint) -> list[str]:
    errors: list[str] = []
    if not checkpoint.worktree:
        errors.append(f"{checkpoint.id} lacks a worktree identity.")
    if not checkpoint.target_fingerprint:
        errors.append(f"{checkpoint.id} lacks a target fingerprint.")
    if not checkpoint.requirement_ids:
        errors.append(f"{checkpoint.id} lacks requirement IDs.")
    if not checkpoint.transformation_ids:
        errors.append(f"{checkpoint.id} lacks transformation IDs.")
    return errors
