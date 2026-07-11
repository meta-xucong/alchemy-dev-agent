"""V2.187 goal-locked bootstrap, phase contracts, and final proof ledger."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from context.objective_compiler import ObjectiveCompiler
from context.objective_models import ObjectiveContract
from context.reference_baseline import ReferenceBaseline, assert_write_allowed, build_reference_baseline
from context.semantic_inventory import RepositoryInventory, SemanticInventoryBuilder
from intake.schema_validation import validate_json_subset
from planner.convergence_graph_builder import ConvergenceGraphBuilder, goal_locked_graph_errors
from planner.transformation_manifest import TransformationManifest, build_transformation_manifest
from runtime.accepted_checkpoint import AcceptedCheckpoint
from runtime.delivery_ledger import DeliveryLedger, git_identity, validate_delivery_ledger
from runtime.convergence_controller import diagnose_convergence
from runtime.independent_verifier import IndependentVerifier, repository_fingerprint
from runtime.progress_model import proof_based_progress
from runtime.verification_matrix import VerificationMatrix

from .roadmap_models import RoadmapExecutionPlan, RoadmapPhase


GOAL_LOCKED_SCHEMA_VERSION = "roadmap_execution_plan_v2_187"
EDIT_ACTIONS = {"add", "modify", "delete", "transplant", "regenerate", "rename_with_semantic_change", "archive"}
BEHAVIOR_OBLIGATIONS = {
    "named_verification_passes",
    "behavior_verification_passes",
    "preserved_behavior_passes",
    "fresh_migration_smoke",
}


@dataclass(slots=True)
class GoalLockedBootstrap:
    contract: ObjectiveContract
    baseline: ReferenceBaseline
    inventory: RepositoryInventory
    manifest: TransformationManifest
    task_graph: dict[str, Any]
    verification_matrix: VerificationMatrix
    validation_errors: list[str] = field(default_factory=list)
    artifact_dir: str = ""

    @property
    def ready(self) -> bool:
        return not self.validation_errors

    def report(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "mode": "goal_locked_convergence",
            "status": "ready" if self.ready else "blocked",
            "schema_version": "2.187",
            "objective_revision": self.contract.revision,
            "target_worktree": self.baseline.target.path,
            "reference_roots": [item.path for item in self.baseline.references],
            "requirement_count": len(self.contract.requirements),
            "initial_forbidden_inventory_hits": len([item for item in self.inventory.hits if item.polarity == "forbidden"]),
            "initial_required_capability_signals": len([item for item in self.inventory.hits if item.polarity == "required_signal"]),
            "transformation_count": len(self.manifest.items),
            "initial_unproven_obligations": len(
                [item for item in self.verification_matrix.items if item.status != "passed"]
            ),
            "validation_errors": list(self.validation_errors),
            "artifact_dir": self.artifact_dir,
        }


class GoalLockedRunCoordinator:
    """Own the immutable objective and independent evidence lifecycle."""

    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)
        self.artifact_dir = self.output_dir / "goal_locked"
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._baseline: ReferenceBaseline | None = None

    def bootstrap(
        self,
        *,
        objective: str,
        documents: Sequence[str | Path],
        repository_path: str | Path,
        reference_paths: Sequence[str | Path] = (),
        acceptance_criteria: Sequence[str] = (),
        resume: bool = False,
    ) -> GoalLockedBootstrap:
        target = Path(repository_path).resolve()
        source_documents = [Path(item) for item in documents if Path(item).is_file()]
        contract = ObjectiveCompiler().compile(
            objective,
            source_documents,
            acceptance_criteria=acceptance_criteria,
        )
        orchestrator = Path(__file__).resolve().parents[1]
        orchestrator_path: Path | None = orchestrator if not _paths_overlap(target, orchestrator) else None
        baseline = build_reference_baseline(
            target_path=target,
            reference_paths=list(reference_paths),
            orchestrator_path=orchestrator_path,
            artifact_paths=[self.artifact_dir],
        )
        self._baseline = baseline
        inventory = SemanticInventoryBuilder().build(target, contract)
        manifest = build_transformation_manifest(contract, inventory)
        graph = ConvergenceGraphBuilder().build(
            project_id=_project_id(target),
            objective_contract=contract,
            reference_baseline=baseline,
            repository_inventory=inventory,
            transformation_manifest=manifest,
        )
        matrix = IndependentVerifier().verify(
            target,
            contract,
            inventory,
            reference_baseline=baseline,
        )
        errors = [
            *contract.validation_errors,
            *baseline.validation_errors,
            *manifest.validation_errors,
            *goal_locked_graph_errors(graph),
        ]
        if any(req.class_name == "must_reference" for req in contract.requirements) and not baseline.references:
            errors.append("Objective requires a reference repository, but no read-only reference path was declared.")
        previous_contract = _read_json(self.artifact_dir / "objective_contract.json")
        if resume and previous_contract:
            previous_revision = str(previous_contract.get("revision", ""))
            if previous_revision and previous_revision != contract.revision:
                errors.append("Objective contract revision changed during resume; start a new run instead of mutating the locked goal.")

        payloads = {
            "objective_contract.json": contract.to_dict(),
            "reference_baseline.json": baseline.to_dict(),
            "repository_inventory.initial.json": inventory.to_dict(),
            "transformation_manifest.json": manifest.to_dict(),
            "convergence_task_graph.json": graph.to_dict(),
            "verification_matrix.initial.json": matrix.to_dict(),
        }
        errors.extend(_schema_errors(payloads))
        errors = _dedupe(errors)
        bootstrap = GoalLockedBootstrap(
            contract=contract,
            baseline=baseline,
            inventory=inventory,
            manifest=manifest,
            task_graph=graph.to_dict(),
            verification_matrix=matrix,
            validation_errors=errors,
            artifact_dir=str(self.artifact_dir.resolve()),
        )
        for name, payload in payloads.items():
            _write_json(self.artifact_dir / name, payload)
        _write_json(self.artifact_dir / "goal_locked_status.json", bootstrap.report())
        return bootstrap

    def build_plan(
        self,
        base_plan: RoadmapExecutionPlan,
        bootstrap: GoalLockedBootstrap,
    ) -> RoadmapExecutionPlan:
        requirements = {item.id: item for item in bootstrap.contract.requirements}
        phases: list[RoadmapPhase] = []
        graph_nodes = [
            node
            for node in bootstrap.task_graph.get("nodes", [])
            if isinstance(node, dict)
            and any(
                isinstance(evidence, dict) and evidence.get("type") == "task_contract"
                for evidence in node.get("evidence", [])
            )
        ]
        for index, node in enumerate(graph_nodes, start=1):
            contract = next(
                evidence
                for evidence in node.get("evidence", [])
                if isinstance(evidence, dict) and evidence.get("type") == "task_contract"
            )
            requirement_ids = [str(item) for item in contract.get("requirement_ids", [])]
            transformation_ids = [str(item) for item in contract.get("transformation_ids", [])]
            action = str(contract.get("action", ""))
            read_only = bool(contract.get("read_only"))
            source_refs: list[str] = []
            phase_requirements: list[str] = []
            proof_obligations: list[str] = []
            for requirement_id in requirement_ids:
                requirement = requirements[requirement_id]
                source_refs.append(
                    f"{requirement.source.document}:{requirement.source.line_start}#{requirement.source.quote_hash}"
                )
                phase_requirements.append(f"{requirement.id} [{requirement.class_name}] {requirement.statement}")
                proof_obligations.extend(requirement.proof_obligations)
            phase_requirements.extend(
                [
                    f"Required transformation: {action} ({', '.join(transformation_ids)}).",
                    f"Expected final state: {json.dumps(contract.get('expected_final_state', {}), sort_keys=True)}.",
                    "Return requirement-scoped command, test, changed-file, and inventory evidence; task completion alone is not proof.",
                ]
            )
            if contract.get("required_strategy_decision"):
                phase_requirements.append(
                    "Before editing, record `DECISION_RECORD:` with the selected preserve/transplant/repair/redesign/delete strategy and reason."
                )
            elif "decision_record_references_source" in proof_obligations:
                phase_requirements.append(
                    "Record `DECISION_RECORD:` explaining how the declared reference controls the implementation strategy."
                )
            if bootstrap.baseline.references:
                phase_requirements.append(
                    "References are read-only. Record consulted paths with `REFERENCE_FILES:` and never report them as changed files."
                )
            write_paths = [str(item) for item in contract.get("allowed_write_paths", []) if str(item)]
            phase = RoadmapPhase(
                phase_id=f"goal_phase_{index:03d}",
                title=str(node.get("title", f"Goal-locked transformation {index}")),
                source_references=source_refs,
                phase_type="test" if action == "verify" else "architecture" if read_only else "feature",
                prerequisites=[phases[-1].phase_id] if phases else [],
                requirements=phase_requirements,
                scope_controls=_scope_controls(write_paths, read_only=read_only),
                global_constraints=_dedupe(
                    [
                        *base_plan.global_constraints,
                        "The objective contract is immutable during this run.",
                        "Never weaken, hide, rename, or waive a requirement to make verification pass.",
                        "Only the declared target worktree is writable; reference and orchestrator repositories are read-only.",
                    ]
                ),
                phase_local_constraints=[
                    f"Requirement IDs: {', '.join(requirement_ids)}",
                    f"Transformation IDs: {', '.join(transformation_ids)}",
                    f"Allowed write paths: {', '.join(write_paths) if write_paths else '(read-only)' }",
                ],
                verification={
                    "requirement_ids": requirement_ids,
                    "transformation_ids": transformation_ids,
                    "proof_obligations": _dedupe(proof_obligations),
                    "action": action,
                    "read_only": read_only,
                    "strategy_required": str(contract.get("required_strategy_decision", "")),
                    "expected_final_state": dict(contract.get("expected_final_state", {})),
                },
                promotion_gate={
                    "required_score": 0.85,
                    "required_tests_pass": True,
                    "goal_locked_evidence_required": True,
                },
            )
            phases.append(phase)
        return RoadmapExecutionPlan(
            root_objective=base_plan.root_objective,
            source_mode=base_plan.source_mode,
            completion_policy="goal_locked_full_roadmap",
            global_constraints=phases[0].global_constraints if phases else list(base_plan.global_constraints),
            external_blockers=list(base_plan.external_blockers),
            phases=phases,
            final_acceptance={
                **base_plan.final_acceptance,
                "objective_contract_revision": bootstrap.contract.revision,
                "all_must_obligations_fresh_and_passed": True,
                "forbidden_inventory_zero": True,
                "coherent_delivery_ledger": True,
            },
            delivery_policy=dict(base_plan.delivery_policy),
            confidence=1.0 if bootstrap.ready else 0.0,
            schema_version=GOAL_LOCKED_SCHEMA_VERSION,
        )

    def record_phase(
        self,
        *,
        phase: RoadmapPhase,
        phase_record: dict[str, Any],
        repository_path: str | Path,
    ) -> dict[str, Any]:
        target = Path(repository_path).resolve()
        fingerprint = repository_fingerprint(target)
        signals = _result_signals(phase_record.get("result", {}))
        independent_changed_files = _dedupe(
            _normalize_relative_path(path) for path in phase_record.get("independent_changed_files", [])
        )
        independent_commands = [
            dict(item)
            for item in phase_record.get("independent_command_results", [])
            if isinstance(item, dict)
            and item.get("source") == "alchemy_controller"
            and item.get("executed") is True
        ]
        independently_validated = bool(independent_commands) and all(
            _exit_code(item.get("exit_code", 1)) == 0 for item in independent_commands
        )
        signals["changed_files"] = independent_changed_files
        signals["commands_passed"] = independently_validated
        signals["tests_passed"] = [
            str(item.get("command", "independent validation"))
            for item in independent_commands
            if _exit_code(item.get("exit_code", 1)) == 0
        ]
        file_fingerprints = {
            path: _changed_file_fingerprint(target, path)
            for path in signals["changed_files"]
        }
        action = str(phase.verification.get("action", ""))
        proof_obligations = list(phase.verification.get("proof_obligations", []))
        proof_gaps: list[str] = []
        if signals["changed_files"]:
            phase_baseline = build_reference_baseline(
                target_path=target,
                reference_paths=[item.path for item in self._baseline.references] if self._baseline else [],
            )
            try:
                assert_write_allowed(
                    phase_baseline,
                    [(target / _normalize_relative_path(path)).resolve() for path in signals["changed_files"]],
                )
            except ValueError as exc:
                proof_gaps.append(str(exc))
        existing_signals = int(
            (phase.verification.get("expected_final_state", {}) or {}).get("existing_capability_signals", 0) or 0
        )
        verified_existing = bool(existing_signals and signals["commands_passed"] and signals["tests_passed"])
        if action in EDIT_ACTIONS and not signals["changed_files"] and not verified_existing:
            proof_gaps.append(f"{phase.phase_id} edit phase reported no changed-file evidence.")
        if action in EDIT_ACTIONS and not phase_record.get("independent_snapshot"):
            proof_gaps.append(f"{phase.phase_id} lacks an independent before/after repository snapshot.")
        if phase.verification.get("strategy_required") and not signals["decision_recorded"]:
            proof_gaps.append(f"{phase.phase_id} lacks the required DECISION_RECORD evidence.")
        if "decision_record_references_source" in proof_obligations:
            if not signals["decision_recorded"]:
                proof_gaps.append(f"{phase.phase_id} lacks the reference strategy DECISION_RECORD evidence.")
            if not signals["reference_files_recorded"]:
                proof_gaps.append(f"{phase.phase_id} lacks required REFERENCE_FILES evidence.")
        if action == "verify" and not (signals["commands_passed"] and signals["tests_passed"]):
            proof_gaps.append(f"{phase.phase_id} verification phase lacks passing command and test evidence.")
        reference_drift = self._reference_drift()
        accepted = phase_record.get("status") == "done" and not proof_gaps and not reference_drift
        payload = {
            "schema_version": "2.187",
            "phase_id": phase.phase_id,
            "status": "done" if accepted else "blocked",
            "worktree": str(target),
            "repository_fingerprint": fingerprint,
            "requirement_ids": list(phase.verification.get("requirement_ids", [])),
            "transformation_ids": list(phase.verification.get("transformation_ids", [])),
            "proof_obligations": proof_obligations,
            "action": action,
            "verified_existing_capability": verified_existing,
            "changed_files": signals["changed_files"],
            "file_fingerprints": file_fingerprints,
            "commands_passed": signals["commands_passed"],
            "tests_passed": signals["tests_passed"],
            "decision_recorded": signals["decision_recorded"],
            "reference_files_recorded": signals["reference_files_recorded"],
            "evidence_excerpt": signals["evidence"][:30],
            "reference_drift": reference_drift,
            "proof_gaps": proof_gaps,
        }
        _write_json(self.artifact_dir / "phase_proofs" / f"{phase.phase_id}.json", payload)
        return payload

    def diagnose_phase_failure(
        self,
        *,
        bootstrap: GoalLockedBootstrap,
        phase: RoadmapPhase,
        repository_path: str | Path,
        phase_payload: dict[str, Any],
    ) -> dict[str, Any]:
        inventory = SemanticInventoryBuilder().build(repository_path, bootstrap.contract)
        requirement_ids = [str(item) for item in phase.verification.get("requirement_ids", [])]
        counts = {requirement_id: 0 for requirement_id in requirement_ids}
        for hit in inventory.hits:
            if hit.requirement_id in counts:
                counts[hit.requirement_id] += 1
        history_path = self.artifact_dir / "convergence_history.json"
        history_payload = _read_json(history_path)
        history = [item for item in history_payload.get("decisions", []) if isinstance(item, dict)]
        previous = [str(item.get("fingerprint", "")) for item in history]
        decision = diagnose_convergence(
            requirement_gaps=requirement_ids,
            inventory_counts=counts,
            previous_fingerprints=previous,
            failure_kind=_failure_kind(phase_payload),
        ).to_dict()
        decision.update(
            {
                "phase_id": phase.phase_id,
                "requirement_ids": requirement_ids,
                "inventory_counts": counts,
            }
        )
        history.append(decision)
        _write_json(history_path, {"schema_version": "2.187", "decisions": history})
        return decision

    def finalize(
        self,
        *,
        bootstrap: GoalLockedBootstrap,
        plan: RoadmapExecutionPlan,
        phase_records: Sequence[Any],
        final_worker: dict[str, Any],
        repository_path: str | Path,
        waivers: list[dict[str, Any]] = (),
    ) -> dict[str, Any]:
        target = Path(repository_path).resolve()
        inventory = SemanticInventoryBuilder().build(target, bootstrap.contract)
        final_fingerprint = repository_fingerprint(target)
        proofs = self._load_phase_proofs()
        evidence = _verification_evidence(
            bootstrap.contract,
            proofs,
            final_worker,
            target=target,
            final_fingerprint=final_fingerprint,
        )
        matrix = IndependentVerifier().verify(
            target,
            bootstrap.contract,
            inventory,
            evidence=evidence,
            reference_baseline=bootstrap.baseline,
            waivers=list(waivers),
        )
        checkpoints = [_checkpoint_from_proof(item) for item in proofs if item.get("status") == "done"]
        identity = git_identity(target)
        ledger = DeliveryLedger(
            baseline=bootstrap.baseline.target.head,
            target_worktree=str(target),
            final_fingerprint=final_fingerprint,
            verification_matrix_revision=matrix.revision,
            verification_repository_fingerprint=matrix.repository_fingerprint,
            branch=identity.get("branch", ""),
            commit=identity.get("commit", ""),
            checkpoints=checkpoints,
            waivers=list(waivers),
            handoff_decision="approved" if not matrix.hard_failures else "blocked",
            delivery_diff=_dedupe(path for item in proofs for path in item.get("changed_files", [])),
        )
        incomplete_phases = [phase.phase_id for phase in plan.phases if phase.status != "completed" and not phase.optional]
        if incomplete_phases:
            ledger.handoff_decision = "blocked"
        reference_drift = self._reference_drift()
        if reference_drift:
            ledger.handoff_decision = "blocked"
        ledger_errors = validate_delivery_ledger(ledger)
        if incomplete_phases:
            ledger_errors.append("Required goal-locked phases are incomplete: " + ", ".join(incomplete_phases) + ".")
        ledger_errors.extend(reference_drift)
        ledger_errors = _dedupe(ledger_errors)
        if ledger_errors:
            ledger.handoff_decision = "blocked"
        coherent = not ledger_errors and ledger.handoff_decision == "approved"
        progress = proof_based_progress(matrix, delivery_ledger_coherent=coherent)
        blockers = _dedupe([*matrix.hard_failures, *ledger_errors])
        report = {
            **bootstrap.report(),
            "status": "passed" if not blockers and progress == 1.0 else "blocked",
            "target_worktree": str(target),
            "repository_fingerprint": final_fingerprint,
            "current_forbidden_inventory_hits": len([item for item in inventory.hits if item.polarity == "forbidden"]),
            "current_required_capability_signals": len([item for item in inventory.hits if item.polarity == "required_signal"]),
            "verification_summary": matrix.to_dict()["summary"],
            "progress": progress,
            "remaining_requirement_ids": sorted(
                {item.requirement_id for item in matrix.items if item.status not in {"passed", "waived"}}
            ),
            "blockers": blockers,
            "delivery_ledger_errors": ledger_errors,
            "reference_drift": reference_drift,
            "next_action": "handoff" if not blockers and progress == 1.0 else "re-index proof gaps and replan from the locked objective",
        }
        _write_json(self.artifact_dir / "repository_inventory.current.json", inventory.to_dict())
        _write_json(self.artifact_dir / "verification_matrix.current.json", matrix.to_dict())
        _write_json(self.artifact_dir / "delivery_ledger.json", ledger.to_dict())
        _write_json(self.artifact_dir / "goal_locked_status.json", report)
        return report

    def _reference_drift(self) -> list[str]:
        if not self._baseline or not self._baseline.references:
            return []
        current = build_reference_baseline(
            target_path=self._baseline.target.path,
            reference_paths=[item.path for item in self._baseline.references],
        )
        expected = {item.path: item.head for item in self._baseline.references}
        return [
            f"Read-only reference repository changed during the run: {item.path}"
            for item in current.references
            if expected.get(item.path) != item.head
        ]

    def _load_phase_proofs(self) -> list[dict[str, Any]]:
        proof_dir = self.artifact_dir / "phase_proofs"
        return [payload for path in sorted(proof_dir.glob("*.json")) if (payload := _read_json(path))]


def goal_locked_enabled(run_payload: dict[str, Any]) -> bool:
    if run_payload.get("legacy_unlocked") is True or run_payload.get("explicit_legacy_unlocked") is True:
        return False
    return True


def reference_paths_from_payload(run_payload: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    values.extend(run_payload.get("reference_repository_paths", []) or [])
    if run_payload.get("reference_repository_path"):
        values.append(run_payload["reference_repository_path"])
    return _dedupe(str(item) for item in values if str(item).strip())


def _verification_evidence(
    contract: ObjectiveContract,
    proofs: list[dict[str, Any]],
    final_worker: dict[str, Any],
    *,
    target: Path,
    final_fingerprint: str,
) -> dict[str, dict[str, dict[str, Any]]]:
    result: dict[str, dict[str, dict[str, Any]]] = {}
    by_requirement: dict[str, list[dict[str, Any]]] = {}
    for proof in proofs:
        for requirement_id in proof.get("requirement_ids", []):
            by_requirement.setdefault(str(requirement_id), []).append(proof)
    final_signals = _result_signals(final_worker)
    final_markers = "\n".join(final_signals["evidence"]).upper()
    independent_results = [
        dict(item)
        for item in final_worker.get("independent_command_results", [])
        if isinstance(item, dict)
        and item.get("source") == "alchemy_controller"
        and item.get("executed") is True
    ]
    independent_tests_passed = [
        str(item.get("command", "independent test"))
        for item in independent_results
        if str(item.get("kind", "")) in {"test", "build"}
        and _exit_code(item.get("exit_code", 1)) == 0
    ]
    broad_final_pass = (
        str(final_worker.get("status", "")).lower() == "passed"
        and final_worker.get("independent_verification") is True
        and final_worker.get("independent_verification_source") == "alchemy_controller"
        and bool(independent_results)
        and bool(independent_tests_passed)
        and all(_exit_code(item.get("exit_code", 1)) == 0 for item in independent_results)
        and all(
            marker in final_markers
            for marker in ("FINAL_AUDIT_STATUS: PASS", "SIMULATION_TEST_STATUS: PASS", "REAL_TEST_STATUS: PASS")
        )
    )
    for requirement in contract.requirements:
        requirement_evidence: dict[str, dict[str, Any]] = {}
        requirement_proofs = by_requirement.get(requirement.id, [])
        for obligation in requirement.proof_obligations:
            proof_payload: dict[str, Any] | None = None
            if obligation == "implementation_evidence_present":
                proof_payload = next(
                    (
                        proof
                        for proof in reversed(requirement_proofs)
                        if (
                            proof.get("changed_files") and _proof_files_are_current(target, proof)
                        )
                        or (
                            proof.get("verified_existing_capability")
                            and proof.get("repository_fingerprint") == final_fingerprint
                        )
                    ),
                    None,
                )
            elif obligation in BEHAVIOR_OBLIGATIONS:
                if broad_final_pass:
                    proof_payload = {"source": "final_independent_worker", "markers": True}
                else:
                    proof_payload = next(
                        (
                            proof
                            for proof in reversed(requirement_proofs)
                            if proof.get("repository_fingerprint") == final_fingerprint
                            and proof.get("commands_passed")
                            and proof.get("tests_passed")
                        ),
                        None,
                    )
            elif obligation == "decision_record_present":
                proof_payload = next((proof for proof in reversed(requirement_proofs) if proof.get("decision_recorded")), None)
            elif obligation == "decision_record_references_source":
                proof_payload = next(
                    (
                        proof
                        for proof in reversed(requirement_proofs)
                        if proof.get("decision_recorded") and proof.get("reference_files_recorded")
                    ),
                    None,
                )
            if proof_payload is not None:
                requirement_evidence[obligation] = {
                    "status": "passed",
                    "repository_fingerprint": final_fingerprint,
                    "evidence": proof_payload,
                }
        if requirement_evidence:
            result[requirement.id] = requirement_evidence
    return result


def _result_signals(payload: Any) -> dict[str, Any]:
    changed_files: list[str] = []
    command_statuses: dict[str, int] = {}
    tests_passed: list[str] = []
    evidence: list[str] = []

    def visit(value: Any, *, key: str = "", depth: int = 0) -> None:
        if depth > 12:
            return
        if isinstance(value, dict):
            if "exit_code" in value:
                try:
                    command = str(value.get("command", "") or f"command-{len(command_statuses) + 1}")
                    command_statuses[command] = int(value.get("exit_code", 1))
                except (TypeError, ValueError):
                    command_statuses[str(value.get("command", "unknown"))] = 1
            for child_key, child in value.items():
                visit(child, key=str(child_key), depth=depth + 1)
        elif isinstance(value, list):
            for child in value[:500]:
                visit(child, key=key, depth=depth + 1)
        elif isinstance(value, str):
            text = value.strip()
            if not text:
                return
            if key in {"files_changed", "changed_files", "delivery_diff"}:
                changed_files.append(text)
            elif key == "tests_passed":
                tests_passed.append(text)
            elif key in {"evidence", "summary", "raw_output", "tests_failed"}:
                evidence.append(text[:4000])

    visit(payload)
    evidence_text = "\n".join(evidence).upper()
    return {
        "changed_files": _dedupe(_normalize_relative_path(path) for path in changed_files),
        "commands_passed": bool(command_statuses) and all(code == 0 for code in command_statuses.values()),
        "tests_passed": _dedupe(tests_passed),
        "decision_recorded": "DECISION_RECORD:" in evidence_text,
        "reference_files_recorded": "REFERENCE_FILES:" in evidence_text,
        "evidence": evidence,
    }


def _checkpoint_from_proof(proof: dict[str, Any]) -> AcceptedCheckpoint:
    return AcceptedCheckpoint(
        id=f"checkpoint-{proof.get('phase_id', 'unknown')}",
        worktree=str(proof.get("worktree", "")),
        target_fingerprint=str(proof.get("repository_fingerprint", "")),
        changed_files=[str(item) for item in proof.get("changed_files", [])],
        requirement_ids=[str(item) for item in proof.get("requirement_ids", [])],
        transformation_ids=[str(item) for item in proof.get("transformation_ids", [])],
        evidence_ids=[str(proof.get("phase_id", ""))],
    )


def _proof_files_are_current(target: Path, proof: dict[str, Any]) -> bool:
    fingerprints = proof.get("file_fingerprints", {})
    return bool(fingerprints) and all(
        _changed_file_fingerprint(target, str(path)) == str(expected)
        for path, expected in fingerprints.items()
    )


def _changed_file_fingerprint(target: Path, relative: str) -> str:
    path = (target / _normalize_relative_path(relative)).resolve()
    if not _is_within(path, target):
        return "outside-target"
    if not path.exists():
        return "deleted"
    if not path.is_file():
        return "not-a-file"
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(64 * 1024):
                digest.update(chunk)
    except OSError:
        return "unreadable"
    return "sha256:" + digest.hexdigest()


def _scope_controls(write_paths: list[str], *, read_only: bool) -> dict[str, Any]:
    if read_only:
        return {"allowed_prefixes": [], "protected_prefixes": [], "target_files": [], "boundary_mode": "strict"}
    targets = [path for path in write_paths if "*" not in path]
    prefixes = [path.split("*", 1)[0].rstrip("/") + "/" for path in write_paths if "*" in path]
    return {
        "allowed_prefixes": _dedupe(prefixes),
        "protected_prefixes": [],
        "target_files": _dedupe(targets),
        "boundary_mode": "large_refactor",
    }


def _schema_errors(payloads: dict[str, dict[str, Any]]) -> list[str]:
    root = Path(__file__).resolve().parents[1]
    schemas = {
        "objective_contract.json": "objective_contract_schema.json",
        "reference_baseline.json": "reference_baseline_schema.json",
        "repository_inventory.initial.json": "repository_inventory_schema.json",
        "transformation_manifest.json": "transformation_manifest_schema.json",
        "verification_matrix.initial.json": "verification_matrix_schema.json",
    }
    errors: list[str] = []
    for payload_name, schema_name in schemas.items():
        schema = _read_json(root / "specs" / schema_name)
        if not schema:
            errors.append(f"Missing or invalid schema: {schema_name}")
            continue
        errors.extend(
            f"{payload_name}: {error}"
            for error in validate_json_subset(payloads[payload_name], schema, schema, "$")
        )
    return errors


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _paths_overlap(left: Path, right: Path) -> bool:
    return _is_within(left, right) or _is_within(right, left)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _project_id(target: Path) -> str:
    clean = "".join(char.lower() if char.isalnum() else "-" for char in target.name).strip("-")
    return clean or "goal-locked-project"


def _failure_kind(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, ensure_ascii=False).lower()
    if any(marker in text for marker in ("permission", "access denied", "cache", "toolchain", "executable", "credential", "usage limit", "preflight")):
        return "environment"
    if "timed out" in text or "timeout" in text:
        return "timeout"
    if any(marker in text for marker in ("test", "build", "lint", "verification")):
        return "test_failure"
    return "worker_failure"


def _normalize_relative_path(value: str) -> str:
    return value.replace("\\", "/").strip().lstrip("./")


def _exit_code(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


def _dedupe(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value).strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result
