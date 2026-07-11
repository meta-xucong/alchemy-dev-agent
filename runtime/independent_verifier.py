"""Objective-derived verifier that does not trust task completion."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from context.objective_models import ObjectiveContract
from context.reference_baseline import ReferenceBaseline
from context.semantic_inventory import RepositoryInventory
from runtime.verification_matrix import VerificationItem, VerificationMatrix


class IndependentVerifier:
    def verify(
        self,
        root: Path | str,
        contract: ObjectiveContract,
        inventory: RepositoryInventory,
        *,
        evidence: dict[str, dict[str, dict[str, Any]]] | None = None,
        reference_baseline: ReferenceBaseline | None = None,
        waivers: list[dict[str, Any]] | None = None,
    ) -> VerificationMatrix:
        fingerprint = repository_fingerprint(root)
        evidence = evidence or {}
        authorized_waivers = {
            str(item.get("requirement_id")): item
            for item in waivers or []
            if item.get("authorized") is True
            and str(item.get("requirement_id", ""))
            and str(item.get("authority", ""))
            and str(item.get("reason", ""))
            and str(item.get("expires_at", ""))
        }
        remaining_hits = {}
        for hit in inventory.hits:
            if hit.polarity == "forbidden":
                remaining_hits[hit.requirement_id] = remaining_hits.get(hit.requirement_id, 0) + 1
        items: list[VerificationItem] = []
        hard_failures: list[str] = []
        for requirement in contract.requirements:
            for obligation in requirement.proof_obligations:
                supplied = evidence.get(requirement.id, {}).get(obligation, {})
                waiver = authorized_waivers.get(requirement.id)
                if waiver:
                    status = "waived"
                    item_evidence = {"waiver": waiver}
                elif (
                    requirement.class_name.startswith("must_absent")
                    and obligation in _INVENTORY_OBLIGATIONS
                    and remaining_hits.get(requirement.id, 0)
                ):
                    status = "failed"
                    item_evidence = {"remaining_inventory_hits": remaining_hits[requirement.id]}
                elif requirement.class_name.startswith("must_absent") and obligation in _INVENTORY_OBLIGATIONS:
                    status = "passed"
                    item_evidence = {"remaining_inventory_hits": 0, "inventory_root": inventory.root_path}
                elif obligation == "reference_baseline_declared" and reference_baseline and reference_baseline.references:
                    status = "passed"
                    item_evidence = {
                        "reference_ids": [item.id for item in reference_baseline.references],
                        "reference_heads": [item.head for item in reference_baseline.references],
                    }
                elif supplied:
                    supplied_fingerprint = str(supplied.get("repository_fingerprint", ""))
                    if supplied_fingerprint != fingerprint:
                        status = "stale"
                        item_evidence = {
                            **supplied,
                            "reason": "Evidence repository fingerprint does not match the current target.",
                        }
                    elif str(supplied.get("status", "")).lower() == "passed":
                        status = "passed"
                        item_evidence = dict(supplied.get("evidence", supplied))
                    else:
                        status = "failed"
                        item_evidence = dict(supplied.get("evidence", supplied))
                else:
                    status = "unproven"
                    item_evidence = {"reason": "No fresh objective-derived evidence proves this obligation."}
                if requirement.strength == "must" and status not in {"passed", "waived"}:
                    if status == "failed" and requirement.class_name.startswith("must_absent"):
                        hard_failures.append(f"{requirement.id} has remaining forbidden inventory for {obligation}.")
                    else:
                        hard_failures.append(f"{requirement.id} obligation {obligation} is {status}.")
                items.append(
                    VerificationItem(
                        requirement_id=requirement.id,
                        obligation=obligation,
                        status=status,
                        repository_fingerprint=fingerprint,
                        evidence=item_evidence,
                    )
                )
        return VerificationMatrix(repository_fingerprint=fingerprint, items=items, hard_failures=sorted(set(hard_failures)))


def repository_fingerprint(root: Path | str) -> str:
    root_path = Path(root)
    digest = hashlib.sha256()
    if not root_path.exists():
        return "missing"
    skip = {".git", ".alchemy", ".codex-longrun", ".test-tmp", "node_modules", "vendor", "__pycache__"}
    for path in sorted(
        p
        for p in root_path.rglob("*")
        if p.is_file()
        and not p.is_symlink()
        and not any(part in skip for part in p.relative_to(root_path).parts)
    ):
        relative = path.relative_to(root_path).as_posix()
        digest.update(relative.encode("utf-8"))
        try:
            with path.open("rb") as stream:
                while chunk := stream.read(64 * 1024):
                    digest.update(chunk)
        except OSError:
            continue
    return "sha256:" + digest.hexdigest()


_INVENTORY_OBLIGATIONS = {
    "static_inventory_zero",
    "runtime_route_inventory_zero",
    "fresh_schema_inventory_zero",
    "public_contract_inventory_zero",
}
