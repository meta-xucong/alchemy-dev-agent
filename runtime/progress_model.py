"""Proof-based progress calculation for V2.187."""

from __future__ import annotations

from runtime.verification_matrix import VerificationMatrix


GATE_CEILINGS = {
    "objective_validated": 0.10,
    "inventory_complete": 0.20,
    "manifest_validated": 0.30,
    "implementation_state_reached": 0.70,
    "source_schema_contract_proof": 0.85,
    "behavior_operational_verification": 0.95,
    "delivery_ledger_coherent": 1.0,
}


def proof_based_progress(matrix: VerificationMatrix, *, delivery_ledger_coherent: bool = False) -> float:
    if not matrix.items:
        return 0.0
    passed = len([item for item in matrix.items if item.status == "passed"])
    raw = passed / len(matrix.items)
    if matrix.hard_failures:
        return min(raw, GATE_CEILINGS["source_schema_contract_proof"] - 0.01)
    if not delivery_ledger_coherent:
        return min(raw, GATE_CEILINGS["behavior_operational_verification"])
    return 1.0 if raw == 1.0 else min(raw, GATE_CEILINGS["behavior_operational_verification"])
