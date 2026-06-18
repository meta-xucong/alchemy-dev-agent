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
from runtime.control import ControlDecision
from runtime.codex_worker import CodexWorkerAdapter, CodexWorkerInput, CodexWorkerResult
from runtime.evaluator import Evaluator
from runtime.github_flow import GitHubFlow
from runtime.orchestrator import Orchestrator
from runtime.models import Dependency, RuntimeState, TaskGraph, TaskNode
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

        self.assertIn(["codex", "exec", "--json", "--sandbox", "workspace-write"], calls)
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

    def test_real_worker_decodes_bytes_output_with_replacement(self) -> None:
        def fake_runner(args, *, cwd, input, capture_output, text, timeout, check):
            if args and str(args[0]).endswith("codex"):
                self.assertFalse(text)
                self.assertIsInstance(input, bytes)
                payload = {
                    "task_id": "T012C",
                    "status": "completed",
                    "summary": "bytes decoded",
                    "files_changed": [],
                    "commands_run": [],
                    "tests_passed": ["decode"],
                    "tests_failed": [],
                    "evidence": ["utf8 replacement safe"],
                    "known_issues": [],
                    "follow_up_tasks": [],
                    "confidence": 0.9,
                }
                return subprocess.CompletedProcess(args, 0, json.dumps(payload).encode("utf-8") + b"\xa6", b"")
            return subprocess.CompletedProcess(args, 0, "", "")

        worker = CodexWorkerAdapter(dry_run=False, runner=fake_runner)
        result = worker.execute(CodexWorkerInput(task_id="T012C", goal="decode output", repository_path="."))

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.summary, "bytes decoded")
        self.assertIn("\ufffd", result.raw_output)

    def test_worker_result_coerces_non_dict_command_entries(self) -> None:
        payload = {
            "task_id": "T012B",
            "status": "completed",
            "summary": "done",
            "files_changed": "README.md",
            "commands_run": ["python -m unittest"],
            "tests_passed": "unit tests",
            "tests_failed": None,
            "evidence": "verified",
            "known_issues": None,
            "follow_up_tasks": None,
            "confidence": "0.8",
        }

        result = CodexWorkerResult.from_dict(payload)

        self.assertEqual(result.files_changed, ["README.md"])
        self.assertEqual(result.commands_run[0].command, "python -m unittest")
        self.assertEqual(result.tests_passed, ["unit tests"])
        self.assertEqual(result.evidence, ["verified"])
        self.assertEqual(result.confidence, 0.8)

    def test_real_worker_rolls_back_out_of_scope_changes(self) -> None:
        with temp_project_dir() as tmp_dir:
            subprocess.run(["git", "init"], cwd=tmp_dir, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_dir, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_dir, check=True)
            allowed = Path(tmp_dir) / "allowed.md"
            allowed.write_text("before\n", encoding="utf-8")
            subprocess.run(["git", "add", "allowed.md"], cwd=tmp_dir, check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_dir, check=True, capture_output=True, text=True)

            real_run = subprocess.run

            def fake_runner(args, *, cwd, input, capture_output, text, timeout, check):
                if args and args[0] == "codex":
                    Path(cwd, "unexpected.md").write_text("out of scope\n", encoding="utf-8")
                    payload = {
                        "task_id": "T013",
                        "status": "completed",
                        "summary": "changed file",
                        "files_changed": ["unexpected.md"],
                        "commands_run": [],
                        "tests_passed": [],
                        "tests_failed": [],
                        "evidence": [],
                        "known_issues": [],
                        "follow_up_tasks": [],
                        "confidence": 1.0,
                    }
                    return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")
                return real_run(args, cwd=cwd, input=input, capture_output=capture_output, text=text, timeout=timeout, check=check)

            worker = CodexWorkerAdapter(dry_run=False, runner=fake_runner)
            result = worker.execute(
                CodexWorkerInput(
                    task_id="T013",
                    goal="only edit allowed file",
                    repository_path=tmp_dir,
                    allowed_files=["allowed.md"],
                )
            )

            self.assertEqual(result.status, "failed")
            self.assertIn("outside the task boundary", result.summary)
            self.assertFalse((Path(tmp_dir) / "unexpected.md").exists())


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
            if args == ["gh", "pr", "view", "agent/test", "--json", "url,number,state"]:
                return subprocess.CompletedProcess(args, 1, "", "no pull request")
            if args == ["gh", "pr", "create", "--title", "test", "--body", "body", "--head", "agent/test"]:
                return subprocess.CompletedProcess(args, 0, "https://example.test/pr/1\n", "")
            if args == [
                "gh",
                "pr",
                "checks",
                "agent/test",
                "--json",
                "name,state,bucket,workflow,link,completedAt,startedAt",
            ]:
                return subprocess.CompletedProcess(args, 0, '[{"name":"ci","bucket":"pass"}]\n', "")
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
        self.assertEqual(result.ci_status, "passed")
        self.assertNotIn(["git", "commit", "-m", "test"], calls)
        self.assertIn(["git", "push", "-u", "origin", "agent/test"], calls)
        self.assertIn(["gh", "pr", "create", "--title", "test", "--body", "body", "--head", "agent/test"], calls)

    def test_real_flow_reuses_existing_pull_request(self) -> None:
        calls: list[list[str]] = []

        def fake_runner(args, *, cwd, capture_output, text, check):
            calls.append(args)
            if args == ["git", "status", "--short"]:
                return subprocess.CompletedProcess(args, 0, "", "")
            if args == ["git", "rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(args, 0, "abc123\n", "")
            if args == ["gh", "pr", "view", "agent/test", "--json", "url,number,state"]:
                return subprocess.CompletedProcess(args, 0, '{"url":"https://example.test/pr/2","number":2,"state":"OPEN"}\n', "")
            if args == [
                "gh",
                "pr",
                "checks",
                "agent/test",
                "--json",
                "name,state,bucket,workflow,link,completedAt,startedAt",
            ]:
                return subprocess.CompletedProcess(args, 8, '[{"name":"ci","bucket":"pending"}]\n', "")
            return subprocess.CompletedProcess(args, 0, "", "")

        result = GitHubFlow(dry_run=False, runner=fake_runner).record_execution(
            repository_path=".",
            branch="agent/test",
            task_ids=["T001"],
            title="test",
            body="body",
        )

        self.assertEqual(result.pull_request_url, "https://example.test/pr/2")
        self.assertEqual(result.ci_status, "pending")
        self.assertNotIn(["gh", "pr", "create", "--title", "test", "--body", "body", "--head", "agent/test"], calls)

    def test_collect_ci_status_marks_failures(self) -> None:
        def fake_runner(args, *, cwd, capture_output, text, check):
            if args == [
                "gh",
                "pr",
                "checks",
                "agent/test",
                "--json",
                "name,state,bucket,workflow,link,completedAt,startedAt",
            ]:
                return subprocess.CompletedProcess(args, 1, '[{"name":"ci","bucket":"fail"}]\n', "")
            return subprocess.CompletedProcess(args, 0, "", "")

        status, details = GitHubFlow(dry_run=False, runner=fake_runner).collect_ci_status(
            repository_path=".",
            branch="agent/test",
        )

        self.assertEqual(status, "failed")
        self.assertEqual(details[0]["name"], "ci")

    def test_wait_for_ci_status_polls_until_terminal_status(self) -> None:
        calls = 0

        def fake_runner(args, *, cwd, capture_output, text, check):
            nonlocal calls
            if args == [
                "gh",
                "pr",
                "checks",
                "agent/test",
                "--json",
                "name,state,bucket,workflow,link,completedAt,startedAt",
            ]:
                calls += 1
                if calls == 1:
                    return subprocess.CompletedProcess(args, 8, '[{"name":"ci","bucket":"pending"}]\n', "")
                return subprocess.CompletedProcess(args, 0, '[{"name":"ci","bucket":"pass"}]\n', "")
            return subprocess.CompletedProcess(args, 0, "", "")

        status, details = GitHubFlow(dry_run=False, runner=fake_runner).wait_for_ci_status(
            repository_path=".",
            branch="agent/test",
            timeout_seconds=1,
            poll_interval_seconds=0.01,
        )

        self.assertEqual(status, "passed")
        self.assertEqual(details[0]["bucket"], "pass")
        self.assertEqual(calls, 2)


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

    def test_stop_controller_blocks_before_dispatching_worker(self) -> None:
        class StopController:
            def before_task(self, task_id: str) -> ControlDecision:
                return ControlDecision("stop", f"stop before {task_id}")

        class CountingWorker:
            def __init__(self) -> None:
                self.calls = 0

            def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
                self.calls += 1
                return CodexWorkerResult(task_id=worker_input.task_id, status="completed", summary="done")

        with temp_project_dir() as tmp_dir:
            worker = CountingWorker()
            orchestrator = Orchestrator(
                StateManager(Path(tmp_dir) / ".alchemy" / "state.json"),
                worker=worker,  # type: ignore[arg-type]
                controller=StopController(),
                repository_path=tmp_dir,
            )

            state = orchestrator.run("build a todo app with login", reset=True)

            self.assertEqual(worker.calls, 0)
            self.assertFalse(state.done)
            self.assertEqual(state.blockers[0]["id"], "B-RUN-STOPPED")
            self.assertEqual(state.iteration_history[-1]["type"], "run_stopped")

    def test_pause_controller_returns_before_dispatching_worker(self) -> None:
        class PauseController:
            def before_task(self, task_id: str) -> ControlDecision:
                return ControlDecision("pause", f"pause before {task_id}")

        class CountingWorker:
            def __init__(self) -> None:
                self.calls = 0

            def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
                self.calls += 1
                return CodexWorkerResult(task_id=worker_input.task_id, status="completed", summary="done")

        with temp_project_dir() as tmp_dir:
            worker = CountingWorker()
            orchestrator = Orchestrator(
                StateManager(Path(tmp_dir) / ".alchemy" / "state.json"),
                worker=worker,  # type: ignore[arg-type]
                controller=PauseController(),
                repository_path=tmp_dir,
            )

            state = orchestrator.run("build a todo app with login", reset=True)

            self.assertEqual(worker.calls, 0)
            self.assertFalse(state.done)
            self.assertEqual(state.iteration_history[-1]["type"], "run_paused")
            self.assertFalse(state.blockers)

    def test_worker_inputs_include_file_boundaries(self) -> None:
        class CaptureWorker:
            def __init__(self) -> None:
                self.inputs: list[CodexWorkerInput] = []

            def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
                self.inputs.append(worker_input)
                return CodexWorkerResult(task_id=worker_input.task_id, status="completed", summary="done")

        with temp_project_dir() as tmp_dir:
            graph = TaskGraphEngine().create_default_graph("objective")
            implementation = next(node for node in graph.nodes if node.type == "backend")
            implementation.relevant_files = ["src/app.py"]
            worker = CaptureWorker()
            Orchestrator(
                StateManager(Path(tmp_dir) / "state.json"),
                worker=worker,  # type: ignore[arg-type]
                repository_path=tmp_dir,
            ).run("objective", reset=True, task_graph=graph, max_iterations=2)

        inputs = {item.task_id: item for item in worker.inputs}
        self.assertEqual(inputs["T001"].allowed_files, [])
        self.assertIn("If allowed_files is empty", " ".join(inputs["T001"].constraints))
        self.assertEqual(inputs[implementation.id].allowed_files, ["src/app.py"])

    def test_static_document_verification_and_review_do_not_call_worker(self) -> None:
        class DocWorker:
            def __init__(self, repo: Path) -> None:
                self.repo = repo
                self.calls: list[str] = []

            def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
                self.calls.append(worker_input.task_id)
                target = self.repo / "docs" / "probe.md"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("probe\n", encoding="utf-8")
                return CodexWorkerResult(
                    task_id=worker_input.task_id,
                    status="completed",
                    summary="created probe",
                    files_changed=["docs/probe.md"],
                    tests_passed=["static document inspection"],
                    evidence=["created docs/probe.md"],
                    confidence=1.0,
                )

        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            graph = TaskGraph(
                graph_id="doc-only",
                version=1,
                nodes=[
                    TaskNode(
                        id="T001",
                        title="Create probe",
                        description="Create docs/probe.md",
                        type="documentation",
                        assigned_agent="architect",
                        completion_criteria=["`docs/probe.md` exists."],
                        relevant_files=["docs/probe.md"],
                        commands_to_run=["static document inspection"],
                    ),
                    TaskNode(
                        id="T002",
                        title="Verify probe",
                        description="Verify docs/probe.md",
                        type="test",
                        assigned_agent="test",
                        dependencies=["T001"],
                        completion_criteria=["`docs/probe.md` exists."],
                        relevant_files=["docs/probe.md"],
                        commands_to_run=["static document inspection"],
                    ),
                    TaskNode(
                        id="T003",
                        title="Review probe",
                        description="Review probe",
                        type="review",
                        assigned_agent="reviewer",
                        dependencies=["T002"],
                        completion_criteria=["Reviewer approval is recorded."],
                    ),
                    TaskNode(
                        id="T004",
                        title="Release probe",
                        description="Record evidence",
                        type="release",
                        assigned_agent="reviewer",
                        dependencies=["T003"],
                    ),
                ],
                dependencies=[
                    Dependency(source="T001", target="T002", type="requires_test_pass"),
                    Dependency(source="T002", target="T003", type="requires_review"),
                    Dependency(source="T003", target="T004", type="requires_review"),
                ],
            )
            worker = DocWorker(repo)
            state = Orchestrator(
                StateManager(repo / "state.json"),
                worker=worker,  # type: ignore[arg-type]
                repository_path=repo,
            ).run("doc probe", reset=True, task_graph=graph, max_iterations=6)

        self.assertTrue(state.done)
        self.assertEqual(worker.calls, ["T001"])
        nodes = {node.id: node for node in state.task_graph.nodes}
        self.assertEqual(nodes["T002"].evidence[-1]["result"]["commands_run"][0]["command"], "static document inspection")
        self.assertEqual(nodes["T003"].evidence[-1]["result"]["status"], "completed")

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
