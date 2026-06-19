from __future__ import annotations

import unittest

from autodev.delivery_evidence import build_delivery_evidence


class DeliveryEvidenceTests(unittest.TestCase):
    def test_ready_delivery_evidence_summarizes_review_contract(self) -> None:
        evidence = build_delivery_evidence(
            status="done",
            delivery_report={
                "ready_for_review": True,
                "summary": "DONE condition met.",
                "final_gate": {"score": 0.96, "reason": "DONE condition met."},
                "artifact": {
                    "profile": "static_web_app",
                    "static_status": "completed",
                    "semantic_probe": {"status": "completed", "tests_passed": ["controls"]},
                    "scenario_probe": {"status": "completed", "tests_passed": ["scenario"]},
                    "native_ui_tests": {
                        "status": "generated",
                        "framework": "playwright",
                        "write_mode": "report_only",
                        "target_path": "generated_tests/playwright/alchemy_acceptance.spec.ts",
                    },
                },
                "github": {
                    "branch": "agent/example",
                    "pull_request_url": "https://example.test/pr/1",
                    "ci_status": "passed",
                    "merge": {"status": "merged", "summary": "Merged."},
                },
                "blockers": [],
                "next_actions": ["Review the PR."],
            },
            artifact_report={"browser_verification": {"status": "completed"}},
            requirement_coverage={
                "status": "passed",
                "coverage_score": 1.0,
                "entries": [
                    {"coverage_status": "covered"},
                    {"coverage_status": "covered"},
                ],
                "missing_must_requirement_ids": [],
                "partial_must_requirement_ids": [],
            },
            generated_ci={"status": "generated"},
            development_cycle={
                "status": "passed",
                "score": 1.0,
                "steps": [
                    {"name": "read_documents", "status": "passed"},
                    {"name": "iteration", "status": "waived"},
                ],
            },
            recovery_comparison={
                "status": "improved",
                "summary": "Repair run improved the source run evidence.",
                "source_run_id": "run_001",
                "current_run_id": "run_002",
                "score_delta": 0.1,
                "coverage_delta": 0.2,
                "resolved_missing_must_requirement_ids": ["REQ-1"],
                "new_missing_must_requirement_ids": [],
                "probe_changes": [
                    {
                        "name": "scenario",
                        "source_status": "failed",
                        "current_status": "passed",
                        "direction": "improved",
                    }
                ],
                "repair_suggestions": [
                    {
                        "id": "RS-001",
                        "agent": "debug",
                        "task_type": "debug",
                        "priority": "must",
                        "title": "Cover new feedback must requirements",
                        "reason": "Feedback introduced new must requirements that are not covered yet.",
                        "requirement_ids": ["REQ-2"],
                        "worker_goal": "Implement or fix the linked must requirements.",
                    }
                ],
            },
        )

        self.assertEqual(evidence["status"], "ready")
        self.assertTrue(evidence["ready_for_review"])
        self.assertEqual(evidence["requirements"]["covered"], 2)
        self.assertEqual(evidence["requirements"]["missing_must"], 0)
        self.assertEqual(evidence["probes"]["overall_status"], "passed")
        self.assertEqual(evidence["native_ui_tests"]["framework"], "playwright")
        self.assertEqual(evidence["github"]["merge_status"], "merged")
        self.assertEqual(evidence["development_cycle"]["passed_steps"], 2)
        self.assertEqual(evidence["recovery_comparison"]["status"], "improved")
        self.assertEqual(evidence["recovery_comparison"]["resolved_missing_must_requirement_ids"], ["REQ-1"])
        self.assertEqual(evidence["repair_suggestions"][0]["agent"], "debug")
        self.assertIn("Cover new feedback must requirements", evidence["next_actions"])
        self.assertIn("Repair Comparison", [card["label"] for card in evidence["cards"]])
        self.assertGreaterEqual(len(evidence["cards"]), 8)

    def test_blocked_delivery_evidence_surfaces_blockers(self) -> None:
        evidence = build_delivery_evidence(
            status="blocked",
            delivery_report={
                "ready_for_review": False,
                "summary": "Execution preflight failed.",
                "final_gate": {"score": 0.2, "reason": "Blocked."},
                "artifact": {"profile": "unknown"},
                "github": {"ci_status": "failed"},
                "blockers": [{"id": "B-PREFLIGHT", "description": "Codex missing."}],
                "next_actions": ["Install Codex CLI."],
            },
            artifact_report={},
            requirement_coverage={
                "status": "failed",
                "coverage_score": 0,
                "entries": [{"coverage_status": "missing"}],
                "missing_must_requirement_ids": ["REQ-001"],
            },
            generated_ci={"status": "skipped"},
            development_cycle={"status": "partial", "steps": []},
        )

        self.assertEqual(evidence["status"], "blocked")
        self.assertFalse(evidence["ready_for_review"])
        self.assertEqual(evidence["requirements"]["missing"], 1)
        self.assertEqual(evidence["requirements"]["missing_must"], 1)
        self.assertEqual(evidence["blockers"][0]["id"], "B-PREFLIGHT")
        self.assertEqual(evidence["next_actions"], ["Install Codex CLI."])


if __name__ == "__main__":
    unittest.main()
