from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from runtime.agent_router import AgentRouter
from runtime.codex_worker import CodexWorkerAdapter, CodexWorkerInput
from runtime.evaluator import Evaluator
from runtime.orchestrator import Orchestrator
from runtime.state_manager import StateManager
from runtime.task_graph_engine import TaskGraphEngine


class TaskGraphEngineTests(unittest.TestCase):
    def test_ready_tasks_follow_dependencies(self) -> None:
        engine = TaskGraphEngine()
        graph = engine.create_default_graph("build a todo app with login")

        ready = engine.get_ready_tasks(graph)
        self.assertEqual([task.id for task in ready], ["T001"])

        engine.mark_completed(graph, "T001", {"summary": "done"})
        ready = engine.get_ready_tasks(graph)
        self.assertEqual([task.id for task in ready], ["T002"])


class AgentRouterTests(unittest.TestCase):
    def test_routes_task_to_assigned_agent(self) -> None:
        graph = TaskGraphEngine().create_default_graph("objective")
        task = graph.nodes[0]

        self.assertEqual(AgentRouter().route(task), "architect")


class CodexWorkerTests(unittest.TestCase):
    def test_worker_returns_passed_result_by_default(self) -> None:
        worker = CodexWorkerAdapter()
        result = worker.execute(CodexWorkerInput(task_id="T001", goal="do work"))

        self.assertEqual(result.status, "passed")
        self.assertTrue(result.diff)

    def test_worker_can_return_failed_by_constraint(self) -> None:
        worker = CodexWorkerAdapter()
        result = worker.execute(CodexWorkerInput(task_id="T001", goal="do work", constraints=["fail"]))

        self.assertEqual(result.status, "failed")


class EvaluatorTests(unittest.TestCase):
    def test_evaluator_requires_completed_graph(self) -> None:
        manager = StateManager(Path(tempfile.mkdtemp()) / "state.json")
        state = manager.initialize("objective")

        result = Evaluator().evaluate(state)

        self.assertFalse(result.done)
        self.assertLess(result.final_score, 0.85)

    def test_evaluator_marks_done_after_all_tasks_complete(self) -> None:
        engine = TaskGraphEngine()
        manager = StateManager(Path(tempfile.mkdtemp()) / "state.json")
        state = manager.initialize("objective", engine)

        for node in state.task_graph.nodes:
            engine.mark_completed(state.task_graph, node.id, {"summary": "done"})

        result = Evaluator().evaluate(state)

        self.assertTrue(result.done)
        self.assertGreaterEqual(result.final_score, 0.85)


class OrchestratorTests(unittest.TestCase):
    def test_run_reaches_done_and_persists_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / ".alchemy" / "state.json"
            orchestrator = Orchestrator(StateManager(state_path))

            state = orchestrator.run("build a todo app with login", reset=True)

            self.assertTrue(state.done)
            self.assertTrue(state_path.exists())
            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertTrue(persisted["done"])
            self.assertEqual(persisted["evaluation_result"]["reason"], "DONE condition met.")

    def test_cli_smoke_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "runtime.run_loop",
                    "--project",
                    tmp_dir,
                    "--objective",
                    "build a todo app with login",
                    "--reset",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["done"])


if __name__ == "__main__":
    unittest.main()
