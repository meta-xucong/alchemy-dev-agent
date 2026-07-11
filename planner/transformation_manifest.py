"""V2.187 transformation manifest generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from context.objective_models import ObjectiveContract
from context.semantic_inventory import RepositoryInventory

ManifestAction = Literal[
    "add",
    "modify",
    "delete",
    "transplant",
    "regenerate",
    "rename_with_semantic_change",
    "archive",
    "inspect",
    "verify",
    "waive",
]


@dataclass(slots=True)
class TransformationItem:
    id: str
    requirements: list[str]
    domain: str
    action: ManifestAction
    targets: list[str]
    dependency_closure: list[str] = field(default_factory=list)
    expected_final_state: dict[str, Any] = field(default_factory=dict)
    verification: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "requirements": list(self.requirements),
            "domain": self.domain,
            "action": self.action,
            "targets": list(self.targets),
            "dependency_closure": list(self.dependency_closure),
            "expected_final_state": dict(self.expected_final_state),
            "verification": list(self.verification),
        }


@dataclass(slots=True)
class TransformationManifest:
    items: list[TransformationItem]
    validation_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "2.187",
            "items": [item.to_dict() for item in self.items],
            "validation_errors": list(self.validation_errors),
        }


def build_transformation_manifest(contract: ObjectiveContract, inventory: RepositoryInventory) -> TransformationManifest:
    items: list[TransformationItem] = []
    hits_by_requirement: dict[str, list[str]] = {}
    closure_by_requirement: dict[str, set[str]] = {}
    required_signals_by_requirement: dict[str, list[str]] = {}
    for hit in inventory.hits:
        if hit.polarity == "forbidden":
            hits_by_requirement.setdefault(hit.requirement_id, []).append(hit.path)
        else:
            required_signals_by_requirement.setdefault(hit.requirement_id, []).append(hit.path)
        closure_by_requirement.setdefault(hit.requirement_id, set()).add(hit.surface_class)
    for requirement in contract.requirements:
        if requirement.class_name.startswith("must_absent"):
            targets = sorted(set(hits_by_requirement.get(requirement.id, [])))
            action: ManifestAction = "delete" if targets else "verify"
            expected = {"inventory_hits": 0}
            if requirement.class_name == "must_absent_runtime":
                expected["runtime_routes"] = 0
            if requirement.class_name == "must_absent_fresh_schema":
                expected["fresh_tables"] = 0
            verification = list(requirement.proof_obligations)
        elif requirement.class_name in {"must_reference", "must_decide", "may_reframe"}:
            action = "inspect"
            targets = []
            expected = {"decision_record_references_source": True}
            verification = list(requirement.proof_obligations)
        elif requirement.class_name in {"must_verify", "must_preserve"}:
            action = "verify"
            targets = list(requirement.scope)
            expected = {"proof_obligations_pass": True}
            verification = list(requirement.proof_obligations)
        elif requirement.class_name == "may_waive":
            action = "waive"
            targets = []
            expected = {"explicit_authorized_waiver": True}
            verification = list(requirement.proof_obligations)
        else:
            existing_signals = sorted(set(required_signals_by_requirement.get(requirement.id, [])))
            action = "modify" if existing_signals else "add"
            targets = existing_signals or list(requirement.scope)
            expected = {
                "proof_obligations_pass": True,
                "existing_capability_signals": len(existing_signals),
            }
            verification = list(requirement.proof_obligations)
        items.append(
            TransformationItem(
                id=f"TRANS-{len(items) + 1:03d}",
                requirements=[requirement.id],
                domain=requirement.domain,
                action=action,
                targets=targets,
                dependency_closure=sorted(closure_by_requirement.get(requirement.id, set())),
                expected_final_state=expected,
                verification=verification,
            )
        )
    manifest = TransformationManifest(items=items)
    manifest.validation_errors = validate_transformation_manifest(contract, manifest)
    return manifest


def validate_transformation_manifest(contract: ObjectiveContract, manifest: TransformationManifest) -> list[str]:
    errors: list[str] = []
    requirement_ids = {requirement.id for requirement in contract.requirements if requirement.strength == "must"}
    covered = {requirement_id for item in manifest.items for requirement_id in item.requirements}
    missing = sorted(requirement_ids - covered)
    if missing:
        errors.append("Must requirements missing transformation coverage: " + ", ".join(missing) + ".")
    for item in manifest.items:
        if item.action == "delete" and not item.expected_final_state.get("inventory_hits") == 0:
            errors.append(f"{item.id} delete item does not require zero inventory.")
        if item.action in {"inspect", "verify", "waive"} and item.action == "inspect" and item.targets:
            errors.append(f"{item.id} read-only inspection unexpectedly declares write targets.")
        if item.action == "rename_with_semantic_change" and "semantic_change" not in item.expected_final_state:
            errors.append(f"{item.id} rename action lacks semantic-change proof.")
    return errors
