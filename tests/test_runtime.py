from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from runtime.agent_router import AgentRouter
from runtime.codex_worker import CodexWorkerAdapter, CodexWorkerInput, CodexWorkerResult
from runtime.evaluator import Evaluator
from runtime.github_flow import GitHubFlow
from runtime.orchestrator import Orchestrator
from runtime.models import RuntimeState
from runtime.state_manager import StateManager
from runtime.task_graph_engine import TaskGraphEngine


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"


_TEMP_COUNTER = 0
_TEMP_RUN_ID = str(time.time_ns())


@contextmanager
def temp_project_dir() -> Iterator[str]:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    path = TEST_TMP_ROOT / f"case-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield str(path)
    finally:
        shutil.rmtree(path, ignore_errors=True)


class TaskGraphEngineTests(unittest.TestCase):
    def test_ready_tasks_follow_dependencies(self) -> None:
        engine = TaskGraphEngine()
        graph = engine.create_default_graph("build a todo app with login")

        ready = engine.get_ready_tasks(graph)
        self.assertEqual([task.id for task in ready], ["T001"])

        engine.mark_completed(graph, "T001", {"summary": "done"})
        ready = engine.get_ready_tasks(graph)
        self.assertEqual([task.id for task in ready], ["T002"])

    def test_debug_task_is_created_once_for_retryable_failure(self) -> None:
        engine = TaskGraphEngine()
        graph = engine.create_default_graph("objective")
        task = engine.get_node(graph, "T002")
        task.retry_count = 1

        debug_task = engine.create_debug_task(graph, task, "tests failed")
        same_task = engine.create_debug_task(graph, task, "tests failed again")

        self.assertIs(debug_task, same_task)
        self.assertEqual(debug_task.type, "debug")
        self.assertGreater(debug_task.priority, task.priority)


class AgentRouterTests(unittest.TestCase):
    def test_routes_task_to_assigned_agent(self) -> None:
        graph = TaskGraphEngine().create_default_graph("objective")
        task = graph.nodes[0]

        self.assertEqual(AgentRouter().route(task), "architect")


class CodexWorkerTests(unittest.TestCase):
    def test_worker_returns_completed_result_by_default(self) -> None:
        worker = CodexWorkerAdapter()
        result = worker.execute(CodexWorkerInput(task_id="T001", goal="do work"))

        self.assertEqual(result.status, "completed")
        self.assertTrue(result.files_changed)

    def test_worker_can_return_failed_by_constraint(self) -> None:
        worker = CodexWorkerAdapter()
        result = worker.execute(CodexWorkerInput(task_id="T001", goal="do work", constraints=["fail"]))

        self.assertEqual(result.status, "failed")

    def test_real_worker_parses_structured_subprocess_output(self) -> None:
        calls: list[list[str]] = []

        def fake_runner(args, *, cwd, input, capture_output, text, timeout, check):
            calls.append(args)
            payload = {
                "task_id": "T010",
                "status": "completed",
                "summary": "implemented task",
                "files_changed": ["runtime/example.py"],
                "commands_run": [{"command": "python -m unittest", "exit_code": 0}],
                "tests_passed": ["runtime tests"],
                "tests_failed": [],
                "evidence": ["all criteria met"],
                "known_issues": [],
                "follow_up_tasks": [],
                "confidence": 0.95,
            }
            return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

        worker = CodexWorkerAdapter(dry_run=False, runner=fake_runner)
        result = worker.execute(CodexWorkerInput(task_id="T010", goal="do work", repository_path="."))

        self.assertEqual(calls[0], ["codex", "exec", "--json"])
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.files_changed, ["runtime/example.py"])
        self.assertEqual(result.commands_run[0].exit_code, 0)

    def test_real_worker_reports_unparseable_output_as_failed(self) -> None:
        def fake_runner(args, *, cwd, input, capture_output, text, timeout, check):
            return subprocess.CompletedProcess(args, 1, "plain text", "error")

        worker = CodexWorkerAdapter(dry_run=False, runner=fake_runner)
        result = worker.execute(CodexWorkerInput(task_id="T011", goal="do work", repository_path="."))

        self.assertEqual(result.status, "failed")
        self.assertIn("parseable", result.summary)

    def test_real_worker_parses_jsonl_event_stream_output(self) -> None:
        def fake_runner(args, *, cwd, input, capture_output, text, timeout, check):
            event_stream = "\n".join(
                [
                    json.dumps({"type": "session.started"}),
                    json.dumps(
                        {
                            "type": "message",
                            "item": {
                                "content": [
                                    {
                                        "text": json.dumps(
                                            {
                                                "task_id": "T012",
                                                "status": "completed",
                                                "summary": "done from event stream",
                                                "files_changed": ["runtime/codex_worker.py"],
                                                "commands_run": [],
                                                "tests_passed": ["worker parsing"],
                                                "tests_failed": [],
                                                "evidence": ["jsonl parsed"],
                                                "known_issues": [],
                                                "follow_up_tasks": [],
                                                "confidence": 0.9,
                                            }
                                        )
                                    }
                                ]
                            },
                        }
                    ),
                ]
            )
            return subprocess.CompletedProcess(args, 0, event_stream, "")

        worker = CodexWorkerAdapter(dry_run=False, runner=fake_runner)
        result = worker.execute(CodexWorkerInput(task_id="T012", goal="do work", repository_path="."))

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.summary, "done from event stream")
        self.assertEqual(result.tests_passed, ["worker parsing"])


