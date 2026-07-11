from __future__ import annotations

import shutil
import time
import unittest
import json
from pathlib import Path

from autodev.full_roadmap_executor import FullRoadmapExecutor
from context.objective_compiler import ObjectiveCompiler
from context.builder import goal_lock_from_constraints
from context.reference_baseline import assert_write_allowed, build_reference_baseline
from context.semantic_inventory import SemanticInventoryBuilder
from planner.convergence_graph_builder import ConvergenceGraphBuilder
from planner.task_contract_validator import validate_task_contract
from planner.transformation_manifest import build_transformation_manifest
from runtime.accepted_checkpoint import AcceptedCheckpoint
from runtime.convergence_controller import diagnose_convergence
from runtime.delivery_ledger import DeliveryLedger, validate_delivery_ledger
from runtime.evaluator import Evaluator
from runtime.independent_verifier import IndependentVerifier
from runtime.models import RuntimeState, TaskGraph, TaskNode
from runtime.progress_model import proof_based_progress
from runtime.independent_verifier import repository_fingerprint


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"


class GoalLockedConvergenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = TEST_TMP_ROOT / f"goal-locked-{time.time_ns()}"
        self.target = self.root / "target"
        self.reference = self.root / "sub2api"
        self.target.mkdir(parents=True)
        self.reference.mkdir(parents=True)
        (self.target / "backend" / "ent" / "schema").mkdir(parents=True)
        (self.target / "backend" / "internal" / "server").mkdir(parents=True)
        (self.target / "frontend" / "src" / "api").mkdir(parents=True)
        (self.target / "backend" / "ent" / "schema" / "rpm_capacity.go").write_text(
            "package schema\n// RPM capacity table\n",
            encoding="utf-8",
        )
        (self.target / "backend" / "internal" / "server" / "rpm_routes.go").write_text(
            "package server\n// rpm capacity route\n",
            encoding="utf-8",
        )
        (self.target / "frontend" / "src" / "api" / "rpm.ts").write_text(
            "export const rpmCapacity = true\n",
            encoding="utf-8",
        )
        self.spec = self.root / "billing_core.md"
        self.spec.write_text(
            "\n".join(
                [
                    "# Billing Core",
                    "## Requirements",
                    "- Must implement wallet payment and usage audit capabilities.",
                    "- Must remove forbidden RPM capacity product domains from source.",
                    "- Must not create RPM capacity tables in fresh schema migrations.",
                    "- Must remove RPM capacity public API and UI copy.",
                    "- Must use original Sub2API as a read-only structural reference before large repairs.",
                    "- Must verify backend, frontend, fresh install, startup, and smoke evidence passes.",
                ]
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def test_billing_core_fixture_fails_inventory_and_plans_delete_not_rpm_repair(self) -> None:
        contract = ObjectiveCompiler().compile("Deliver Billing Core", [self.spec])
        baseline = build_reference_baseline(
            target_path=self.target,
            reference_paths=[self.reference],
        )
        inventory = SemanticInventoryBuilder().build(self.target, contract)
        manifest = build_transformation_manifest(contract, inventory)
        graph = ConvergenceGraphBuilder().build(
            project_id="billing-core",
            objective_contract=contract,
            reference_baseline=baseline,
            repository_inventory=inventory,
            transformation_manifest=manifest,
        )
        matrix = IndependentVerifier().verify(self.target, contract, inventory)

        self.assertEqual(contract.validation_errors, [])
        self.assertEqual(baseline.validation_errors, [])
        self.assertGreaterEqual(len(inventory.hits), 3)
        delete_items = [item for item in manifest.items if item.action == "delete"]
        self.assertTrue(delete_items)
        self.assertTrue(all(item.expected_final_state["inventory_hits"] == 0 for item in delete_items))
        titles = [node.title for node in graph.nodes]
        self.assertTrue(any(title.startswith("Delete forbidden rpm capacity") for title in titles))
        self.assertFalse(any("Repair final backend admin RPM capacity contracts" in title for title in titles))
        self.assertTrue(matrix.hard_failures)
        self.assertLess(proof_based_progress(matrix, delivery_ledger_coherent=False), 1.0)

    def test_reference_roles_are_enforced_and_references_are_not_writable(self) -> None:
        baseline = build_reference_baseline(target_path=self.target, reference_paths=[self.reference])

        self.assertFalse(baseline.references[0].writable)
        assert_write_allowed(baseline, [self.target / "backend" / "ok.go"])
        with self.assertRaises(ValueError):
            assert_write_allowed(baseline, [self.reference / "do_not_write.go"])

    def test_task_contract_requires_requirement_transform_and_strategy(self) -> None:
        task = {
            "id": "T002",
            "action": "delete",
            "size": "large",
            "requirement_ids": ["REQ-002"],
            "transformation_ids": ["TRANS-002"],
            "expected_final_state": {"inventory_hits": 0},
            "allowed_write_paths": ["backend/ent/schema/rpm_capacity.go"],
            "required_strategy_decision": "delete",
        }

        self.assertEqual(validate_task_contract(task), [])
        task.pop("required_strategy_decision")
        self.assertIn("medium/large edit lacks required strategy decision", " ".join(validate_task_contract(task)))

    def test_repeated_unchanged_failure_backtracks_strategy(self) -> None:
        first = diagnose_convergence(
            requirement_gaps=["REQ-002"],
            inventory_counts={"REQ-002": 3},
            previous_fingerprints=[],
            failure_kind="timeout",
        )
        third = diagnose_convergence(
            requirement_gaps=["REQ-002"],
            inventory_counts={"REQ-002": 3},
            previous_fingerprints=[first.fingerprint, first.fingerprint],
            failure_kind="timeout",
        )

        self.assertEqual(first.action, "refresh_inventory_and_replan")
        self.assertEqual(third.action, "strategy_backtrack")

    def test_evaluator_rejects_failed_or_stale_verification_matrix(self) -> None:
        matrix = {
            "hard_failures": ["REQ-002 has remaining forbidden inventory."],
            "items": [
                {"requirement_id": "REQ-002", "obligation": "static_inventory_zero", "status": "failed"},
                {"requirement_id": "REQ-003", "obligation": "fresh_schema_inventory_zero", "status": "stale"},
            ],
        }
        node = TaskNode(
            id="T001",
            title="Review delivery readiness",
            description="review",
            type="review",
            assigned_agent="reviewer",
            status="completed",
            completion_criteria=["approved"],
            evidence=[{"type": "worker_result", "result": {"status": "completed"}}],
        )
        state = RuntimeState(
            objective="Deliver",
            task_graph=TaskGraph(graph_id="g", version=1, nodes=[node]),
            github={"commit": "abc"},
            repository={"verification_matrix": matrix},
        )

        result = Evaluator().evaluate(state)

        self.assertFalse(result.done)
        self.assertTrue(any("remaining forbidden inventory" in failure for failure in result.hard_failures))
        self.assertTrue(any("is stale" in failure for failure in result.hard_failures))

    def test_delivery_ledger_requires_one_worktree(self) -> None:
        ledger = DeliveryLedger(
            baseline="base",
            target_worktree=str(self.target),
            final_fingerprint="sha256:final",
            verification_matrix_revision="sha256:matrix",
            handoff_decision="approved",
            checkpoints=[
                AcceptedCheckpoint(
                    id="C001",
                    worktree=str(self.target),
                    target_fingerprint="sha256:1",
                    changed_files=["backend/a.go"],
                    requirement_ids=["REQ-001"],
                    transformation_ids=["TRANS-001"],
                ),
                AcceptedCheckpoint(
                    id="C002",
                    worktree=str(self.root / "other"),
                    target_fingerprint="sha256:2",
                    changed_files=["backend/b.go"],
                    requirement_ids=["REQ-002"],
                    transformation_ids=["TRANS-002"],
                ),
            ],
        )

        self.assertEqual(validate_delivery_ledger(ledger), ["Accepted checkpoints reference more than one worktree."])

    def test_chinese_negative_reference_and_verification_requirements_are_compiled_with_source_spans(self) -> None:
        document = self.root / "开发文档.md"
        document.write_text(
            "\n".join(
                [
                    "# 开发要求",
                    "- 必须删除网关和上游账号池源码，不能只隐藏路由。",
                    "- 必须以原版 Sub2API 作为只读参考。",
                    "- 必须运行后端、前端、全新迁移和启动验收。",
                ]
            ),
            encoding="utf-8",
        )

        contract = ObjectiveCompiler().compile("完成产品裁剪", [document])

        self.assertEqual(contract.validation_errors, [])
        self.assertEqual(
            [item.class_name for item in contract.requirements],
            ["must_absent_source", "must_reference", "must_verify"],
        )
        self.assertEqual(contract.requirements[0].source.line_start, 2)
        self.assertEqual(contract.requirements[0].source.line_end, 2)
        self.assertTrue(contract.requirements[0].source.quote_hash.startswith("sha256:"))

    def test_positive_requirement_is_unproven_without_fresh_evidence(self) -> None:
        document = self.root / "positive.md"
        document.write_text("# Requirements\n- Must implement wallet settlement behavior.\n", encoding="utf-8")
        contract = ObjectiveCompiler().compile("Build wallet", [document])
        inventory = SemanticInventoryBuilder().build(self.target, contract)

        matrix = IndependentVerifier().verify(self.target, contract, inventory)

        self.assertTrue(matrix.hard_failures)
        self.assertTrue(all(item.status == "unproven" for item in matrix.items))
        self.assertLess(proof_based_progress(matrix, delivery_ledger_coherent=True), 1.0)

    def test_context_bundle_goal_lock_reference_preserves_contract_identity(self) -> None:
        payload = goal_lock_from_constraints(
            [
                "Goal-locked convergence is active.",
                "Goal-locked objective revision: sha256:contract",
                f"Goal-locked artifact directory: {self.root / 'run' / 'goal_locked'}",
            ]
        )

        self.assertEqual(payload["mode"], "goal_locked_convergence")
        self.assertEqual(payload["objective_contract_revision"], "sha256:contract")
        self.assertFalse(payload["legacy_unlocked"])

    def test_stale_evidence_cannot_prove_a_changed_repository(self) -> None:
        document = self.root / "verify.md"
        document.write_text("# Requirements\n- Must verify backend behavior.\n", encoding="utf-8")
        contract = ObjectiveCompiler().compile("Verify", [document])
        inventory = SemanticInventoryBuilder().build(self.target, contract)
        old_fingerprint = repository_fingerprint(self.target)
        (self.target / "changed.txt").write_text("changed\n", encoding="utf-8")

        matrix = IndependentVerifier().verify(
            self.target,
            contract,
            inventory,
            evidence={
                "REQ-001": {
                    "named_verification_passes": {
                        "status": "passed",
                        "repository_fingerprint": old_fingerprint,
                        "evidence": {"command": "test"},
                    }
                }
            },
        )

        self.assertEqual(matrix.items[0].status, "stale")
        self.assertIn("is stale", matrix.hard_failures[0])

    def test_goal_locked_executor_emits_artifacts_and_reaches_proof_based_done(self) -> None:
        forbidden = self.target / "backend" / "rpm_capacity.go"
        forbidden.parent.mkdir(parents=True, exist_ok=True)
        forbidden.write_text("package backend\n// rpm capacity\n", encoding="utf-8")
        document = self.root / "goal.md"
        document.write_text(
            "\n".join(
                [
                    "# Requirements",
                    "- Must use the original Sub2API reference as read-only guidance.",
                    "- Must remove forbidden RPM capacity from source.",
                    "- Must verify backend, frontend, build, startup, and smoke evidence.",
                ]
            ),
            encoding="utf-8",
        )

        def fake_runner(**kwargs):
            output_dir = Path(kwargs["output_dir"])
            title = Path(kwargs["documents"][-1]).read_text(encoding="utf-8").splitlines()[0].lstrip("# ")
            if "final_verification" in output_dir.as_posix():
                return GoalLockedFakeResult(
                    title,
                    evidence=[
                        "FINAL_AUDIT_STATUS: PASS",
                        "SIMULATION_TEST_STATUS: PASS",
                        "REAL_TEST_STATUS: PASS",
                    ],
                    commands=[{"command": "full verification", "exit_code": 0}],
                    tests=["full verification"],
                )
            if title.startswith("Decide governed strategy"):
                return GoalLockedFakeResult(
                    title,
                    evidence=["DECISION_RECORD: repair from declared reference", "REFERENCE_FILES: README.md"],
                )
            if title.startswith("Delete forbidden"):
                for path in self.target.rglob("*rpm*"):
                    if path.is_file():
                        path.unlink()
                return GoalLockedFakeResult(
                    title,
                    files_changed=[
                        "backend/rpm_capacity.go",
                        "backend/ent/schema/rpm_capacity.go",
                        "backend/internal/server/rpm_routes.go",
                        "frontend/src/api/rpm.ts",
                    ],
                    evidence=["DECISION_RECORD: delete forbidden dependency closure"],
                )
            return GoalLockedFakeResult(
                title,
                commands=[{"command": "verify", "exit_code": 0}],
                tests=["verify"],
            )

        result = FullRoadmapExecutor(document_runner=fake_runner).run(
            objective="Deliver the exact documented final state.",
            documents=[document],
            repository_path=self.target,
            output_dir=self.root / "run",
            run_payload={
                "full_roadmap": True,
                "real_codex": True,
                "goal_locked_convergence": True,
                "reference_repository_paths": [str(self.reference)],
            },
        )
        payload = result.to_dict()

        self.assertEqual(payload["status"], "done", json.dumps(payload["blockers"], indent=2))
        self.assertEqual(payload["goal_locked"]["progress"], 1.0)
        self.assertEqual(payload["roadmap"]["schema_version"], "roadmap_execution_plan_v2_187")
        self.assertFalse(any("Repair final backend admin RPM" in phase["title"] for phase in payload["roadmap"]["phases"]))
        for artifact in (
            "objective_contract.json",
            "reference_baseline.json",
            "repository_inventory.current.json",
            "transformation_manifest.json",
            "verification_matrix.current.json",
            "delivery_ledger.json",
        ):
            self.assertTrue((self.root / "run" / "goal_locked" / artifact).is_file(), artifact)

    def test_goal_locked_executor_blocks_worker_claim_without_edit_evidence(self) -> None:
        document = self.root / "claim.md"
        document.write_text("# Requirements\n- Must implement wallet settlement behavior.\n", encoding="utf-8")

        result = FullRoadmapExecutor(document_runner=lambda **kwargs: GoalLockedFakeResult("claim")).run(
            objective="Implement wallet settlement.",
            documents=[document],
            repository_path=self.target,
            output_dir=self.root / "claim-run",
            run_payload={"goal_locked_convergence": True},
        )

        self.assertEqual(result.status, "blocked")
        self.assertIn("reported no changed-file evidence", "\n".join(result.blockers))


class GoalLockedFakeResult:
    def __init__(
        self,
        title: str,
        *,
        files_changed: list[str] | None = None,
        evidence: list[str] | None = None,
        commands: list[dict[str, object]] | None = None,
        tests: list[str] | None = None,
    ) -> None:
        self.title = title
        self.files_changed = files_changed or []
        self.evidence = evidence or []
        self.commands = commands or []
        self.tests = tests or []

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "done",
            "blockers": [],
            "files_changed": self.files_changed,
            "commands_run": self.commands,
            "tests_passed": self.tests,
            "evidence": self.evidence,
            "runtime_state": {"done": True, "blockers": [], "task_graph": {"nodes": []}},
            "delivery_report": {
                "status": "passed",
                "final_gate": {"score": 0.95, "decision": "handoff"},
                "github": {"status": "passed"},
            },
            "requirement_coverage": {"status": "passed", "missing_requirements": []},
        }


if __name__ == "__main__":
    unittest.main()
