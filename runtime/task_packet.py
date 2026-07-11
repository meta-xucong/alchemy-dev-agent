"""Bounded task packet serialization for V2.187 workers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TaskPacket:
    task_id: str
    target_root: str
    allowed_write_paths: list[str]
    reference_roots: list[str] = field(default_factory=list)
    requirement_ids: list[str] = field(default_factory=list)
    transformation_ids: list[str] = field(default_factory=list)
    objective_slice: list[dict[str, Any]] = field(default_factory=list)
    inventory_slice: list[dict[str, Any]] = field(default_factory=list)
    required_strategy_decision: str = ""
    non_goals: list[str] = field(default_factory=list)
    repository_fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "2.187",
            "task_id": self.task_id,
            "target_root": self.target_root,
            "allowed_write_paths": list(self.allowed_write_paths),
            "reference_roots": list(self.reference_roots),
            "requirement_ids": list(self.requirement_ids),
            "transformation_ids": list(self.transformation_ids),
            "objective_slice": list(self.objective_slice),
            "inventory_slice": list(self.inventory_slice),
            "required_strategy_decision": self.required_strategy_decision,
            "non_goals": list(self.non_goals),
            "repository_fingerprint": self.repository_fingerprint,
        }


def validate_task_packet(packet: TaskPacket) -> list[str]:
    errors: list[str] = []
    if not packet.task_id:
        errors.append("Task packet lacks a task ID.")
    if not packet.target_root:
        errors.append("Task packet lacks a target root.")
    if not packet.requirement_ids:
        errors.append(f"Task packet {packet.task_id} lacks requirement IDs.")
    if not packet.transformation_ids:
        errors.append(f"Task packet {packet.task_id} lacks transformation IDs.")
    target = packet.target_root.rstrip("/\\").lower()
    for reference in packet.reference_roots:
        if reference.rstrip("/\\").lower() == target:
            errors.append(f"Task packet {packet.task_id} uses the target as a reference root.")
    return errors
