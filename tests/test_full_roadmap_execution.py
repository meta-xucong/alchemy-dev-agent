from __future__ import annotations

import os
import shutil
import time
import unittest
import json
from pathlib import Path

from autodev.final_system_audit import FinalSystemAudit
from autodev.final_verification_loop import FinalVerificationLoop
from autodev.document_reference_expander import expand_development_documents
from autodev.full_roadmap_executor import (
    FullRoadmapExecutor,
    blockers_are_auto_repairable,
    bootstrap_phase_repair_documents,
    interrupted_phase_resume_source,
    latest_verification_issue_context_document,
    next_phase_repair_path,
    next_phase_run_dir,
    phase_has_worker_timeout_stop_boundary,
    phase_repository_path,
    phase_run_payload,
    read_json,
    should_auto_repair_phase,
    write_json,
    write_phase_document,
    write_phase_repair_document,
)
from autodev.phase_promotion import final_handoff_allowed, next_ready_phase, phase_promotion_decision
from autodev.project_analysis_gate import ProjectAnalysisGate
from autodev.roadmap_auditor import RoadmapAuditor
from autodev.roadmap_extractor import RoadmapExtractor, classify_constraints
from autodev.roadmap_models import PhaseExecutionRecord, RoadmapExecutionPlan, RoadmapPhase


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_RUN_ID = str(time.time_ns())
_TEMP_COUNTER = 0


def temp_root() -> Path:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    root = TEST_TMP_ROOT / f"full-roadmap-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def write_v3_docs(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# Creative Agent Roadmap",
                "",
                "## V3.0 Foundation",
                "",
                "### Goal",
                "Build independent planning-only core.",
                "",
                "### Requirements",
                "- Must create schemas.",
                "- Must not import V1/V2 runtime modules.",
                "- Do not implement real image generation in V3.0 Foundation.",
                "",
                "## V3.1 Brand Consistency Foundation",
                "",
                "### Requirements",
                "- Must implement brand memory consistency.",
                "- Must preserve V3 independence.",
                "",
                "## V3.2 Generation Loop MVP",
                "",
                "### Requirements",
                "- Must implement generation loop planning.",
                "- Must not route V3 generation through V1/V2 APIs.",
            ]
        ),
        encoding="utf-8",
    )


class FakePhaseResult:
    def __init__(
        self,
        phase_title: str,
        *,
        score: float = 0.91,
        blockers: list[str] | None = None,
        evidence: list[str] | None = None,
    ) -> None:
        self.phase_title = phase_title
        self.score = score
        self.blockers = list(blockers or [])
        self.evidence = list(evidence or [])

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "done" if not self.blockers else "blocked",
            "delivery_report": {
                "final_gate": {
                    "score": self.score,
                    "dimension_scores": {
                        "test_health": 1.0,
                        "spec_alignment": self.score,
                        "graph_completion": 1.0,
                        "reviewer_approval": 1.0,
                        "risk_quality": self.score,
                    },
                    "hard_failures": list(self.blockers),
                    "required_changes": [],
                },
                "ready_for_review": True,
            },
            "runtime_state": {
                "done": not self.blockers,
                "blockers": list(self.blockers),
                "evaluation": {"done": not self.blockers, "final_gate_score": self.score},
            },
            "requirement_coverage": {"status": "passed", "covered": True},
            "scope_boundary": {"status": "passed", "protected_paths": []},
            "tests_passed": ["deterministic phase tests passed"],
            "evidence": list(self.evidence),
            "phase_title": self.phase_title,
        }


class FullRoadmapExecutionTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_roadmap_extractor_finds_later_phases_and_classifies_constraints(self) -> None:
        root = temp_root()
        doc = root / "roadmap.md"
        write_v3_docs(doc)

        plan = RoadmapExtractor().extract(
            objective="Implement the full creative agent roadmap.",
            documents=[doc],
            source_mode="github_repo",
        )

        self.assertEqual(plan.completion_policy, "full_roadmap")
        self.assertGreaterEqual(len(plan.phases), 3)
        titles = [phase.title for phase in plan.phases]
        self.assertIn("V3.0 Foundation", titles)
        self.assertIn("V3.1 Brand Consistency Foundation", titles)
        self.assertIn("V3.2 Generation Loop MVP", titles)
        self.assertTrue(any("V1/V2" in item for item in plan.global_constraints))
        v30 = plan.phases[0]
        self.assertTrue(any("real image generation" in item for item in v30.phase_local_constraints))

    def test_roadmap_extractor_ignores_v3_constraint_sentences_as_phases(self) -> None:
        root = temp_root()
        doc = root / "roadmap.md"
        doc.write_text(
            "\n".join(
                [
                    "# Roadmap",
                    "V3 may use V1/V2 only as historical reference, not as runtime dependency.",
                    "V3-owned layer:",
                    "V3 keeps the central-brain + multi-agent framework.",
                    "V3 code must not import from V1 or V2 runtime modules.",
                    "V2 concept: PromptTransformResult",
                    "",
                    "## V3.0 Foundation",
                    "- Must build foundation.",
                    "",
                    "## V3.1 Brand Consistency Foundation",
                    "- Must build brand memory.",
                    "",
                    "V3.2 Generation Loop MVP",
                    "- Must build generation loop.",
                ]
            ),
            encoding="utf-8",
        )

        plan = RoadmapExtractor().extract(objective="Build the V3 roadmap.", documents=[doc])
        titles = [phase.title for phase in plan.phases]

        self.assertEqual(titles, ["V3.0 Foundation", "V3.1 Brand Consistency Foundation", "V3.2 Generation Loop MVP"])

    def test_roadmap_extractor_keeps_decimal_phase_sections_distinct(self) -> None:
        root = temp_root()
        doc = root / "billing-plan.md"
        doc.write_text(
            "\n".join(
                [
                    "# Billing Roadmap",
                    "",
                    "## Phase 3: Wallet Core",
                    "- Establish wallet domain contract.",
                    "",
                    "## Phase 3.1: Wallet Ledger Schema",
                    "- Add wallet transaction schema and migration.",
                    "",
                    "## Phase 3.2: Wallet Service Atomic Operations",
                    "- Add idempotent credit and debit service operations.",
                    "",
                    "## Phase 4: Metering API",
                    "- Add meter debit endpoint.",
                ]
            ),
            encoding="utf-8",
        )

        plan = RoadmapExtractor().extract(objective="Build billing core.", documents=[doc])

        self.assertEqual(
            [phase.title for phase in plan.phases],
            [
                "Phase 3: Wallet Core",
                "Phase 3.1: Wallet Ledger Schema",
                "Phase 3.2: Wallet Service Atomic Operations",
                "Phase 4: Metering API",
            ],
        )

    def test_roadmap_extractor_deduplicates_versions_and_ignores_section_labels(self) -> None:
        root = temp_root()
        detailed = root / "13_STEP_BY_STEP_DELIVERY_PLAN.md"
        detailed.write_text(
            "\n".join(
                [
                    "# Plan",
                    "V3.0 Foundation",
                    "V3.1 Brand Consistency Foundation",
                    "V3.2 Generation Loop MVP",
                    "### V3.1 Out of Scope",
                    "### V3.1 Acceptance Criteria",
                    "V3.2 should allow selected vertical packs to influence evaluation policy.",
                ]
            ),
            encoding="utf-8",
        )
        roadmap = root / "05_DEVELOPMENT_ROADMAP.md"
        roadmap.write_text(
            "\n".join(
                [
                    "# Roadmap",
                    "## V3.0 Creative Core foundation",
                    "## V3.1 Brand Memory + Consistency Engine",
                    "## V3.2 Candidate Scoring + Auto Refine Loop",
                    "## V3.3 Layout Engine + External Text Rendering",
                    "# Phase 2 Prompt: V3.1 Brand Consistency Foundation",
                    "# Phase 3 Prompt: V3.2 Generation Loop MVP",
                ]
            ),
            encoding="utf-8",
        )

        plan = RoadmapExtractor().extract(objective="Build the V3 roadmap.", documents=[roadmap, detailed])
        titles = [phase.title for phase in plan.phases]

        self.assertEqual(
            titles,
            [
                "V3.0 Foundation",
                "V3.1 Brand Consistency Foundation",
                "V3.2 Generation Loop MVP",
                "V3.3 Layout Engine + External Text Rendering",
            ],
        )

    def test_roadmap_extractor_prefers_numbered_headings_over_code_fence_summaries(self) -> None:
        root = temp_root()
        plan_doc = root / "13_STEP_BY_STEP_DELIVERY_PLAN.md"
        plan_doc.write_text(
            "\n".join(
                [
                    "# Plan",
                    "```text",
                    "V3.0 Foundation",
                    "V3.1 Brand Consistency Foundation",
                    "```",
                    "",
                    "## 2. V3.0 Foundation",
                    "",
                    "### Requirements",
                    "- Build independent foundation.",
                    "- No V1/V2 runtime imports.",
                    "",
                    "## 3. V3.1 Brand Consistency Foundation",
                    "",
                    "### Requirements",
                    "- Add persistent brand memory.",
                ]
            ),
            encoding="utf-8",
        )
        reference_doc = root / "04_OPEN_SOURCE_REFERENCE_MAP.md"
        reference_doc.write_text(
            "\n".join(
                [
                    "# Reference Map",
                    "## Priority Recommendation",
                    "### Phase 1: Study and absorb ideas only",
                    "### Phase 2: Implement lightweight interfaces",
                ]
            ),
            encoding="utf-8",
        )

        plan = RoadmapExtractor().extract(objective="Build the complete V3 roadmap.", documents=[reference_doc, plan_doc])

        self.assertEqual([phase.title for phase in plan.phases], ["V3.0 Foundation", "V3.1 Brand Consistency Foundation"])
        self.assertIn("Build independent foundation.", plan.phases[0].requirements)
        self.assertIn("Add persistent brand memory.", plan.phases[1].requirements)
        self.assertFalse(any(phase.title.startswith("Phase ") for phase in plan.phases))

    def test_auditor_repairs_missing_contract_fields(self) -> None:
        plan = RoadmapExecutionPlan(root_objective="Build everything", phases=[RoadmapPhase(phase_id="", title="", requirements=[])])

        repaired, audit = RoadmapAuditor().audit_and_repair(plan)

        self.assertEqual(audit.status, "passed")
        self.assertTrue(audit.repaired)
        self.assertEqual(repaired.completion_policy, "full_roadmap")
        self.assertEqual(repaired.phases[0].phase_id, "phase_001")
        self.assertTrue(repaired.phases[0].promotion_gate)

    def test_project_analysis_gate_allows_clean_v3_roadmap_and_records_ignored_noise(self) -> None:
        root = temp_root()
        doc = root / "13_STEP_BY_STEP_DELIVERY_PLAN.md"
        doc.write_text(
            "\n".join(
                [
                    "# Plan",
                    "V3 may use V1/V2 only as historical reference, not as runtime dependency.",
                    "V3 code must not import from V1 or V2 runtime modules.",
                    "",
                    "V3.0 Foundation",
                    "- Must build foundation.",
                    "V3.1 Brand Consistency Foundation",
                    "- Must build brand consistency.",
                    "V3.2 Generation Loop MVP",
                    "- Must build generation loop.",
                    "### V3.2 Out of Scope",
                    "V3.2 should allow selected vertical packs to influence evaluation policy.",
                ]
            ),
            encoding="utf-8",
        )
        plan = RoadmapExtractor().extract(objective="Build the complete V3 roadmap.", documents=[doc])

        report = ProjectAnalysisGate().analyze(plan=plan, documents=[doc])

        self.assertTrue(report.ready_to_start)
        self.assertEqual(report.start_decision, "start")
        self.assertEqual(len(report.valid_phases), 3)
        ignored_reasons = {candidate.reason for candidate in report.ignored_phase_candidates}
        self.assertIn("constraint_or_policy_sentence", ignored_reasons)
        self.assertIn("section_label_out_of_scope", ignored_reasons)

    def test_v3_roadmap_extracts_scope_controls_for_every_phase(self) -> None:
        root = temp_root()
        doc = root / "13_STEP_BY_STEP_DELIVERY_PLAN.md"
        doc.write_text(
            "\n".join(
                [
                    "# Plan",
                    "Build the independent V3 skeleton under:",
                    "alchemy_creative_agent_3_0/app/",
                    "V3.0 must be fully independent from V1/V2.",
                    "Do not import or call any V1/V2 runtime modules.",
                    "",
                    "V3.0 Foundation",
                    "- Must build foundation.",
                    "V3.1 Brand Consistency Foundation",
                    "- Must build brand consistency.",
                ]
            ),
            encoding="utf-8",
        )

        plan = RoadmapExtractor().extract(objective="Build the complete V3 roadmap.", documents=[doc])

        self.assertGreaterEqual(len(plan.phases), 2)
        for phase in plan.phases:
            controls = phase.scope_controls
            self.assertIn("alchemy_creative_agent_3_0/", controls["allowed_prefixes"])
            self.assertIn("custom_media_agent_2_0/", controls["protected_prefixes"])
            self.assertIn("src_skeleton/", controls["protected_prefixes"])

    def test_entry_prompt_reference_expansion_reads_repository_docs(self) -> None:
        root = temp_root()
        repo = root / "repo"
        docs = repo / "alchemy_creative_agent_3_0" / "docs"
        docs.mkdir(parents=True)
        (repo / "alchemy_creative_agent_3_0" / "README.md").write_text("# V3 Readme\n", encoding="utf-8")
        entry = docs / "06_CODEX_TASK_PROMPT.md"
        entry.write_text(
            "\n".join(
                [
                    "# Task Prompt",
                    "Read these first:",
                    "```text",
                    "alchemy_creative_agent_3_0/README.md",
                    "alchemy_creative_agent_3_0/docs/13_STEP_BY_STEP_DELIVERY_PLAN.md",
                    "```",
                    "Build under alchemy_creative_agent_3_0/app/.",
                    "Do not import from V1 or V2 runtime modules.",
                ]
            ),
            encoding="utf-8",
        )
        delivery_plan = docs / "13_STEP_BY_STEP_DELIVERY_PLAN.md"
        delivery_plan.write_text(
            "\n".join(
                [
                    "# Plan",
                    "V3.0 Foundation",
                    "- Must build foundation.",
                    "V3.1 Brand Consistency Foundation",
                    "- Must build brand memory.",
                    "V3.2 Generation Loop MVP",
                    "- Must build generation loop.",
                ]
            ),
            encoding="utf-8",
        )

        expansion = expand_development_documents([entry], repository_path=repo)

        self.assertEqual(Path(expansion.documents[0]), entry.resolve())
        self.assertIn(str(delivery_plan.resolve()), expansion.documents)
        self.assertIn(str((repo / "alchemy_creative_agent_3_0" / "README.md").resolve()), expansion.documents)

    def test_executor_uses_entry_prompt_references_for_full_roadmap_analysis(self) -> None:
        root = temp_root()
        repo = root / "repo"
        docs = repo / "alchemy_creative_agent_3_0" / "docs"
        docs.mkdir(parents=True)
        entry = docs / "06_CODEX_TASK_PROMPT.md"
        entry.write_text(
            "\n".join(
                [
                    "# Task Prompt",
                    "Read these documents first:",
                    "```text",
                    "alchemy_creative_agent_3_0/docs/13_STEP_BY_STEP_DELIVERY_PLAN.md",
                    "```",
                    "V3.0 must be fully independent from V1/V2.",
                    "Build the independent V3 skeleton under:",
                    "alchemy_creative_agent_3_0/app/",
                ]
            ),
            encoding="utf-8",
        )
        (docs / "13_STEP_BY_STEP_DELIVERY_PLAN.md").write_text(
            "\n".join(
                [
                    "# Plan",
                    "V3.0 Foundation",
                    "- Must build foundation.",
                    "V3.1 Brand Consistency Foundation",
                    "- Must build brand memory.",
                    "V3.2 Generation Loop MVP",
                    "- Must build generation loop.",
                ]
            ),
            encoding="utf-8",
        )
        calls: list[str] = []

        def fake_runner(**kwargs):
            title = Path(kwargs["documents"][-1]).read_text(encoding="utf-8").splitlines()[0].lstrip("# ")
            calls.append(title)
            return FakePhaseResult(title)

        result = FullRoadmapExecutor(document_runner=fake_runner).run(
            objective="Implement the complete V3 roadmap.",
            documents=[entry],
            repository_path=repo,
            output_dir=root / "run",
        )
        payload = result.to_dict()

        self.assertEqual(payload["status"], "done")
        self.assertEqual(payload["project_analysis"]["start_decision"], "start")
        self.assertGreaterEqual(len(payload["document_expansion"]["added_documents"]), 1)
        self.assertEqual(calls[:3], ["V3.0 Foundation", "V3.1 Brand Consistency Foundation", "V3.2 Generation Loop MVP"])

    def test_phase_document_includes_scope_controls(self) -> None:
        root = temp_root()
        phase = RoadmapPhase(
            phase_id="phase_001",
            title="V3.0 Foundation",
            requirements=["Must build V3 foundation."],
            scope_controls={
                "allowed_prefixes": ["alchemy_creative_agent_3_0/"],
                "protected_prefixes": ["custom_media_agent_2_0/", "src_skeleton/"],
                "target_files": [],
            },
        )
        plan = RoadmapExecutionPlan(
            root_objective="Build V3.",
            phases=[phase],
            global_constraints=["V3 imports no V1/V2 runtime modules."],
        )

        path = write_phase_document(root / "phase.md", root_objective="Build V3.", phase=phase, plan=plan)
        text = Path(path).read_text(encoding="utf-8")

        self.assertIn("## Scope Controls", text)
        self.assertIn("Allowed implementation scope:", text)
        self.assertIn("alchemy_creative_agent_3_0/", text)
        self.assertIn("Protected paths:", text)
        self.assertIn("custom_media_agent_2_0/", text)
        self.assertIn("Treat files outside the allowed implementation scope as read-only", text)

    def test_large_refactor_phase_document_records_boundary_mode(self) -> None:
        root = temp_root()
        phase = RoadmapPhase(
            phase_id="phase_002",
            title="Phase 1: Product Rename",
            requirements=["Must update module, README, Docker/service name, and frontend title."],
            scope_controls={"boundary_mode": "large_refactor"},
        )
        plan = RoadmapExecutionPlan(root_objective="Build Billing Core.", phases=[phase])

        path = write_phase_document(root / "phase.md", root_objective="Build Billing Core.", phase=phase, plan=plan)
        text = Path(path).read_text(encoding="utf-8")

        self.assertIn("## Boundary Mode", text)
        self.assertIn("Scope boundary mode: large_refactor", text)
        self.assertIn("bounded product-scale vertical slice", text)
        self.assertIn("Do not pull requirements from later roadmap phases", text)

    def test_documentation_phase_is_scoped_to_docs_and_does_not_use_large_refactor(self) -> None:
        root = temp_root()
        doc = root / "roadmap.md"
        doc.write_text(
            "\n".join(
                [
                    "# Roadmap",
                    "## Phase 0: 文档冻结",
                    "- 本文档确认。",
                    "- 明确第一版 demo 必须独立运行。",
                ]
            ),
            encoding="utf-8",
        )

        plan = RoadmapExtractor().extract(objective="Build Billing Core.", documents=[doc])
        phase = plan.phases[0]
        plan.global_constraints = ["后端不能注册 token 中转/API 网关路由。"]
        path = write_phase_document(root / "phase.md", root_objective="Build Billing Core.", phase=phase, plan=plan)
        payload = phase_run_payload({"boundary_mode": "large_refactor"}, phase)
        text = Path(path).read_text(encoding="utf-8")

        self.assertEqual(phase.phase_type, "documentation")
        self.assertEqual(payload["boundary_mode"], "strict")
        self.assertIn("Scope boundary mode: strict", payload["constraints"])
        self.assertNotIn("Scope boundary mode: large_refactor", payload["constraints"])
        self.assertIn("Allowed implementation scope:", text)
        self.assertIn("docs/", text)
        self.assertIn("Documentation Phase Verification", text)
        self.assertIn("Global Constraints Reference", text)
        self.assertNotIn("后端不能注册 token 中转/API 网关路由。", text)

    def test_schema_build_phase_gets_minimum_iteration_budget_for_split_tail(self) -> None:
        schema_phase = RoadmapPhase(
            phase_id="phase_011",
            title="Schema pruning and build",
            requirements=["Prune Ent schema.", "Fresh DB migration succeeds.", "Frontend build/typecheck passes."],
            scope_controls={"boundary_mode": "large_refactor"},
        )
        frontend_phase = RoadmapPhase(
            phase_id="phase_010",
            title="Frontend closure",
            requirements=["Close remaining frontend navigation and copy."],
            scope_controls={"boundary_mode": "large_refactor"},
        )

        schema_payload = phase_run_payload({"boundary_mode": "large_refactor", "max_iterations": 4}, schema_phase)
        frontend_payload = phase_run_payload({"boundary_mode": "large_refactor", "max_iterations": 4}, frontend_phase)

        self.assertEqual(schema_payload["max_iterations"], 8)
        self.assertEqual(frontend_payload["max_iterations"], 4)

    def test_documentation_phase_promotion_accepts_done_with_document_evidence(self) -> None:
        phase = RoadmapPhase(
            phase_id="phase_001",
            title="Phase 0: 文档冻结",
            phase_type="documentation",
            promotion_gate={"required_score": 0.85},
        )
        result = FakePhaseResult("Phase 0: 文档冻结", score=0.84).to_dict()

        promotion = phase_promotion_decision(phase, result)

        self.assertTrue(promotion["can_promote"])
        self.assertEqual(promotion["score"], 0.85)

    def test_interrupted_phase_attempt_uses_new_run_directory(self) -> None:
        root = temp_root()
        phase_dir = root / "phases" / "phase_002"
        (phase_dir / "run" / "workers").mkdir(parents=True)
        (phase_dir / "run" / "state.json").write_text("{}", encoding="utf-8")

        self.assertEqual(next_phase_run_dir(phase_dir), phase_dir / "run_attempt_002")

        (phase_dir / "run_attempt_002").mkdir()
        self.assertEqual(next_phase_run_dir(phase_dir), phase_dir / "run_attempt_003")

    def test_blocked_phase_record_uses_new_run_directory_on_resume(self) -> None:
        root = temp_root()
        phase_dir = root / "phases" / "phase_004"
        (phase_dir / "run" / "workers").mkdir(parents=True)
        (phase_dir / "run" / "state.json").write_text("{}", encoding="utf-8")
        write_json(phase_dir / "phase_record.json", {"phase_id": "phase_004", "status": "blocked"})

        self.assertEqual(next_phase_run_dir(phase_dir), phase_dir / "run_attempt_002")

    def test_phase_repair_document_path_preserves_existing_repair_briefs(self) -> None:
        root = temp_root()
        phase_dir = root / "phases" / "phase_010"
        phase_dir.mkdir(parents=True)
        (phase_dir / "phase_repair_001.md").write_text("old repair", encoding="utf-8")
        (phase_dir / "phase_repair_002.md").write_text("old repair", encoding="utf-8")

        self.assertEqual(next_phase_repair_path(phase_dir), phase_dir / "phase_repair_003.md")

    def test_interrupted_active_phase_attempt_is_resumable(self) -> None:
        root = temp_root()
        phase_dir = root / "phases" / "phase_004"
        active_run = phase_dir / "run_attempt_006"
        (active_run / "workers").mkdir(parents=True)
        write_json(
            active_run / "state.json",
            {
                "active_tasks": ["T002"],
                "task_graph": {"nodes": [{"id": "T002", "status": "active"}]},
            },
        )
        write_json(
            active_run / "workers" / "T002.json",
            {
                "task_id": "T002",
                "status": "running",
                "worker_pid": 99999999,
            },
        )

        resume = interrupted_phase_resume_source(phase_dir)

        self.assertEqual(resume.resume_from, active_run)
        self.assertEqual(resume.active_run_dir, active_run)
        self.assertEqual(resume.blockers, [])

    def test_terminal_active_phase_attempt_is_not_resumed(self) -> None:
        root = temp_root()
        phase_dir = root / "phases" / "phase_010"
        stale_active = phase_dir / "run_attempt_019"
        (stale_active / "workers").mkdir(parents=True)
        write_json(
            stale_active / "state.json",
            {
                "active_tasks": ["T002"],
                "task_graph": {"nodes": [{"id": "T002", "status": "active"}]},
                "worker_lifecycle": [
                    {
                        "task_id": "T002",
                        "status": "timed_out",
                        "worker_pid": 99999999,
                    }
                ],
            },
        )
        write_json(
            stale_active / "workers" / "T002.json",
            {
                "task_id": "T002",
                "status": "timed_out",
                "worker_pid": 99999999,
            },
        )

        resume = interrupted_phase_resume_source(phase_dir)

        self.assertIsNone(resume.resume_from)
        self.assertIsNone(resume.active_run_dir)
        self.assertEqual(resume.blockers, [])

    def test_dead_debug_active_phase_attempt_is_not_resumed(self) -> None:
        root = temp_root()
        phase_dir = root / "phases" / "phase_010"
        stale_active = phase_dir / "run_attempt_020"
        (stale_active / "workers").mkdir(parents=True)
        write_json(
            stale_active / "state.json",
            {
                "active_tasks": ["T002-DEBUG-1"],
                "failed_tasks": ["T002"],
                "task_graph": {
                    "nodes": [
                        {"id": "T002", "status": "failed"},
                        {"id": "T002-DEBUG-1", "status": "active"},
                    ]
                },
            },
        )
        write_json(
            stale_active / "workers" / "T002-DEBUG-1.json",
            {
                "task_id": "T002-DEBUG-1",
                "status": "running",
                "worker_pid": 99999999,
            },
        )

        resume = interrupted_phase_resume_source(phase_dir)

        self.assertIsNone(resume.resume_from)
        self.assertIsNone(resume.active_run_dir)
        self.assertEqual(resume.blockers, [])

    def test_supervisor_stopped_active_phase_attempt_is_not_resumed(self) -> None:
        root = temp_root()
        phase_dir = root / "phases" / "phase_010"
        stopped_active = phase_dir / "run_attempt_025"
        (stopped_active / "workers").mkdir(parents=True)
        write_json(
            stopped_active / "state.json",
            {
                "active_tasks": ["T001"],
                "task_graph": {"nodes": [{"id": "T001", "status": "active"}]},
            },
        )
        write_json(
            stopped_active / "workers" / "T001.json",
            {
                "task_id": "T001",
                "status": "running",
                "worker_pid": 99999999,
            },
        )
        write_json(stopped_active / "supervisor_stop.json", {"reason": "same-scope retry stopped"})

        resume = interrupted_phase_resume_source(phase_dir)

        self.assertIsNone(resume.resume_from)
        self.assertIsNone(resume.active_run_dir)
        self.assertEqual(resume.blockers, [])

    def test_completed_phase_record_reuses_stable_run_directory(self) -> None:
        root = temp_root()
        phase_dir = root / "phases" / "phase_004"
        (phase_dir / "run" / "workers").mkdir(parents=True)
        (phase_dir / "run" / "state.json").write_text("{}", encoding="utf-8")
        write_json(phase_dir / "phase_record.json", {"phase_id": "phase_004", "status": "done"})

        self.assertEqual(next_phase_run_dir(phase_dir), phase_dir / "run")

    def test_project_analysis_gate_blocks_suspicious_phase_explosion(self) -> None:
        phases = [
            RoadmapPhase(phase_id=f"phase_{index:03d}", title=f"V9.{index} Feature Wave", requirements=["Implement feature."])
            for index in range(1, 23)
        ]
        plan = RoadmapExecutionPlan(root_objective="Build too many phases", phases=phases, confidence=0.9)

        report = ProjectAnalysisGate().analyze(plan=plan, max_default_phases=20)

        self.assertFalse(report.ready_to_start)
        self.assertEqual(report.start_decision, "repair_roadmap")
        self.assertTrue(any("above the default safe limit" in warning for warning in report.warnings))

    def test_constraint_classifier_does_not_block_on_negative_heavy_provider_rules(self) -> None:
        _global, local, blockers = classify_constraints(
            [
                "\n".join(
                    [
                        "### Not Included",
                        "- real GPU sidecars",
                        "- real IP-Adapter / InstantStyle",
                        "- real ControlNet",
                        "",
                        "- Do not add heavy GPU dependencies in the first implementation unless required later.",
                        "- No heavy GPU dependency is required for foundation tests.",
                        "- Real provider execution requires API key configuration.",
                    ]
                )
            ]
        )

        self.assertTrue(any("GPU" in item for item in local))
        self.assertTrue(any("ControlNet" in item for item in local))
        self.assertEqual(blockers, ["Real provider execution requires API key configuration."])

    def test_constraint_classifier_does_not_block_on_product_automation_requirements(self) -> None:
        _global, _local, blockers = classify_constraints(
            [
                "\n".join(
                    [
                        "- The user should not need to manually select models, prompts, seeds, samplers, LoRAs, ControlNet maps, or workflow nodes.",
                        "- The system should make provider selection automatic.",
                    ]
                )
            ]
        )

        self.assertEqual(blockers, [])

    def test_constraint_classifier_does_not_block_on_billing_core_migration_work(self) -> None:
        global_constraints, _local, blockers = classify_constraints(
            [
                "\n".join(
                    [
                        "- 当前 admin routes 注册了大量账号池、代理、渠道、订阅、配额接口；目标系统必须改成白名单。",
                        "- 当前 frontend router 和菜单有账号池、代理、渠道、模型、订阅等页面；目标系统必须删除这些 router/service 引用。",
                        "- 最终 demo 的 fresh migration 不能创建或依赖 token 中转站表。",
                    ]
                )
            ]
        )

        self.assertEqual(blockers, [])
        self.assertTrue(any("目标系统必须改成白名单" in item for item in global_constraints))
        self.assertTrue(any("router/service" in item for item in global_constraints))

    def test_constraint_classifier_does_not_block_on_schema_field_definitions(self) -> None:
        _global, _local, blockers = classify_constraints(
            [
                "\n".join(
                    [
                        "```json",
                        "requires_gpu: bool",
                        "provider_name: string",
                        "```",
                        "Real provider execution requires API key configuration.",
                    ]
                )
            ]
        )

        self.assertEqual(blockers, ["Real provider execution requires API key configuration."])

    def test_constraint_classifier_treats_secret_redaction_as_policy_not_blocker(self) -> None:
        global_constraints, _local, blockers = classify_constraints(
            [
                "- Normal `CandidateView.metadata` must not expose secrets, raw provider credentials, or hidden reasoning.",
            ]
        )

        self.assertEqual(blockers, [])
        self.assertTrue(any("must not expose secrets" in item for item in global_constraints))

    def test_roadmap_extractor_keeps_general_creative_workspace_phase(self) -> None:
        root = temp_root()
        doc = root / "v3-roadmap.md"
        doc.write_text(
            "\n".join(
                [
                    "# V3 Roadmap",
                    "V3.6 Scenario Pack Framework and V3 Home UI",
                    "V3.7 General Creative Workspace and Runtime Flow",
                    "V3.8 Future Vertical Agent Specialization",
                ]
            ),
            encoding="utf-8",
        )

        plan = RoadmapExtractor().extract(objective="Build all V3 phases.", documents=[doc])
        titles = [phase.title for phase in plan.phases]

        self.assertIn("V3.7 General Creative Workspace and Runtime Flow", titles)

    def test_future_vertical_phase_is_optional_and_not_auto_selected(self) -> None:
        root = temp_root()
        doc = root / "v3-roadmap.md"
        doc.write_text(
            "\n".join(
                [
                    "# V3 Roadmap",
                    "V3.7 General Creative Workspace and Runtime Flow",
                    "V3.8 Future Vertical Agent Specialization",
                ]
            ),
            encoding="utf-8",
        )

        plan = RoadmapExtractor().extract(objective="Build current V3 product target.", documents=[doc])
        by_title = {phase.title: phase for phase in plan.phases}

        self.assertTrue(by_title["V3.8 Future Vertical Agent Specialization"].optional)
        by_title["V3.7 General Creative Workspace and Runtime Flow"].status = "completed"
        self.assertIsNone(next_ready_phase(plan))

    def test_executor_stops_before_phase_execution_when_analysis_blocks_start(self) -> None:
        root = temp_root()
        doc = root / "roadmap.md"
        doc.write_text(
            "\n".join(["# Roadmap", *[f"## V9.{index} Feature Wave\n- Must implement feature {index}." for index in range(1, 23)]]),
            encoding="utf-8",
        )
        calls: list[dict[str, object]] = []

        def fake_runner(**kwargs):
            calls.append(kwargs)
            return FakePhaseResult("should not run")

        result = FullRoadmapExecutor(document_runner=fake_runner).run(
            objective="Build every phase.",
            documents=[doc],
            output_dir=root / "run",
            max_phases=20,
        )
        payload = result.to_dict()

        self.assertEqual(payload["status"], "blocked")
        self.assertFalse(calls)
        self.assertEqual(payload["project_analysis"]["start_decision"], "repair_roadmap")
        self.assertTrue((root / "run" / "project_analysis_report.json").exists())

    def test_final_handoff_is_blocked_when_required_phases_remain(self) -> None:
        plan = RoadmapExecutionPlan(
            root_objective="Build everything",
            phases=[
                RoadmapPhase(phase_id="phase_001", title="Foundation", status="completed"),
                RoadmapPhase(phase_id="phase_002", title="Generation", status="pending"),
            ],
        )

        decision = final_handoff_allowed(plan)
        audit = FinalSystemAudit().audit(plan, [])

        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["incomplete_phase_ids"], ["phase_002"])
        self.assertEqual(audit["status"], "blocked")

    def test_final_verification_report_challenges_audit_and_test_dimensions(self) -> None:
        plan = RoadmapExecutionPlan(
            root_objective="Build everything",
            phases=[RoadmapPhase(phase_id="phase_001", title="Foundation", status="completed", requirements=["Build it."])],
        )
        record = PhaseExecutionRecord(
            phase_id="phase_001",
            title="Foundation",
            status="done",
            output_dir="phase",
            result=FakePhaseResult("Foundation").to_dict(),
            promotion={"can_promote": True, "score": 0.91, "required_score": 0.85},
        )

        report = FinalVerificationLoop().audit(plan, [record], run_payload={"real_codex": False})
        payload = report.to_dict()

        self.assertEqual(payload["status"], "passed")
        self.assertTrue(payload["ready_for_final_handoff"])
        self.assertIn("roadmap_completion", {item["id"] for item in payload["dimensions"]})
        self.assertIn("deterministic_tests", {item["id"] for item in payload["test_stages"]})

    def test_final_verification_blocks_low_phase_gate_before_handoff(self) -> None:
        plan = RoadmapExecutionPlan(
            root_objective="Build everything",
            phases=[RoadmapPhase(phase_id="phase_001", title="Foundation", status="completed")],
        )
        record = PhaseExecutionRecord(
            phase_id="phase_001",
            title="Foundation",
            status="done",
            output_dir="phase",
            result=FakePhaseResult("Foundation", score=0.80).to_dict(),
            promotion={"can_promote": False, "score": 0.80, "required_score": 0.85},
        )

        audit = FinalSystemAudit().audit(plan, [record])

        self.assertEqual(audit["status"], "blocked")
        self.assertFalse(audit["ready_for_final_handoff"])
        self.assertEqual(audit["final_verification"]["status"], "iterate")

    def test_final_verification_ignores_stale_gate_failures_on_promoted_phase(self) -> None:
        plan = RoadmapExecutionPlan(
            root_objective="Build everything",
            phases=[RoadmapPhase(phase_id="phase_001", title="Foundation", status="completed")],
        )
        result = FakePhaseResult("Foundation").to_dict()
        result["delivery_report"]["final_gate"]["hard_failures"] = ["Required tests are failing."]
        result["runtime_state"]["evaluation"]["hard_failures"] = ["Required tests are failing."]
        record = PhaseExecutionRecord(
            phase_id="phase_001",
            title="Foundation",
            status="done",
            output_dir="phase",
            result=result,
            promotion={"can_promote": True, "score": 0.94, "required_score": 0.85, "reasons": []},
        )

        report = FinalVerificationLoop().audit(plan, [record], run_payload={"real_codex": False}).to_dict()

        self.assertEqual(report["status"], "passed")
        blocker_cleanliness = next(item for item in report["dimensions"] if item["id"] == "blocker_cleanliness")
        self.assertEqual(blocker_cleanliness["status"], "passed")

    def test_final_verification_still_blocks_current_payload_blockers(self) -> None:
        plan = RoadmapExecutionPlan(
            root_objective="Build everything",
            phases=[RoadmapPhase(phase_id="phase_001", title="Foundation", status="completed")],
        )
        result = FakePhaseResult("Foundation").to_dict()
        result["blockers"] = ["Current manual blocker."]
        record = PhaseExecutionRecord(
            phase_id="phase_001",
            title="Foundation",
            status="done",
            output_dir="phase",
            result=result,
            promotion={"can_promote": True, "score": 0.94, "required_score": 0.85, "reasons": []},
        )

        report = FinalVerificationLoop().audit(plan, [record], run_payload={"real_codex": False}).to_dict()

        self.assertEqual(report["status"], "iterate")
        self.assertIn("Resolve blockers", "\n".join(report["blockers"]))

    def test_final_verification_requires_supplied_known_findings_to_be_resolved(self) -> None:
        plan = RoadmapExecutionPlan(
            root_objective="Build everything",
            phases=[RoadmapPhase(phase_id="phase_001", title="Foundation", status="completed")],
        )
        record = PhaseExecutionRecord(
            phase_id="phase_001",
            title="Foundation",
            status="done",
            output_dir="phase",
            result=FakePhaseResult("Foundation").to_dict(),
            promotion={"can_promote": True, "score": 0.91, "required_score": 0.85},
        )

        audit = FinalSystemAudit().audit(
            plan,
            [record],
            run_payload={"known_final_audit_findings": ["Scenario X passes tests but violates the product contract."]},
        )
        repaired = FinalSystemAudit().audit(
            plan,
            [record],
            worker_verification={"status": "passed"},
            run_payload={"known_final_audit_findings": ["Scenario X passes tests but violates the product contract."]},
        )

        self.assertEqual(audit["status"], "blocked")
        self.assertEqual(audit["final_verification"]["status"], "iterate")
        self.assertEqual(repaired["status"], "passed")

    def test_executor_runs_all_phases_instead_of_stopping_after_first(self) -> None:
        root = temp_root()
        doc = root / "roadmap.md"
        write_v3_docs(doc)
        calls: list[str] = []

        def fake_runner(**kwargs):
            phase_doc = Path(kwargs["documents"][-1]).read_text(encoding="utf-8")
            title = phase_doc.splitlines()[0].lstrip("# ")
            calls.append(title)
            return FakePhaseResult(title)

        result = FullRoadmapExecutor(document_runner=fake_runner).run(
            objective="Implement the full creative agent roadmap.",
            documents=[doc],
            repository_path=root / "repo",
            output_dir=root / "run",
        )

        payload = result.to_dict()
        self.assertEqual(payload["status"], "done")
        self.assertGreaterEqual(len(calls), 3)
        self.assertEqual(calls[:3], ["V3.0 Foundation", "V3.1 Brand Consistency Foundation", "V3.2 Generation Loop MVP"])
        self.assertEqual(payload["final_audit"]["status"], "passed")
        phase_statuses = [phase["status"] for phase in payload["roadmap"]["phases"]]
        self.assertTrue(all(status == "completed" for status in phase_statuses))

    def test_executor_auto_repairs_low_scoring_phase_before_blocking(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        doc = root / "roadmap.md"
        write_v3_docs(doc)
        calls: list[list[str]] = []

        class LowThenPassingResult:
            def __init__(self, passing: bool) -> None:
                self.passing = passing

            def to_dict(self) -> dict[str, object]:
                score = 0.9 if self.passing else 0.84
                return {
                    "status": "done",
                    "delivery_report": {
                        "final_gate": {
                            "score": score,
                            "dimension_scores": {
                                "test_health": 1.0,
                                "spec_alignment": 0.8 if not self.passing else 0.9,
                                "graph_completion": 1.0,
                                "reviewer_approval": 1.0,
                                "risk_quality": 0.0 if not self.passing else 1.0,
                            },
                            "hard_failures": [],
                            "required_changes": [],
                        },
                        "ready_for_review": True,
                    },
                    "runtime_state": {
                        "done": self.passing,
                        "blockers": [],
                        "evaluation": {"done": self.passing, "final_gate_score": score},
                    },
                }

        def fake_runner(**kwargs):
            docs = [str(item) for item in kwargs["documents"]]
            calls.append(docs)
            return LowThenPassingResult(any("phase_repair_" in item for item in docs) or len(calls) > 1)

        result = FullRoadmapExecutor(document_runner=fake_runner).run(
            objective="Execute the full roadmap and repair phase gates automatically.",
            documents=[doc],
            repository_path=repo,
            output_dir=root / "run",
            run_payload={"max_phase_repair_attempts": 2},
        )
        payload = result.to_dict()
        phase_record = payload["phase_records"][0]

        self.assertEqual(payload["status"], "done")
        self.assertGreaterEqual(len(calls), 2)
        self.assertTrue(any("phase_repair_001.md" in item for item in calls[1]))
        self.assertEqual(phase_record["status"], "done")
        self.assertEqual(len(phase_record["promotion"]["attempts"]), 2)
        self.assertEqual(phase_record["promotion"]["attempts"][0]["status"], "blocked")
        self.assertEqual(phase_record["promotion"]["attempts"][1]["status"], "done")
        self.assertTrue((root / "run" / "phases" / "phase_001" / "phase_repair_001.md").exists())

    def test_executor_auto_repairs_technical_blocker_phase_before_blocking(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        doc = root / "roadmap.md"
        write_v3_docs(doc)
        calls: list[list[str]] = []

        class TechnicalBlockerThenPassingResult:
            def __init__(self, passing: bool) -> None:
                self.passing = passing

            def to_dict(self) -> dict[str, object]:
                blocker = {
                    "id": "B-T004-2",
                    "type": "technical_limit",
                    "description": "Retry policy exhausted for wallet recharge and payment surfaces.",
                    "task_ids": ["T004"],
                    "can_continue_partially": False,
                }
                if self.passing:
                    return FakePhaseResult("V3.0 Foundation").to_dict()
                return {
                    "status": "blocked",
                    "delivery_report": {
                        "final_gate": {
                            "score": 0.1,
                            "dimension_scores": {"test_health": 0.0, "spec_alignment": 0.0},
                            "hard_failures": ["One or more required tasks failed or are blocked."],
                            "required_changes": ["T004: resolve failed task."],
                        },
                        "ready_for_review": False,
                    },
                    "runtime_state": {
                        "done": False,
                        "blockers": [blocker],
                        "evaluation": {
                            "done": False,
                            "final_gate_score": 0.1,
                            "hard_failures": ["One or more required tasks failed or are blocked."],
                            "required_changes": ["T004: resolve failed task."],
                        },
                    },
                }

        def fake_runner(**kwargs):
            docs = [str(item) for item in kwargs["documents"]]
            calls.append(docs)
            return TechnicalBlockerThenPassingResult(len(calls) > 1 or any("phase_repair_" in item for item in docs))

        result = FullRoadmapExecutor(document_runner=fake_runner).run(
            objective="Convert Billing Core into an independent CRM system.",
            documents=[doc],
            repository_path=repo,
            output_dir=root / "run",
            run_payload={"max_phase_repair_attempts": 1},
        )
        payload = result.to_dict()
        repair_doc = root / "run" / "phases" / "phase_001" / "phase_repair_001.md"

        self.assertEqual(payload["status"], "done")
        self.assertGreaterEqual(len(calls), 2)
        self.assertTrue(any("phase_repair_001.md" in item for item in calls[1]))
        self.assertTrue(repair_doc.exists())
        repair_text = repair_doc.read_text(encoding="utf-8")
        self.assertIn("B-T004-2", repair_text)
        self.assertIn("T004: resolve failed task.", repair_text)
        self.assertEqual(payload["phase_records"][0]["promotion"]["attempts"][0]["status"], "blocked")
        self.assertEqual(payload["phase_records"][0]["promotion"]["attempts"][1]["status"], "done")

    def test_phase_repair_document_includes_focused_failed_task_evidence(self) -> None:
        root = temp_root()
        phase = RoadmapPhase(
            phase_id="phase_010",
            title="Frontend CRM Closure",
            requirements=["Close user API key and admin usage workflows."],
        )
        blocker = {
            "id": "B-T006-2",
            "type": "technical_limit",
            "description": "Retry policy exhausted for frontend API key closure.",
            "task_ids": ["T006"],
            "can_continue_partially": False,
        }
        result = {
            "status": "blocked",
            "delivery_report": {
                "final_gate": {
                    "score": 0.27,
                    "dimension_scores": {"test_health": 0.0, "spec_alignment": 0.5},
                    "hard_failures": ["One or more required tasks failed or are blocked."],
                    "required_changes": ["T006: resolve failed task."],
                }
            },
            "runtime_state": {
                "blockers": [blocker],
                "completed_tasks": ["T001", "T002", "T005"],
                "task_graph": {
                    "nodes": [
                        {"id": "T001", "status": "completed", "title": "Plan implementation"},
                        {
                            "id": "T006",
                            "status": "failed",
                            "title": "Close usage API key and admin user workflows",
                            "retry_count": 2,
                            "retry_policy": {"max_attempts": 2},
                            "relevant_files": ["frontend/src/views/user/*Key*.vue", "frontend/src/api/**"],
                            "evidence": [
                                {
                                    "type": "worker_result",
                                    "result": {
                                        "status": "partial",
                                        "summary": "Targeted checks passed, but full-suite failures are outside allowed_files.",
                                        "tests_passed": ["Targeted Vitest verification passed."],
                                        "tests_failed": [
                                            "src/components/account/__tests__/AccountUsageCell.spec.ts failed.",
                                            "src/views/admin/DashboardView.vue unhandled render error.",
                                        ],
                                        "known_issues": [
                                            "Out-of-scope full-suite failures remain in AccountUsageCell and DashboardView."
                                        ],
                                        "follow_up_tasks": [
                                            "Update out-of-scope AccountUsageCell tests or component call contract."
                                        ],
                                        "files_changed": ["frontend/src/api/keys.ts"],
                                        "worker_lifecycle": {"timeout_seconds": 900},
                                    },
                                }
                            ],
                        },
                    ]
                },
            },
        }
        repair_doc = root / "phase_repair_001.md"

        write_phase_repair_document(
            repair_doc,
            phase=phase,
            result=result,
            promotion={"required_score": 0.85, "score": 0.27, "reasons": ["Phase has blockers."]},
            attempt_index=1,
        )
        text = repair_doc.read_text(encoding="utf-8")

        self.assertIn("## Focused Repair Scope", text)
        self.assertIn("Primary failed task IDs: T006", text)
        self.assertIn("Completed tasks to preserve: T001, T002, T005", text)
        self.assertIn("AccountUsageCell.spec.ts", text)
        self.assertIn("expanded allowed files", text)
        self.assertIn("split this workflow", text)

    def test_phase_repair_document_includes_completed_verification_failures(self) -> None:
        root = temp_root()
        phase = RoadmapPhase(
            phase_id="phase_010",
            title="Frontend CRM Closure",
            requirements=["Close frontend CRM build and compliance artifacts."],
        )
        result = {
            "status": "done",
            "delivery_report": {
                "final_gate": {
                    "score": 0.42,
                    "dimension_scores": {"test_health": 0.0, "spec_alignment": 0.25},
                    "hard_failures": ["Required tests are failing."],
                    "required_changes": [],
                }
            },
            "runtime_state": {
                "completed_tasks": ["T001", "T014"],
                "task_graph": {
                    "nodes": [
                        {"id": "T001", "status": "completed", "title": "Plan implementation"},
                        {
                            "id": "T014",
                            "type": "test",
                            "status": "completed",
                            "title": "Verify implementation against project checks",
                            "relevant_files": ["frontend/src/components/admin/AdminComplianceDialog.vue"],
                            "evidence": [
                                {
                                    "type": "worker_result",
                                    "result": {
                                        "status": "partial",
                                        "summary": "Frontend build failed on missing raw Markdown imports.",
                                        "tests_failed": [
                                            "pnpm --dir frontend run build failed.",
                                        ],
                                        "known_issues": [
                                            "docs/legal/admin-compliance.zh.md and docs/legal/admin-compliance.en.md are missing.",
                                        ],
                                        "follow_up_tasks": [
                                            "Add docs/legal/admin-compliance.zh.md and docs/legal/admin-compliance.en.md.",
                                        ],
                                        "commands_run": [
                                            {
                                                "command": "pnpm --dir frontend run build",
                                                "exit_code": 1,
                                                "stderr": 'Could not resolve "../../../../docs/legal/admin-compliance.zh.md?raw" from frontend/src/components/admin/AdminComplianceDialog.vue.',
                                                "stdout": "",
                                            }
                                        ],
                                    },
                                }
                            ],
                        },
                    ]
                },
            },
        }
        repair_doc = root / "phase_repair_001.md"

        write_phase_repair_document(
            repair_doc,
            phase=phase,
            result=result,
            promotion={"required_score": 0.85, "score": 0.42, "reasons": ["Phase score 0.42 is below required 0.85."]},
            attempt_index=1,
        )
        text = repair_doc.read_text(encoding="utf-8")

        self.assertIn("## Failing Verification Issues", text)
        self.assertIn("Must repair T014 verification issue", text)
        self.assertIn("pnpm --dir frontend run build", text)
        self.assertIn("Target files:", text)
        self.assertIn("docs/legal/admin-compliance.zh.md", text)
        self.assertIn("docs/legal/admin-compliance.en.md", text)
        self.assertIn("frontend/src/components/admin/AdminComplianceDialog.vue", text)

    def test_phase_repair_document_ignores_successful_verification_warnings(self) -> None:
        root = temp_root()
        phase = RoadmapPhase(
            phase_id="phase_010",
            title="Frontend CRM Closure",
            requirements=["Close frontend CRM build and compliance artifacts."],
        )
        result = {
            "status": "done",
            "delivery_report": {
                "final_gate": {
                    "score": 0.7,
                    "dimension_scores": {"test_health": 1.0, "spec_alignment": 0.7},
                    "hard_failures": [],
                    "required_changes": [],
                }
            },
            "runtime_state": {
                "completed_tasks": ["T018"],
                "task_graph": {
                    "nodes": [
                        {
                            "id": "T018",
                            "type": "test",
                            "status": "completed",
                            "title": "Verify implementation against project checks",
                            "evidence": [
                                {
                                    "type": "worker_result",
                                    "result": {
                                        "status": "completed",
                                        "summary": "All requested verification commands completed successfully.",
                                        "known_issues": [
                                            "Repository worktree is dirty from pre-existing changes.",
                                            "Build output contains non-fatal Browserslist warnings.",
                                        ],
                                        "commands_run": [
                                            {
                                                "command": "pnpm --dir frontend run build",
                                                "exit_code": 0,
                                                "stdout": "built successfully",
                                                "stderr": "Browserslist: caniuse-lite is outdated",
                                            }
                                        ],
                                    },
                                }
                            ],
                        }
                    ]
                },
            },
        }
        repair_doc = root / "phase_repair_001.md"

        write_phase_repair_document(
            repair_doc,
            phase=phase,
            result=result,
            promotion={"required_score": 0.85, "score": 0.7, "reasons": ["Coverage evidence is incomplete."]},
            attempt_index=1,
        )
        text = repair_doc.read_text(encoding="utf-8")

        self.assertNotIn("## Failing Verification Issues", text)
        self.assertNotIn("Must repair T018 verification issue", text)
        self.assertNotIn("Browserslist", text)

    def test_bootstrap_recovers_prior_verification_failure_context(self) -> None:
        root = temp_root()
        phase_dir = root / "phase_010"
        phase_dir.mkdir(parents=True)
        phase = RoadmapPhase(
            phase_id="phase_010",
            title="Frontend CRM Closure",
            requirements=["Close frontend CRM build and compliance artifacts."],
        )
        failing_run = phase_dir / "run_attempt_041"
        later_run = phase_dir / "run_attempt_043"
        failing_run.mkdir()
        later_run.mkdir()
        write_json(
            failing_run / "state.json",
            {
                "completed_tasks": ["T001", "T014"],
                "evaluation": {
                    "final_gate_score": 0.425,
                    "hard_failures": ["Required tests are failing."],
                    "dimension_scores": {"test_health": 0.0},
                },
                "task_graph": {
                    "nodes": [
                        {"id": "T001", "status": "completed", "title": "Plan implementation"},
                        {
                            "id": "T014",
                            "type": "test",
                            "status": "completed",
                            "title": "Verify implementation against project checks",
                            "evidence": [
                                {
                                    "type": "worker_result",
                                    "result": {
                                        "status": "partial",
                                        "summary": "Frontend build failed on missing raw Markdown imports.",
                                        "tests_failed": ["pnpm --dir frontend run build failed."],
                                        "known_issues": [
                                            "docs/legal/admin-compliance.zh.md and docs/legal/admin-compliance.en.md are missing.",
                                        ],
                                        "commands_run": [
                                            {
                                                "command": "pnpm --dir frontend run build",
                                                "exit_code": 1,
                                                "stderr": 'Could not resolve "../../../../docs/legal/admin-compliance.zh.md?raw" from frontend/src/components/admin/AdminComplianceDialog.vue.',
                                            }
                                        ],
                                    },
                                }
                            ],
                        },
                    ]
                },
            },
        )
        write_json(
            later_run / "state.json",
            {
                "completed_tasks": ["T001"],
                "evaluation": {"final_gate_score": 0.7, "dimension_scores": {"spec_alignment": 0.0}},
                "task_graph": {"nodes": [{"id": "T001", "status": "completed", "title": "Plan implementation"}]},
            },
        )
        previous_record = PhaseExecutionRecord(
            phase_id="phase_010",
            title="Frontend CRM Closure",
            status="blocked",
            output_dir=str(later_run),
            result={"status": "done", "runtime_state": {}, "delivery_report": {"final_gate": {"score": 0.7}}},
            promotion={"can_promote": False, "required_score": 0.85, "score": 0.7, "reasons": ["Low score."]},
        )

        docs = bootstrap_phase_repair_documents(
            phase_dir,
            phase=phase,
            previous_record=previous_record,
            max_repair_documents=2,
        )

        self.assertEqual(len(docs), 1)
        text = Path(docs[0]).read_text(encoding="utf-8")
        self.assertIn("Repair attempt: verification-issue context", text)
        self.assertIn("Verification issue run directory:", text)
        self.assertIn("run_attempt_041", text)
        self.assertIn("docs/legal/admin-compliance.zh.md", text)
        self.assertIn("frontend/src/components/admin/AdminComplianceDialog.vue", text)

    def test_latest_verification_issue_context_stops_after_clean_test_verification(self) -> None:
        root = temp_root()
        phase_dir = root / "phase_010"
        phase_dir.mkdir(parents=True)
        phase = RoadmapPhase(
            phase_id="phase_010",
            title="Frontend CRM Closure",
            requirements=["Close frontend CRM build and compliance artifacts."],
        )
        failing_run = phase_dir / "run_attempt_041"
        clean_run = phase_dir / "run_attempt_044"
        failing_run.mkdir()
        clean_run.mkdir()
        write_json(
            failing_run / "state.json",
            {
                "completed_tasks": ["T014"],
                "evaluation": {"final_gate_score": 0.425, "hard_failures": ["Required tests are failing."]},
                "task_graph": {
                    "nodes": [
                        {
                            "id": "T014",
                            "type": "test",
                            "status": "completed",
                            "title": "Verify implementation against project checks",
                            "evidence": [
                                {
                                    "type": "worker_result",
                                    "result": {
                                        "status": "partial",
                                        "summary": "Frontend build failed on missing raw Markdown imports.",
                                        "tests_failed": ["pnpm --dir frontend run build failed."],
                                        "known_issues": [
                                            "docs/legal/admin-compliance.zh.md and docs/legal/admin-compliance.en.md are missing.",
                                        ],
                                        "commands_run": [
                                            {
                                                "command": "pnpm --dir frontend run build",
                                                "exit_code": 1,
                                                "stderr": 'Could not resolve "../../../../docs/legal/admin-compliance.zh.md?raw".',
                                            }
                                        ],
                                    },
                                }
                            ],
                        }
                    ]
                },
            },
        )
        write_json(
            clean_run / "state.json",
            {
                "completed_tasks": ["T018"],
                "evaluation": {"final_gate_score": 0.7, "dimension_scores": {"test_health": 1.0}},
                "task_graph": {
                    "nodes": [
                        {
                            "id": "T018",
                            "type": "test",
                            "status": "completed",
                            "title": "Verify implementation against project checks",
                            "evidence": [
                                {
                                    "type": "worker_result",
                                    "result": {
                                        "status": "completed",
                                        "summary": "All requested verification commands completed successfully.",
                                        "known_issues": [
                                            "Repository worktree is dirty from pre-existing changes.",
                                            "Build output contains non-fatal warning noise.",
                                        ],
                                        "commands_run": [
                                            {"command": "pnpm --dir frontend run build", "exit_code": 0}
                                        ],
                                    },
                                }
                            ],
                        }
                    ]
                },
            },
        )

        context = latest_verification_issue_context_document(phase_dir, phase=phase)

        self.assertEqual(context, "")
        self.assertEqual(list(phase_dir.glob("phase_repair_resume_*.md")), [])

    def test_blocked_low_score_phase_without_blockers_is_auto_repairable(self) -> None:
        result = {
            "status": "blocked",
            "runtime_state": {"blockers": []},
            "delivery_report": {
                "final_gate": {
                    "score": 0.7018,
                    "hard_failures": [
                        "Must requirements are missing coverage: REQ-009, REQ-022.",
                    ],
                    "required_changes": [],
                    "dimension_scores": {"spec_alignment": 0.7},
                }
            },
        }
        promotion = {"can_promote": False, "required_score": 0.85, "score": 0.7018}

        self.assertTrue(should_auto_repair_phase(promotion, result))

    def test_blocked_credential_gate_without_runtime_blockers_is_not_auto_repairable(self) -> None:
        result = {
            "status": "blocked",
            "runtime_state": {"blockers": []},
            "delivery_report": {
                "final_gate": {
                    "score": 0.2,
                    "hard_failures": ["Credential required before deployment verification can continue."],
                    "required_changes": [],
                    "dimension_scores": {"test_health": 0.2},
                }
            },
        }
        promotion = {"can_promote": False, "required_score": 0.85, "score": 0.2}

        self.assertFalse(should_auto_repair_phase(promotion, result))

    def test_bootstrap_writes_repair_doc_for_blocked_low_score_without_runtime_blockers(self) -> None:
        root = temp_root()
        phase_dir = root / "phase_010"
        phase_dir.mkdir(parents=True)
        phase = RoadmapPhase(
            phase_id="phase_010",
            title="Frontend CRM Closure",
            requirements=["Close frontend CRM build and coverage evidence."],
        )
        previous_record = PhaseExecutionRecord(
            phase_id="phase_010",
            title="Frontend CRM Closure",
            status="blocked",
            output_dir=str(phase_dir / "run_attempt_044"),
            result={
                "status": "blocked",
                "runtime_state": {
                    "blockers": [],
                    "completed_tasks": ["T017", "T018", "T019", "T020"],
                },
                "delivery_report": {
                    "final_gate": {
                        "score": 0.7018,
                        "hard_failures": [
                            "Must requirements are missing coverage: REQ-009, REQ-022.",
                        ],
                        "required_changes": [],
                        "dimension_scores": {"spec_alignment": 0.7},
                    }
                },
            },
            promotion={
                "can_promote": False,
                "required_score": 0.85,
                "score": 0.7018,
                "reasons": ["Phase score 0.70 is below required 0.85."],
            },
        )

        docs = bootstrap_phase_repair_documents(
            phase_dir,
            phase=phase,
            previous_record=previous_record,
            max_repair_documents=2,
        )

        self.assertEqual(len(docs), 1)
        text = Path(docs[0]).read_text(encoding="utf-8")
        self.assertIn("Repair attempt: 1", text)
        self.assertIn("Completed tasks to preserve: T017, T018, T019, T020", text)
        self.assertIn("Must requirements are missing coverage", text)

    def test_bootstrap_skips_empty_supervisor_stopped_attempt_for_prior_repairable_gate(self) -> None:
        root = temp_root()
        phase_dir = root / "phase_010"
        phase_dir.mkdir(parents=True)
        phase = RoadmapPhase(
            phase_id="phase_010",
            title="Frontend CRM Closure",
            requirements=["Close frontend CRM build and coverage evidence."],
        )
        repairable_run = phase_dir / "run_attempt_044"
        stopped_run = phase_dir / "run_attempt_045"
        repairable_run.mkdir()
        stopped_run.mkdir()
        write_json(
            repairable_run / "document_run_report.json",
            {
                "status": "blocked",
                "runtime_state": {
                    "blockers": [],
                    "completed_tasks": ["T017", "T018", "T019", "T020"],
                },
                "delivery_report": {
                    "final_gate": {
                        "score": 0.7018,
                        "hard_failures": [
                            "Must requirements are missing coverage: REQ-009, REQ-022.",
                        ],
                        "required_changes": [],
                        "dimension_scores": {"spec_alignment": 0.7},
                    }
                },
            },
        )
        write_json(
            stopped_run / "supervisor_stop.json",
            {"reason": "Stopped invalid broad graph."},
        )
        previous_record = PhaseExecutionRecord(
            phase_id="phase_010",
            title="Frontend CRM Closure",
            status="blocked",
            output_dir=str(stopped_run),
            result={
                "status": "blocked",
                "runtime_state": {
                    "blockers": [
                        {
                            "id": "B-T001-0",
                            "type": "technical_limit",
                            "description": "Codex worker was cancelled by operator stop request.",
                            "task_ids": ["T001"],
                            "can_continue_partially": False,
                        }
                    ],
                    "completed_tasks": [],
                },
            },
            promotion={
                "can_promote": False,
                "required_score": 0.85,
                "score": 0.0,
                "reasons": ["Phase has blockers."],
            },
        )

        docs = bootstrap_phase_repair_documents(
            phase_dir,
            phase=phase,
            previous_record=previous_record,
            max_repair_documents=2,
        )

        self.assertEqual(len(docs), 1)
        text = Path(docs[0]).read_text(encoding="utf-8")
        self.assertIn("Completed tasks to preserve: T017, T018, T019, T020", text)
        self.assertIn("Must requirements are missing coverage", text)
        self.assertNotIn("operator stop request", text)

    def test_executor_revalidates_existing_promotable_attempt_before_new_phase_run(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        output = root / "run"
        phase_dir = output / "phases" / "phase_010"
        repairable_run = phase_dir / "run_attempt_047"
        blocked_run = phase_dir / "run_attempt_048"
        repairable_run.mkdir(parents=True)
        blocked_run.mkdir()
        plan = RoadmapExecutionPlan(
            root_objective="Convert Billing Core into an independent CRM system.",
            phases=[
                RoadmapPhase(
                    phase_id="phase_010",
                    title="Frontend CRM Closure",
                    requirements=["Close frontend CRM workflows."],
                )
            ],
            confidence=0.9,
        )
        write_json(output / "roadmap_execution_plan.json", plan.to_dict())
        write_json(output / "roadmap_audit.json", {"status": "passed", "issues": []})
        write_json(output / "project_analysis_report.json", {"ready_to_start": True})
        write_json(
            phase_dir / "phase_record.json",
            {
                "phase_id": "phase_010",
                "title": "Frontend CRM Closure",
                "status": "blocked",
                "output_dir": str(blocked_run),
                "result": {"status": "blocked", "runtime_state": {"blockers": []}},
                "promotion": {"can_promote": False, "score": 0.1455, "reasons": ["Phase has blockers."]},
            },
        )
        runtime_state = {
            "objective": "phase 010",
            "task_graph": {
                "graph_id": "phase-010",
                "version": 1,
                "nodes": [
                    {
                        "id": "T001",
                        "title": "Preserved frontend closure",
                        "description": "Preserved completed frontend work.",
                        "type": "frontend",
                        "assigned_agent": "frontend",
                        "status": "completed",
                        "completion_criteria": ["Preserved completion evidence is carried forward."],
                        "evidence": [{"type": "focused_repair_preserved_task", "result": {"status": "completed"}}],
                    },
                    {
                        "id": "T024",
                        "title": "Verify implementation against project checks",
                        "description": "Run verification.",
                        "type": "test",
                        "assigned_agent": "test",
                        "status": "completed",
                        "completion_criteria": ["Verification passes."],
                        "evidence": [
                            {
                                "type": "worker_result",
                                "result": {
                                    "status": "completed",
                                    "tests_failed": [],
                                    "known_issues": ["Frontend build emitted a non-fatal Vite dynamic import warning."],
                                },
                            }
                        ],
                    },
                    {
                        "id": "T025",
                        "title": "Review delivery readiness",
                        "description": "Review evidence.",
                        "type": "review",
                        "assigned_agent": "review",
                        "status": "completed",
                        "completion_criteria": ["Reviewer approves."],
                        "evidence": [{"type": "worker_result", "result": {"status": "completed", "tests_failed": []}}],
                    },
                    {
                        "id": "T026",
                        "title": "Record delivery evidence",
                        "description": "Record evidence.",
                        "type": "release",
                        "assigned_agent": "release",
                        "status": "completed",
                        "completion_criteria": ["Delivery evidence is recorded."],
                        "evidence": [{"type": "ci_result", "result": {"status": "completed"}}],
                    },
                ],
                "dependencies": [],
            },
            "active_tasks": [],
            "completed_tasks": ["T001", "T024", "T025", "T026"],
            "failed_tasks": [],
            "blockers": [],
            "github": {"commit": "local-evidence", "pull_request_url": "local-delivery"},
            "repository": {
                "requirement_coverage": {
                    "coverage_score": 0.9,
                    "missing_must_requirement_ids": [],
                    "partial_must_requirement_ids": [],
                }
            },
        }
        write_json(
            repairable_run / "document_run_report.json",
            {
                "status": "done",
                "runtime_state": runtime_state,
                "delivery_report": {
                    "ready_for_review": False,
                    "final_gate": {"score": 0.6945, "reason": "Old evaluator score was below threshold."},
                },
            },
        )

        def fail_runner(**_kwargs):
            self.fail("promotable existing attempt should be reused before launching a new phase run")

        result = FullRoadmapExecutor(document_runner=fail_runner).run(
            objective="Convert Billing Core into an independent CRM system.",
            documents=[],
            repository_path=repo,
            output_dir=output,
            max_phases=1,
            run_payload={"max_phase_repair_attempts": 2},
        )
        record = read_json(phase_dir / "phase_record.json")

        self.assertEqual(result.phase_records[-1]["status"], "done")
        self.assertEqual(record["status"], "done")
        self.assertEqual(record["output_dir"], str(repairable_run))
        self.assertGreaterEqual(record["promotion"]["score"], 0.85)

    def test_executor_bootstraps_blocked_phase_resume_with_repair_evidence(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        doc = root / "roadmap.md"
        write_v3_docs(doc)
        blocker = {
            "id": "B-T006-2",
            "type": "technical_limit",
            "description": "Retry policy exhausted for frontend API key closure.",
            "task_ids": ["T006"],
            "can_continue_partially": False,
        }

        class BlockingPhaseResult:
            def to_dict(self) -> dict[str, object]:
                return {
                    "status": "blocked",
                    "delivery_report": {
                        "final_gate": {
                            "score": 0.27,
                            "dimension_scores": {"test_health": 0.0, "spec_alignment": 0.5},
                            "hard_failures": ["One or more required tasks failed or are blocked."],
                            "required_changes": ["T006: resolve failed task."],
                        },
                        "ready_for_review": False,
                    },
                    "runtime_state": {
                        "done": False,
                        "blockers": [blocker],
                        "completed_tasks": ["T001", "T002", "T005"],
                        "task_graph": {
                            "nodes": [
                                {"id": "T001", "status": "completed", "title": "Plan implementation"},
                                {
                                    "id": "T006",
                                    "status": "failed",
                                    "title": "Close usage API key and admin user workflows",
                                    "evidence": [
                                        {
                                            "type": "worker_result",
                                            "result": {
                                                "status": "partial",
                                                "summary": "Full-suite failures are outside allowed_files.",
                                                "tests_failed": ["src/components/account/__tests__/AccountUsageCell.spec.ts failed."],
                                            },
                                        }
                                    ],
                                },
                            ]
                        },
                    },
                }

        first_result = FullRoadmapExecutor(document_runner=lambda **_: BlockingPhaseResult()).run(
            objective="Convert Billing Core into an independent CRM system.",
            documents=[doc],
            repository_path=repo,
            output_dir=root / "run",
            run_payload={"max_phase_repair_attempts": 0},
        )
        self.assertEqual(first_result.status, "blocked")

        calls: list[list[str]] = []

        def resume_runner(**kwargs):
            docs = [str(item) for item in kwargs["documents"]]
            calls.append(docs)
            return FakePhaseResult("resumed phase")

        second_result = FullRoadmapExecutor(document_runner=resume_runner).run(
            objective="Convert Billing Core into an independent CRM system.",
            documents=[doc],
            repository_path=repo,
            output_dir=root / "run",
            run_payload={"max_phase_repair_attempts": 1},
        )
        payload = second_result.to_dict()
        repair_doc = root / "run" / "phases" / "phase_001" / "phase_repair_resume_001.md"

        self.assertEqual(payload["status"], "done")
        self.assertGreaterEqual(len(calls), 1)
        self.assertTrue(
            any("phase_001" in item and "phase_repair_resume_" in item for docs in calls for item in docs),
            calls,
        )
        self.assertTrue(repair_doc.exists())
        self.assertIn("Primary failed task IDs: T006", repair_doc.read_text(encoding="utf-8"))

    def test_executor_reuses_newer_disk_repair_brief_when_phase_record_is_stale(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        output = root / "run"
        phase_dir = output / "phases" / "phase_010"
        phase_dir.mkdir(parents=True)
        plan = RoadmapExecutionPlan(
            root_objective="Convert Billing Core into an independent CRM system.",
            phases=[
                RoadmapPhase(
                    phase_id="phase_010",
                    title="Frontend CRM Closure",
                    requirements=["Sweep frontend product copy and i18n."],
                )
            ],
            confidence=0.9,
        )
        write_json(output / "roadmap_execution_plan.json", plan.to_dict())
        write_json(output / "roadmap_audit.json", {"status": "passed", "issues": []})
        write_json(output / "project_analysis_report.json", {"ready_to_start": True})
        stale_record = phase_dir / "phase_record.json"
        write_json(
            stale_record,
            {
                "phase_id": "phase_010",
                "title": "Frontend CRM Closure",
                "status": "blocked",
                "output_dir": str(phase_dir / "run_attempt_028"),
                "result": {
                    "status": "blocked",
                    "runtime_state": {
                        "blockers": [
                            {
                                "type": "environment",
                                "description": "Codex CLI usage limit reached.",
                                "task_ids": ["T001"],
                            }
                        ]
                    },
                },
                "promotion": {"can_promote": False, "reasons": ["Phase has blockers."]},
            },
        )
        repair_doc = phase_dir / "phase_repair_006.md"
        repair_doc.write_text(
            "\n".join(
                [
                    "# Auto Repair For Frontend CRM Closure",
                    "",
                    "- Primary failed task IDs: T007.",
                    "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task.",
                    "### Task T007 - Sweep frontend product copy and i18n",
                    "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        old_time = time.time() - 60
        os.utime(stale_record, (old_time, old_time))

        calls: list[list[str]] = []

        def resume_runner(**kwargs):
            docs = [str(item) for item in kwargs["documents"]]
            calls.append(docs)
            return FakePhaseResult("resumed from disk repair")

        result = FullRoadmapExecutor(document_runner=resume_runner).run(
            objective="Convert Billing Core into an independent CRM system.",
            documents=[],
            repository_path=repo,
            output_dir=output,
            run_payload={"max_phase_repair_attempts": 1},
        )

        self.assertEqual(result.status, "done")
        self.assertTrue(any(str(repair_doc.resolve()) in docs for docs in calls), calls)
        self.assertFalse(
            any("phase_repair_resume_" in item for docs in calls for item in docs),
            calls,
        )

    def test_executor_reuses_recent_disk_repair_briefs_when_latest_depends_on_prior_split(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        output = root / "run"
        phase_dir = output / "phases" / "phase_010"
        phase_dir.mkdir(parents=True)
        plan = RoadmapExecutionPlan(
            root_objective="Convert Billing Core into an independent CRM system.",
            phases=[
                RoadmapPhase(
                    phase_id="phase_010",
                    title="Frontend CRM Closure",
                    requirements=["Close frontend CRM workflows."],
                )
            ],
            confidence=0.9,
        )
        write_json(output / "roadmap_execution_plan.json", plan.to_dict())
        write_json(output / "roadmap_audit.json", {"status": "passed", "issues": []})
        write_json(output / "project_analysis_report.json", {"ready_to_start": True})
        stale_record = phase_dir / "phase_record.json"
        write_json(
            stale_record,
            {
                "phase_id": "phase_010",
                "title": "Frontend CRM Closure",
                "status": "blocked",
                "result": {"status": "blocked", "runtime_state": {"blockers": []}},
                "promotion": {"can_promote": False, "reasons": ["Phase has blockers."]},
            },
        )
        repair_006 = phase_dir / "phase_repair_006.md"
        repair_006.write_text(
            "\n".join(
                [
                    "# Auto Repair",
                    "- Primary failed task IDs: T007.",
                    "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006.",
                    "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        repair_007 = phase_dir / "phase_repair_007.md"
        repair_007.write_text(
            "\n".join(
                [
                    "# Auto Repair",
                    "- Primary failed task IDs: T009.",
                    "- Completed tasks to preserve: T007, T008, T001, T002, T003, T004, T005, T006.",
                    "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        old_time = time.time() - 90
        os.utime(stale_record, (old_time, old_time))
        repair_006_time = time.time() - 30
        repair_007_time = time.time() - 10
        os.utime(repair_006, (repair_006_time, repair_006_time))
        os.utime(repair_007, (repair_007_time, repair_007_time))

        calls: list[list[str]] = []

        def resume_runner(**kwargs):
            docs = [str(item) for item in kwargs["documents"]]
            calls.append(docs)
            return FakePhaseResult("resumed from cumulative disk repairs")

        result = FullRoadmapExecutor(document_runner=resume_runner).run(
            objective="Convert Billing Core into an independent CRM system.",
            documents=[],
            repository_path=repo,
            output_dir=output,
            run_payload={"max_phase_repair_attempts": 2},
        )

        self.assertEqual(result.status, "done")
        self.assertEqual(len(calls), 1)
        docs = calls[0]
        self.assertIn(str(repair_006.resolve()), docs)
        self.assertIn(str(repair_007.resolve()), docs)
        self.assertLess(docs.index(str(repair_006.resolve())), docs.index(str(repair_007.resolve())))
        self.assertFalse(any("phase_repair_resume_" in item for item in docs), docs)

    def test_blocked_phase_resume_keeps_recent_repair_context_even_when_record_is_newer(self) -> None:
        root = temp_root()
        phase_dir = root / "phase_010"
        phase_dir.mkdir()
        record_path = phase_dir / "phase_record.json"
        write_json(record_path, {"phase_id": "phase_010", "status": "blocked"})
        for name, task_id in (("phase_repair_006.md", "T007"), ("phase_repair_007.md", "T009")):
            (phase_dir / name).write_text(
                "\n".join(
                    [
                        "# Auto Repair",
                        f"- Primary failed task IDs: {task_id}.",
                        "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
        old_time = time.time() - 60
        os.utime(phase_dir / "phase_repair_006.md", (old_time, old_time))
        os.utime(phase_dir / "phase_repair_007.md", (old_time + 10, old_time + 10))
        new_time = time.time()
        os.utime(record_path, (new_time, new_time))
        previous_record = PhaseExecutionRecord(
            phase_id="phase_010",
            title="Frontend CRM Closure",
            status="blocked",
            output_dir=str(phase_dir / "run_attempt_038"),
            result={
                "status": "blocked",
                "runtime_state": {
                    "blockers": [
                        {
                            "type": "technical_limit",
                            "description": "T010 exceeded the Codex worker timeout.",
                            "task_ids": ["T010"],
                        }
                    ]
                },
            },
            promotion={"can_promote": False, "reasons": ["Phase has blockers."]},
        )

        docs = bootstrap_phase_repair_documents(
            phase_dir,
            phase=RoadmapPhase(phase_id="phase_010", title="Frontend CRM Closure", requirements=[]),
            previous_record=previous_record,
            max_repair_documents=2,
        )

        names = [Path(item).name for item in docs]
        self.assertEqual(names, ["phase_repair_006.md", "phase_repair_007.md", "phase_repair_resume_001.md"])

    def test_supervisor_stopped_phase_keeps_existing_repair_docs_when_record_is_newer(self) -> None:
        root = temp_root()
        phase_dir = root / "phase_011"
        stopped = phase_dir / "run_attempt_005"
        stopped.mkdir(parents=True)
        record_path = phase_dir / "phase_record.json"
        write_json(record_path, {"phase_id": "phase_011", "status": "blocked", "output_dir": str(stopped)})
        write_json(stopped / "supervisor_stop.json", {"reason": "stale repair graph stopped"})
        for name, task_id in (("phase_repair_001.md", "T002"), ("phase_repair_002.md", "T002")):
            (phase_dir / name).write_text(
                "\n".join(
                    [
                        "# Auto Repair",
                        f"- Primary failed task IDs: {task_id}.",
                        "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
        old_time = time.time() - 120
        os.utime(phase_dir / "phase_repair_001.md", (old_time, old_time))
        os.utime(phase_dir / "phase_repair_002.md", (old_time + 10, old_time + 10))
        new_time = time.time()
        os.utime(record_path, (new_time, new_time))
        previous_record = PhaseExecutionRecord(
            phase_id="phase_011",
            title="Schema build",
            status="blocked",
            output_dir=str(stopped),
            result={
                "status": "blocked",
                "runtime_state": {
                    "blockers": [
                        {
                            "type": "technical_limit",
                            "description": "Codex worker was cancelled by operator stop request.",
                            "task_ids": ["T001"],
                        }
                    ]
                },
            },
            promotion={"can_promote": False, "reasons": ["Phase has blockers."]},
        )

        docs = bootstrap_phase_repair_documents(
            phase_dir,
            phase=RoadmapPhase(phase_id="phase_011", title="Schema build", requirements=[]),
            previous_record=previous_record,
            max_repair_documents=2,
        )

        names = [Path(item).name for item in docs]
        self.assertEqual(names, ["phase_repair_001.md", "phase_repair_002.md"])

    def test_schema_phase_repair_context_keeps_full_split_chain_beyond_repair_budget(self) -> None:
        root = temp_root()
        phase_dir = root / "phase_011"
        stopped = phase_dir / "run_attempt_010"
        stopped.mkdir(parents=True)
        record_path = phase_dir / "phase_record.json"
        write_json(record_path, {"phase_id": "phase_011", "status": "blocked", "output_dir": str(stopped)})
        write_json(stopped / "supervisor_stop.json", {"reason": "stale split context stopped"})
        for index, task_id in (
            (1, "T002"),
            (2, "T002"),
            (3, "T003"),
            (4, "T003"),
            (5, "T006"),
            (6, "T006"),
            (7, "T008"),
            (8, "T009"),
            (9, "T010"),
            (10, "T014"),
            (11, "T015"),
            (12, "T022"),
            (13, "T023"),
            (14, "T024"),
        ):
            repair_doc = phase_dir / f"phase_repair_{index:03d}.md"
            repair_doc.write_text(
                "\n".join(
                    [
                        "# Auto Repair",
                        f"- Primary failed task IDs: {task_id}.",
                        "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            old_time = time.time() - (120 - index)
            os.utime(repair_doc, (old_time, old_time))
        new_time = time.time()
        os.utime(record_path, (new_time, new_time))
        previous_record = PhaseExecutionRecord(
            phase_id="phase_011",
            title="Schema build",
            status="blocked",
            output_dir=str(stopped),
            result={"status": "blocked", "runtime_state": {"blockers": []}},
            promotion={"can_promote": False, "reasons": ["Phase has blockers."]},
        )

        docs = bootstrap_phase_repair_documents(
            phase_dir,
            phase=RoadmapPhase(
                phase_id="phase_011",
                title="Schema build",
                requirements=["Prune Ent schema.", "Fresh DB migration succeeds."],
            ),
            previous_record=previous_record,
            max_repair_documents=2,
        )

        names = [Path(item).name for item in docs]
        self.assertEqual(
            names,
            [
                "phase_repair_001.md",
                "phase_repair_002.md",
                "phase_repair_003.md",
                "phase_repair_004.md",
                "phase_repair_005.md",
                "phase_repair_006.md",
                "phase_repair_007.md",
                "phase_repair_008.md",
                "phase_repair_009.md",
                "phase_repair_010.md",
                "phase_repair_011.md",
                "phase_repair_012.md",
                "phase_repair_013.md",
                "phase_repair_014.md",
            ],
        )

    def test_worker_timeout_stop_boundary_bootstrap_reuses_existing_repair_context(self) -> None:
        root = temp_root()
        phase_dir = root / "phase_011"
        run_dir = phase_dir / "run_attempt_017"
        run_dir.mkdir(parents=True)
        record_path = phase_dir / "phase_record.json"
        write_json(record_path, {"phase_id": "phase_011", "status": "blocked", "output_dir": str(run_dir)})
        for index, task_id in ((6, "T006"), (7, "T008")):
            repair_doc = phase_dir / f"phase_repair_{index:03d}.md"
            repair_doc.write_text(
                "\n".join(
                    [
                        "# Auto Repair",
                        f"- Primary failed task IDs: {task_id}.",
                        "- Completed tasks to preserve: T006, T007, T001, T002, T003, T004, T005.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            old_time = time.time() - (60 - index)
            os.utime(repair_doc, (old_time, old_time))
        os.utime(record_path, (time.time(), time.time()))
        phase = RoadmapPhase(
            phase_id="phase_011",
            title="Phase 8: Schema pruning and build",
            requirements=["Prune Ent schema.", "Regenerate Ent.", "Fresh DB migration succeeds."],
        )
        result = {
            "status": "blocked",
            "runtime_state": {
                "blockers": [
                    {
                        "id": "B-T008-1",
                        "type": "technical_limit",
                        "can_continue_partially": False,
                        "description": "T008 exceeded the Codex worker timeout. Stop instead of launching a same-scope debug task.",
                    }
                ]
            },
        }
        promotion = {
            "can_promote": False,
            "required_score": 0.85,
            "score": 0.1528,
            "reasons": ["Phase has blockers."],
        }
        previous_record = PhaseExecutionRecord(
            phase_id="phase_011",
            title=phase.title,
            status="blocked",
            output_dir=str(run_dir),
            result=result,
            promotion=promotion,
        )

        self.assertFalse(should_auto_repair_phase(promotion, result))
        docs = bootstrap_phase_repair_documents(
            phase_dir,
            phase=phase,
            previous_record=previous_record,
            max_repair_documents=2,
        )

        self.assertEqual([Path(item).name for item in docs], ["phase_repair_006.md", "phase_repair_007.md"])

    def test_supervisor_stopped_attempt_context_preserves_newer_completed_tasks(self) -> None:
        root = temp_root()
        phase_dir = root / "phase_010"
        stopped = phase_dir / "run_attempt_040"
        stopped.mkdir(parents=True)
        record_path = phase_dir / "phase_record.json"
        write_json(record_path, {"phase_id": "phase_010", "status": "blocked"})
        for name, task_id in (("phase_repair_006.md", "T007"), ("phase_repair_007.md", "T009")):
            (phase_dir / name).write_text(
                "\n".join(
                    [
                        "# Auto Repair",
                        f"- Primary failed task IDs: {task_id}.",
                        "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
        write_json(
            stopped / "state.json",
            {
                "active_tasks": ["T012"],
                "completed_tasks": ["T001", "T010"],
                "task_graph": {
                    "nodes": [
                        {"id": "T010", "status": "completed"},
                        {"id": "T011", "status": "completed"},
                        {"id": "T012", "status": "active"},
                    ]
                },
            },
        )
        write_json(stopped / "supervisor_stop.json", {"reason": "pause for output budget fix"})
        old_time = time.time() - 60
        os.utime(record_path, (old_time, old_time))
        os.utime(phase_dir / "phase_repair_006.md", (old_time - 30, old_time - 30))
        os.utime(phase_dir / "phase_repair_007.md", (old_time - 20, old_time - 20))
        os.utime(stopped / "state.json", (old_time + 20, old_time + 20))
        previous_record = PhaseExecutionRecord(
            phase_id="phase_010",
            title="Frontend CRM Closure",
            status="blocked",
            output_dir=str(phase_dir / "run_attempt_038"),
            result={
                "status": "blocked",
                "runtime_state": {
                    "blockers": [
                        {
                            "type": "technical_limit",
                            "description": "T010 exceeded the Codex worker timeout.",
                            "task_ids": ["T010"],
                        }
                    ]
                },
            },
            promotion={"can_promote": False, "reasons": ["Phase has blockers."]},
        )

        docs = bootstrap_phase_repair_documents(
            phase_dir,
            phase=RoadmapPhase(phase_id="phase_010", title="Frontend CRM Closure", requirements=[]),
            previous_record=previous_record,
            max_repair_documents=2,
        )

        names = [Path(item).name for item in docs]
        self.assertEqual(names, ["phase_repair_006.md", "phase_repair_007.md", "phase_repair_resume_001.md"])
        context = Path(docs[-1]).read_text(encoding="utf-8")
        self.assertIn("Completed tasks to preserve: T001, T010, T011.", context)
        self.assertIn("Active tasks at supervisor stop: T012.", context)
        self.assertIn("Primary failed task IDs: T012, T010.", context)
        self.assertIn("Task T010 previously exceeded the Codex worker timeout", context)

        docs_again = bootstrap_phase_repair_documents(
            phase_dir,
            phase=RoadmapPhase(phase_id="phase_010", title="Frontend CRM Closure", requirements=[]),
            previous_record=previous_record,
            max_repair_documents=2,
        )

        self.assertEqual([Path(item).name for item in docs_again], names)

    def test_iteration_limit_context_preserves_clean_completed_tasks(self) -> None:
        root = temp_root()
        phase_dir = root / "phase_011"
        phase_dir.mkdir(parents=True)
        iteration_run = phase_dir / "run_attempt_023"
        stopped_run = phase_dir / "run_attempt_024"
        iteration_run.mkdir()
        stopped_run.mkdir()
        record_path = phase_dir / "phase_record.json"
        write_json(record_path, {"phase_id": "phase_011", "status": "blocked", "output_dir": str(stopped_run)})
        for index, task_id in ((10, "T016"), (11, "T022")):
            (phase_dir / f"phase_repair_{index:03d}.md").write_text(
                "\n".join(
                    [
                        "# Auto Repair",
                        f"- Primary failed task IDs: {task_id}.",
                        "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
        write_json(
            iteration_run / "state.json",
            {
                "active_tasks": [],
                "blockers": [],
                "completed_tasks": ["T022", "T023", "T024", "T025"],
                "failed_tasks": [],
                "execution_history": [
                    {"type": "task_completed", "task_id": "T025"},
                    {"type": "iteration_limit", "summary": "Stopped after 4 iterations."},
                ],
                "task_graph": {
                    "nodes": [
                        {"id": f"T{index:03d}", "status": "completed"}
                        for index in range(1, 26)
                    ]
                    + [
                        {"id": "T026", "status": "pending"},
                        {"id": "T027", "status": "pending"},
                    ]
                },
            },
        )
        write_json(stopped_run / "state.json", {"active_tasks": [], "completed_tasks": [], "task_graph": {"nodes": []}})
        write_json(stopped_run / "supervisor_stop.json", {"reason": "bad restart stopped"})
        old_time = time.time() - 120
        os.utime(phase_dir / "phase_repair_010.md", (old_time, old_time))
        os.utime(phase_dir / "phase_repair_011.md", (old_time + 10, old_time + 10))
        os.utime(iteration_run / "state.json", (old_time + 20, old_time + 20))
        os.utime(record_path, (old_time + 60, old_time + 60))
        previous_record = PhaseExecutionRecord(
            phase_id="phase_011",
            title="Schema pruning and build",
            status="blocked",
            output_dir=str(stopped_run),
            result={"status": "blocked", "runtime_state": {"blockers": []}},
            promotion={"can_promote": False, "reasons": ["Phase score is below required threshold."]},
        )

        docs = bootstrap_phase_repair_documents(
            phase_dir,
            phase=RoadmapPhase(
                phase_id="phase_011",
                title="Schema pruning and build",
                requirements=["Prune Ent schema.", "Fresh DB migration succeeds."],
            ),
            previous_record=previous_record,
            max_repair_documents=2,
        )

        names = [Path(item).name for item in docs]
        self.assertEqual(names, ["phase_repair_010.md", "phase_repair_011.md", "phase_repair_resume_001.md"])
        context = Path(docs[-1]).read_text(encoding="utf-8")
        self.assertIn("Repair attempt: iteration-limit context", context)
        self.assertIn("Primary failed task IDs: T026, T027.", context)
        self.assertIn("Completed tasks to preserve: T022, T023, T024, T025", context)
        self.assertIn(f"Iteration-limit run directory: {iteration_run}", context)

    def test_existing_repair_context_does_not_exhaust_new_repair_budget(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        output = root / "run"
        phase_dir = output / "phases" / "phase_010"
        phase_dir.mkdir(parents=True)
        plan = RoadmapExecutionPlan(
            root_objective="Convert Billing Core into an independent CRM system.",
            phases=[
                RoadmapPhase(
                    phase_id="phase_010",
                    title="Frontend CRM Closure",
                    requirements=["Close frontend CRM workflows."],
                )
            ],
            confidence=0.9,
        )
        write_json(output / "roadmap_execution_plan.json", plan.to_dict())
        write_json(output / "roadmap_audit.json", {"status": "passed", "issues": []})
        write_json(output / "project_analysis_report.json", {"ready_to_start": True})
        stale_record = phase_dir / "phase_record.json"
        write_json(
            stale_record,
            {
                "phase_id": "phase_010",
                "title": "Frontend CRM Closure",
                "status": "blocked",
                "result": {"status": "blocked", "runtime_state": {"blockers": []}},
                "promotion": {"can_promote": False, "reasons": ["Phase has blockers."]},
            },
        )
        for index in range(1, 6):
            (phase_dir / f"phase_repair_{index:03d}.md").write_text("older repair\n", encoding="utf-8")
        for name, task_id in (("phase_repair_006.md", "T007"), ("phase_repair_007.md", "T009")):
            (phase_dir / name).write_text(
                "\n".join(
                    [
                        "# Auto Repair",
                        f"- Primary failed task IDs: {task_id}.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006.",
                        "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
        old_time = time.time() - 90
        os.utime(stale_record, (old_time, old_time))
        for index in range(1, 6):
            os.utime(phase_dir / f"phase_repair_{index:03d}.md", (old_time - index, old_time - index))
        os.utime(phase_dir / "phase_repair_006.md", (time.time() - 30, time.time() - 30))
        os.utime(phase_dir / "phase_repair_007.md", (time.time() - 10, time.time() - 10))

        calls: list[list[str]] = []

        def repair_then_pass_runner(**kwargs):
            docs = [str(item) for item in kwargs["documents"]]
            calls.append(docs)
            if any("phase_repair_008.md" in item for item in docs):
                return FakePhaseResult("resumed with newly generated repair")
            return FakePhaseResult(
                "blocked before new repair",
                score=0.2,
                blockers=["T010 exceeded the Codex worker timeout."],
            )

        result = FullRoadmapExecutor(document_runner=repair_then_pass_runner).run(
            objective="Convert Billing Core into an independent CRM system.",
            documents=[],
            repository_path=repo,
            output_dir=output,
            run_payload={"max_phase_repair_attempts": 2},
        )

        self.assertEqual(result.status, "done")
        self.assertGreaterEqual(len(calls), 2)
        self.assertTrue((phase_dir / "phase_repair_008.md").exists())
        self.assertTrue(any("phase_repair_008.md" in item for item in calls[-1]))
        self.assertFalse(any("Phase auto-repair limit reached" in blocker for blocker in result.blockers))

    def test_worker_timeout_stop_boundary_writes_repair_doc_without_next_attempt(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        doc = root / "roadmap.md"
        write_v3_docs(doc)
        output = root / "run"
        phase_dir = output / "phases" / "phase_001"
        timeout_blocker = {
            "id": "B-T006-1",
            "type": "technical_limit",
            "description": "T006 exceeded the Codex worker timeout. Stop instead of launching a same-scope debug task.",
            "task_ids": ["T006"],
            "can_continue_partially": False,
        }
        calls: list[str] = []

        def timeout_runner(**kwargs):
            calls.append(str(kwargs["output_dir"]))
            return FakePhaseResult("Schema pruning and build verification", score=0.13, blockers=[timeout_blocker])

        result = FullRoadmapExecutor(document_runner=timeout_runner).run(
            objective="Convert Billing Core into an independent CRM system.",
            documents=[doc],
            repository_path=repo,
            output_dir=output,
            max_phases=1,
            run_payload={"max_phase_repair_attempts": 2},
        )

        record = read_json(phase_dir / "phase_record.json")
        self.assertEqual(result.status, "blocked")
        self.assertEqual(len(calls), 1)
        self.assertTrue(phase_has_worker_timeout_stop_boundary(record["result"]))
        self.assertTrue((phase_dir / "phase_repair_001.md").exists())
        self.assertFalse((phase_dir / "run_attempt_002").exists())
        self.assertEqual(len(record["promotion"]["attempts"]), 1)
        self.assertIn("non-partial worker-timeout blocker", "\n".join(result.blockers))

    def test_phase_repair_distinguishes_technical_and_environment_blockers(self) -> None:
        self.assertTrue(
            blockers_are_auto_repairable(
                [
                    {
                        "id": "B-T004-2",
                        "type": "technical_limit",
                        "description": "Retry policy exhausted for wallet recharge surfaces.",
                        "task_ids": ["T004"],
                        "can_continue_partially": False,
                    }
                ]
            )
        )
        self.assertTrue(
            blockers_are_auto_repairable(
                [
                    {
                        "id": "B-T006-2",
                        "type": "technical_limit",
                        "description": "Retry policy exhausted for the product API key management workflow.",
                        "task_ids": ["T006"],
                        "can_continue_partially": False,
                    }
                ]
            )
        )
        self.assertFalse(
            blockers_are_auto_repairable(
                [
                    {
                        "id": "B-PREFLIGHT",
                        "type": "environment",
                        "description": "GitHub CLI is not logged in.",
                        "can_continue_partially": False,
                    }
                ]
            )
        )
        self.assertFalse(
            blockers_are_auto_repairable(
                [
                    {
                        "id": "B-T005-2",
                        "type": "technical_limit",
                        "description": "Retry policy exhausted after 2 attempt(s): Codex CLI usage limit reached; try again at 5:39 PM.",
                        "task_ids": ["T005"],
                        "can_continue_partially": False,
                    }
                ]
            )
        )

    def test_real_codex_phases_continue_in_previous_phase_worktree(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        doc = root / "roadmap.md"
        write_v3_docs(doc)
        repositories_seen: list[str] = []

        class WorktreePhaseResult:
            def __init__(self, title: str, repository_path: str) -> None:
                self.title = title
                self.repository_path = repository_path

            def to_dict(self) -> dict[str, object]:
                return {
                    "status": "done",
                    "delivery_report": {
                        "final_gate": {
                            "score": 0.91,
                            "dimension_scores": {
                                "test_health": 1.0,
                                "spec_alignment": 0.91,
                                "graph_completion": 1.0,
                                "reviewer_approval": 1.0,
                                "risk_quality": 1.0,
                            },
                            "hard_failures": [],
                            "required_changes": [],
                        },
                        "ready_for_review": True,
                    },
                    "runtime_state": {
                        "done": True,
                        "blockers": [],
                        "evaluation": {"done": True, "final_gate_score": 0.91},
                        "repository": {"path": self.repository_path},
                    },
                    "workspace": {"execution_path": self.repository_path, "worktree_path": self.repository_path},
                    "requirement_coverage": {"status": "passed", "covered": True},
                    "tests_passed": ["phase checks passed"],
                    "evidence": [self.title],
                }

        def fake_runner(**kwargs):
            repo_path = str(kwargs["repository_path"])
            repositories_seen.append(repo_path)
            title = Path(kwargs["documents"][-1]).read_text(encoding="utf-8").splitlines()[0].lstrip("# ")
            if len(repositories_seen) == 1:
                return WorktreePhaseResult(title, str(root / "phase1-worktree"))
            return WorktreePhaseResult(title, repo_path)

        result = FullRoadmapExecutor(document_runner=fake_runner).run(
            objective="Implement the full creative agent roadmap.",
            documents=[doc],
            repository_path=repo,
            output_dir=root / "run",
            run_payload={"real_codex": True, "full_roadmap": True},
        )

        payload = result.to_dict()
        self.assertEqual(payload["status"], "blocked")
        self.assertGreaterEqual(len(repositories_seen), 3)
        self.assertEqual(repositories_seen[0], str(repo))
        self.assertEqual(repositories_seen[1], str(root / "phase1-worktree"))
        self.assertEqual(repositories_seen[2], str(root / "phase1-worktree"))

    def test_phase_run_payload_disables_fresh_isolation_for_inherited_worktree(self) -> None:
        phase = RoadmapPhase(
            phase_id="phase_002",
            title="Implementation Phase",
            requirements=["Implement the next feature."],
            scope_controls={"boundary_mode": "large_refactor"},
        )

        payload = phase_run_payload(
            {"real_codex": True, "isolate_real_run": True, "boundary_mode": "large_refactor"},
            phase,
            inherited_repository_path="D:/tmp/inherited-worktree",
        )

        self.assertFalse(payload["isolate_real_run"])
        self.assertIn("inherited full-roadmap worktree", "\n".join(payload["constraints"]))

    def test_phase_repository_path_prefers_last_completed_phase_runtime_path(self) -> None:
        record = PhaseExecutionRecord(
            phase_id="phase_001",
            title="Phase One",
            status="done",
            output_dir="run/phase_001",
            result={
                "runtime_state": {"repository": {"path": "D:/tmp/phase-one-worktree"}},
                "workspace": {"execution_path": "D:/tmp/phase-one-worktree"},
            },
            promotion={"can_promote": True},
        )

        selected = phase_repository_path("D:/tmp/original", [record], run_payload={"real_codex": True})

        self.assertEqual(selected, "D:/tmp/phase-one-worktree")

    def test_final_verification_worker_uses_last_completed_phase_worktree(self) -> None:
        root = temp_root()
        doc = root / "roadmap.md"
        write_v3_docs(doc)
        inherited = "D:/tmp/final-phase-worktree"
        captured: list[dict[str, object]] = []

        def fake_runner(**kwargs):
            captured.append(dict(kwargs))
            return FakePhaseResult(
                "Final Full-System Audit And Testing",
                evidence=[
                    "FINAL_AUDIT_STATUS: PASS",
                    "SIMULATION_TEST_STATUS: PASS",
                    "REAL_TEST_STATUS: PASS",
                ],
            )

        phase_record = PhaseExecutionRecord(
            phase_id="phase_012",
            title="Final phase",
            status="done",
            output_dir="run/phase_012",
            result={
                "runtime_state": {"repository": {"path": inherited}},
                "workspace": {"execution_path": inherited},
            },
            promotion={"can_promote": True},
        )

        report = FullRoadmapExecutor(document_runner=fake_runner)._run_final_verification_worker(
            objective="Finish CRM",
            plan=RoadmapExecutionPlan(root_objective="Finish CRM", phases=[]),
            phase_records=[phase_record],
            documents=[doc],
            attachments=[],
            repository_url="",
            repository_path="D:/tmp/original",
            repository_visibility="private",
            output_dir=root / "final_verification",
            run_payload={"real_codex": True, "isolate_real_run": True, "boundary_mode": "large_refactor"},
        )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(captured[0]["repository_path"], inherited)
        self.assertFalse(captured[0]["isolate_real_run"])
        self.assertGreaterEqual(captured[0]["max_iterations"], 24)

    def test_final_verification_worker_uses_next_attempt_after_stopped_attempt(self) -> None:
        root = temp_root()
        doc = root / "roadmap.md"
        write_v3_docs(doc)
        output_dir = root / "final_verification"
        stopped_attempt = output_dir / "run_attempt_001"
        stopped_attempt.mkdir(parents=True)
        write_json(stopped_attempt / "supervisor_stop.json", {"reason": "operator stopped stale attempt"})
        captured: list[dict[str, object]] = []

        def fake_runner(**kwargs):
            captured.append(dict(kwargs))
            return FakePhaseResult(
                "Final Full-System Audit And Testing",
                evidence=[
                    "FINAL_AUDIT_STATUS: PASS",
                    "SIMULATION_TEST_STATUS: PASS",
                    "REAL_TEST_STATUS: PASS",
                ],
            )

        report = FullRoadmapExecutor(document_runner=fake_runner)._run_final_verification_worker(
            objective="Finish CRM",
            plan=RoadmapExecutionPlan(root_objective="Finish CRM", phases=[]),
            phase_records=[],
            documents=[doc],
            attachments=[],
            repository_url="",
            repository_path=root / "repo",
            repository_visibility="private",
            output_dir=output_dir,
            run_payload={"real_codex": True, "boundary_mode": "large_refactor", "max_final_verification_attempts": 1},
        )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(Path(captured[0]["output_dir"]).name, "run_attempt_002")
        self.assertTrue((output_dir / "attempt_002.json").exists())
        self.assertGreaterEqual(captured[0]["max_iterations"], 24)

    def test_final_verification_relaunch_carries_previous_failure_repair_context(self) -> None:
        root = temp_root()
        doc = root / "roadmap.md"
        write_v3_docs(doc)
        output_dir = root / "final_verification"
        output_dir.mkdir()
        write_json(
            output_dir / "final_verification_worker_report.json",
            {
                "status": "failed",
                "required_actions": ["Phase has blockers."],
                "result": {
                    "evidence": [
                        "FINAL_AUDIT_STATUS=FAIL: source-boundary violations remain.",
                        "The prior debug worker could not repair implementation defects because allowed_files was empty.",
                    ],
                    "known_issues": [
                        "Fresh migrations and frontend API/i18n surfaces still expose relay-era product behavior."
                    ],
                },
            },
        )
        captured: list[dict[str, object]] = []

        def fake_runner(**kwargs):
            captured.append(dict(kwargs))
            return FakePhaseResult(
                "Final Full-System Audit And Testing",
                evidence=[
                    "FINAL_AUDIT_STATUS: PASS",
                    "SIMULATION_TEST_STATUS: PASS",
                    "REAL_TEST_STATUS: PASS",
                ],
            )

        report = FullRoadmapExecutor(document_runner=fake_runner)._run_final_verification_worker(
            objective="Finish CRM",
            plan=RoadmapExecutionPlan(root_objective="Finish CRM", phases=[]),
            phase_records=[],
            documents=[doc],
            attachments=[],
            repository_url="",
            repository_path=root / "repo",
            repository_visibility="private",
            output_dir=output_dir,
            run_payload={"real_codex": True, "boundary_mode": "large_refactor", "max_final_verification_attempts": 1},
        )

        repair_docs = [Path(item) for item in captured[0]["documents"] if "final_verification_repair_resume" in str(item)]
        self.assertEqual(report["status"], "passed")
        self.assertEqual(len(repair_docs), 1)
        text = repair_docs[0].read_text(encoding="utf-8")
        self.assertIn("source-boundary", text)
        self.assertIn("backend migrations", text)
        self.assertGreaterEqual(captured[0]["max_iterations"], 24)

    def test_final_verification_relaunch_writes_fresh_resume_for_latest_failed_attempt(self) -> None:
        root = temp_root()
        doc = root / "roadmap.md"
        write_v3_docs(doc)
        output_dir = root / "final_verification"
        output_dir.mkdir()
        (output_dir / "final_verification_repair_resume_001.md").write_text(
            "Repair attempt: run_attempt_003\n",
            encoding="utf-8",
        )
        write_json(
            output_dir / "final_verification_worker_report.json",
            {
                "status": "failed",
                "attempts": [
                    {
                        "attempt": 6,
                        "output_dir": str(output_dir / "run_attempt_006"),
                        "status": "blocked",
                    }
                ],
                "result": {
                    "status": "blocked",
                    "runtime_state": {
                        "completed_tasks": ["T002"],
                        "failed_tasks": ["T003"],
                        "blockers": [
                            {
                                "id": "B-T003-1",
                                "type": "technical_limit",
                                "description": "T003 exceeded the Codex worker timeout.",
                                "task_ids": ["T003"],
                            }
                        ],
                        "task_graph": {
                            "nodes": [
                                {"id": "T002", "title": "Repair final backend migration contracts", "status": "completed"},
                                {
                                    "id": "T003",
                                    "title": "Repair final backend schema and domain contracts",
                                    "status": "failed",
                                    "relevant_files": ["backend/ent/**", "backend/internal/domain/**"],
                                    "evidence": [
                                        {
                                            "type": "worker_result",
                                            "result": {
                                                "status": "failed",
                                                "summary": "Codex worker timed out after 900 seconds.",
                                                "known_issues": ["Task-local repository changes were rolled back after timeout."],
                                                "worker_lifecycle": {"timeout_seconds": 900, "timed_out_at": "2026-06-28T13:17:11+00:00"},
                                            },
                                        }
                                    ],
                                },
                            ]
                        },
                    },
                },
            },
        )
        captured: list[dict[str, object]] = []

        def fake_runner(**kwargs):
            captured.append(dict(kwargs))
            return FakePhaseResult(
                "Final Full-System Audit And Testing",
                evidence=[
                    "FINAL_AUDIT_STATUS: PASS",
                    "SIMULATION_TEST_STATUS: PASS",
                    "REAL_TEST_STATUS: PASS",
                ],
            )

        report = FullRoadmapExecutor(document_runner=fake_runner)._run_final_verification_worker(
            objective="Finish CRM",
            plan=RoadmapExecutionPlan(root_objective="Finish CRM", phases=[]),
            phase_records=[],
            documents=[doc],
            attachments=[],
            repository_url="",
            repository_path=root / "repo",
            repository_visibility="private",
            output_dir=output_dir,
            run_payload={"real_codex": True, "boundary_mode": "large_refactor", "max_final_verification_attempts": 1},
        )

        repair_docs = [Path(item) for item in captured[0]["documents"] if "final_verification_repair_resume" in str(item)]
        self.assertEqual(report["status"], "passed")
        self.assertEqual(repair_docs[-1].name, "final_verification_repair_resume_002.md")
        text = repair_docs[-1].read_text(encoding="utf-8")
        self.assertIn("Repair attempt: run_attempt_006", text)
        self.assertIn("Primary failed task IDs: T003", text)
        self.assertIn("Completed tasks to preserve: T002", text)
        self.assertIn("split backend schema/domain repair", text)

    def test_final_verification_resume_records_frontend_api_i18n_timeout_focus(self) -> None:
        root = temp_root()
        doc = root / "roadmap.md"
        write_v3_docs(doc)
        output_dir = root / "final_verification"
        output_dir.mkdir()
        for index in range(1, 6):
            (output_dir / f"final_verification_repair_resume_{index:03d}.md").write_text(
                f"Repair attempt: run_attempt_{index + 4:03d}\n",
                encoding="utf-8",
            )
        write_json(
            output_dir / "final_verification_worker_report.json",
            {
                "status": "failed",
                "attempts": [
                    {
                        "attempt": 10,
                        "output_dir": str(output_dir / "run_attempt_010"),
                        "status": "blocked",
                    }
                ],
                "result": {
                    "status": "blocked",
                    "evidence": ["FINAL_AUDIT_STATUS=FAIL: source-boundary repair attempt needs continuation."],
                    "runtime_state": {
                        "completed_tasks": ["T004", "T005"],
                        "failed_tasks": ["T006"],
                        "blockers": [
                            {
                                "id": "B-T006-1",
                                "type": "technical_limit",
                                "description": "T006 exceeded the Codex worker timeout. Stop instead of launching a same-scope debug task.",
                                "task_ids": ["T006"],
                            }
                        ],
                        "task_graph": {
                            "nodes": [
                                {"id": "T001", "title": "Use deterministic final verification graph", "status": "completed"},
                                {"id": "T002", "title": "Repair final backend migration contracts", "status": "completed"},
                                {"id": "T003", "title": "Repair final backend Ent schema contracts", "status": "completed"},
                                {"id": "T004", "title": "Repair final backend domain and repository contracts", "status": "completed"},
                                {"id": "T005", "title": "Repair final backend service handler server contracts", "status": "completed"},
                                {
                                    "id": "T006",
                                    "title": "Repair final frontend API and i18n contracts",
                                    "status": "failed",
                                    "relevant_files": [
                                        "frontend/src/api/**",
                                        "frontend/src/i18n/**",
                                        "frontend/src/constants/**",
                                        "frontend/src/types/**",
                                    ],
                                    "evidence": [
                                        {
                                            "type": "worker_result",
                                            "result": {
                                                "status": "failed",
                                                "summary": "Codex worker timed out after 900 seconds.",
                                                "known_issues": ["Task-local repository changes were rolled back after timeout."],
                                                "worker_lifecycle": {
                                                    "status": "timed_out",
                                                    "timeout_seconds": 900,
                                                    "timed_out_at": "2026-06-28T17:32:52+00:00",
                                                },
                                            },
                                        }
                                    ],
                                },
                            ]
                        },
                    },
                },
            },
        )
        captured: list[dict[str, object]] = []

        def fake_runner(**kwargs):
            captured.append(dict(kwargs))
            return FakePhaseResult(
                "Final Full-System Audit And Testing",
                evidence=[
                    "FINAL_AUDIT_STATUS: PASS",
                    "SIMULATION_TEST_STATUS: PASS",
                    "REAL_TEST_STATUS: PASS",
                ],
            )

        report = FullRoadmapExecutor(document_runner=fake_runner)._run_final_verification_worker(
            objective="Finish CRM",
            plan=RoadmapExecutionPlan(root_objective="Finish CRM", phases=[]),
            phase_records=[],
            documents=[doc],
            attachments=[],
            repository_url="",
            repository_path=root / "repo",
            repository_visibility="private",
            output_dir=output_dir,
            run_payload={"real_codex": True, "boundary_mode": "large_refactor", "max_final_verification_attempts": 1},
        )

        repair_docs = [Path(item) for item in captured[0]["documents"] if "final_verification_repair_resume" in str(item)]
        self.assertEqual(report["status"], "passed")
        self.assertEqual(repair_docs[-1].name, "final_verification_repair_resume_006.md")
        text = repair_docs[-1].read_text(encoding="utf-8")
        self.assertIn("Repair attempt: run_attempt_010", text)
        self.assertIn("Primary failed task IDs: T006", text)
        completed_line = next(line for line in text.splitlines() if "Completed tasks to preserve:" in line)
        for task_id in ("T001", "T002", "T003", "T004", "T005"):
            self.assertIn(task_id, completed_line)
        self.assertNotIn("T006", completed_line)
        self.assertIn("Task T006 - Repair final frontend API and i18n contracts", text)
        self.assertIn("Worker summary: Codex worker timed out after 900 seconds.", text)

    def test_final_verification_resume_records_frontend_routes_timeout_focus(self) -> None:
        root = temp_root()
        doc = root / "roadmap.md"
        write_v3_docs(doc)
        output_dir = root / "final_verification"
        output_dir.mkdir()
        for index in range(1, 7):
            (output_dir / f"final_verification_repair_resume_{index:03d}.md").write_text(
                f"Repair attempt: run_attempt_{index + 4:03d}\n",
                encoding="utf-8",
            )
        write_json(
            output_dir / "final_verification_worker_report.json",
            {
                "status": "failed",
                "attempts": [
                    {
                        "attempt": 11,
                        "output_dir": str(output_dir / "run_attempt_011"),
                        "status": "blocked",
                    }
                ],
                "result": {
                    "status": "blocked",
                    "evidence": ["FINAL_AUDIT_STATUS=FAIL: source-boundary repair attempt needs continuation."],
                    "runtime_state": {
                        "completed_tasks": ["T006", "T007", "T008"],
                        "failed_tasks": ["T009"],
                        "blockers": [
                            {
                                "id": "B-T009-1",
                                "type": "technical_limit",
                                "description": "T009 exceeded the Codex worker timeout. Stop instead of launching a same-scope debug task.",
                                "task_ids": ["T009"],
                            }
                        ],
                        "task_graph": {
                            "nodes": [
                                {"id": "T001", "title": "Use deterministic final verification graph", "status": "completed"},
                                {"id": "T002", "title": "Repair final backend migration contracts", "status": "completed"},
                                {"id": "T003", "title": "Repair final backend Ent schema contracts", "status": "completed"},
                                {"id": "T004", "title": "Repair final backend domain and repository contracts", "status": "completed"},
                                {"id": "T005", "title": "Repair final backend service handler server contracts", "status": "completed"},
                                {"id": "T006", "title": "Repair final frontend API module contracts", "status": "completed"},
                                {"id": "T007", "title": "Repair final frontend i18n locale contracts", "status": "completed"},
                                {"id": "T008", "title": "Repair final frontend constants and shared types contracts", "status": "completed"},
                                {
                                    "id": "T009",
                                    "title": "Repair final frontend routes views and tests",
                                    "status": "failed",
                                    "relevant_files": [
                                        "frontend/src/router/**",
                                        "frontend/src/views/**",
                                        "frontend/src/components/**",
                                        "frontend/src/composables/**",
                                        "frontend/src/stores/**",
                                        "frontend/src/tests/**",
                                        "frontend/tests/**",
                                    ],
                                    "evidence": [
                                        {
                                            "type": "worker_result",
                                            "result": {
                                                "status": "failed",
                                                "summary": "Codex worker timed out after 900 seconds.",
                                                "known_issues": ["Task-local repository changes were rolled back after timeout."],
                                                "worker_lifecycle": {
                                                    "status": "timed_out",
                                                    "timeout_seconds": 900,
                                                    "timed_out_at": "2026-06-28T19:17:59+00:00",
                                                },
                                            },
                                        }
                                    ],
                                },
                            ]
                        },
                    },
                },
            },
        )
        captured: list[dict[str, object]] = []

        def fake_runner(**kwargs):
            captured.append(dict(kwargs))
            return FakePhaseResult(
                "Final Full-System Audit And Testing",
                evidence=[
                    "FINAL_AUDIT_STATUS: PASS",
                    "SIMULATION_TEST_STATUS: PASS",
                    "REAL_TEST_STATUS: PASS",
                ],
            )

        report = FullRoadmapExecutor(document_runner=fake_runner)._run_final_verification_worker(
            objective="Finish CRM",
            plan=RoadmapExecutionPlan(root_objective="Finish CRM", phases=[]),
            phase_records=[],
            documents=[doc],
            attachments=[],
            repository_url="",
            repository_path=root / "repo",
            repository_visibility="private",
            output_dir=output_dir,
            run_payload={"real_codex": True, "boundary_mode": "large_refactor", "max_final_verification_attempts": 1},
        )

        repair_docs = [Path(item) for item in captured[0]["documents"] if "final_verification_repair_resume" in str(item)]
        self.assertEqual(report["status"], "passed")
        self.assertEqual(repair_docs[-1].name, "final_verification_repair_resume_007.md")
        text = repair_docs[-1].read_text(encoding="utf-8")
        self.assertIn("Repair attempt: run_attempt_011", text)
        self.assertIn("Primary failed task IDs: T009", text)
        completed_line = next(line for line in text.splitlines() if "Completed tasks to preserve:" in line)
        for task_id in ("T001", "T002", "T003", "T004", "T005", "T006", "T007", "T008"):
            self.assertIn(task_id, completed_line)
        self.assertNotIn("T009", completed_line)
        self.assertIn("Task T009 - Repair final frontend routes views and tests", text)
        self.assertIn("Worker summary: Codex worker timed out after 900 seconds.", text)

    def test_final_verification_resume_records_frontend_view_component_timeout_focus(self) -> None:
        root = temp_root()
        doc = root / "roadmap.md"
        write_v3_docs(doc)
        output_dir = root / "final_verification"
        output_dir.mkdir()
        for index in range(1, 8):
            (output_dir / f"final_verification_repair_resume_{index:03d}.md").write_text(
                f"Repair attempt: run_attempt_{index + 4:03d}\n",
                encoding="utf-8",
            )
        write_json(
            output_dir / "final_verification_worker_report.json",
            {
                "status": "failed",
                "attempts": [
                    {
                        "attempt": 12,
                        "output_dir": str(output_dir / "run_attempt_012"),
                        "status": "blocked",
                    }
                ],
                "result": {
                    "status": "blocked",
                    "evidence": ["FINAL_AUDIT_STATUS=FAIL: source-boundary repair attempt needs continuation."],
                    "runtime_state": {
                        "completed_tasks": ["T006", "T007", "T008", "T009"],
                        "failed_tasks": ["T010"],
                        "blockers": [
                            {
                                "id": "B-T010-1",
                                "type": "technical_limit",
                                "description": "T010 exceeded the Codex worker timeout. Stop instead of launching a same-scope debug task.",
                                "task_ids": ["T010"],
                            }
                        ],
                        "task_graph": {
                            "nodes": [
                                {"id": "T001", "title": "Use deterministic final verification graph", "status": "completed"},
                                {"id": "T002", "title": "Repair final backend migration contracts", "status": "completed"},
                                {"id": "T003", "title": "Repair final backend Ent schema contracts", "status": "completed"},
                                {"id": "T004", "title": "Repair final backend domain and repository contracts", "status": "completed"},
                                {"id": "T005", "title": "Repair final backend service handler server contracts", "status": "completed"},
                                {"id": "T006", "title": "Repair final frontend API module contracts", "status": "completed"},
                                {"id": "T007", "title": "Repair final frontend i18n locale contracts", "status": "completed"},
                                {"id": "T008", "title": "Repair final frontend constants and shared types contracts", "status": "completed"},
                                {"id": "T009", "title": "Repair final frontend route and app shell contracts", "status": "completed"},
                                {
                                    "id": "T010",
                                    "title": "Repair final frontend view and component contracts",
                                    "status": "failed",
                                    "relevant_files": [
                                        "frontend/src/views/**",
                                        "frontend/src/components/**",
                                        "frontend/src/styles/**",
                                        "frontend/src/types/**",
                                        "frontend/package.json",
                                        "frontend/pnpm-lock.yaml",
                                    ],
                                    "evidence": [
                                        {
                                            "type": "worker_result",
                                            "result": {
                                                "status": "failed",
                                                "summary": "Codex worker timed out after 900 seconds.",
                                                "known_issues": ["Task-local repository changes were rolled back after timeout."],
                                                "worker_lifecycle": {
                                                    "status": "timed_out",
                                                    "timeout_seconds": 900,
                                                    "timed_out_at": "2026-06-28T20:18:22+00:00",
                                                },
                                            },
                                        }
                                    ],
                                },
                            ]
                        },
                    },
                },
            },
        )
        captured: list[dict[str, object]] = []

        def fake_runner(**kwargs):
            captured.append(dict(kwargs))
            return FakePhaseResult(
                "Final Full-System Audit And Testing",
                evidence=[
                    "FINAL_AUDIT_STATUS: PASS",
                    "SIMULATION_TEST_STATUS: PASS",
                    "REAL_TEST_STATUS: PASS",
                ],
            )

        report = FullRoadmapExecutor(document_runner=fake_runner)._run_final_verification_worker(
            objective="Finish CRM",
            plan=RoadmapExecutionPlan(root_objective="Finish CRM", phases=[]),
            phase_records=[],
            documents=[doc],
            attachments=[],
            repository_url="",
            repository_path=root / "repo",
            repository_visibility="private",
            output_dir=output_dir,
            run_payload={"real_codex": True, "boundary_mode": "large_refactor", "max_final_verification_attempts": 1},
        )

        repair_docs = [Path(item) for item in captured[0]["documents"] if "final_verification_repair_resume" in str(item)]
        self.assertEqual(report["status"], "passed")
        self.assertEqual(repair_docs[-1].name, "final_verification_repair_resume_008.md")
        text = repair_docs[-1].read_text(encoding="utf-8")
        self.assertIn("Repair attempt: run_attempt_012", text)
        self.assertIn("Primary failed task IDs: T010", text)
        completed_line = next(line for line in text.splitlines() if "Completed tasks to preserve:" in line)
        for task_id in ("T001", "T002", "T003", "T004", "T005", "T006", "T007", "T008", "T009"):
            self.assertIn(task_id, completed_line)
        self.assertNotIn("T010", completed_line)
        self.assertIn("Task T010 - Repair final frontend view and component contracts", text)
        self.assertIn("Worker summary: Codex worker timed out after 900 seconds.", text)

    def test_final_verification_resume_records_frontend_admin_component_timeout_focus(self) -> None:
        root = temp_root()
        doc = root / "roadmap.md"
        write_v3_docs(doc)
        output_dir = root / "final_verification"
        output_dir.mkdir()
        for index in range(1, 9):
            (output_dir / f"final_verification_repair_resume_{index:03d}.md").write_text(
                f"Repair attempt: run_attempt_{index + 4:03d}\n",
                encoding="utf-8",
            )
        write_json(
            output_dir / "final_verification_worker_report.json",
            {
                "status": "failed",
                "attempts": [
                    {
                        "attempt": 13,
                        "output_dir": str(output_dir / "run_attempt_013"),
                        "status": "blocked",
                    }
                ],
                "result": {
                    "status": "blocked",
                    "evidence": ["FINAL_AUDIT_STATUS=FAIL: source-boundary repair attempt needs continuation."],
                    "runtime_state": {
                        "completed_tasks": ["T010"],
                        "failed_tasks": ["T011"],
                        "blockers": [
                            {
                                "id": "B-T011-1",
                                "type": "technical_limit",
                                "description": "T011 exceeded the Codex worker timeout. Stop instead of launching a same-scope debug task.",
                                "task_ids": ["T011"],
                            }
                        ],
                        "task_graph": {
                            "nodes": [
                                {"id": "T001", "title": "Use deterministic final verification graph", "status": "completed"},
                                {"id": "T002", "title": "Repair final backend migration contracts", "status": "completed"},
                                {"id": "T003", "title": "Repair final backend Ent schema contracts", "status": "completed"},
                                {"id": "T004", "title": "Repair final backend domain and repository contracts", "status": "completed"},
                                {"id": "T005", "title": "Repair final backend service handler server contracts", "status": "completed"},
                                {"id": "T006", "title": "Repair final frontend API module contracts", "status": "completed"},
                                {"id": "T007", "title": "Repair final frontend i18n locale contracts", "status": "completed"},
                                {"id": "T008", "title": "Repair final frontend constants and shared types contracts", "status": "completed"},
                                {"id": "T009", "title": "Repair final frontend route and app shell contracts", "status": "completed"},
                                {"id": "T010", "title": "Repair final frontend account component contracts", "status": "completed"},
                                {
                                    "id": "T011",
                                    "title": "Repair final frontend admin operation component contracts",
                                    "status": "failed",
                                    "relevant_files": [
                                        "frontend/src/components/admin/**",
                                        "frontend/src/components/channels/**",
                                        "frontend/src/types/**",
                                        "frontend/package.json",
                                        "frontend/pnpm-lock.yaml",
                                    ],
                                    "evidence": [
                                        {
                                            "type": "worker_result",
                                            "result": {
                                                "status": "failed",
                                                "summary": "Codex worker timed out after 900 seconds.",
                                                "known_issues": ["Task-local repository changes were rolled back after timeout."],
                                                "worker_lifecycle": {
                                                    "status": "timed_out",
                                                    "timeout_seconds": 900,
                                                    "timed_out_at": "2026-06-28T21:26:21+00:00",
                                                },
                                            },
                                        }
                                    ],
                                },
                            ]
                        },
                    },
                },
            },
        )
        captured: list[dict[str, object]] = []

        def fake_runner(**kwargs):
            captured.append(dict(kwargs))
            return FakePhaseResult(
                "Final Full-System Audit And Testing",
                evidence=[
                    "FINAL_AUDIT_STATUS: PASS",
                    "SIMULATION_TEST_STATUS: PASS",
                    "REAL_TEST_STATUS: PASS",
                ],
            )

        report = FullRoadmapExecutor(document_runner=fake_runner)._run_final_verification_worker(
            objective="Finish CRM",
            plan=RoadmapExecutionPlan(root_objective="Finish CRM", phases=[]),
            phase_records=[],
            documents=[doc],
            attachments=[],
            repository_url="",
            repository_path=root / "repo",
            repository_visibility="private",
            output_dir=output_dir,
            run_payload={"real_codex": True, "boundary_mode": "large_refactor", "max_final_verification_attempts": 1},
        )

        repair_docs = [Path(item) for item in captured[0]["documents"] if "final_verification_repair_resume" in str(item)]
        self.assertEqual(report["status"], "passed")
        self.assertEqual(repair_docs[-1].name, "final_verification_repair_resume_009.md")
        self.assertGreaterEqual(captured[0]["max_iterations"], 24)
        text = repair_docs[-1].read_text(encoding="utf-8")
        self.assertIn("Repair attempt: run_attempt_013", text)
        self.assertIn("Primary failed task IDs: T011", text)
        completed_line = next(line for line in text.splitlines() if "Completed tasks to preserve:" in line)
        for task_id in ("T001", "T002", "T003", "T004", "T005", "T006", "T007", "T008", "T009", "T010"):
            self.assertIn(task_id, completed_line)
        self.assertNotIn("T011", completed_line)
        self.assertIn("Task T011 - Repair final frontend admin operation component contracts", text)
        self.assertIn("Worker summary: Codex worker timed out after 900 seconds.", text)

    def test_final_verification_resume_preserves_partial_downstream_handoff(self) -> None:
        root = temp_root()
        doc = root / "roadmap.md"
        write_v3_docs(doc)
        output_dir = root / "final_verification"
        output_dir.mkdir()
        write_json(
            output_dir / "final_verification_worker_report.json",
            {
                "status": "failed",
                "attempts": [
                    {
                        "attempt": 8,
                        "output_dir": str(output_dir / "run_attempt_008"),
                        "status": "blocked",
                    }
                ],
                "result": {
                    "status": "blocked",
                    "evidence": ["FINAL_AUDIT_STATUS=FAIL: source-boundary repair attempt needs continuation."],
                    "runtime_state": {
                        "completed_tasks": ["T003"],
                        "failed_tasks": ["T004", "T004-DEBUG-1"],
                        "blockers": [
                            {
                                "id": "B-T004-DEBUG-1-0",
                                "type": "technical_limit",
                                "description": "Debug worker stopped by supervisor.",
                                "task_ids": ["T004-DEBUG-1"],
                            }
                        ],
                        "task_graph": {
                            "nodes": [
                                {"id": "T003", "title": "Repair final backend Ent schema contracts", "status": "completed"},
                                {
                                    "id": "T004",
                                    "title": "Repair final backend domain and repository contracts",
                                    "type": "integration",
                                    "status": "ready",
                                    "dependencies": ["T003"],
                                    "relevant_files": [
                                        "backend/internal/domain/**",
                                        "backend/internal/repository/**",
                                        "backend/go.mod",
                                        "backend/go.sum",
                                    ],
                                    "evidence": [
                                        {
                                            "type": "worker_result",
                                            "result": {
                                                "status": "partial",
                                                "summary": "Repository compile is blocked by service code outside allowed_files.",
                                                "files_changed": ["backend/internal/repository/group_repo.go"],
                                                "tests_passed": ["go test ./internal/domain -run '^$'"],
                                                "tests_failed": ["go test ./internal/repository -run '^$'"],
                                                "known_issues": [
                                                    "internal/service/payment_config_plans.go still references removed Ent fields."
                                                ],
                                                "follow_up_tasks": [
                                                    "Update internal/service/payment_config_plans.go in the service repair task."
                                                ],
                                            },
                                        }
                                    ],
                                },
                                {
                                    "id": "T005",
                                    "title": "Repair final backend service handler server contracts",
                                    "type": "integration",
                                    "status": "pending",
                                    "dependencies": ["T004"],
                                    "relevant_files": [
                                        "backend/internal/service/**",
                                        "backend/internal/handler/**",
                                        "backend/internal/server/**",
                                        "backend/cmd/**",
                                        "backend/go.mod",
                                        "backend/go.sum",
                                    ],
                                },
                                {
                                    "id": "T004-DEBUG-1",
                                    "title": "Debug T004",
                                    "type": "debug",
                                    "status": "blocked",
                                },
                            ]
                        },
                    },
                },
            },
        )
        captured: list[dict[str, object]] = []

        def fake_runner(**kwargs):
            captured.append(dict(kwargs))
            return FakePhaseResult(
                "Final Full-System Audit And Testing",
                evidence=[
                    "FINAL_AUDIT_STATUS: PASS",
                    "SIMULATION_TEST_STATUS: PASS",
                    "REAL_TEST_STATUS: PASS",
                ],
            )

        report = FullRoadmapExecutor(document_runner=fake_runner)._run_final_verification_worker(
            objective="Finish CRM",
            plan=RoadmapExecutionPlan(root_objective="Finish CRM", phases=[]),
            phase_records=[],
            documents=[doc],
            attachments=[],
            repository_url="",
            repository_path=root / "repo",
            repository_visibility="private",
            output_dir=output_dir,
            run_payload={"real_codex": True, "boundary_mode": "large_refactor", "max_final_verification_attempts": 1},
        )

        repair_docs = [Path(item) for item in captured[0]["documents"] if "final_verification_repair_resume" in str(item)]
        self.assertEqual(report["status"], "passed")
        text = repair_docs[-1].read_text(encoding="utf-8")
        self.assertIn("Repair attempt: run_attempt_008", text)
        self.assertIn("Completed tasks to preserve: T003, T004", text)
        self.assertIn("Primary failed task IDs: T004-DEBUG-1", text)

    def test_final_verification_resume_reopens_preserved_task_when_later_failure_targets_its_scope(self) -> None:
        root = temp_root()
        doc = root / "roadmap.md"
        write_v3_docs(doc)
        output_dir = root / "final_verification"
        output_dir.mkdir()
        write_json(
            output_dir / "final_verification_worker_report.json",
            {
                "status": "failed",
                "attempts": [
                    {
                        "attempt": 9,
                        "output_dir": str(output_dir / "run_attempt_009"),
                        "status": "blocked",
                    }
                ],
                "result": {
                    "status": "blocked",
                    "evidence": ["FINAL_AUDIT_STATUS=FAIL: source-boundary repair attempt needs continuation."],
                    "runtime_state": {
                        "completed_tasks": ["T001", "T002", "T003", "T004"],
                        "failed_tasks": ["T005"],
                        "blockers": [
                            {
                                "id": "B-T005-1",
                                "type": "technical_limit",
                                "description": "T005 returned partial.",
                                "task_ids": ["T005"],
                            }
                        ],
                        "task_graph": {
                            "nodes": [
                                {"id": "T001", "title": "Use deterministic final verification graph", "status": "completed"},
                                {
                                    "id": "T002",
                                    "title": "Repair final backend migration contracts",
                                    "status": "completed",
                                    "relevant_files": ["backend/migrations/001_init.sql"],
                                },
                                {
                                    "id": "T003",
                                    "title": "Repair final backend Ent schema contracts",
                                    "status": "completed",
                                    "relevant_files": ["backend/ent/**", "backend/go.mod", "backend/go.sum"],
                                },
                                {
                                    "id": "T004",
                                    "title": "Repair final backend domain and repository contracts",
                                    "status": "completed",
                                    "relevant_files": ["backend/internal/domain/**", "backend/internal/repository/**"],
                                },
                                {
                                    "id": "T005",
                                    "title": "Repair final backend service handler server contracts",
                                    "status": "failed",
                                    "dependencies": ["T004"],
                                    "relevant_files": [
                                        "backend/internal/service/**",
                                        "backend/internal/handler/**",
                                        "backend/internal/server/**",
                                    ],
                                    "evidence": [
                                        {
                                            "type": "worker_result",
                                            "result": {
                                                "status": "partial",
                                                "summary": "Service scope compiles; cmd/server is blocked by repository code.",
                                                "files_changed": ["backend/internal/service/payment_config_plans.go"],
                                                "tests_passed": ["go test -run '^$' ./internal/service"],
                                                "tests_failed": ["go test -run '^$' ./cmd/server failed"],
                                                "known_issues": [
                                                    "backend/internal/repository/account_repo.go references removed Account schema fields."
                                                ],
                                                "follow_up_tasks": [
                                                    "Repair backend/internal/repository/account_repo.go before rerunning cmd/server."
                                                ],
                                            },
                                        }
                                    ],
                                },
                            ]
                        },
                    },
                },
            },
        )
        captured: list[dict[str, object]] = []

        def fake_runner(**kwargs):
            captured.append(dict(kwargs))
            return FakePhaseResult(
                "Final Full-System Audit And Testing",
                evidence=[
                    "FINAL_AUDIT_STATUS: PASS",
                    "SIMULATION_TEST_STATUS: PASS",
                    "REAL_TEST_STATUS: PASS",
                ],
            )

        report = FullRoadmapExecutor(document_runner=fake_runner)._run_final_verification_worker(
            objective="Finish CRM",
            plan=RoadmapExecutionPlan(root_objective="Finish CRM", phases=[]),
            phase_records=[],
            documents=[doc],
            attachments=[],
            repository_url="",
            repository_path=root / "repo",
            repository_visibility="private",
            output_dir=output_dir,
            run_payload={"real_codex": True, "boundary_mode": "large_refactor", "max_final_verification_attempts": 1},
        )

        repair_docs = [Path(item) for item in captured[0]["documents"] if "final_verification_repair_resume" in str(item)]
        self.assertEqual(report["status"], "passed")
        text = repair_docs[-1].read_text(encoding="utf-8")
        self.assertIn("Repair attempt: run_attempt_009", text)
        completed_line = next(line for line in text.splitlines() if "Completed tasks to preserve:" in line)
        self.assertIn("T003", completed_line)
        self.assertNotIn("T004", completed_line)
        self.assertIn("backend/internal/repository/account_repo.go", text)

    def test_executor_generates_document_package_for_one_sentence_mode(self) -> None:
        root = temp_root()
        calls: list[str] = []

        def fake_runner(**kwargs):
            calls.append(Path(kwargs["documents"][-1]).name)
            return FakePhaseResult("phase")

        result = FullRoadmapExecutor(document_runner=fake_runner).run(
            objective="Build a simple booking app.",
            documents=[],
            primary_input_mode="one_line_fallback",
            output_dir=root / "run",
        )

        payload = result.to_dict()
        self.assertEqual(payload["status"], "done")
        package = payload["generated_development_package"]
        self.assertEqual(package["status"], "generated")
        self.assertTrue((root / "run" / "generated_development_package" / "03_roadmap.md").exists())
        self.assertGreaterEqual(len(payload["phase_records"]), 3)
        self.assertTrue(calls)

    def test_real_codex_full_roadmap_runs_final_verification_worker(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        doc = root / "roadmap.md"
        write_v3_docs(doc)
        calls: list[str] = []

        def fake_runner(**kwargs):
            title = Path(kwargs["documents"][-1]).read_text(encoding="utf-8").splitlines()[0].lstrip("# ")
            calls.append(title)
            if title == "Final Full-System Audit And Testing":
                return FakePhaseResult(
                    title,
                    evidence=[
                        "FINAL_AUDIT_STATUS: PASS",
                        "SIMULATION_TEST_STATUS: PASS",
                        "REAL_TEST_STATUS: PASS",
                    ],
                )
            return FakePhaseResult(title)

        result = FullRoadmapExecutor(document_runner=fake_runner).run(
            objective="Implement the full creative agent roadmap.",
            documents=[doc],
            repository_path=repo,
            output_dir=root / "run",
            run_payload={"real_codex": True, "full_roadmap": True},
        )
        payload = result.to_dict()

        self.assertEqual(payload["status"], "done")
        self.assertIn("Final Full-System Audit And Testing", calls)
        self.assertEqual(payload["final_verification_worker"]["status"], "passed")
        self.assertEqual(payload["final_audit"]["final_verification"]["worker_verification"]["status"], "passed")
        self.assertEqual(payload["final_audit"]["final_verification"]["test_status"], "passed")

    def test_max_phase_count_does_not_block_final_audit_after_last_phase(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        doc = root / "roadmap.md"
        write_v3_docs(doc)
        calls: list[str] = []

        def fake_runner(**kwargs):
            title = Path(kwargs["documents"][-1]).read_text(encoding="utf-8").splitlines()[0].lstrip("# ")
            calls.append(title)
            if title == "Final Full-System Audit And Testing":
                return FakePhaseResult(
                    title,
                    evidence=[
                        "FINAL_AUDIT_STATUS: PASS",
                        "SIMULATION_TEST_STATUS: PASS",
                        "REAL_TEST_STATUS: PASS",
                    ],
                )
            return FakePhaseResult(title)

        result = FullRoadmapExecutor(document_runner=fake_runner).run(
            objective="Implement the full creative agent roadmap.",
            documents=[doc],
            repository_path=repo,
            output_dir=root / "run",
            max_phases=3,
            run_payload={"real_codex": True, "full_roadmap": True},
        )
        payload = result.to_dict()

        self.assertEqual(payload["status"], "done")
        self.assertIn("Final Full-System Audit And Testing", calls)
        self.assertNotIn("Maximum roadmap phase count reached.", payload["blockers"])

    def test_strict_real_final_verification_requires_explicit_worker_status_markers(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        doc = root / "roadmap.md"
        write_v3_docs(doc)

        def fake_runner(**kwargs):
            title = Path(kwargs["documents"][-1]).read_text(encoding="utf-8").splitlines()[0].lstrip("# ")
            return FakePhaseResult(title)

        result = FullRoadmapExecutor(document_runner=fake_runner).run(
            objective="Implement the full creative agent roadmap.",
            documents=[doc],
            repository_path=repo,
            output_dir=root / "run",
            run_payload={"real_codex": True, "full_roadmap": True},
        )
        payload = result.to_dict()
        final_verification = payload["final_audit"]["final_verification"]

        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["final_verification_worker"]["status"], "passed")
        self.assertEqual(final_verification["status"], "iterate")
        self.assertEqual(final_verification["audit_status"], "iterate")
        self.assertEqual(final_verification["test_status"], "iterate")
        self.assertIn("FINAL_AUDIT_STATUS", "\n".join(final_verification["blockers"]))
        self.assertIn("FINAL_AUDIT_STATUS", "\n".join(payload["blockers"]))

    def test_strict_real_final_verification_blocks_failed_status_marker(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        doc = root / "roadmap.md"
        write_v3_docs(doc)

        def fake_runner(**kwargs):
            title = Path(kwargs["documents"][-1]).read_text(encoding="utf-8").splitlines()[0].lstrip("# ")
            if title == "Final Full-System Audit And Testing":
                return FakePhaseResult(
                    title,
                    evidence=[
                        "FINAL_AUDIT_STATUS: PASS",
                        "SIMULATION_TEST_STATUS: FAIL",
                        "REAL_TEST_STATUS: PASS",
                    ],
                )
            return FakePhaseResult(title)

        result = FullRoadmapExecutor(document_runner=fake_runner).run(
            objective="Implement the full creative agent roadmap.",
            documents=[doc],
            repository_path=repo,
            output_dir=root / "run",
            run_payload={"real_codex": True, "full_roadmap": True},
        )
        payload = result.to_dict()
        final_verification = payload["final_audit"]["final_verification"]

        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(final_verification["test_status"], "iterate")
        simulation_stage = next(item for item in final_verification["test_stages"] if item["id"] == "simulation_tests")
        self.assertEqual(simulation_stage["status"], "failed")
        self.assertIn("SIMULATION_TEST_STATUS", "\n".join(payload["blockers"]))

    def test_final_verification_worker_failure_blocks_done(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        doc = root / "roadmap.md"
        write_v3_docs(doc)

        def fake_runner(**kwargs):
            title = Path(kwargs["documents"][-1]).read_text(encoding="utf-8").splitlines()[0].lstrip("# ")
            if title == "Final Full-System Audit And Testing":
                return FakePhaseResult(title, score=0.70)
            return FakePhaseResult(title)

        result = FullRoadmapExecutor(document_runner=fake_runner).run(
            objective="Implement the full creative agent roadmap.",
            documents=[doc],
            repository_path=repo,
            output_dir=root / "run",
            run_payload={
                "real_codex": True,
                "full_roadmap": True,
                "max_final_verification_attempts": 1,
            },
        )
        payload = result.to_dict()

        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["final_verification_worker"]["status"], "failed")
        self.assertEqual(payload["final_audit"]["status"], "blocked")
        self.assertIn("Phase score", "\n".join(payload["blockers"]))

    def test_real_dry_run_executor_does_not_stop_after_first_phase_when_later_phases_remain(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        (repo / "README.md").write_text("# Smoke Repo\n", encoding="utf-8")
        doc = root / "roadmap.md"
        doc.write_text(
            "\n".join(
                [
                    "# Roadmap",
                    "## V1.0 Foundation",
                    "### Requirements",
                    "- Must create a foundation note in README.md.",
                    "## V1.1 Core Feature",
                    "### Requirements",
                    "- Must create a core feature note in README.md.",
                    "## V1.2 Verification And Delivery",
                    "### Requirements",
                    "- Must verify the final result and record delivery evidence.",
                ]
            ),
            encoding="utf-8",
        )

        result = FullRoadmapExecutor().run(
            objective="Execute every phase in the roadmap.",
            documents=[doc],
            repository_path=repo,
            output_dir=root / "run",
            run_payload={"real_codex": False, "real_github": False, "max_iterations": 20},
        )

        payload = result.to_dict()
        self.assertGreaterEqual(len(payload["phase_records"]), 2)
        self.assertEqual(payload["phase_records"][0]["status"], "done")
        self.assertEqual(payload["phase_records"][1]["status"], "done")
        self.assertNotEqual(payload["phase_records"][0]["title"], payload["phase_records"][1]["title"])

    def test_executor_resumes_existing_output_after_completed_first_phase(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        doc = root / "roadmap.md"
        write_v3_docs(doc)
        plan = RoadmapExtractor().extract(
            objective="Implement the full creative agent roadmap.",
            documents=[doc],
            source_mode="local_repo",
        )
        plan, audit = RoadmapAuditor().audit_and_repair(plan)
        plan.phases[0].status = "completed"
        output = root / "run"
        phase_one = output / "phases" / plan.phases[0].phase_id
        phase_one.mkdir(parents=True)
        write_json(output / "roadmap_execution_plan.json", plan.to_dict())
        write_json(output / "roadmap_audit.json", audit.to_dict())
        write_json(
            output / "project_analysis_report.json",
            ProjectAnalysisGate().analyze(plan=plan, documents=[doc]).to_dict(),
        )
        write_json(
            output / "expanded_document_index.json",
            {"documents": [str(doc.resolve())], "added_documents": []},
        )
        write_json(
            phase_one / "phase_record.json",
            {
                "phase_id": plan.phases[0].phase_id,
                "title": plan.phases[0].title,
                "status": "done",
                "output_dir": str(phase_one),
                "result": FakePhaseResult(plan.phases[0].title).to_dict(),
                "promotion": {"can_promote": True, "status": "passed"},
            },
        )
        calls: list[str] = []
        running_snapshots: list[dict[str, object]] = []

        def fake_runner(**kwargs):
            running_snapshots.append(json.loads((output / "full_roadmap_report.json").read_text(encoding="utf-8")))
            title = Path(kwargs["documents"][-1]).read_text(encoding="utf-8").splitlines()[0].lstrip("# ")
            calls.append(title)
            return FakePhaseResult(title)

        result = FullRoadmapExecutor(document_runner=fake_runner).run(
            objective="Implement the full creative agent roadmap.",
            documents=[doc],
            repository_path=repo,
            output_dir=output,
        )

        payload = result.to_dict()
        self.assertEqual(payload["status"], "done")
        self.assertEqual(calls, ["V3.1 Brand Consistency Foundation", "V3.2 Generation Loop MVP"])
        self.assertEqual(len(payload["phase_records"]), 3)
        self.assertTrue(all(phase["status"] == "completed" for phase in payload["roadmap"]["phases"]))

    def test_executor_resumes_existing_output_after_blocked_report(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        doc = root / "roadmap.md"
        write_v3_docs(doc)
        plan = RoadmapExtractor().extract(
            objective="Implement the full creative agent roadmap.",
            documents=[doc],
            source_mode="local_repo",
        )
        plan, audit = RoadmapAuditor().audit_and_repair(plan)
        output = root / "run"
        write_json(output / "roadmap_execution_plan.json", plan.to_dict())
        write_json(output / "roadmap_audit.json", audit.to_dict())
        write_json(
            output / "project_analysis_report.json",
            ProjectAnalysisGate().analyze(plan=plan, documents=[doc]).to_dict(),
        )
        write_json(
            output / "expanded_document_index.json",
            {"documents": [str(doc.resolve())], "added_documents": []},
        )
        for phase in plan.phases[:2]:
            phase_dir = output / "phases" / phase.phase_id
            phase_dir.mkdir(parents=True, exist_ok=True)
            write_json(
                phase_dir / "phase_record.json",
                {
                    "phase_id": phase.phase_id,
                    "title": phase.title,
                    "status": "done",
                    "output_dir": str(phase_dir),
                    "result": FakePhaseResult(phase.title).to_dict(),
                    "promotion": {"can_promote": True, "status": "passed"},
                },
            )
        blocked_phase = plan.phases[2]
        blocked_dir = output / "phases" / blocked_phase.phase_id
        blocked_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            blocked_dir / "phase_record.json",
            {
                "phase_id": blocked_phase.phase_id,
                "title": blocked_phase.title,
                "status": "blocked",
                "output_dir": str(blocked_dir),
                "result": FakePhaseResult(blocked_phase.title, blockers=["old blocked report"]).to_dict(),
                "promotion": {"can_promote": False, "status": "blocked"},
            },
        )
        write_json(output / "full_roadmap_report.json", {"status": "blocked", "phase_records": []})
        calls: list[str] = []
        running_snapshots: list[dict[str, object]] = []

        def fake_runner(**kwargs):
            running_snapshots.append(json.loads((output / "full_roadmap_report.json").read_text(encoding="utf-8")))
            title = Path(kwargs["documents"][-1]).read_text(encoding="utf-8").splitlines()[0].lstrip("# ")
            calls.append(title)
            return FakePhaseResult(title)

        result = FullRoadmapExecutor(document_runner=fake_runner).run(
            objective="Implement the full creative agent roadmap.",
            documents=[doc],
            repository_path=repo,
            output_dir=output,
            run_payload={"max_phase_repair_attempts": 0},
        )

        payload = result.to_dict()
        self.assertEqual(payload["status"], "done")
        self.assertEqual(calls, [blocked_phase.title])
        self.assertEqual(len(payload["phase_records"]), 3)
        self.assertTrue(all(phase["status"] == "completed" for phase in payload["roadmap"]["phases"]))
        self.assertEqual(running_snapshots[0]["status"], "running")
        self.assertEqual(running_snapshots[0]["active_phase"]["phase_id"], blocked_phase.phase_id)
        self.assertEqual(len(running_snapshots[0]["phase_records"]), 2)

    def test_executor_resumes_latest_interrupted_phase_attempt(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        doc = root / "roadmap.md"
        doc.write_text("# One Phase\n\n## V1\n- Finish frontend.\n", encoding="utf-8")
        phase = RoadmapPhase(
            phase_id="phase_001",
            title="V1",
            requirements=["Finish frontend."],
            promotion_gate={"required_score": 0.85},
        )
        plan = RoadmapExecutionPlan(root_objective="Resume interrupted work.", phases=[phase], confidence=0.9)
        output = root / "run"
        phase_dir = output / "phases" / phase.phase_id
        interrupted = phase_dir / "run_attempt_006"
        (interrupted / "workers").mkdir(parents=True)
        write_json(output / "roadmap_execution_plan.json", plan.to_dict())
        write_json(output / "roadmap_audit.json", {"status": "passed", "issues": []})
        write_json(output / "project_analysis_report.json", {"ready_to_start": True})
        write_json(output / "expanded_document_index.json", {"documents": [str(doc)], "added_documents": []})
        write_json(
            phase_dir / "phase_record.json",
            {
                "phase_id": phase.phase_id,
                "title": phase.title,
                "status": "blocked",
                "output_dir": str(phase_dir / "run_attempt_003"),
                "result": FakePhaseResult(phase.title, blockers=["old blocker"]).to_dict(),
                "promotion": {"can_promote": False, "status": "blocked"},
            },
        )
        write_json(
            interrupted / "state.json",
            {
                "active_tasks": ["T002"],
                "task_graph": {"nodes": [{"id": "T002", "status": "active"}]},
            },
        )
        write_json(
            interrupted / "workers" / "T002.json",
            {"task_id": "T002", "status": "running", "worker_pid": 99999999},
        )
        resume_sources: list[object] = []

        def fake_runner(**kwargs):
            resume_sources.append(kwargs.get("resume_from"))
            return FakePhaseResult(phase.title)

        result = FullRoadmapExecutor(document_runner=fake_runner).run(
            objective="Resume interrupted work.",
            documents=[doc],
            repository_path=repo,
            output_dir=output,
        )

        payload = result.to_dict()
        self.assertEqual(payload["status"], "done")
        self.assertEqual(resume_sources, [interrupted])
        self.assertEqual(payload["phase_records"][0]["promotion"]["attempts"][0]["resume_from"], str(interrupted))

    def test_interrupted_resume_does_not_fall_back_past_newer_terminal_attempt(self) -> None:
        root = temp_root()
        phase_dir = root / "phase_010"
        stale = phase_dir / "run_attempt_014"
        newer = phase_dir / "run_attempt_015"
        (stale / "workers").mkdir(parents=True)
        newer.mkdir(parents=True)
        write_json(
            stale / "state.json",
            {
                "active_tasks": ["T005-DEBUG-1"],
                "task_graph": {"nodes": [{"id": "T005-DEBUG-1", "status": "active"}]},
            },
        )
        write_json(
            stale / "workers" / "T005-DEBUG-1.json",
            {"task_id": "T005-DEBUG-1", "status": "completed", "worker_pid": 99999999},
        )
        write_json(
            newer / "state.json",
            {
                "active_tasks": [],
                "blockers": [{"id": "B-T004-2", "type": "technical_limit"}],
                "task_graph": {"nodes": [{"id": "T004", "status": "failed"}]},
            },
        )

        resume = interrupted_phase_resume_source(phase_dir)

        self.assertIsNone(resume.resume_from)
        self.assertIsNone(resume.active_run_dir)
        self.assertEqual(resume.blockers, [])


if __name__ == "__main__":
    unittest.main()
