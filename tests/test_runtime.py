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
from runtime.artifact_profile import ArtifactProfileDetector
from runtime.artifact_verifier import BrowserArtifactEvidenceVerifier, BrowserArtifactRunner, StaticWebArtifactVerifier
from runtime.control import ControlDecision
from runtime.codex_worker import CodexWorkerAdapter, CodexWorkerInput, CodexWorkerResult
from runtime.evaluator import Evaluator
from runtime.github_flow import GitHubExecutionResult, GitHubFlow
from runtime.orchestrator import Orchestrator
from runtime.models import Dependency, RuntimeState, TaskGraph, TaskNode
from runtime.state_manager import StateManager
from runtime.task_graph_engine import TaskGraphEngine
from runtime.requirement_coverage import RequirementCoverageBuilder
from runtime.generated_ci import StaticWebCIGenerator
from runtime.worker_lifecycle import ManagedSubprocessRunner, WorkerLifecycleRecorder


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

    def test_worker_prompt_forbids_protected_terms_in_generated_files(self) -> None:
        prompt = CodexWorkerAdapter().build_prompt(
            CodexWorkerInput(
                task_id="T001",
                goal="build original platformer",
                objective="Build an original retro platformer inspired by a protected commercial game.",
                allowed_files=["index.html"],
            )
        )

        self.assertIn("Do not write protected names", prompt)
        self.assertIn("even in safety notes", prompt)

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

    def test_real_worker_records_lifecycle_for_managed_subprocess(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
            lifecycle = WorkerLifecycleRecorder(repo / ".alchemy" / "workers")
            worker = CodexWorkerAdapter(
                executable=sys.executable,
                dry_run=False,
                timeout_seconds=10,
                lifecycle_recorder=lifecycle,
            )

            result = worker.execute(
                CodexWorkerInput(
                    task_id="T900",
                    goal="emit worker json",
                    repository_path=str(repo),
                    allowed_files=[],
                )
            )

            self.assertEqual(result.status, "failed")
            self.assertEqual(result.worker_lifecycle["task_id"], "T900")
            self.assertEqual(result.worker_lifecycle["status"], "completed")
            self.assertIsInstance(result.worker_lifecycle["worker_pid"], int)
            self.assertTrue((repo / ".alchemy" / "workers" / "T900.json").exists())

    def test_managed_subprocess_runner_terminates_on_timeout(self) -> None:
        with temp_project_dir() as tmp_dir:
            terminated: list[int] = []

            def fake_terminator(pid: int) -> dict[str, object]:
                terminated.append(pid)
                return {"terminated": True, "method": "fake"}

            recorder = WorkerLifecycleRecorder(Path(tmp_dir) / "workers", terminator=fake_terminator)
            record = recorder.start("T901", 1)
            runner = ManagedSubprocessRunner(recorder, record)

            with self.assertRaises(subprocess.TimeoutExpired):
                runner(
                    [
                        sys.executable,
                        "-c",
                        "import time; time.sleep(30)",
                    ],
                    cwd=tmp_dir,
                    input=b"",
                    capture_output=True,
                    text=False,
                    timeout=0.1,
                    check=False,
                )

        self.assertTrue(terminated)
        self.assertEqual(record.status, "timed_out")
        self.assertFalse(record.cleanup_required)
        self.assertEqual(record.termination["method"], "fake")

    def test_real_worker_timeout_result_includes_lifecycle_cleanup(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
            terminated: list[int] = []

            def fake_terminator(pid: int) -> dict[str, object]:
                terminated.append(pid)
                return {"terminated": True, "method": "fake"}

            worker = CodexWorkerAdapter(
                executable=sys.executable,
                dry_run=False,
                timeout_seconds=1,
                lifecycle_recorder=WorkerLifecycleRecorder(repo / "workers", terminator=fake_terminator),
            )
            (repo / "exec").write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
            result = worker.execute(
                CodexWorkerInput(
                    task_id="T902",
                    goal="timeout",
                    repository_path=str(repo),
                    allowed_files=[],
                )
            )

        self.assertEqual(result.status, "failed")
        self.assertIn("timed out", result.summary)
        self.assertEqual(result.worker_lifecycle["status"], "timed_out")
        self.assertFalse(result.worker_lifecycle["cleanup_required"])
        self.assertTrue(terminated)


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

    def test_real_flow_sets_local_commit_identity_when_missing(self) -> None:
        calls: list[list[str]] = []

        def fake_runner(args, *, cwd, capture_output, text, check):
            calls.append(args)
            if args == ["git", "config", "--get", "user.name"]:
                return subprocess.CompletedProcess(args, 1, "", "")
            if args == ["git", "config", "--get", "user.email"]:
                return subprocess.CompletedProcess(args, 1, "", "")
            if args == ["git", "status", "--short"]:
                return subprocess.CompletedProcess(args, 0, "A  index.html\n", "")
            if args == ["git", "rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(args, 0, "abc123\n", "")
            if args == ["gh", "pr", "view", "agent/test", "--json", "url,number,state"]:
                return subprocess.CompletedProcess(args, 0, '{"url":"https://example.test/pr/3","number":3,"state":"OPEN"}\n', "")
            return subprocess.CompletedProcess(args, 0, "", "")

        result = GitHubFlow(dry_run=False, runner=fake_runner).record_execution(
            repository_path=".",
            branch="agent/test",
            task_ids=["T001"],
            title="test",
            body="body",
            collect_ci=False,
        )

        self.assertEqual(result.status, "pushed")
        self.assertIn(["git", "config", "user.name", "Alchemy Dev Agent"], calls)
        self.assertIn(["git", "config", "user.email", "alchemy-dev-agent@users.noreply.github.com"], calls)
        self.assertIn(["git", "commit", "-m", "test"], calls)

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

    def test_real_flow_can_enable_auto_merge_after_passing_ci(self) -> None:
        calls: list[list[str]] = []

        def fake_runner(args, *, cwd, capture_output, text, check):
            calls.append(args)
            if args == ["git", "status", "--short"]:
                return subprocess.CompletedProcess(args, 0, "M  index.html\n", "")
            if args == ["git", "rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(args, 0, "abc123\n", "")
            if args == ["gh", "pr", "view", "agent/test", "--json", "url,number,state"]:
                return subprocess.CompletedProcess(args, 0, '{"url":"https://example.test/pr/9","number":9,"state":"OPEN"}\n', "")
            if args == [
                "gh",
                "pr",
                "checks",
                "agent/test",
                "--json",
                "name,state,bucket,workflow,link,completedAt,startedAt",
            ]:
                return subprocess.CompletedProcess(args, 0, '[{"name":"ci","bucket":"pass"}]\n', "")
            if args == ["gh", "pr", "merge", "agent/test", "--squash", "--delete-branch", "--auto"]:
                return subprocess.CompletedProcess(args, 0, "Auto-merge enabled\n", "")
            if args == ["gh", "pr", "view", "agent/test", "--json", "url,number,state,mergedAt"]:
                return subprocess.CompletedProcess(
                    args,
                    0,
                    '{"url":"https://example.test/pr/9","number":9,"state":"OPEN","mergedAt":null}\n',
                    "",
                )
            return subprocess.CompletedProcess(args, 0, "", "")

        result = GitHubFlow(dry_run=False, runner=fake_runner).record_execution(
            repository_path=".",
            branch="agent/test",
            task_ids=["T001"],
            title="test",
            body="body",
            auto_merge=True,
        )

        self.assertEqual(result.merge["status"], "auto_merge_enabled")
        self.assertIn(["gh", "pr", "merge", "agent/test", "--squash", "--delete-branch", "--auto"], calls)

    def test_real_flow_reports_merged_when_auto_merge_command_finds_pr_already_merged(self) -> None:
        def fake_runner(args, *, cwd, capture_output, text, check):
            if args == ["git", "status", "--short"]:
                return subprocess.CompletedProcess(args, 0, "", "")
            if args == ["git", "rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(args, 0, "abc123\n", "")
            if args == ["gh", "pr", "view", "agent/test", "--json", "url,number,state"]:
                return subprocess.CompletedProcess(args, 0, '{"url":"https://example.test/pr/12","number":12,"state":"MERGED"}\n', "")
            if args == [
                "gh",
                "pr",
                "checks",
                "agent/test",
                "--json",
                "name,state,bucket,workflow,link,completedAt,startedAt",
            ]:
                return subprocess.CompletedProcess(args, 0, '[{"name":"ci","bucket":"pass"}]\n', "")
            if args == ["gh", "pr", "merge", "agent/test", "--squash", "--delete-branch", "--auto"]:
                return subprocess.CompletedProcess(args, 0, "", "")
            if args == ["gh", "pr", "view", "agent/test", "--json", "url,number,state,mergedAt"]:
                return subprocess.CompletedProcess(
                    args,
                    0,
                    '{"url":"https://example.test/pr/12","number":12,"state":"MERGED","mergedAt":"2026-06-19T08:57:44Z"}\n',
                    "",
                )
            return subprocess.CompletedProcess(args, 0, "", "")

        result = GitHubFlow(dry_run=False, runner=fake_runner).record_execution(
            repository_path=".",
            branch="agent/test",
            task_ids=["T001"],
            title="test",
            body="body",
            auto_merge=True,
        )

        self.assertEqual(result.merge["status"], "merged")
        self.assertEqual(result.merge["remote_state"]["state"], "MERGED")

    def test_real_flow_skips_auto_merge_without_passing_ci(self) -> None:
        def fake_runner(args, *, cwd, capture_output, text, check):
            if args == ["git", "status", "--short"]:
                return subprocess.CompletedProcess(args, 0, "", "")
            if args == ["git", "rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(args, 0, "abc123\n", "")
            if args == ["gh", "pr", "view", "agent/test", "--json", "url,number,state"]:
                return subprocess.CompletedProcess(args, 0, '{"url":"https://example.test/pr/10","number":10,"state":"OPEN"}\n', "")
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

        result = GitHubFlow(dry_run=False, runner=fake_runner).record_execution(
            repository_path=".",
            branch="agent/test",
            task_ids=["T001"],
            title="test",
            body="body",
            auto_merge=True,
        )

        self.assertEqual(result.ci_status, "failed")
        self.assertEqual(result.merge["status"], "skipped")

    def test_real_flow_treats_remote_merged_pr_as_merge_success_after_local_cleanup_error(self) -> None:
        def fake_runner(args, *, cwd, capture_output, text, check):
            if args == ["git", "status", "--short"]:
                return subprocess.CompletedProcess(args, 0, "", "")
            if args == ["git", "rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(args, 0, "abc123\n", "")
            if args == ["gh", "pr", "view", "agent/test", "--json", "url,number,state"]:
                return subprocess.CompletedProcess(args, 0, '{"url":"https://example.test/pr/11","number":11,"state":"OPEN"}\n', "")
            if args == [
                "gh",
                "pr",
                "checks",
                "agent/test",
                "--json",
                "name,state,bucket,workflow,link,completedAt,startedAt",
            ]:
                return subprocess.CompletedProcess(args, 0, '[{"name":"ci","bucket":"pass"}]\n', "")
            if args == ["gh", "pr", "merge", "agent/test", "--squash", "--delete-branch", "--auto"]:
                return subprocess.CompletedProcess(args, 1, "", "fatal: local worktree conflict\n")
            if args == ["gh", "pr", "merge", "agent/test", "--squash", "--delete-branch"]:
                return subprocess.CompletedProcess(
                    args,
                    1,
                    "",
                    "! Pull request owner/repo#11 was already merged\nfatal: local worktree conflict\n",
                )
            if args == ["gh", "pr", "view", "agent/test", "--json", "url,number,state,mergedAt"]:
                return subprocess.CompletedProcess(
                    args,
                    0,
                    '{"url":"https://example.test/pr/11","number":11,"state":"MERGED","mergedAt":"2026-06-19T08:57:44Z"}\n',
                    "",
                )
            return subprocess.CompletedProcess(args, 0, "", "")

        result = GitHubFlow(dry_run=False, runner=fake_runner).record_execution(
            repository_path=".",
            branch="agent/test",
            task_ids=["T001"],
            title="test",
            body="body",
            auto_merge=True,
        )

        self.assertEqual(result.merge["status"], "merged")
        self.assertEqual(result.merge["remote_state"]["state"], "MERGED")

    def test_real_flow_returns_pushed_with_failed_ci_evidence(self) -> None:
        def fake_runner(args, *, cwd, capture_output, text, check):
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
                return subprocess.CompletedProcess(args, 1, '[{"name":"ci","bucket":"fail"}]\n', "")
            return subprocess.CompletedProcess(args, 0, "", "")

        result = GitHubFlow(dry_run=False, runner=fake_runner).record_execution(
            repository_path=".",
            branch="agent/test",
            task_ids=["T001"],
            title="test",
            body="body",
        )

        self.assertEqual(result.status, "pushed")
        self.assertEqual(result.ci_status, "failed")


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

    def test_evaluator_blocks_missing_must_requirement_coverage(self) -> None:
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
        state.repository["requirement_coverage"] = {
            "coverage_score": 0.25,
            "missing_must_requirement_ids": ["REQ-001"],
            "partial_must_requirement_ids": [],
        }

        result = Evaluator().evaluate(state)

        self.assertFalse(result.done)
        self.assertIn("REQ-001", " ".join(result.hard_failures))
        self.assertLess(result.spec_alignment, 1.0)


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

    def test_orchestrator_records_worker_lifecycle_in_runtime_state(self) -> None:
        class LifecycleWorker:
            def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
                return CodexWorkerResult(
                    task_id=worker_input.task_id,
                    status="completed",
                    summary="done",
                    worker_lifecycle={
                        "task_id": worker_input.task_id,
                        "worker_pid": 123,
                        "started_at": "2026-06-19T00:00:00+00:00",
                        "completed_at": "2026-06-19T00:00:01+00:00",
                        "timed_out_at": "",
                        "terminated_at": "",
                        "timeout_seconds": 10,
                        "status": "completed",
                        "returncode": 0,
                        "process_group": "alchemy-run-test",
                        "cleanup_required": False,
                        "termination": {},
                        "error": "",
                    },
                )

        with temp_project_dir() as tmp_dir:
            state = Orchestrator(
                StateManager(Path(tmp_dir) / "state.json"),
                repository_path=tmp_dir,
                worker=LifecycleWorker(),  # type: ignore[arg-type]
            ).run("build a todo app with login", reset=True, max_iterations=2)

        self.assertTrue(state.worker_lifecycle)
        self.assertEqual(state.worker_lifecycle[0]["worker_pid"], 123)

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

    def test_static_document_verification_requires_target_files(self) -> None:
        with temp_project_dir() as tmp_dir:
            task = TaskNode(
                id="T001",
                title="Verify docs",
                description="Verify generated document evidence.",
                type="test",
                assigned_agent="test",
                completion_criteria=["A generated document exists."],
                commands_to_run=["static document inspection"],
            )
            result = Orchestrator(StateManager(Path(tmp_dir) / "state.json"), repository_path=tmp_dir)._static_document_result(task)

        self.assertEqual(result.status, "failed")
        self.assertIn("No task-specific document files", result.tests_failed[0])

    def test_static_artifact_verifier_accepts_original_canvas_platformer(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "index.html").write_text(
                """
                <!doctype html>
                <canvas id="game"></canvas>
                <script>
                const level = { tiles: [], player: {}, enemy: {}, coin: {}, flag: {} };
                const score = 0;
                const timer = 400;
                function physics() {}
                function collision() {}
                addEventListener("keydown", event => console.log(event.code));
                function frame() { requestAnimationFrame(frame); }
                frame();
                </script>
                """,
                encoding="utf-8",
            )

            result = StaticWebArtifactVerifier().verify(repo, ["index.html"])

        self.assertEqual(result.status, "completed")
        self.assertIn("static artifact inspection", result.tests_passed)
        self.assertEqual(result.profile["name"], "canvas_game")

    def test_artifact_profile_detector_classifies_common_projects(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "package.json").write_text('{"scripts":{"test":"node tests.js"}}\n', encoding="utf-8")

            profile = ArtifactProfileDetector().detect(repo, ["index.html"])

        self.assertEqual(profile.name, "node_project")

        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "README.md").write_text("# Docs\n", encoding="utf-8")

            profile = ArtifactProfileDetector().detect(repo, ["README.md"])

        self.assertEqual(profile.name, "documentation_only")

    def test_browser_artifact_evidence_verifier_records_pixel_diff(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            from PIL import Image

            first = repo / "initial.png"
            second = repo / "after.png"
            Image.new("RGB", (8, 8), "white").save(first)
            image = Image.new("RGB", (8, 8), "white")
            image.putpixel((2, 2), (0, 0, 0))
            image.save(second)

            result = BrowserArtifactEvidenceVerifier().verify_existing_evidence(
                output_dir=repo,
                url="http://127.0.0.1:8000/index.html",
                initial_screenshot="initial.png",
                after_interaction_screenshot="after.png",
            )

        self.assertEqual(result.status, "completed")
        self.assertGreater(result.pixel_diff["changed_pixels"], 0)
        self.assertIn("browser artifact evidence", result.tests_passed)

    def test_browser_artifact_runner_starts_server_and_records_screenshots(self) -> None:
        from PIL import Image

        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "index.html").write_text("<!doctype html><canvas id='game'></canvas>", encoding="utf-8")

            def fake_browser(request: dict[str, object]) -> dict[str, object]:
                self.assertTrue(str(request["url"]).startswith("http://127.0.0.1:"))
                first = Path(str(request["initial_screenshot"]))
                second = Path(str(request["after_interaction_screenshot"]))
                initial = Image.new("RGB", (8, 8), "white")
                initial.putpixel((1, 1), (20, 20, 20))
                initial.save(first)
                image = Image.new("RGB", (8, 8), "white")
                image.putpixel((3, 3), (0, 0, 0))
                image.save(second)
                return {"status": "completed", "evidence": ["fake browser completed"]}

            result = BrowserArtifactRunner(fake_browser).verify(
                repo,
                ["index.html"],
                output_dir=repo / "evidence",
                profile_name="canvas_game",
            )

        self.assertEqual(result.status, "completed")
        self.assertGreater(result.pixel_diff["changed_pixels"], 0)
        self.assertIn("fake browser completed", result.evidence)

    def test_browser_artifact_runner_resolves_relative_output_dir_before_verification(self) -> None:
        from PIL import Image

        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "index.html").write_text("<!doctype html><canvas id='game'></canvas>", encoding="utf-8")
            relative_output = Path(repo.name) / "browser-evidence"
            seen_initial_paths: list[Path] = []

            def fake_browser(request: dict[str, object]) -> dict[str, object]:
                first = Path(str(request["initial_screenshot"]))
                second = Path(str(request["after_interaction_screenshot"]))
                seen_initial_paths.append(first)
                self.assertTrue(first.is_absolute())
                self.assertTrue(second.is_absolute())
                initial = Image.new("RGB", (8, 8), "white")
                initial.putpixel((1, 1), (20, 20, 20))
                initial.save(first)
                image = Image.new("RGB", (8, 8), "white")
                image.putpixel((3, 3), (0, 0, 0))
                image.save(second)
                return {"status": "completed"}

            old_cwd = Path.cwd()
            try:
                import os

                os.chdir(repo.parent)
                result = BrowserArtifactRunner(fake_browser).verify(
                    repo,
                    ["index.html"],
                    output_dir=relative_output,
                    profile_name="canvas_game",
                )
            finally:
                os.chdir(old_cwd)

        self.assertEqual(result.status, "completed")
        self.assertTrue(seen_initial_paths)
        self.assertGreater(result.pixel_diff["changed_pixels"], 0)

    def test_browser_artifact_runner_fails_on_console_errors(self) -> None:
        from PIL import Image

        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "index.html").write_text("<!doctype html><main>App</main>", encoding="utf-8")

            def fake_browser(request: dict[str, object]) -> dict[str, object]:
                first = Path(str(request["initial_screenshot"]))
                second = Path(str(request["after_interaction_screenshot"]))
                image = Image.new("RGB", (4, 4), "white")
                image.putpixel((1, 1), (0, 0, 0))
                image.save(first)
                image.save(second)
                return {"status": "completed", "console_errors": ["boom"]}

            result = BrowserArtifactRunner(fake_browser).verify(
                repo,
                ["index.html"],
                output_dir=repo / "evidence",
                profile_name="static_web_app",
            )

        self.assertEqual(result.status, "failed")
        self.assertIn("boom", result.tests_failed[0])

    def test_orchestrator_runs_static_artifact_inspection_deterministically(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "index.html").write_text(
                """
                <!doctype html>
                <canvas id="game"></canvas>
                <script>
                const level = { player: {}, enemy: {}, coin: {}, flag: {}, tile: [] };
                let score = 0, timer = 300;
                function physics() {}
                function collision() {}
                document.addEventListener("keydown", () => {});
                requestAnimationFrame(function frame(){ requestAnimationFrame(frame); });
                </script>
                """,
                encoding="utf-8",
            )
            task = TaskNode(
                id="T001",
                title="Verify web artifact",
                description="Verify generated canvas artifact.",
                type="test",
                assigned_agent="test",
                relevant_files=["index.html"],
                commands_to_run=["static artifact inspection"],
            )
            result = Orchestrator(StateManager(repo / "state.json"), repository_path=repo)._static_artifact_result(task)

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.commands_run[0].command, "static artifact inspection")

    def test_release_task_blocks_when_ci_is_failed(self) -> None:
        class FailedCIFlow:
            def record_execution(self, **kwargs) -> GitHubExecutionResult:
                return GitHubExecutionResult(
                    status="pushed",
                    branch="agent/test",
                    commit="abc123",
                    pull_request_url="https://example.test/pr/4",
                    ci_status="failed",
                    ci_details=[{"name": "ci", "bucket": "fail"}],
                    summary="GitHub delivery completed with CI status failed.",
                )

        with temp_project_dir() as tmp_dir:
            graph = TaskGraph(
                graph_id="release-ci",
                version=1,
                nodes=[
                    TaskNode(
                        id="T001",
                        title="Review",
                        description="Review evidence",
                        type="review",
                        assigned_agent="reviewer",
                        status="completed",
                        completion_criteria=["Reviewer approval is recorded."],
                        evidence=[{"type": "worker_result", "result": {"status": "completed", "tests_failed": []}}],
                    ),
                    TaskNode(
                        id="T002",
                        title="Release",
                        description="Record GitHub evidence",
                        type="release",
                        assigned_agent="reviewer",
                        dependencies=["T001"],
                    ),
                ],
                dependencies=[Dependency(source="T001", target="T002", type="requires_review")],
            )

            state = Orchestrator(
                StateManager(Path(tmp_dir) / "state.json"),
                github_flow=FailedCIFlow(),  # type: ignore[arg-type]
                repository_path=tmp_dir,
            ).run("release with failing ci", reset=True, task_graph=graph, max_iterations=2)

        nodes = {node.id: node for node in state.task_graph.nodes}
        self.assertEqual(nodes["T002"].status, "blocked")
        self.assertFalse(state.done)
        self.assertEqual(state.github["ci_status"], "failed")
        self.assertTrue(any(blocker["type"] == "quality_gate" for blocker in state.blockers))

    def test_release_task_blocks_when_ci_status_is_unknown(self) -> None:
        class UnknownCIFlow:
            def record_execution(self, **kwargs) -> GitHubExecutionResult:
                return GitHubExecutionResult(
                    status="pushed",
                    branch="agent/test",
                    commit="abc123",
                    pull_request_url="https://example.test/pr/5",
                    ci_status="unknown",
                    summary="GitHub delivery completed without CI status.",
                )

        with temp_project_dir() as tmp_dir:
            graph = TaskGraph(
                graph_id="release-ci-unknown",
                version=1,
                nodes=[
                    TaskNode(
                        id="T001",
                        title="Review",
                        description="Review evidence",
                        type="review",
                        assigned_agent="reviewer",
                        status="completed",
                        evidence=[{"type": "worker_result", "result": {"status": "completed", "tests_failed": []}}],
                    ),
                    TaskNode(
                        id="T002",
                        title="Release",
                        description="Record GitHub evidence",
                        type="release",
                        assigned_agent="reviewer",
                        dependencies=["T001"],
                    ),
                ],
                dependencies=[Dependency(source="T001", target="T002", type="requires_review")],
            )

            state = Orchestrator(
                StateManager(Path(tmp_dir) / "state.json"),
                github_flow=UnknownCIFlow(),  # type: ignore[arg-type]
                repository_path=tmp_dir,
            ).run("release with unknown ci", reset=True, task_graph=graph, max_iterations=2)

        nodes = {node.id: node for node in state.task_graph.nodes}
        self.assertEqual(nodes["T002"].status, "blocked")
        self.assertFalse(state.done)
        self.assertEqual(state.github["ci_status"], "unknown")

    def test_release_task_allows_unknown_ci_when_collection_is_disabled(self) -> None:
        class UnknownCIFlow:
            def __init__(self) -> None:
                self.kwargs: dict[str, object] = {}

            def record_execution(self, **kwargs) -> GitHubExecutionResult:
                self.kwargs = kwargs
                return GitHubExecutionResult(
                    status="pushed",
                    branch="agent/test",
                    commit="abc123",
                    pull_request_url="https://example.test/pr/5",
                    ci_status="waived",
                    ci_details=[{"bucket": "waived"}],
                    summary="GitHub delivery completed with explicit CI waiver.",
                )

        flow = UnknownCIFlow()
        with temp_project_dir() as tmp_dir:
            graph = TaskGraph(
                graph_id="release-ci-disabled",
                version=1,
                nodes=[
                    TaskNode(
                        id="T001",
                        title="Review",
                        description="Review evidence",
                        type="review",
                        assigned_agent="reviewer",
                        status="completed",
                        evidence=[{"type": "worker_result", "result": {"status": "completed", "tests_failed": []}}],
                    ),
                    TaskNode(
                        id="T002",
                        title="Release",
                        description="Record GitHub evidence",
                        type="release",
                        assigned_agent="reviewer",
                        dependencies=["T001"],
                    ),
                ],
                dependencies=[Dependency(source="T001", target="T002", type="requires_review")],
            )

            state = Orchestrator(
                StateManager(Path(tmp_dir) / "state.json"),
                github_flow=flow,  # type: ignore[arg-type]
                repository_path=tmp_dir,
                github_collect_ci=False,
            ).run("release without ci collection", reset=True, task_graph=graph, max_iterations=2)

        nodes = {node.id: node for node in state.task_graph.nodes}
        self.assertEqual(nodes["T002"].status, "completed")
        self.assertFalse(state.blockers)
        self.assertEqual(flow.kwargs["collect_ci"], False)
        self.assertEqual(state.github["ci_status"], "waived")

    def test_real_flow_records_explicit_ci_waiver_when_collection_is_disabled(self) -> None:
        def fake_runner(args, *, cwd, capture_output, text, check):
            if args == ["git", "status", "--short"]:
                return subprocess.CompletedProcess(args, 0, "A  index.html\n", "")
            if args == ["git", "rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(args, 0, "abc123\n", "")
            if args == ["gh", "pr", "view", "agent/test", "--json", "url,number,state"]:
                return subprocess.CompletedProcess(args, 0, '{"url":"https://example.test/pr/7","number":7,"state":"OPEN"}\n', "")
            return subprocess.CompletedProcess(args, 0, "", "")

        result = GitHubFlow(dry_run=False, runner=fake_runner).record_execution(
            repository_path=".",
            branch="agent/test",
            task_ids=["T001"],
            title="test",
            body="body",
            collect_ci=False,
        )

        self.assertEqual(result.status, "pushed")
        self.assertEqual(result.ci_status, "waived")
        self.assertEqual(result.ci_details[0]["bucket"], "waived")

    def test_release_task_passes_ci_wait_configuration_to_github_flow(self) -> None:
        class CapturingFlow:
            def __init__(self) -> None:
                self.kwargs: dict[str, object] = {}

            def record_execution(self, **kwargs) -> GitHubExecutionResult:
                self.kwargs = kwargs
                return GitHubExecutionResult(
                    status="pushed",
                    branch="agent/test",
                    commit="abc123",
                    pull_request_url="https://example.test/pr/6",
                    ci_status="passed",
                    summary="GitHub delivery completed with CI status passed.",
                )

        flow = CapturingFlow()
        with temp_project_dir() as tmp_dir:
            graph = TaskGraph(
                graph_id="release-ci-wait",
                version=1,
                nodes=[
                    TaskNode(
                        id="T001",
                        title="Review",
                        description="Review evidence",
                        type="review",
                        assigned_agent="reviewer",
                        status="completed",
                        evidence=[{"type": "worker_result", "result": {"status": "completed", "tests_failed": []}}],
                    ),
                    TaskNode(
                        id="T002",
                        title="Release",
                        description="Record GitHub evidence",
                        type="release",
                        assigned_agent="reviewer",
                        dependencies=["T001"],
                    ),
                ],
                dependencies=[Dependency(source="T001", target="T002", type="requires_review")],
            )

            state = Orchestrator(
                StateManager(Path(tmp_dir) / "state.json"),
                github_flow=flow,  # type: ignore[arg-type]
                repository_path=tmp_dir,
                github_ci_wait_seconds=45,
                github_ci_poll_interval_seconds=3,
            ).run("release with ci wait", reset=True, task_graph=graph, max_iterations=2)

        nodes = {node.id: node for node in state.task_graph.nodes}
        self.assertEqual(nodes["T002"].status, "completed")
        self.assertFalse(state.blockers)
        self.assertEqual(flow.kwargs["collect_ci"], True)
        self.assertEqual(flow.kwargs["ci_wait_seconds"], 45)
        self.assertEqual(flow.kwargs["ci_poll_interval_seconds"], 3)

    def test_release_task_generates_static_ci_before_github_flow(self) -> None:
        class CapturingFlow:
            def __init__(self) -> None:
                self.workflow_existed_before_record = False

            def record_execution(self, **kwargs) -> GitHubExecutionResult:
                repository_path = Path(str(kwargs["repository_path"]))
                self.workflow_existed_before_record = (
                    repository_path / ".github" / "workflows" / "alchemy-static-checks.yml"
                ).is_file()
                return GitHubExecutionResult(
                    status="pushed",
                    branch="agent/test",
                    commit="abc123",
                    pull_request_url="https://example.test/pr/8",
                    ci_status="passed",
                    summary="GitHub delivery completed with CI status passed.",
                )

        flow = CapturingFlow()
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "index.html").write_text("<main><canvas id=\"game\"></canvas></main>", encoding="utf-8")
            graph = TaskGraph(
                graph_id="release-static-ci",
                version=1,
                nodes=[
                    TaskNode(
                        id="T001",
                        title="Review",
                        description="Review evidence",
                        type="review",
                        assigned_agent="reviewer",
                        status="completed",
                        evidence=[{"type": "worker_result", "result": {"status": "completed", "tests_failed": []}}],
                    ),
                    TaskNode(
                        id="T002",
                        title="Release",
                        description="Record GitHub evidence",
                        type="release",
                        assigned_agent="reviewer",
                        dependencies=["T001"],
                    ),
                ],
                dependencies=[Dependency(source="T001", target="T002", type="requires_review")],
            )
            initial_state = RuntimeState(objective="release static canvas game", task_graph=graph)
            initial_state.repository = {
                "provider": "local",
                "path": tmp_dir,
                "generate_static_ci": True,
                "artifact_profile": "canvas_game",
            }

            state = Orchestrator(
                StateManager(repo / "state.json"),
                github_flow=flow,  # type: ignore[arg-type]
                repository_path=repo,
            ).run("release static canvas game", reset=True, initial_state=initial_state, max_iterations=2)

        self.assertTrue(flow.workflow_existed_before_record)
        self.assertEqual(state.repository["generated_ci"]["status"], "generated")
        self.assertTrue(any(event["type"] == "generated_static_ci" for event in state.iteration_history))

    def test_release_task_preserves_existing_generated_static_ci_report(self) -> None:
        class CapturingFlow:
            def record_execution(self, **kwargs) -> GitHubExecutionResult:
                return GitHubExecutionResult(
                    status="pushed",
                    branch="agent/test",
                    commit="abc123",
                    pull_request_url="https://example.test/pr/9",
                    ci_status="passed",
                    summary="GitHub delivery completed with CI status passed.",
                )

        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            workflow_path = repo / ".github" / "workflows" / "alchemy-static-checks.yml"
            workflow_path.parent.mkdir(parents=True)
            workflow_path.write_text("name: existing\n", encoding="utf-8")
            graph = TaskGraph(
                graph_id="release-existing-static-ci",
                version=1,
                nodes=[
                    TaskNode(
                        id="T001",
                        title="Review",
                        description="Review evidence",
                        type="review",
                        assigned_agent="reviewer",
                        status="completed",
                        evidence=[{"type": "worker_result", "result": {"status": "completed", "tests_failed": []}}],
                    ),
                    TaskNode(
                        id="T002",
                        title="Release",
                        description="Record GitHub evidence",
                        type="release",
                        assigned_agent="reviewer",
                        dependencies=["T001"],
                    ),
                ],
                dependencies=[Dependency(source="T001", target="T002", type="requires_review")],
            )
            initial_state = RuntimeState(objective="release static canvas game", task_graph=graph)
            initial_state.repository = {
                "provider": "local",
                "path": tmp_dir,
                "generate_static_ci": True,
                "artifact_profile": "canvas_game",
                "generated_ci": {
                    "status": "generated",
                    "workflow_path": ".github/workflows/alchemy-static-checks.yml",
                    "summary": "Generated lightweight static web artifact CI workflow.",
                },
            }

            state = Orchestrator(
                StateManager(repo / "state.json"),
                github_flow=CapturingFlow(),  # type: ignore[arg-type]
                repository_path=repo,
            ).run("release static canvas game", reset=True, initial_state=initial_state, max_iterations=2)

        self.assertEqual(state.repository["generated_ci"]["status"], "generated")

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


class RequirementCoverageTests(unittest.TestCase):
    def test_requirement_coverage_marks_existing_completed_requirement_covered(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "src").mkdir()
            (repo / "src" / "feature.py").write_text("print('ok')\n", encoding="utf-8")

            report = RequirementCoverageBuilder().build(
                repository_path=repo,
                context_bundle={
                    "requirement_map": {
                        "requirements": [
                            {
                                "id": "REQ-001",
                                "priority": "must",
                                "text": "Implement feature",
                                "related_files": ["src/feature.py"],
                                "planned_task_ids": ["T002", "T003"],
                            }
                        ]
                    }
                },
                task_graph={
                    "nodes": [
                        {
                            "id": "T002",
                            "type": "backend",
                            "status": "completed",
                            "relevant_files": ["src/feature.py"],
                            "evidence": [{"summary": "implementation done"}],
                        },
                        {
                            "id": "T003",
                            "type": "test",
                            "status": "completed",
                            "relevant_files": ["src/feature.py"],
                            "evidence": [{"summary": "tests passed"}],
                        },
                    ]
                },
                runtime_state={"completed_tasks": ["T002", "T003"]},
                artifact_report={"static_verification": {"status": "completed"}},
            )

        payload = report.to_dict()
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["coverage_score"], 1.0)
        self.assertEqual(payload["entries"][0]["coverage_status"], "covered")

    def test_requirement_coverage_marks_missing_files_missing(self) -> None:
        with temp_project_dir() as tmp_dir:
            report = RequirementCoverageBuilder().build(
                repository_path=tmp_dir,
                context_bundle={
                    "requirement_map": {
                        "requirements": [
                            {
                                "id": "REQ-001",
                                "priority": "must",
                                "text": "Implement missing file",
                                "related_files": ["src/missing.py"],
                                "planned_task_ids": ["T002"],
                            }
                        ]
                    }
                },
                task_graph={
                    "nodes": [
                        {
                            "id": "T002",
                            "type": "backend",
                            "status": "completed",
                            "relevant_files": ["src/missing.py"],
                        }
                    ]
                },
                runtime_state={"completed_tasks": ["T002"]},
                artifact_report={},
            )

        payload = report.to_dict()
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["entries"][0]["coverage_status"], "missing")
        self.assertEqual(payload["missing_must_requirement_ids"], ["REQ-001"])


class GeneratedCITests(unittest.TestCase):
    def test_static_web_ci_generator_creates_workflow_when_missing(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "index.html").write_text("<!doctype html><canvas></canvas>", encoding="utf-8")

            result = StaticWebCIGenerator().generate_if_needed(
                repo,
                artifact_profile="canvas_game",
                collect_ci=True,
            )

            self.assertEqual(result.status, "generated")
            self.assertTrue((repo / ".github" / "workflows" / "alchemy-static-checks.yml").exists())

    def test_static_web_ci_generator_skips_existing_workflow(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            workflow = repo / ".github" / "workflows" / "ci.yml"
            workflow.parent.mkdir(parents=True)
            workflow.write_text("name: ci\n", encoding="utf-8")
            (repo / "index.html").write_text("<!doctype html><canvas></canvas>", encoding="utf-8")

            result = StaticWebCIGenerator().generate_if_needed(
                repo,
                artifact_profile="canvas_game",
                collect_ci=True,
            )

            self.assertEqual(result.status, "skipped")
            self.assertFalse((repo / ".github" / "workflows" / "alchemy-static-checks.yml").exists())


if __name__ == "__main__":
    unittest.main()
