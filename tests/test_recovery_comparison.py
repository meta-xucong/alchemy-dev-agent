from __future__ import annotations

import unittest

from autodev.recovery_comparison import build_recovery_comparison


class RecoveryComparisonTests(unittest.TestCase):
    def test_feedback_repair_comparison_records_resolved_gaps_and_probe_improvements(self) -> None:
        source = {
            "run_id": "run_001",
            "status": "blocked",
            "runtime_state": {
                "evaluation": {"final_gate_score": 0.42},
                "blockers": [{"id": "B-SCENARIO", "description": "Scenario failed."}],
            },
            "requirement_coverage": {
                "coverage_score": 0.4,
                "missing_must_requirement_ids": ["REQ-1"],
                "partial_must_requirement_ids": ["REQ-2"],
            },
            "delivery_report": {
                "ready_for_review": False,
                "artifact": {
                    "semantic_probe": {"status": "failed"},
                    "scenario_probe": {"status": "failed"},
                },
                "github": {"ci_status": "failed"},
                "blockers": [{"id": "B-SCENARIO", "description": "Scenario failed."}],
            },
        }
        current = {
            "run_id": "run_002",
            "status": "done",
            "runtime_state": {"evaluation": {"final_gate_score": 0.93}},
            "requirement_coverage": {
                "coverage_score": 1.0,
                "missing_must_requirement_ids": [],
                "partial_must_requirement_ids": [],
            },
            "delivery_report": {
                "ready_for_review": True,
                "artifact": {
                    "semantic_probe": {"status": "completed"},
                    "scenario_probe": {"status": "completed"},
                },
                "github": {"ci_status": "passed"},
                "blockers": [],
            },
        }

        comparison = build_recovery_comparison(source_run=source, current_run=current)

        self.assertEqual(comparison["status"], "improved")
        self.assertEqual(comparison["source_run_id"], "run_001")
        self.assertEqual(comparison["current_run_id"], "run_002")
        self.assertEqual(comparison["resolved_missing_must_requirement_ids"], ["REQ-1"])
        self.assertEqual(comparison["resolved_partial_must_requirement_ids"], ["REQ-2"])
        self.assertEqual(comparison["new_missing_must_requirement_ids"], [])
        self.assertGreater(comparison["score_delta"], 0)
        self.assertGreater(comparison["coverage_delta"], 0)
        self.assertLess(comparison["blocker_delta"], 0)
        directions = {change["name"]: change["direction"] for change in comparison["probe_changes"]}
        self.assertEqual(directions["semantic"], "improved")
        self.assertEqual(directions["scenario"], "improved")
        self.assertEqual(directions["ci"], "improved")

    def test_feedback_repair_comparison_detects_mixed_regression(self) -> None:
        source = {
            "run_id": "run_001",
            "status": "done",
            "runtime_state": {"evaluation": {"final_gate_score": 0.86}},
            "requirement_coverage": {
                "coverage_score": 0.9,
                "missing_must_requirement_ids": [],
                "partial_must_requirement_ids": ["REQ-2"],
            },
            "delivery_report": {
                "artifact": {"semantic_probe": {"status": "completed"}},
                "blockers": [],
            },
        }
        current = {
            "run_id": "run_002",
            "status": "done",
            "runtime_state": {"evaluation": {"final_gate_score": 0.9}},
            "requirement_coverage": {
                "coverage_score": 0.95,
                "missing_must_requirement_ids": ["REQ-3"],
                "partial_must_requirement_ids": [],
            },
            "delivery_report": {
                "artifact": {"semantic_probe": {"status": "completed"}},
                "blockers": [],
            },
        }

        comparison = build_recovery_comparison(source_run=source, current_run=current)

        self.assertEqual(comparison["status"], "mixed")
        self.assertEqual(comparison["resolved_partial_must_requirement_ids"], ["REQ-2"])
        self.assertEqual(comparison["new_missing_must_requirement_ids"], ["REQ-3"])

    def test_feedback_repair_counts_new_covered_feedback_requirements_as_improvement(self) -> None:
        source = {
            "run_id": "run_001",
            "status": "done",
            "runtime_state": {"evaluation": {"final_gate_score": 0.95}},
            "requirement_coverage": {
                "coverage_score": 1.0,
                "entries": [
                    {"requirement_id": "REQ-1", "priority": "must", "coverage_status": "covered"},
                ],
                "missing_must_requirement_ids": [],
                "partial_must_requirement_ids": [],
            },
            "delivery_report": {"ready_for_review": True, "artifact": {}, "blockers": []},
        }
        current = {
            "run_id": "run_002",
            "status": "done",
            "runtime_state": {"evaluation": {"final_gate_score": 0.95}},
            "requirement_coverage": {
                "coverage_score": 1.0,
                "entries": [
                    {"requirement_id": "REQ-1", "priority": "must", "coverage_status": "covered"},
                    {"requirement_id": "REQ-2", "priority": "must", "coverage_status": "covered"},
                ],
                "missing_must_requirement_ids": [],
                "partial_must_requirement_ids": [],
            },
            "delivery_report": {"ready_for_review": True, "artifact": {}, "blockers": []},
        }

        comparison = build_recovery_comparison(source_run=source, current_run=current)

        self.assertEqual(comparison["status"], "improved")
        self.assertEqual(comparison["new_must_requirement_ids"], ["REQ-2"])
        self.assertEqual(comparison["covered_new_must_requirement_ids"], ["REQ-2"])
        self.assertEqual(comparison["uncovered_new_must_requirement_ids"], [])


if __name__ == "__main__":
    unittest.main()
