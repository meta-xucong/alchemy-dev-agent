from __future__ import annotations

import json
import shutil
import time
import unittest
from pathlib import Path

from runtime import RuntimeRecovery, TaskGraphEngine
from runtime.models import RuntimeState


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_RUN_ID = str(time.time_ns())
_TEMP_COUNTER = 0


def temp_root() -> Path:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    root = TEST_TMP_ROOT / f"recovery-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    root.mkdir(parents=True, exist_ok=False)
    return root


class RuntimeRecoveryTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_prepare_resets_failed_active_and_blocked_tasks(self) -> None:
        graph = TaskGraphEngine().create_default_graph("objective")
        graph.nodes[0].status = "completed"
        graph.nodes[1].status = "failed"
        graph.nodes[1].retry_count = 1
        graph.nodes[2].status = "active"
        graph.nodes[3].status = "blocked"
        state = RuntimeState(
            objective="objective",
            task_graph=graph,
            active_tasks=["T003"],
            failed_tasks=["T002", "T004"],
            worker_lifecycle=[
                {
                    "task_id": "T003",
                    "worker_pid": 123,
                    "started_at": "2026-06-19T00:00:00+00:00",
                    "completed_at": "",
                    "timed_out_at": "2026-06-19T00:01:00+00:00",
                    "terminated_at": "2026-06-19T00:01:01+00:00",
                    "timeout_seconds": 60,
                    "status": "timed_out",
                    "returncode": None,
                    "process_group": "alchemy-run-test",
                    "cleanup_required": False,
                    "termination": {"terminated": True},
                    "error": "timeout",
                }
            ],
            blockers=[
                {
                    "id": "B-T002-1",
                    "type": "technical_limit",
                    "description": "failed",
                    "required_resolution": "retry",
                    "task_ids": ["T002"],
                },
                {
                    "id": "B-RUN-STOPPED",
                    "type": "operator_control",
                    "description": "stopped",
                    "required_resolution": "resume",
                    "task_ids": [],
                },
            ],
        )

        source = RuntimeRecovery().load_source(write_report(temp_root(), state))
        result = RuntimeRecovery().prepare(source)

        self.assertEqual({node.id: node.status for node in result.state.task_graph.nodes}["T002"], "pending")
        self.assertEqual({node.id: node.status for node in result.state.task_graph.nodes}["T003"], "pending")
        self.assertEqual({node.id: node.status for node in result.state.task_graph.nodes}["T004"], "pending")
        self.assertEqual(result.state.active_tasks, [])
        self.assertEqual(result.state.failed_tasks, [])
        self.assertFalse(result.state.blockers)
        self.assertEqual(set(result.checkpoint["reset_task_ids"]), {"T002", "T003", "T004"})
        self.assertEqual(result.checkpoint["worker_lifecycle"][0]["task_id"], "T003")
        self.assertEqual(result.checkpoint["worker_lifecycle"][0]["previous_status"], "timed_out")
        self.assertEqual(result.state.iteration_history[-1]["type"], "recovery_checkpoint")

    def test_prepare_blocks_when_no_retryable_tasks_exist(self) -> None:
        state = RuntimeState(
            objective="objective",
            task_graph=TaskGraphEngine().create_default_graph("objective"),
        )
        source = RuntimeRecovery().load_source(write_report(temp_root(), state))

        result = RuntimeRecovery().prepare(source)

        self.assertTrue(result.blockers)
        self.assertIn("No retryable", result.blockers[0])

    def test_prepare_reconciles_completed_active_worker_from_directory(self) -> None:
        root = temp_root()
        graph = TaskGraphEngine().create_default_graph("objective")
        graph.nodes[0].status = "active"
        state = RuntimeState(
            objective="objective",
            task_graph=graph,
            active_tasks=["T001"],
        )
        (root / "state.json").write_text(json.dumps(state.to_dict(), indent=2) + "\n", encoding="utf-8")
        workers = root / "workers"
        workers.mkdir()
        (workers / "T001.json").write_text(
            json.dumps(
                {
                    "task_id": "T001",
                    "status": "completed",
                    "returncode": 0,
                    "worker_pid": 123,
                    "cleanup_required": False,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        source = RuntimeRecovery().load_source(root)
        result = RuntimeRecovery().prepare(source)

        self.assertFalse(result.blockers)
        self.assertEqual(result.state.active_tasks, [])
        self.assertEqual(result.state.completed_tasks, ["T001"])
        self.assertEqual(result.state.task_graph.nodes[0].status, "completed")
        self.assertEqual(result.checkpoint["reset_task_ids"], [])
        self.assertEqual(result.checkpoint["reconciled_completed_task_ids"], ["T001"])


def write_report(root: Path, state: RuntimeState) -> Path:
    report = root / "run.json"
    report.write_text(
        json.dumps(
            {
                "run_id": "run_001",
                "project_id": "proj_test",
                "runtime_state": state.to_dict(),
                "workspace": {"execution_path": str(root / "repo")},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return report


if __name__ == "__main__":
    unittest.main()
