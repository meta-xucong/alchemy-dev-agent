"""Shared models for full-roadmap execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class RoadmapPhase:
    phase_id: str
    title: str
    source_references: list[str] = field(default_factory=list)
    status: str = "pending"
    phase_type: str = "feature"
    prerequisites: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    scope_controls: dict[str, object] = field(default_factory=dict)
    global_constraints: list[str] = field(default_factory=list)
    phase_local_constraints: list[str] = field(default_factory=list)
    verification: dict[str, object] = field(default_factory=dict)
    promotion_gate: dict[str, object] = field(default_factory=dict)
    optional: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "phase_id": self.phase_id,
            "title": self.title,
            "source_references": list(self.source_references),
            "status": self.status,
            "phase_type": self.phase_type,
            "prerequisites": list(self.prerequisites),
            "requirements": list(self.requirements),
            "scope_controls": dict(self.scope_controls),
            "global_constraints": list(self.global_constraints),
            "phase_local_constraints": list(self.phase_local_constraints),
            "verification": dict(self.verification),
            "promotion_gate": dict(self.promotion_gate),
            "optional": self.optional,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RoadmapPhase":
        return cls(
            phase_id=str(payload.get("phase_id", "")),
            title=str(payload.get("title", "")),
            source_references=[str(item) for item in payload.get("source_references", [])],
            status=str(payload.get("status", "pending")),
            phase_type=str(payload.get("phase_type", "feature")),
            prerequisites=[str(item) for item in payload.get("prerequisites", [])],
            requirements=[str(item) for item in payload.get("requirements", [])],
            scope_controls=dict(payload.get("scope_controls", {}) if isinstance(payload.get("scope_controls"), dict) else {}),
            global_constraints=[str(item) for item in payload.get("global_constraints", [])],
            phase_local_constraints=[str(item) for item in payload.get("phase_local_constraints", [])],
            verification=dict(payload.get("verification", {}) if isinstance(payload.get("verification"), dict) else {}),
            promotion_gate=dict(payload.get("promotion_gate", {}) if isinstance(payload.get("promotion_gate"), dict) else {}),
            optional=bool(payload.get("optional", False)),
        )


@dataclass(slots=True)
class RoadmapExecutionPlan:
    root_objective: str
    source_mode: str = "uploaded_docs"
    completion_policy: str = "full_roadmap"
    global_constraints: list[str] = field(default_factory=list)
    external_blockers: list[str] = field(default_factory=list)
    phases: list[RoadmapPhase] = field(default_factory=list)
    final_acceptance: dict[str, object] = field(default_factory=dict)
    delivery_policy: dict[str, object] = field(default_factory=dict)
    confidence: float = 0.0
    schema_version: str = "roadmap_execution_plan_v1"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "root_objective": self.root_objective,
            "source_mode": self.source_mode,
            "completion_policy": self.completion_policy,
            "global_constraints": list(self.global_constraints),
            "external_blockers": list(self.external_blockers),
            "phases": [phase.to_dict() for phase in self.phases],
            "final_acceptance": dict(self.final_acceptance),
            "delivery_policy": dict(self.delivery_policy),
            "confidence": self.confidence,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RoadmapExecutionPlan":
        return cls(
            root_objective=str(payload.get("root_objective", "")),
            source_mode=str(payload.get("source_mode", "uploaded_docs")),
            completion_policy=str(payload.get("completion_policy", "full_roadmap")),
            global_constraints=[str(item) for item in payload.get("global_constraints", [])],
            external_blockers=[str(item) for item in payload.get("external_blockers", [])],
            phases=[RoadmapPhase.from_dict(dict(item)) for item in payload.get("phases", []) if isinstance(item, dict)],
            final_acceptance=dict(payload.get("final_acceptance", {}) if isinstance(payload.get("final_acceptance"), dict) else {}),
            delivery_policy=dict(payload.get("delivery_policy", {}) if isinstance(payload.get("delivery_policy"), dict) else {}),
            confidence=float(payload.get("confidence", 0.0) or 0.0),
            schema_version=str(payload.get("schema_version", "roadmap_execution_plan_v1")),
            created_at=str(payload.get("created_at", "")) or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )


@dataclass(slots=True)
class RoadmapAuditResult:
    status: str
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    repaired: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "issues": list(self.issues),
            "warnings": list(self.warnings),
            "repaired": self.repaired,
        }


@dataclass(slots=True)
class PhaseExecutionRecord:
    phase_id: str
    title: str
    status: str
    output_dir: str
    result: dict[str, object] = field(default_factory=dict)
    promotion: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "phase_id": self.phase_id,
            "title": self.title,
            "status": self.status,
            "output_dir": self.output_dir,
            "result": dict(self.result),
            "promotion": dict(self.promotion),
        }