class GitHubFlowTests(unittest.TestCase):
    def test_dry_run_records_github_evidence(self) -> None:
        result = GitHubFlow(dry_run=True).record_execution(
            repository_path=".",
            branch="agent/test",
            task_ids=["T001"],
            title="test",
            body="body",
        )

        self.assertEqual(result.status, "recorded")
        self.assertEqual(result.ci_status, "passed")
        self.assertTrue(result.pull_request_url.startswith("dry-run://"))

    def test_real_flow_skips_commit_when_no_changes_exist(self) -> None:
        calls: list[list[str]] = []

        def fake_runner(args, *, cwd, capture_output, text, check):
            calls.append(args)
            if args == ["git", "status", "--short"]:
                return subprocess.CompletedProcess(args, 0, "", "")
            if args == ["gh", "pr", "create", "--title", "test", "--body", "body"]:
                return subprocess.CompletedProcess(args, 0, "https://example.test/pr/1\n", "")
            if args == ["git", "rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(args, 0, "abc123\n", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        result = GitHubFlow(dry_run=False, runner=fake_runner).record_execution(
            repository_path=".",
            branch="agent/test",
            task_ids=["T001"],
            title="test",
            body="body",
        )

        self.assertEqual(result.status, "pushed")
        self.assertEqual(result.commit, "abc123")
        self.assertNotIn(["git", "commit", "-m", "test"], calls)
        self.assertIn(["git", "push", "-u", "origin", "agent/test"], calls)


class EvaluatorTests(unittest.TestCase):
    def test_evaluator_requires_completed_graph(self) -> None:
        with temp_project_dir() as tmp_dir:
            manager = StateManager(Path(tmp_dir) / "state.json")
            state = manager.initialize("objective")

        result = Evaluator().evaluate(state)

        self.assertFalse(result.done)
        self.assertLess(result.final_score, 0.85)
        self.assertIn("Required tasks are unfinished", result.hard_failures[0])

    def test_evaluator_marks_done_after_graph_review_and_github_evidence(self) -> None:
        engine = TaskGraphEngine()
        with temp_project_dir() as tmp_dir:
            manager = StateManager(Path(tmp_dir) / "state.json")
            state = manager.initialize("objective", engine)

        for node in state.task_graph.nodes:
            engine.mark_completed(
                state.task_graph,
                node.id,
                {
                    "type": "worker_result",
                    "summary": "done",
                    "result": {"status": "completed", "tests_failed": []},
                },
            )
        state.github = {"commit": "abc123", "pull_request_url": "https://example.test/pr/1"}

        result = Evaluator().evaluate(state)

        self.assertTrue(result.done)
        self.assertGreaterEqual(result.final_score, 0.85)
        self.assertEqual(result.reviewer_decision, "approved")


class OrchestratorTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_run_reaches_done_and_persists_state(self) -> None:
        with temp_project_dir() as tmp_dir:
            state_path = Path(tmp_dir) / ".alchemy" / "state.json"
            orchestrator = Orchestrator(StateManager(state_path), repository_path=tmp_dir)

            state = orchestrator.run("build a todo app with login", reset=True)

            self.assertTrue(state.done)
            self.assertTrue(state_path.exists())
            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertTrue(persisted["done"])
            self.assertEqual(persisted["evaluation"]["reason"], "DONE condition met.")
            self.assertIn("pull_request_url", persisted["github"])

    def test_failed_task_creates_debug_task_and_retries(self) -> None:
        class FlakyWorker:
            def __init__(self) -> None:
                self.calls = 0

            def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
                if worker_input.task_id == "T002" and self.calls == 1:
                    self.calls += 1
                    return CodexWorkerResult(
                        task_id=worker_input.task_id,
                        status="failed",
                        summary="first attempt failed",
                        tests_failed=["unit tests"],
                    )
                self.calls += 1
                return CodexWorkerResult(
                    task_id=worker_input.task_id,
                    status="completed",
                    summary="completed",
                    tests_passed=["unit tests"],
                    evidence=["ok"],
                    confidence=0.9,
                )

        with temp_project_dir() as tmp_dir:
            orchestrator = Orchestrator(
                StateManager(Path(tmp_dir) / ".alchemy" / "state.json"),
                worker=FlakyWorker(),  # type: ignore[arg-type]
                repository_path=tmp_dir,
            )

            state = orchestrator.run("build a todo app with login", reset=True)

            task_ids = {node.id for node in state.task_graph.nodes}
            self.assertIn("T002-DEBUG-1", task_ids)
            self.assertTrue(state.done)
            self.assertFalse(state.blockers)

    def test_cli_smoke_run(self) -> None:
        with temp_project_dir() as tmp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
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
            self.assertEqual(payload["evaluation"]["status"], "passed")


