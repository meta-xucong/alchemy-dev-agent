"""Worker strategy decision records."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Strategy = Literal["preserve", "transplant", "repair_from_reference", "redesign", "delete", "waive"]


@dataclass(slots=True)
class DecisionRecord:
    strategy: Strategy
    requirement_ids: list[str]
    inspected_target_files: list[str] = field(default_factory=list)
    inspected_reference_files: list[str] = field(default_factory=list)
    reason: str = ""
    risks: list[str] = field(default_factory=list)
    expected_inventory_delta: dict[str, int] = field(default_factory=dict)
    verification_commands: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "requirement_ids": list(self.requirement_ids),
            "inspected_target_files": list(self.inspected_target_files),
            "inspected_reference_files": list(self.inspected_reference_files),
            "reason": self.reason,
            "risks": list(self.risks),
            "expected_inventory_delta": dict(self.expected_inventory_delta),
            "verification_commands": list(self.verification_commands),
        }


def validate_decision_record(record: DecisionRecord, *, requires_reference: bool = False) -> list[str]:
    errors: list[str] = []
    if not record.requirement_ids:
        errors.append("Decision record lacks requirement IDs.")
    if record.strategy in {"transplant", "repair_from_reference"} or requires_reference:
        if not record.inspected_reference_files:
            errors.append("Reference strategy decision lacks inspected reference files.")
    if not record.reason:
        errors.append("Decision record lacks a reason.")
    return errors