class ContractAlignmentTests(unittest.TestCase):
    def test_v2_intake_and_context_schemas_are_parseable_and_complete(self) -> None:
        project_brief_schema = json.loads(Path("specs/project_brief_schema.json").read_text(encoding="utf-8"))
        context_bundle_schema = json.loads(Path("specs/context_bundle_schema.json").read_text(encoding="utf-8"))

        brief_properties = project_brief_schema["properties"]
        context_properties = context_bundle_schema["properties"]

        for key in [
            "objective",
            "primary_input_mode",
            "documents",
            "attachments",
            "repository",
            "constraints",
            "acceptance_criteria",
            "generated_from_one_liner",
            "blockers",
        ]:
            self.assertIn(key, brief_properties, f"{key} missing from project_brief_schema.json")

        mode_enum = brief_properties["primary_input_mode"]["enum"]
        self.assertIn("document_driven", mode_enum)
        self.assertIn("one_line_fallback", mode_enum)
        self.assertIn("repository", brief_properties)

        for key in [
            "document_index",
            "repository_map",
            "requirement_map",
            "test_profile",
            "risk_profile",
            "blockers",
        ]:
            self.assertIn(key, context_properties, f"{key} missing from context_bundle_schema.json")

        self.assertEqual(project_brief_schema["properties"]["schema_version"]["const"], "2.0")
        self.assertEqual(context_bundle_schema["properties"]["schema_version"]["const"], "2.0")

    def test_runtime_state_fields_are_declared_in_state_schema(self) -> None:
        state_schema = json.loads(Path("specs/state_schema_v2.json").read_text(encoding="utf-8"))
        properties = state_schema["properties"]

        with temp_project_dir() as tmp_dir:
            state = Orchestrator(StateManager(Path(tmp_dir) / ".alchemy" / "state.json"), repository_path=tmp_dir).run(
                "build a todo app with login",
                reset=True,
            )
        runtime_payload = state.to_dict()

        for key in runtime_payload:
            self.assertIn(key, properties, f"{key} missing from state_schema_v2.json")

        self.assertIn("evaluation_result", properties)
        self.assertIn("iteration_history", properties)
        self.assertIn("done", properties)
        self.assertIn("created_at", properties)
        self.assertIn("commit", properties["github"]["properties"])
        self.assertIn("branch", properties["github"]["properties"])

    def test_runtime_task_node_fields_are_declared_in_task_graph_schema(self) -> None:
        task_schema = json.loads(Path("specs/task_graph_schema.json").read_text(encoding="utf-8"))
        node_properties = task_schema["$defs"]["node"]["properties"]
        graph = TaskGraphEngine().create_default_graph("build a todo app with login")

        for node in graph.to_dict()["nodes"]:
            for key in node:
                self.assertIn(key, node_properties, f"{key} missing from task_graph_schema.json")

        self.assertIn("commands_to_run", node_properties)
        self.assertIn("relevant_files", node_properties)

    def test_runtime_state_loads_schema_style_task_references_as_ids(self) -> None:
        state = RuntimeState.from_dict(
            {
                "objective": "objective",
                "task_graph": TaskGraphEngine().create_default_graph("objective").to_dict(),
                "active_tasks": [{"task_id": "T001", "status": "active"}],
                "completed_tasks": [{"task_id": "T002", "completed_at": "2026-01-01T00:00:00+00:00", "evidence": []}],
                "failed_tasks": [{"task_id": "T003", "failed_at": "2026-01-01T00:00:00+00:00", "reason": "failed"}],
                "evaluation_score": 0.0,
                "blockers": [],
                "done_criteria": ["done"],
            }
        )

        self.assertEqual(state.active_tasks, ["T001"])
        self.assertEqual(state.completed_tasks, ["T002"])
        self.assertEqual(state.failed_tasks, ["T003"])


if __name__ == "__main__":
    unittest.main()
