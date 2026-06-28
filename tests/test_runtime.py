from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

from runtime.agent_router import AgentRouter
from runtime.acceptance_scenarios import AcceptanceScenarioPlanner
from runtime.artifact_profile import ArtifactProfileDetector
from runtime.artifact_verifier import BrowserArtifactEvidenceVerifier, BrowserArtifactRunner, StaticWebArtifactVerifier
from runtime.control import ControlDecision, MarkerFileExecutionController
from runtime.codex_worker import (
    RAW_OUTPUT_LIMIT,
    CodexWorkerAdapter,
    CodexWorkerInput,
    CodexWorkerResult,
    CommandResult,
    _build_codex_subprocess_env,
)
from runtime.evaluator import Evaluator
from runtime.github_flow import GitHubExecutionResult, GitHubFlow
from runtime.orchestrator import Orchestrator
from runtime.models import Dependency, RuntimeState, TaskGraph, TaskNode
from runtime.state_manager import StateManager
from runtime.task_graph_engine import TaskGraphEngine
from runtime.requirement_coverage import RequirementCoverageBuilder
from runtime.generated_ci import StaticWebCIGenerator
from runtime.worker_lifecycle import ManagedSubprocessRunner, WorkerLifecycleRecorder, _managed_process_startup_kwargs


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

    def test_debug_task_for_read_only_test_task_does_not_inherit_files(self) -> None:
        engine = TaskGraphEngine()
        graph = TaskGraph(
            graph_id="read-only-debug",
            version=1,
            nodes=[
                TaskNode(
                    id="T001",
                    title="Audit",
                    description="Audit source docs.",
                    type="test",
                    assigned_agent="test",
                    status="failed",
                    retry_count=1,
                    relevant_files=["docs/requirements.md", "backend/**"],
                    commands_to_run=["pytest"],
                    boundary_mode="large_refactor",
                )
            ],
        )
        task = engine.get_node(graph, "T001")

        debug_task = engine.create_debug_task(graph, task, "audit failed")

        self.assertEqual(debug_task.relevant_files, [])
        self.assertEqual(debug_task.commands_to_run, ["pytest"])
        self.assertEqual(debug_task.boundary_mode, "large_refactor")

    def test_debug_task_for_implementation_task_keeps_relevant_files(self) -> None:
        engine = TaskGraphEngine()
        graph = engine.create_default_graph("objective")
        task = engine.get_node(graph, "T002")
        task.retry_count = 1

        debug_task = engine.create_debug_task(graph, task, "tests failed")

        self.assertIn("runtime", debug_task.relevant_files)
        self.assertIn("tests", debug_task.relevant_files)


class AgentRouterTests(unittest.TestCase):
    def test_routes_task_to_assigned_agent(self) -> None:
        graph = TaskGraphEngine().create_default_graph("objective")
        task = graph.nodes[0]

        self.assertEqual(AgentRouter().route(task), "architect")


class AcceptanceScenarioPlannerTests(unittest.TestCase):
    def test_generates_domain_scenarios_from_acceptance_requirements(self) -> None:
        context_bundle = {
            "requirement_map": {
                "requirements": [
                    {
                        "id": "REQ-001",
                        "text": "Users must login with email and password.",
                        "acceptance_criteria": ["Login form accepts credentials and starts a session."],
                    },
                    {
                        "id": "REQ-002",
                        "text": "Users can create, edit, and delete todo records.",
                        "acceptance_criteria": ["CRUD actions update the visible todo list."],
                    },
                    {
                        "id": "REQ-003",
                        "text": "Dashboard shows KPI charts and supports search filters.",
                        "acceptance_criteria": ["Metrics and filters are visible."],
                    },
                    {
                        "id": "REQ-004",
                        "text": "Users can upload an attachment.",
                        "acceptance_criteria": ["File upload control is available."],
                    },
                ]
            }
        }

        plan = AcceptanceScenarioPlanner().build(context_bundle)

        self.assertEqual(plan.status, "generated")
        self.assertEqual({scenario.kind for scenario in plan.scenarios}, {"auth", "crud", "dashboard", "file_upload"})
        crud = next(scenario for scenario in plan.scenarios if scenario.kind == "crud")
        self.assertIn("delete", crud.required_behaviors)


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

    def test_worker_does_not_block_from_natural_language_goal(self) -> None:
        worker = CodexWorkerAdapter()
        result = worker.execute(
            CodexWorkerInput(
                task_id="T001",
                goal="Ensure empty todo submission remains blocked in index.html.",
                commands_to_run=["static artifact inspection"],
            )
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.tests_passed, ["static artifact inspection"])

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

    def test_worker_prompt_allows_dependency_installs_without_manifest_drift(self) -> None:
        prompt = CodexWorkerAdapter().build_prompt(
            CodexWorkerInput(
                task_id="T001",
                goal="run frontend tests",
                allowed_files=["frontend/package.json"],
                commands_to_run=["npm --prefix frontend test"],
            )
        )

        self.assertIn("package-manager install commands", prompt)
        self.assertIn("node_modules", prompt)
        self.assertIn("do not modify manifests or lockfiles", prompt)

    def test_worker_prompt_includes_windows_powershell_command_hygiene(self) -> None:
        prompt = CodexWorkerAdapter().build_prompt(
            CodexWorkerInput(
                task_id="T001",
                goal="inspect and patch wallet handlers",
                allowed_files=["backend/internal/handler/admin/user_handler.go"],
            )
        )

        self.assertIn("rg --files", prompt)
        self.assertIn("Windows PowerShell", prompt)
        self.assertIn("rg --glob", prompt)
        self.assertIn("Select-Object -Index start..end", prompt)
        self.assertIn("Treat shell globbing, quoting, or path-syntax errors", prompt)

    def test_worker_prompt_includes_windows_spaced_path_hardening(self) -> None:
        prompt = CodexWorkerAdapter().build_prompt(
            CodexWorkerInput(
                task_id="T001",
                goal="validate runtime state in a workspace whose path contains spaces",
                allowed_files=[".codex-longrun/state.json"],
            )
        )

        self.assertIn("Quote Windows paths that contain spaces", prompt)
        self.assertIn("`--project`", prompt)
        self.assertIn("prefer setting the working directory", prompt)

    def test_worker_prompt_includes_windows_go_execution_hardening(self) -> None:
        prompt = CodexWorkerAdapter().build_prompt(
            CodexWorkerInput(
                task_id="T002",
                goal="verify Go wallet handlers on Windows",
                allowed_files=["backend/internal/handler/admin/user_handler.go"],
            )
        )

        self.assertIn("confirm the active module root", prompt)
        self.assertIn("go.mod", prompt)
        self.assertIn("cd backend && go test ./...", prompt)
        self.assertIn("do not send regex alternation such as `|`", prompt)
        self.assertIn("already populated `GOMODCACHE`", prompt)
        self.assertIn("Do not launch multiple parallel `go test` processes", prompt)

    def test_worker_prompt_includes_output_budget_hygiene(self) -> None:
        prompt = CodexWorkerAdapter().build_prompt(
            CodexWorkerInput(
                task_id="T003",
                goal="close a large frontend domain surface",
                allowed_files=["frontend/src/api/**", "frontend/src/types/**"],
            )
        )

        self.assertIn("Keep command output small", prompt)
        self.assertIn("rg -l", prompt)
        self.assertIn("Select-Object -First 80", prompt)
        self.assertIn("Do not run broad `rg -n` searches", prompt)
        self.assertIn("summarize large outputs", prompt)

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

        expected_repo_path = str(Path(".").resolve())
        if os.name == "nt":
            expected_args = [
                "codex",
                "--disable",
                "plugins",
                "--dangerously-bypass-approvals-and-sandbox",
                "exec",
                "--json",
                "--cd",
                expected_repo_path,
            ]
        else:
            expected_args = [
                "codex",
                "--disable",
                "plugins",
                "-c",
                'approval_policy="never"',
                "-c",
                'sandbox_mode="workspace-write"',
                "--ask-for-approval",
                "never",
                "--sandbox",
                "workspace-write",
                "exec",
                "--json",
                "--cd",
                expected_repo_path,
            ]
        self.assertIn(expected_args, calls)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.files_changed, ["runtime/example.py"])
        self.assertEqual(result.commands_run[0].exit_code, 0)

    def test_real_worker_can_disable_codex_cli_bypass(self) -> None:
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

        with patch.dict(os.environ, {"ALCHEMY_DISABLE_CODEX_CLI_BYPASS": "1"}):
            worker = CodexWorkerAdapter(dry_run=False, runner=fake_runner)
            worker.execute(CodexWorkerInput(task_id="T010", goal="do work", repository_path="."))

        expected_repo_path = str(Path(".").resolve())
        self.assertIn(
            [
                "codex",
                "--disable",
                "plugins",
                "-c",
                'approval_policy="never"',
                "-c",
                'sandbox_mode="workspace-write"',
                "--ask-for-approval",
                "never",
                "--sandbox",
                "workspace-write",
                "exec",
                "--json",
                "--cd",
                expected_repo_path,
            ],
            calls,
        )

    def test_real_worker_reports_unparseable_output_as_failed(self) -> None:
        def fake_runner(args, *, cwd, input, capture_output, text, timeout, check):
            return subprocess.CompletedProcess(args, 1, "plain text", "error")

        worker = CodexWorkerAdapter(dry_run=False, runner=fake_runner)
        result = worker.execute(CodexWorkerInput(task_id="T011", goal="do work", repository_path="."))

        self.assertEqual(result.status, "failed")
        self.assertIn("parseable", result.summary)

    def test_build_codex_subprocess_env_redirects_home_to_writable_override_root(self) -> None:
        repo = Path.cwd()
        source_root = Path.home() / ".codex" / "memories" / f"codex-home-source-{time.time_ns()}"
        override_root = Path.home() / ".codex" / "memories" / f"codex-home-target-{time.time_ns()}"
        source_root.mkdir(parents=True, exist_ok=True)
        (source_root / "auth.json").write_text('{"OPENAI_API_KEY":"test-key"}\n', encoding="utf-8")
        (source_root / "config.toml").write_text('model_provider = "OpenAI"\n', encoding="utf-8")
        (source_root / "cc-switch-model-catalog.json").write_text('{"models":[]}\n', encoding="utf-8")
        with patch.dict(
            os.environ,
            {
                "ALCHEMY_CODEX_HOME_ROOT": str(override_root),
                "ALCHEMY_CODEX_SOURCE_HOME": str(source_root),
                "CODEX_HOME": "",
            },
            clear=False,
        ):
            env = _build_codex_subprocess_env(repo)

        codex_home = Path(env["CODEX_HOME"])
        self.assertTrue(str(codex_home).startswith(str(override_root)))
        self.assertEqual(env["TMP"], str(codex_home / "tmp"))
        self.assertEqual((codex_home / "auth.json").read_text(encoding="utf-8"), '{"OPENAI_API_KEY":"test-key"}\n')
        self.assertEqual((codex_home / "config.toml").read_text(encoding="utf-8"), 'model_provider = "OpenAI"\n')
        self.assertTrue((codex_home / "cc-switch-model-catalog.json").is_file())
        self.assertTrue(env["SSL_CERT_FILE"])
        probe = codex_home / "__runtime_probe.txt"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()

    def test_build_codex_subprocess_env_bootstraps_go_worker_environment(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "backend").mkdir()
            (repo / "backend" / "go.mod").write_text("module example.com/app\n\ngo 1.26.4\n", encoding="utf-8")
            source_root = repo / "source-codex-home"
            target_root = repo / "target-codex-home"
            go_bin = repo / "tools" / "go" / "bin"
            go_bin.mkdir(parents=True)
            (go_bin / ("go.exe" if os.name == "nt" else "go")).write_text("", encoding="utf-8")
            mod_cache = repo / "shared-gomodcache"
            appdata = str(repo / "real-appdata")
            with patch.dict(
                os.environ,
                {
                    "ALCHEMY_CODEX_HOME_ROOT": str(target_root),
                    "ALCHEMY_CODEX_SOURCE_HOME": str(source_root),
                    "ALCHEMY_GO_BIN": str(go_bin),
                    "ALCHEMY_GOMODCACHE": str(mod_cache),
                    "APPDATA": appdata,
                    "CODEX_HOME": "",
                    "PATH": "",
                    "GOCACHE": "",
                    "GOFLAGS": "",
                    "GOMODCACHE": "",
                    "GOTOOLCHAIN": "",
                },
                clear=False,
            ):
                env = _build_codex_subprocess_env(repo)

        self.assertTrue(env["PATH"].split(os.pathsep)[0].endswith(str(go_bin)))
        self.assertEqual(env["GOMODCACHE"], str(mod_cache))
        self.assertTrue(env["GOCACHE"].endswith(".gocache-alchemy"))
        self.assertEqual(env["GOTOOLCHAIN"], "auto")
        self.assertEqual(env["GOFLAGS"], "-p=1")
        self.assertEqual(env["APPDATA"], appdata)

    def test_build_codex_subprocess_env_can_disable_go_bootstrap(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "go.mod").write_text("module example.com/app\n\ngo 1.22\n", encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    "ALCHEMY_DISABLE_GO_ENV_BOOTSTRAP": "1",
                    "CODEX_HOME": str(repo / "codex-home"),
                    "GOCACHE": "",
                    "GOFLAGS": "",
                    "GOMODCACHE": "",
                    "GOTOOLCHAIN": "",
                },
                clear=False,
            ):
                env = _build_codex_subprocess_env(repo)

        self.assertEqual(env.get("GOMODCACHE", ""), "")
        self.assertEqual(env.get("GOCACHE", ""), "")
        self.assertEqual(env.get("GOFLAGS", ""), "")
        self.assertEqual(env.get("GOTOOLCHAIN", ""), "")

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

    def test_real_worker_usage_limit_jsonl_blocks_without_parse_retry(self) -> None:
        def fake_runner(args, *, cwd, input, capture_output, text, timeout, check):
            event_stream = "\n".join(
                [
                    json.dumps({"type": "thread.started", "thread_id": "thread-usage"}),
                    json.dumps({"type": "turn.started"}),
                    json.dumps(
                        {
                            "type": "error",
                            "message": "You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 5:39 PM.",
                        }
                    ),
                    json.dumps(
                        {
                            "type": "turn.failed",
                            "error": {
                                "message": "You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 5:39 PM."
                            },
                        }
                    ),
                ]
            )
            return subprocess.CompletedProcess(args, 1, event_stream, "Reading prompt from stdin...\n")

        worker = CodexWorkerAdapter(dry_run=False, runner=fake_runner)
        result = worker.execute(CodexWorkerInput(task_id="T012L", goal="handle local usage limit", repository_path="."))

        self.assertEqual(result.status, "blocked")
        self.assertIn("Codex CLI usage limit reached", result.summary)
        self.assertIn("5:39 PM", result.summary)
        self.assertIn("usage limit", result.known_issues[0].lower())
        self.assertIn("turn.failed", result.raw_output)
        self.assertEqual(result.commands_run[0].exit_code, 1)

    def test_real_worker_ignores_usage_limit_text_inside_successful_jsonl_output(self) -> None:
        def fake_runner(args, *, cwd, input, capture_output, text, timeout, check):
            payload = {
                "task_id": "T012M",
                "status": "completed",
                "summary": "planned from repair evidence",
                "files_changed": [],
                "commands_run": [],
                "tests_passed": ["planner evidence parsed"],
                "tests_failed": [],
                "evidence": ["repair note mentions Codex usage limit as historical context"],
                "known_issues": [],
                "follow_up_tasks": [],
                "confidence": 0.9,
            }
            event_stream = "\n".join(
                [
                    json.dumps({"type": "thread.started", "thread_id": "thread-ok"}),
                    json.dumps({"type": "turn.started"}),
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "command_execution",
                                "status": "completed",
                                "aggregated_output": "phase repair note: local Codex usage limit was a previous blocker",
                            },
                        }
                    ),
                    json.dumps(payload),
                ]
            )
            return subprocess.CompletedProcess(args, 0, event_stream, "")

        worker = CodexWorkerAdapter(dry_run=False, runner=fake_runner)
        result = worker.execute(CodexWorkerInput(task_id="T012M", goal="plan with historical quota note", repository_path="."))

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.summary, "planned from repair evidence")
        self.assertEqual(result.tests_passed, ["planner evidence parsed"])

    def test_real_worker_truncates_large_raw_output_after_parsing(self) -> None:
        def fake_runner(args, *, cwd, input, capture_output, text, timeout, check):
            payload = {
                "task_id": "T012D",
                "status": "completed",
                "summary": "parsed from final event",
                "files_changed": [],
                "commands_run": [],
                "tests_passed": ["parse before truncate"],
                "tests_failed": [],
                "evidence": [],
                "known_issues": [],
                "follow_up_tasks": [],
                "confidence": 0.9,
            }
            event_stream = "x" * (RAW_OUTPUT_LIMIT + 5000) + "\n" + json.dumps(payload)
            return subprocess.CompletedProcess(args, 0, event_stream, "")

        worker = CodexWorkerAdapter(dry_run=False, runner=fake_runner)
        result = worker.execute(CodexWorkerInput(task_id="T012D", goal="large output", repository_path="."))

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.summary, "parsed from final event")
        self.assertLessEqual(len(result.raw_output), RAW_OUTPUT_LIMIT)
        self.assertIn("raw output truncated", result.raw_output)
        self.assertIn('"task_id": "T012D"', result.raw_output)

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

    def test_worker_result_truncates_large_structured_text_fields(self) -> None:
        large = "a" * 6000
        payload = {
            "task_id": "T012T",
            "status": "completed",
            "summary": large,
            "files_changed": [],
            "commands_run": [
                {
                    "command": "rg -n old-term frontend/src",
                    "exit_code": 0,
                    "summary": large,
                    "stdout": large,
                    "stderr": large,
                }
            ],
            "tests_passed": [large],
            "tests_failed": [],
            "evidence": [large],
            "known_issues": [large],
            "follow_up_tasks": [large],
            "confidence": 0.9,
            "raw_output": "r" * (RAW_OUTPUT_LIMIT + 100),
        }

        result = CodexWorkerResult.from_dict(payload)

        self.assertLessEqual(len(result.summary), 4000)
        self.assertLessEqual(len(result.commands_run[0].summary), 4000)
        self.assertLessEqual(len(result.commands_run[0].stdout), 1000)
        self.assertLessEqual(len(result.commands_run[0].stderr), 1000)
        self.assertLessEqual(len(result.evidence[0]), 4000)
        self.assertLessEqual(len(result.known_issues[0]), 4000)
        self.assertLessEqual(len(result.follow_up_tasks[0]), 4000)
        self.assertLessEqual(len(result.raw_output), RAW_OUTPUT_LIMIT)
        self.assertIn("truncated", result.commands_run[0].stdout)
        self.assertIn("raw output truncated", result.raw_output)

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

    def test_real_worker_allows_glob_scope_and_rolls_back_protected_directory_change(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            (repo / "custom_media_agent_2_0" / "app").mkdir(parents=True)
            legacy = repo / "custom_media_agent_2_0" / "app" / "runtime.py"
            legacy.write_text("VALUE = 'legacy'\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True, text=True)

            real_run = subprocess.run

            def fake_runner(args, *, cwd, input, capture_output, text, timeout, check):
                if args and args[0] == "codex":
                    Path(cwd, "alchemy_creative_agent_3_0", "app").mkdir(parents=True)
                    Path(cwd, "alchemy_creative_agent_3_0", "app", "__init__.py").write_text("VALUE = 'v3'\n", encoding="utf-8")
                    Path(cwd, "custom_media_agent_2_0", "app", "runtime.py").write_text("VALUE = 'mutated'\n", encoding="utf-8")
                    payload = {
                        "task_id": "T013S",
                        "status": "completed",
                        "summary": "changed v3 and legacy",
                        "files_changed": [
                            "alchemy_creative_agent_3_0/app/__init__.py",
                            "custom_media_agent_2_0/app/runtime.py",
                        ],
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
                    task_id="T013S",
                    goal="only edit V3 scope",
                    repository_path=tmp_dir,
                    allowed_files=["alchemy_creative_agent_3_0/**"],
                )
            )

            self.assertEqual(result.status, "failed")
            self.assertTrue((repo / "alchemy_creative_agent_3_0" / "app" / "__init__.py").exists())
            self.assertEqual(legacy.read_text(encoding="utf-8"), "VALUE = 'legacy'\n")

    def test_real_worker_allows_filename_glob_scope(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            (repo / "frontend" / "src" / "views" / "user").mkdir(parents=True)
            subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=repo, check=True, capture_output=True, text=True)

            real_run = subprocess.run

            def fake_runner(args, *, cwd, input, capture_output, text, timeout, check):
                if args and args[0] == "codex":
                    changed = [
                        "frontend/src/views/user/PaymentView.vue",
                        "frontend/src/views/user/PaymentResultView.vue",
                        "frontend/src/views/user/UserOrdersView.vue",
                    ]
                    for file_path in changed:
                        target = Path(cwd, file_path)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text("<template>billing</template>\n", encoding="utf-8")
                    payload = {
                        "task_id": "T014",
                        "status": "completed",
                        "summary": "updated payment views",
                        "files_changed": changed,
                        "commands_run": [],
                        "tests_passed": ["diff check"],
                        "tests_failed": [],
                        "evidence": [],
                        "known_issues": [],
                        "follow_up_tasks": [],
                        "confidence": 0.9,
                    }
                    return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")
                return real_run(args, cwd=cwd, input=input, capture_output=capture_output, text=text, timeout=timeout, check=check)

            worker = CodexWorkerAdapter(dry_run=False, runner=fake_runner)
            result = worker.execute(
                CodexWorkerInput(
                    task_id="T014",
                    goal="edit payment views",
                    repository_path=tmp_dir,
                    allowed_files=[
                        "frontend/src/views/user/*Payment*.vue",
                        "frontend/src/views/user/*Order*.vue",
                    ],
                )
            )

            self.assertEqual(result.status, "completed")
            self.assertTrue((repo / "frontend" / "src" / "views" / "user" / "PaymentView.vue").exists())

    def test_real_worker_ignores_generated_cache_files_for_boundary_audit(self) -> None:
        with temp_project_dir() as tmp_dir:
            subprocess.run(["git", "init"], cwd=tmp_dir, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_dir, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_dir, check=True)
            allowed = Path(tmp_dir) / "app.py"
            allowed.write_text("def add(a, b):\n    raise NotImplementedError()\n", encoding="utf-8")
            subprocess.run(["git", "add", "app.py"], cwd=tmp_dir, check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_dir, check=True, capture_output=True, text=True)

            real_run = subprocess.run

            def fake_runner(args, *, cwd, input, capture_output, text, timeout, check):
                if args and args[0] == "codex":
                    Path(cwd, "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
                    cache = Path(cwd, "__pycache__")
                    cache.mkdir()
                    (cache / "app.cpython-312.pyc").write_bytes(b"cache")
                    tmp = Path(cwd, ".alchemy_tmp")
                    tmp.mkdir()
                    (tmp / "scratch").write_text("tmp\n", encoding="utf-8")
                    (Path(cwd) / "_tmp_52272_492ee6b655f4904778dec22f2bd6efda").write_text(
                        "codex scratch\n",
                        encoding="utf-8",
                    )
                    go_cache = Path(cwd, "backend", ".gocache-t013", "00")
                    go_cache.mkdir(parents=True)
                    (go_cache / "cache-entry-a").write_text("cache\n", encoding="utf-8")
                    ent_cache = Path(cwd, "backend", "ent", "schema", ".entc")
                    ent_cache.mkdir(parents=True)
                    (ent_cache / "entc.go").write_text("package entc\n", encoding="utf-8")
                    payload = {
                        "task_id": "T013A",
                        "status": "completed",
                        "summary": "changed allowed file",
                        "files_changed": ["app.py"],
                        "commands_run": [],
                        "tests_passed": ["unit tests"],
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
                    task_id="T013A",
                    goal="edit app",
                    repository_path=tmp_dir,
                    allowed_files=["app.py"],
                )
            )

            self.assertEqual(result.status, "completed")
            self.assertEqual(result.files_changed, ["app.py"])
            self.assertIn("return a + b", (Path(tmp_dir) / "app.py").read_text(encoding="utf-8"))
            self.assertTrue((Path(tmp_dir) / "__pycache__" / "app.cpython-312.pyc").exists())
            self.assertTrue((Path(tmp_dir) / ".alchemy_tmp" / "scratch").exists())
            self.assertTrue((Path(tmp_dir) / "_tmp_52272_492ee6b655f4904778dec22f2bd6efda").exists())
            self.assertTrue((Path(tmp_dir) / "backend" / ".gocache-t013" / "00" / "cache-entry-a").exists())
            self.assertTrue((Path(tmp_dir) / "backend" / "ent" / "schema" / ".entc" / "entc.go").exists())

    def test_real_worker_removes_nested_codex_scratch_before_execution(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            target = repo / "frontend" / "app.ts"
            target.parent.mkdir()
            target.write_text("export const value = 1\n", encoding="utf-8")
            scratch = repo / "frontend" / "_tmp_33208_ac37a7662ad1779c7d17ab44429701d1"
            scratch.write_text("codex scratch\n", encoding="utf-8")
            subprocess.run(["git", "add", "frontend/app.ts"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True, text=True)

            def fake_runner(args, *, cwd, input, capture_output, text, timeout, check):
                if args and args[0] == "codex":
                    self.assertFalse(scratch.exists())
                    payload = {
                        "task_id": "T013D",
                        "status": "completed",
                        "summary": "scratch cleaned",
                        "files_changed": [],
                        "commands_run": [],
                        "tests_passed": ["scratch cleanup"],
                        "tests_failed": [],
                        "evidence": [],
                        "known_issues": [],
                        "follow_up_tasks": [],
                        "confidence": 1.0,
                    }
                    return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")
                return subprocess.run(args, cwd=cwd, input=input, capture_output=capture_output, text=text, timeout=timeout, check=check)

            result = CodexWorkerAdapter(dry_run=False, runner=fake_runner).execute(
                CodexWorkerInput(
                    task_id="T013D",
                    goal="clean scratch",
                    repository_path=str(repo),
                    allowed_files=["frontend/app.ts"],
                )
            )

        self.assertEqual(result.status, "completed")

    def test_real_worker_ignores_test_runtime_artifacts_for_boundary_audit(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            target = repo / "alchemy_creative_agent_3_0" / "app" / "product_api.py"
            target.parent.mkdir(parents=True)
            target.write_text("ROUTES = []\n", encoding="utf-8")
            runtime_artifact = (
                repo
                / "alchemy_creative_agent_3_0"
                / "tests"
                / "_runtime_product_api"
                / "select_123"
                / "brands"
                / "brand_product_api.json"
            )
            pytest_cache = repo / "pytest-cache-files-abc123" / "v" / "cache"
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True, text=True)

            real_run = subprocess.run

            def fake_runner(args, *, cwd, input, capture_output, text, timeout, check):
                if args and args[0] == "codex":
                    Path(cwd, "alchemy_creative_agent_3_0", "app", "product_api.py").write_text(
                        "ROUTES = ['/api/v3/creative-agent/jobs']\n",
                        encoding="utf-8",
                    )
                    runtime_artifact.parent.mkdir(parents=True)
                    runtime_artifact.write_text('{"selected": true}\n', encoding="utf-8")
                    pytest_cache.mkdir(parents=True)
                    (pytest_cache / "nodeids").write_text("[]\n", encoding="utf-8")
                    payload = {
                        "task_id": "T013C",
                        "status": "completed",
                        "summary": "changed allowed V3 API and ran tests",
                        "files_changed": ["alchemy_creative_agent_3_0/app/product_api.py"],
                        "commands_run": ["python -B -m pytest alchemy_creative_agent_3_0/tests"],
                        "tests_passed": ["v3 tests"],
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
                    task_id="T013C",
                    goal="edit V3 product API",
                    repository_path=tmp_dir,
                    allowed_files=["alchemy_creative_agent_3_0/app/product_api.py"],
                )
            )

            self.assertEqual(result.status, "completed")
            self.assertEqual(result.files_changed, ["alchemy_creative_agent_3_0/app/product_api.py"])
            self.assertIn("/api/v3/creative-agent/jobs", target.read_text(encoding="utf-8"))
            self.assertTrue(runtime_artifact.exists())
            self.assertTrue((pytest_cache / "nodeids").exists())

    def test_real_worker_expands_new_directory_before_boundary_audit(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            (repo / "README.md").write_text("# repo\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True, text=True)

            real_run = subprocess.run

            def fake_runner(args, *, cwd, input, capture_output, text, timeout, check):
                if args and args[0] == "codex":
                    Path(cwd, "pkg").mkdir()
                    Path(cwd, "pkg", "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
                    payload = {
                        "task_id": "T013B",
                        "status": "completed",
                        "summary": "created allowed package",
                        "files_changed": ["pkg/__init__.py"],
                        "commands_run": [],
                        "tests_passed": ["unit tests"],
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
                    task_id="T013B",
                    goal="create package",
                    repository_path=tmp_dir,
                    allowed_files=["pkg/__init__.py"],
                )
            )

            self.assertEqual(result.status, "completed")
            self.assertEqual(result.files_changed, ["pkg/__init__.py"])
            self.assertTrue((repo / "pkg" / "__init__.py").exists())

    def test_real_worker_records_lifecycle_for_managed_subprocess(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            lifecycle = WorkerLifecycleRecorder(repo / ".alchemy" / "workers")
            record = lifecycle.start("T900", 10)
            runner = ManagedSubprocessRunner(lifecycle, record)

            result = runner(
                [sys.executable, "-c", "print('ok')"],
                cwd=repo,
                input=b"",
                capture_output=True,
                text=False,
                timeout=10,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(record.task_id, "T900")
            self.assertEqual(record.status, "completed")
            self.assertIsInstance(record.worker_pid, int)
            self.assertTrue((repo / ".alchemy" / "workers" / "T900.json").exists())

    def test_managed_subprocess_runner_hides_windows_console_children(self) -> None:
        kwargs = _managed_process_startup_kwargs()

        if os.name == "nt":
            self.assertIn("creationflags", kwargs)
            self.assertTrue(kwargs["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP)
            self.assertTrue(kwargs["creationflags"] & subprocess.CREATE_NO_WINDOW)
            if "startupinfo" in kwargs:
                self.assertEqual(kwargs["startupinfo"].wShowWindow, subprocess.SW_HIDE)
        else:
            self.assertEqual(kwargs, {"preexec_fn": os.setsid})

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

    def test_managed_subprocess_runner_extends_timeout_when_progress_is_detected(self) -> None:
        with temp_project_dir() as tmp_dir:
            recorder = WorkerLifecycleRecorder(Path(tmp_dir) / "workers")
            record = recorder.start("T901G", 1)
            probed: list[int] = []

            def progress_probe(pid: int) -> dict[str, object]:
                probed.append(pid)
                return {
                    "active": True,
                    "reason": "verification child process detected",
                    "active_descendants": [{"pid": 456, "name": "go.exe"}],
                }

            runner = ManagedSubprocessRunner(
                recorder,
                record,
                poll_interval_seconds=0.001,
                timeout_progress_grace_seconds=0.1,
                progress_probe=progress_probe,
            )

            class SlowThenDoneProcess:
                pid = 123
                returncode = 0
                stdin = None
                stdout = None
                stderr = None

                def __init__(self) -> None:
                    self.calls = 0

                def communicate(self, input=None, timeout=None):
                    self.calls += 1
                    if self.calls < 3:
                        time.sleep(0.02)
                        raise subprocess.TimeoutExpired(["codex"], timeout, output=b"", stderr=b"")
                    return b'{"task_id":"T901G","status":"completed"}', b""

                def poll(self):
                    return None

            process = SlowThenDoneProcess()

            stdout, stderr = runner._communicate_with_control(
                process,  # type: ignore[arg-type]
                input=b"",
                timeout=0.001,
                args=["codex"],
            )

        self.assertEqual(stdout, b'{"task_id":"T901G","status":"completed"}')
        self.assertEqual(stderr, b"")
        self.assertEqual(record.timeout_grace_count, 1)
        self.assertGreater(record.timeout_grace_seconds, 0)
        self.assertEqual(probed, [123])

    def test_managed_subprocess_runner_recovers_when_exited_process_keeps_pipe_open(self) -> None:
        with temp_project_dir() as tmp_dir:
            recorder = WorkerLifecycleRecorder(Path(tmp_dir) / "workers")
            record = recorder.start("T901P", 10)
            runner = ManagedSubprocessRunner(
                recorder,
                record,
                cancellation_check=lambda: False,
                poll_interval_seconds=0.01,
                pipe_drain_grace_seconds=0.01,
            )

            class ExitedProcessWithOpenPipes:
                returncode = 0
                stdin = None
                stdout = None
                stderr = None

                def __init__(self) -> None:
                    self.calls = 0

                def communicate(self, input=None, timeout=None):
                    self.calls += 1
                    raise subprocess.TimeoutExpired(
                        ["codex"],
                        timeout,
                        output=b'{"task_id":"T901P","status":"completed"}',
                        stderr=b"",
                    )

                def poll(self):
                    return 0

            process = ExitedProcessWithOpenPipes()

            stdout, stderr = runner._communicate_with_control(
                process,  # type: ignore[arg-type]
                input=b"",
                timeout=10,
                args=["codex"],
            )

        self.assertEqual(stdout, b'{"task_id":"T901P","status":"completed"}')
        self.assertEqual(stderr, b"")
        self.assertEqual(process.calls, 2)
        self.assertIn("captured pipes", record.error)

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

    def test_real_worker_timeout_restores_preexisting_dirty_file_snapshot(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
            target = repo / "app.txt"
            target.write_text("committed\n", encoding="utf-8")
            subprocess.run(["git", "add", "app.txt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True, text=True)
            target.write_text("phase-one\n", encoding="utf-8")

            def fake_runner(args, *, cwd, input, capture_output, text, timeout, check):
                if len(args) >= 2 and args[1] == "exec":
                    target.write_text("timed-out-worker\n", encoding="utf-8")
                    raise subprocess.TimeoutExpired(args, timeout)
                return subprocess.run(
                    args,
                    cwd=cwd,
                    input=input,
                    capture_output=capture_output,
                    text=text,
                    timeout=timeout,
                    check=check,
                )

            worker = CodexWorkerAdapter(
                executable=sys.executable,
                dry_run=False,
                timeout_seconds=1,
                runner=fake_runner,
            )
            result = worker.execute(
                CodexWorkerInput(
                    task_id="T902B",
                    goal="timeout",
                    repository_path=str(repo),
                    allowed_files=["app.txt"],
                )
            )

            self.assertEqual(result.status, "failed")
            self.assertEqual(target.read_text(encoding="utf-8"), "phase-one\n")

    def test_real_worker_zero_timeout_means_unlimited(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
            observed: dict[str, object] = {}

            def fake_runner(args, *, cwd, input, capture_output, text, timeout, check):
                if "exec" in args:
                    observed["timeout"] = timeout
                    return subprocess.CompletedProcess(args, 0, b'{"status":"completed","summary":"ok"}', b"")
                return subprocess.CompletedProcess(args, 0, "", "")

            worker = CodexWorkerAdapter(
                executable=sys.executable,
                dry_run=False,
                timeout_seconds=0,
                runner=fake_runner,
            )
            result = worker.execute(
                CodexWorkerInput(
                    task_id="T902A",
                    goal="unlimited timeout",
                    repository_path=str(repo),
                    allowed_files=[],
                )
            )

        self.assertEqual(result.status, "completed")
        self.assertIsNone(observed["timeout"])

    def test_real_worker_cancellation_result_includes_lifecycle_cleanup(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
            terminated: list[int] = []
            checks = {"count": 0}

            def fake_terminator(pid: int) -> dict[str, object]:
                terminated.append(pid)
                return {"terminated": True, "method": "fake-cancel"}

            def should_cancel(task_id: str) -> bool:
                checks["count"] += 1
                return checks["count"] >= 2

            sleeper = repo / "exec"
            sleeper.write_text(
                "import time\n"
                "time.sleep(30)\n",
                encoding="utf-8",
            )

            worker = CodexWorkerAdapter(
                executable=sys.executable,
                dry_run=False,
                timeout_seconds=10,
                lifecycle_recorder=WorkerLifecycleRecorder(repo / "workers", terminator=fake_terminator),
                cancellation_check=should_cancel,
            )
            result = worker.execute(
                CodexWorkerInput(
                    task_id="T903",
                    goal="cancel",
                    repository_path=str(repo),
                    allowed_files=[],
                )
            )

        self.assertEqual(result.status, "blocked")
        self.assertIn("cancelled", result.summary)
        self.assertEqual(result.worker_lifecycle["status"], "cancelled")
        self.assertEqual(result.worker_lifecycle["termination"]["method"], "fake-cancel")
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

    def test_evaluator_does_not_fail_completed_run_for_benign_environment_warnings(self) -> None:
        engine = TaskGraphEngine()
        with temp_project_dir() as tmp_dir:
            manager = StateManager(Path(tmp_dir) / "state.json")
            state = manager.initialize("objective", engine)

        warning_result = {
            "status": "completed",
            "tests_failed": [],
            "known_issues": [
                "Pytest emitted cache warnings because it could not create files under .pytest_cache due to WinError 5 access denied.",
                "A non-required compileall attempt failed due Windows pycache write PermissionError after an import smoke test.",
                "Root legacy test command python -m pytest tests is listed as a guardrail verification; V3 authoritative verification passed.",
            ],
        }
        for node in state.task_graph.nodes:
            engine.mark_completed(
                state.task_graph,
                node.id,
                {
                    "type": "worker_result",
                    "summary": "done",
                    "result": warning_result,
                },
            )
        state.github = {"commit": "abc123", "pull_request_url": "https://example.test/pr/1"}

        result = Evaluator().evaluate(state)

        self.assertTrue(result.done)
        self.assertGreaterEqual(result.final_score, 0.85)
        self.assertEqual(result.dimension_scores["risk_quality"], 1.0)

    def test_evaluator_does_not_penalize_future_phase_known_issues(self) -> None:
        engine = TaskGraphEngine()
        with temp_project_dir() as tmp_dir:
            manager = StateManager(Path(tmp_dir) / "state.json")
            state = manager.initialize("objective", engine)

        warning_result = {
            "status": "completed",
            "tests_failed": [],
            "known_issues": [
                "Later roadmap phases still need to remove gateway/upstream/account/proxy/channel/model/subscription routes.",
                "Preserved later-phase gateway/schema/UI behavior as explicitly out of scope for Phase 1.",
                "One exploratory read failed because the file does not exist; this was non-blocking and not a requested verification command.",
            ],
        }
        for node in state.task_graph.nodes:
            engine.mark_completed(
                state.task_graph,
                node.id,
                {
                    "type": "worker_result",
                    "summary": "done",
                    "result": warning_result,
                },
            )
        state.github = {"commit": "abc123", "pull_request_url": "https://example.test/pr/1"}

        result = Evaluator().evaluate(state)

        self.assertTrue(result.done)
        self.assertGreaterEqual(result.final_score, 0.85)
        self.assertEqual(result.dimension_scores["risk_quality"], 1.0)

    def test_evaluator_treats_completed_architecture_known_issues_as_planning_notes(self) -> None:
        engine = TaskGraphEngine()
        with temp_project_dir() as tmp_dir:
            manager = StateManager(Path(tmp_dir) / "state.json")
            state = manager.initialize("objective", engine)

        for node in state.task_graph.nodes:
            result = {"status": "completed", "tests_failed": [], "known_issues": []}
            if node.type == "architecture":
                result["known_issues"] = [
                    "Future implementation must remove backend route registration and old token relay concepts.",
                    "Payment and redeem flows are high-risk because existing wiring has legacy dependencies.",
                ]
            engine.mark_completed(
                state.task_graph,
                node.id,
                {
                    "type": "worker_result",
                    "summary": "done",
                    "result": result,
                },
            )
        state.github = {"commit": "abc123", "pull_request_url": "https://example.test/pr/1"}

        result = Evaluator().evaluate(state)

        self.assertTrue(result.done)
        self.assertEqual(result.dimension_scores["risk_quality"], 1.0)

    def test_evaluator_counts_preserved_repair_evidence_for_alignment(self) -> None:
        with temp_project_dir() as tmp_dir:
            manager = StateManager(Path(tmp_dir) / "state.json")
            state = manager.initialize("objective")

        state.task_graph.nodes = []
        for index in range(1, 9):
            state.task_graph.nodes.append(
                TaskNode(
                    id=f"T{index:03d}",
                    title=f"Preserved frontend task {index}",
                    description="Preserved completed Billing Core frontend closure task.",
                    type="frontend" if index > 1 else "architecture",
                    assigned_agent="frontend",
                    status="completed",
                    completion_criteria=["Preserved completion evidence is carried forward."],
                    evidence=[
                        {
                            "type": "focused_repair_preserved_task",
                            "result": {"status": "completed"},
                        }
                    ],
                )
            )
        state.task_graph.nodes.extend(
            [
                TaskNode(
                    id="T021",
                    title="Verify implementation against project checks",
                    description="Run verification.",
                    type="test",
                    assigned_agent="test",
                    status="completed",
                    completion_criteria=["Verification passes."],
                    evidence=[
                        {
                            "type": "worker_result",
                            "result": {
                                "status": "completed",
                                "tests_failed": [],
                                "known_issues": [
                                    "Worktree is already very dirty outside this task; no repository files were edited.",
                                    "Frontend build emitted a non-fatal Vite dynamic/static import chunking warning.",
                                ],
                            },
                        }
                    ],
                ),
                TaskNode(
                    id="T022",
                    title="Review delivery readiness",
                    description="Review evidence.",
                    type="review",
                    assigned_agent="review",
                    status="completed",
                    completion_criteria=["Reviewer approves."],
                    evidence=[
                        {
                            "type": "worker_result",
                            "result": {"status": "completed", "tests_failed": []},
                        }
                    ],
                ),
                TaskNode(
                    id="T023",
                    title="Record delivery evidence",
                    description="Record evidence.",
                    type="release",
                    assigned_agent="release",
                    status="completed",
                    completion_criteria=["Delivery evidence is recorded."],
                    evidence=[
                        {
                            "type": "ci_result",
                            "result": {"status": "completed"},
                        }
                    ],
                ),
            ]
        )
        state.github = {"commit": "local-evidence", "pull_request_url": "local-delivery"}
        state.repository["requirement_coverage"] = {
            "coverage_score": 0.8689,
            "missing_must_requirement_ids": [],
            "partial_must_requirement_ids": [],
        }

        result = Evaluator().evaluate(state)

        self.assertTrue(result.done)
        self.assertGreaterEqual(result.final_score, 0.85)
        self.assertEqual(result.dimension_scores["spec_alignment"], 0.8689)
        self.assertEqual(result.dimension_scores["risk_quality"], 1.0)

    def test_evaluator_ignores_completed_debug_historical_failures(self) -> None:
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
                    "result": {"status": "completed", "tests_failed": [], "known_issues": []},
                },
            )
        state.task_graph.nodes.append(
            TaskNode(
                id="T002-DEBUG-1",
                title="Debug T002",
                description="Diagnose historical environment failure.",
                type="debug",
                assigned_agent="debug",
                status="completed",
                evidence=[
                    {
                        "type": "worker_result",
                        "summary": "diagnosed",
                        "result": {
                            "status": "completed",
                            "tests_passed": ["go test ./... passed after redirecting Go telemetry/cache paths"],
                            "tests_failed": ["Initial go test failed because host Go cache path was not writable."],
                            "known_issues": ["The host Go cache is not writable; workspace-local paths are required."],
                        },
                    }
                ],
            )
        )
        state.github = {"commit": "abc123", "pull_request_url": "https://example.test/pr/1"}

        result = Evaluator().evaluate(state)

        self.assertTrue(result.done)
        self.assertNotIn("Required tests are failing.", result.hard_failures)

    def test_evaluator_ignores_completed_release_dry_run_test_fields(self) -> None:
        engine = TaskGraphEngine()
        with temp_project_dir() as tmp_dir:
            manager = StateManager(Path(tmp_dir) / "state.json")
            state = manager.initialize("objective", engine)

        for node in state.task_graph.nodes:
            result = {"status": "completed", "tests_failed": [], "known_issues": []}
            if node.type == "release":
                result = {
                    "status": "recorded",
                    "tests_passed": ["Dry-run GitHub execution evidence recorded."],
                    "tests_failed": ["Dry-run delivery did not push a real branch or wait for live CI."],
                    "known_issues": ["Dry-run delivery remains local evidence only."],
                    "followups": ["Push a PR when real delivery mode is enabled."],
                }
            engine.mark_completed(
                state.task_graph,
                node.id,
                {
                    "type": "worker_result",
                    "summary": "done",
                    "result": result,
                },
            )
        state.github = {"commit": "abc123", "pull_request_url": "dry-run://pr/1"}

        result = Evaluator().evaluate(state)

        self.assertTrue(result.done)
        self.assertNotIn("Required tests are failing.", result.hard_failures)
        self.assertEqual(result.dimension_scores["risk_quality"], 1.0)

    def test_evaluator_does_not_apply_static_web_gate_to_unknown_artifact_profile(self) -> None:
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
        state.repository["artifact_report"] = {
            "artifact_profile": {"name": "unknown"},
            "static_verification": {
                "status": "failed",
                "tests_failed": ["Protected terms found in generated artifact: toad"],
            },
        }

        result = Evaluator().evaluate(state)

        self.assertTrue(result.done)
        self.assertNotIn("Static artifact verification failed.", result.hard_failures)

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

    def test_evaluator_blocks_partial_must_requirement_coverage(self) -> None:
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
            "coverage_score": 0.85,
            "missing_must_requirement_ids": [],
            "partial_must_requirement_ids": ["REQ-002"],
        }

        result = Evaluator().evaluate(state)

        self.assertFalse(result.done)
        self.assertIn("REQ-002", " ".join(result.hard_failures))

    def test_evaluator_blocks_failed_artifact_probe(self) -> None:
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
        state.repository["artifact_report"] = {
            "artifact_profile": {"name": "static_web_app"},
            "browser_verification": {
                "status": "failed",
                "scenario_probe": {"status": "failed"},
            },
        }

        result = Evaluator().evaluate(state)

        self.assertFalse(result.done)
        self.assertIn("Browser artifact verification failed.", result.hard_failures)
        self.assertIn("Acceptance scenario browser probe failed.", result.hard_failures)


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

    def test_inventory_tasks_are_read_only_even_with_relevant_files(self) -> None:
        with temp_project_dir() as tmp_dir:
            task = TaskNode(
                id="T006",
                title="Inventory Ent regeneration inputs",
                description="Checkpoint Ent inputs before regeneration.",
                type="backend",
                assigned_agent="backend",
                relevant_files=["backend/ent/generate.go", "backend/ent/schema/**", "backend/go.mod"],
                commands_to_run=[],
                boundary_mode="large_refactor",
            )
            state = RuntimeState(
                objective="Repair Billing Core schema phase.",
                task_graph=TaskGraph(graph_id="inventory-readonly", version=1, nodes=[task], dependencies=[]),
            )
            orchestrator = Orchestrator(StateManager(Path(tmp_dir) / ".alchemy" / "state.json"), repository_path=tmp_dir)

            worker_input = orchestrator._build_worker_input(state, task)

        self.assertEqual(worker_input.relevant_files, ["backend/ent/generate.go", "backend/ent/schema/**", "backend/go.mod"])
        self.assertEqual(worker_input.allowed_files, [])
        self.assertTrue(any("read-only inventory/checkpoint task" in item for item in worker_input.constraints))
        self.assertFalse(any("implement cross-module changes" in item for item in worker_input.constraints))

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

    def test_failed_task_interrupts_current_ready_batch_for_debug(self) -> None:
        class FailingFirstWorker:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
                self.calls.append(worker_input.task_id)
                if worker_input.task_id == "T001":
                    return CodexWorkerResult(
                        task_id=worker_input.task_id,
                        status="partial",
                        summary="needs focused repair before adjacent work continues",
                        known_issues=["repair required"],
                    )
                return CodexWorkerResult(
                    task_id=worker_input.task_id,
                    status="completed",
                    summary="completed",
                    tests_passed=["ok"],
                )

        graph = TaskGraph(
            graph_id="debug-priority",
            version=1,
            nodes=[
                TaskNode(id="T001", title="First implementation", description="First", type="frontend", assigned_agent="frontend", priority=90),
                TaskNode(id="T002", title="Adjacent implementation", description="Second", type="frontend", assigned_agent="frontend", priority=80),
            ],
        )
        worker = FailingFirstWorker()

        with temp_project_dir() as tmp_dir:
            state = Orchestrator(
                StateManager(Path(tmp_dir) / ".alchemy" / "state.json"),
                worker=worker,  # type: ignore[arg-type]
                repository_path=tmp_dir,
            ).run("repair before adjacent work", initial_state=RuntimeState(objective="repair before adjacent work", task_graph=graph), max_iterations=1)

        nodes = {node.id: node for node in state.task_graph.nodes}
        self.assertEqual(worker.calls, ["T001"])
        self.assertIn("T001-DEBUG-1", nodes)
        self.assertEqual(nodes["T001-DEBUG-1"].status, "pending")
        self.assertEqual(nodes["T002"].status, "ready")

    def test_partial_result_hands_off_downstream_scoped_blocker(self) -> None:
        class RepositoryThenServiceWorker:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
                self.calls.append(worker_input.task_id)
                if worker_input.task_id == "T004":
                    return CodexWorkerResult(
                        task_id=worker_input.task_id,
                        status="partial",
                        summary="Repository compile is still blocked by service code outside allowed_files.",
                        files_changed=[
                            "backend/internal/repository/group_repo.go",
                            "backend/internal/domain/table_contract.go",
                        ],
                        tests_passed=["go test ./internal/domain -run '^$'"],
                        tests_failed=["go test ./internal/repository -run '^$'"],
                        known_issues=[
                            "internal/service/payment_config_plans.go still references removed ent.Group fields.",
                        ],
                        follow_up_tasks=[
                            "Update internal/service/payment_config_plans.go in the service repair task.",
                        ],
                    )
                return CodexWorkerResult(
                    task_id=worker_input.task_id,
                    status="completed",
                    summary="service scope completed",
                    tests_passed=["go test ./internal/service -run '^$'"],
                )

        graph = TaskGraph(
            graph_id="partial-downstream-handoff",
            version=1,
            nodes=[
                TaskNode(
                    id="T003",
                    title="Repair Ent schema",
                    description="Already completed.",
                    type="integration",
                    assigned_agent="backend",
                    status="completed",
                ),
                TaskNode(
                    id="T004",
                    title="Repair domain and repository",
                    description="Repair repository callers only.",
                    type="integration",
                    assigned_agent="backend",
                    dependencies=["T003"],
                    relevant_files=["backend/internal/domain/**", "backend/internal/repository/**"],
                    boundary_mode="large_refactor",
                ),
                TaskNode(
                    id="T005",
                    title="Repair service handler server",
                    description="Repair service callers after repository contracts change.",
                    type="integration",
                    assigned_agent="backend",
                    dependencies=["T004"],
                    relevant_files=[
                        "backend/internal/service/**",
                        "backend/internal/handler/**",
                        "backend/internal/server/**",
                    ],
                    boundary_mode="large_refactor",
                ),
            ],
        )
        worker = RepositoryThenServiceWorker()

        with temp_project_dir() as tmp_dir:
            state = Orchestrator(
                StateManager(Path(tmp_dir) / ".alchemy" / "state.json"),
                worker=worker,  # type: ignore[arg-type]
                repository_path=tmp_dir,
            ).run(
                "repair final backend contracts",
                initial_state=RuntimeState(
                    objective="repair final backend contracts",
                    task_graph=graph,
                    completed_tasks=["T003"],
                ),
                max_iterations=2,
            )

        nodes = {node.id: node for node in state.task_graph.nodes}
        self.assertEqual(worker.calls, ["T004", "T005"])
        self.assertEqual(nodes["T004"].status, "completed")
        self.assertEqual(nodes["T005"].status, "completed")
        self.assertNotIn("T004-DEBUG-1", nodes)
        self.assertFalse(state.failed_tasks)
        handoff_result = nodes["T004"].evidence[-1]["result"]
        self.assertEqual(handoff_result["status"], "completed")
        self.assertEqual(handoff_result["original_status"], "partial")
        self.assertEqual(handoff_result["tests_failed"], [])
        self.assertEqual(handoff_result["partial_handoff_to"], ["T005"])
        self.assertIn("tests_deferred_to_downstream", handoff_result)
        self.assertEqual(handoff_result["handoff_original_result"]["status"], "partial")
        self.assertTrue(any(event["type"] == "task_partial_handed_off" for event in state.iteration_history))

    def test_partial_result_without_downstream_scope_still_creates_debug_task(self) -> None:
        class RepositoryOnlyPartialWorker:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
                self.calls.append(worker_input.task_id)
                return CodexWorkerResult(
                    task_id=worker_input.task_id,
                    status="partial",
                    summary="Repository compile still fails within repository files.",
                    files_changed=["backend/internal/repository/group_repo.go"],
                    tests_failed=["go test ./internal/repository -run '^$'"],
                    known_issues=[
                        "backend/internal/repository/group_repo.go still has a repository-scoped compile error.",
                    ],
                )

        graph = TaskGraph(
            graph_id="partial-stays-debuggable",
            version=1,
            nodes=[
                TaskNode(
                    id="T004",
                    title="Repair domain and repository",
                    description="Repair repository callers.",
                    type="integration",
                    assigned_agent="backend",
                    relevant_files=["backend/internal/domain/**", "backend/internal/repository/**"],
                    boundary_mode="large_refactor",
                ),
                TaskNode(
                    id="T005",
                    title="Repair service handler server",
                    description="Repair service callers later.",
                    type="integration",
                    assigned_agent="backend",
                    dependencies=["T004"],
                    relevant_files=[
                        "backend/internal/service/**",
                        "backend/internal/handler/**",
                        "backend/internal/server/**",
                    ],
                    boundary_mode="large_refactor",
                ),
            ],
        )
        worker = RepositoryOnlyPartialWorker()

        with temp_project_dir() as tmp_dir:
            state = Orchestrator(
                StateManager(Path(tmp_dir) / ".alchemy" / "state.json"),
                worker=worker,  # type: ignore[arg-type]
                repository_path=tmp_dir,
            ).run(
                "repair final backend contracts",
                initial_state=RuntimeState(objective="repair final backend contracts", task_graph=graph),
                max_iterations=1,
            )

        nodes = {node.id: node for node in state.task_graph.nodes}
        self.assertEqual(worker.calls, ["T004"])
        self.assertEqual(nodes["T004"].status, "pending")
        self.assertIn("T004", state.failed_tasks)
        self.assertIn("T004-DEBUG-1", nodes)
        self.assertEqual(nodes["T004-DEBUG-1"].status, "pending")

    def test_partial_result_raw_timeout_instruction_does_not_record_timeout_blocker(self) -> None:
        class PartialWithTimeoutInstructionWorker:
            def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
                return CodexWorkerResult(
                    task_id=worker_input.task_id,
                    status="partial",
                    summary="Implementation still needs a focused retry.",
                    files_changed=["backend/internal/service/payment_config_plans.go"],
                    known_issues=["A repository caller still needs alignment."],
                    raw_output=(
                        "Prompt context: Worker timeout is a stop boundary; if a task exceeds the configured "
                        "worker budget, record a blocker."
                    ),
                )

        graph = TaskGraph(
            graph_id="partial-raw-timeout-instruction",
            version=1,
            nodes=[
                TaskNode(
                    id="T005",
                    title="Repair service handler server",
                    description="Repair service callers.",
                    type="integration",
                    assigned_agent="backend",
                    relevant_files=["backend/internal/service/**"],
                    boundary_mode="large_refactor",
                )
            ],
        )

        with temp_project_dir() as tmp_dir:
            state = Orchestrator(
                StateManager(Path(tmp_dir) / ".alchemy" / "state.json"),
                worker=PartialWithTimeoutInstructionWorker(),  # type: ignore[arg-type]
                repository_path=tmp_dir,
            ).run(
                "repair final backend contracts",
                initial_state=RuntimeState(objective="repair final backend contracts", task_graph=graph),
                max_iterations=1,
            )

        nodes = {node.id: node for node in state.task_graph.nodes}
        self.assertFalse(state.blockers)
        self.assertIn("T005-DEBUG-1", nodes)
        self.assertEqual(nodes["T005-DEBUG-1"].status, "pending")
        self.assertFalse(any(event["type"] == "worker_timeout_blocker" for event in state.iteration_history))

    def test_worker_timeout_records_blocker_without_debug_task(self) -> None:
        class TimeoutWorker:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
                self.calls.append(worker_input.task_id)
                if worker_input.task_id == "T001":
                    return CodexWorkerResult(
                        task_id=worker_input.task_id,
                        status="completed",
                        summary="planning completed",
                        tests_passed=["planning"],
                        confidence=0.9,
                    )
                return CodexWorkerResult(
                    task_id=worker_input.task_id,
                    status="failed",
                    summary="Codex worker timed out after 600 seconds.",
                    worker_lifecycle={
                        "task_id": worker_input.task_id,
                        "status": "timed_out",
                        "timeout_seconds": 600,
                    },
                )

        worker = TimeoutWorker()
        with temp_project_dir() as tmp_dir:
            state = Orchestrator(
                StateManager(Path(tmp_dir) / ".alchemy" / "state.json"),
                worker=worker,  # type: ignore[arg-type]
                repository_path=tmp_dir,
            ).run("build a todo app with login", reset=True, max_iterations=5)

        nodes = {node.id: node for node in state.task_graph.nodes}
        self.assertEqual(worker.calls, ["T001", "T002"])
        self.assertNotIn("T002-DEBUG-1", nodes)
        self.assertEqual(nodes["T002"].status, "failed")
        self.assertEqual(state.failed_tasks, ["T002"])
        self.assertEqual(state.blockers[0]["id"], "B-T002-1")
        self.assertFalse(state.blockers[0]["can_continue_partially"])
        self.assertTrue(any(event["type"] == "worker_timeout_blocker" for event in state.iteration_history))

    def test_debug_timeout_blocks_parent_without_replaying_original_task(self) -> None:
        class DebugTimeoutWorker:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
                self.calls.append(worker_input.task_id)
                return CodexWorkerResult(
                    task_id=worker_input.task_id,
                    status="failed",
                    summary="Codex worker timed out after 600 seconds.",
                    worker_lifecycle={
                        "task_id": worker_input.task_id,
                        "status": "timed_out",
                        "timeout_seconds": 600,
                    },
                )

        graph = TaskGraphEngine().create_default_graph("complete every documented roadmap phase")
        engine = TaskGraphEngine()
        engine.mark_completed(graph, "T001", {"type": "worker_result", "result": {"status": "completed"}})
        implementation = engine.get_node(graph, "T002")
        implementation.status = "failed"
        implementation.retry_count = 1
        graph.nodes.append(
            TaskNode(
                id="T002-DEBUG-1",
                title="Debug T002",
                description="Diagnose original T002 worker timeout.",
                type="debug",
                assigned_agent="debug",
                status="pending",
                priority=110,
            )
        )
        initial_state = RuntimeState(objective="complete roadmap", task_graph=graph)
        initial_state.completed_tasks = ["T001"]
        initial_state.failed_tasks = ["T002"]

        worker = DebugTimeoutWorker()
        with temp_project_dir() as tmp_dir:
            state = Orchestrator(
                StateManager(Path(tmp_dir) / ".alchemy" / "state.json"),
                worker=worker,  # type: ignore[arg-type]
                repository_path=tmp_dir,
            ).run("complete roadmap", initial_state=initial_state, max_iterations=5)

        nodes = {node.id: node for node in state.task_graph.nodes}
        self.assertEqual(worker.calls, ["T002-DEBUG-1"])
        self.assertEqual(nodes["T002-DEBUG-1"].status, "skipped")
        self.assertEqual(nodes["T002"].status, "blocked")
        self.assertIn("T002", state.failed_tasks)
        self.assertEqual(state.blockers[0]["id"], "B-T002-1")
        self.assertFalse(state.blockers[0]["can_continue_partially"])
        self.assertTrue(any(event["type"] == "worker_timeout_blocker" for event in state.iteration_history))

    def test_non_partial_blocker_stops_current_ready_batch(self) -> None:
        class BlockingFirstWorker:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
                self.calls.append(worker_input.task_id)
                if worker_input.task_id == "T001":
                    return CodexWorkerResult(
                        task_id=worker_input.task_id,
                        status="partial",
                        summary="requires manual resolution before adjacent work can continue",
                        known_issues=["manual resolution required"],
                    )
                return CodexWorkerResult(
                    task_id=worker_input.task_id,
                    status="completed",
                    summary="completed",
                    tests_passed=["ok"],
                )

        graph = TaskGraph(
            graph_id="non-partial-blocker",
            version=1,
            nodes=[
                TaskNode(
                    id="T001",
                    title="Blocking implementation",
                    description="First",
                    type="frontend",
                    assigned_agent="frontend",
                    priority=90,
                    max_attempts=1,
                ),
                TaskNode(
                    id="T002",
                    title="Adjacent implementation",
                    description="Second",
                    type="frontend",
                    assigned_agent="frontend",
                    priority=80,
                ),
            ],
        )
        worker = BlockingFirstWorker()

        with temp_project_dir() as tmp_dir:
            state = Orchestrator(
                StateManager(Path(tmp_dir) / ".alchemy" / "state.json"),
                worker=worker,  # type: ignore[arg-type]
                repository_path=tmp_dir,
            ).run(
                "stop after blocking failure",
                initial_state=RuntimeState(objective="stop after blocking failure", task_graph=graph),
                max_iterations=1,
            )

        nodes = {node.id: node for node in state.task_graph.nodes}
        self.assertEqual(worker.calls, ["T001"])
        self.assertEqual(nodes["T001"].status, "failed")
        self.assertEqual(nodes["T002"].status, "ready")
        self.assertEqual(state.failed_tasks, ["T001"])
        self.assertEqual(state.blockers[0]["id"], "B-T001-1")
        self.assertTrue(any(event["type"] == "run_blocked" for event in state.iteration_history))

    def test_existing_non_partial_blocker_stops_before_dispatch(self) -> None:
        class RecordingWorker:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
                self.calls.append(worker_input.task_id)
                return CodexWorkerResult(
                    task_id=worker_input.task_id,
                    status="completed",
                    summary="completed",
                    tests_passed=["ok"],
                )

        graph = TaskGraph(
            graph_id="existing-non-partial-blocker",
            version=1,
            nodes=[
                TaskNode(
                    id="T001",
                    title="Ready implementation",
                    description="Should not dispatch while a manual blocker is present.",
                    type="backend",
                    assigned_agent="backend",
                    priority=90,
                    status="ready",
                )
            ],
        )
        worker = RecordingWorker()

        with temp_project_dir() as tmp_dir:
            state = Orchestrator(
                StateManager(Path(tmp_dir) / ".alchemy" / "state.json"),
                worker=worker,  # type: ignore[arg-type]
                repository_path=tmp_dir,
            ).run(
                "stop before dispatch",
                initial_state=RuntimeState(
                    objective="stop before dispatch",
                    task_graph=graph,
                    blockers=[
                        {
                            "id": "B-MANUAL",
                            "type": "technical_limit",
                            "description": "Manual resolution is required.",
                            "required_resolution": "Inspect before continuing.",
                            "task_ids": ["T000"],
                            "can_continue_partially": False,
                        }
                    ],
                ),
                max_iterations=1,
            )

        self.assertEqual(worker.calls, [])
        self.assertEqual(state.task_graph.nodes[0].status, "ready")
        self.assertTrue(any(event["type"] == "run_blocked" for event in state.iteration_history))

    def test_failed_debug_task_resets_parent_without_nested_debug_loop(self) -> None:
        class DebugPartialThenRetryWorker:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
                self.calls.append(worker_input.task_id)
                if worker_input.task_id == "T002" and self.calls.count("T002") == 1:
                    return CodexWorkerResult(
                        task_id=worker_input.task_id,
                        status="failed",
                        summary="implementation needs repair",
                        tests_failed=["unit tests"],
                    )
                if worker_input.task_id == "T002-DEBUG-1":
                    return CodexWorkerResult(
                        task_id=worker_input.task_id,
                        status="partial",
                        summary="diagnosed but did not complete repair",
                        known_issues=["retry the parent implementation with the new evidence"],
                    )
                return CodexWorkerResult(
                    task_id=worker_input.task_id,
                    status="completed",
                    summary="completed",
                    tests_passed=["unit tests"],
                    confidence=0.9,
                )

        worker = DebugPartialThenRetryWorker()

        with temp_project_dir() as tmp_dir:
            state = Orchestrator(
                StateManager(Path(tmp_dir) / ".alchemy" / "state.json"),
                worker=worker,  # type: ignore[arg-type]
                repository_path=tmp_dir,
            ).run("build a todo app with login", reset=True, max_iterations=10)

        nodes = {node.id: node for node in state.task_graph.nodes}
        self.assertTrue(state.done)
        self.assertIn("T002-DEBUG-1", nodes)
        self.assertEqual(nodes["T002-DEBUG-1"].status, "skipped")
        self.assertEqual(nodes["T002"].status, "completed")
        self.assertNotIn("T002-DEBUG-1-DEBUG-1", nodes)
        self.assertNotIn("T002-DEBUG-1-DEBUG-1", worker.calls)

    def test_debug_environment_blocker_blocks_parent_without_retry(self) -> None:
        class NoWorkerShouldRun:
            def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
                raise AssertionError(f"worker should not run for {worker_input.task_id}")

        graph = TaskGraphEngine().create_default_graph("repair frontend verification setup")
        engine = TaskGraphEngine()
        engine.mark_completed(graph, "T001", {"type": "worker_result", "result": {"status": "completed"}})
        implementation = engine.get_node(graph, "T002")
        implementation.status = "failed"
        implementation.retry_count = 1
        graph.nodes.append(
            TaskNode(
                id="T002-DEBUG-1",
                title="Debug T002",
                description="Diagnose missing frontend dependencies.",
                type="debug",
                assigned_agent="debug",
                status="pending",
                priority=110,
                retry_count=1,
                evidence=[
                    {
                        "type": "worker_result",
                        "result": {
                            "task_id": "T002-DEBUG-1",
                            "status": "partial",
                            "summary": "Frontend test runner unavailable because node_modules is missing.",
                            "tests_failed": [
                                "vitest is not recognized as an internal or external command.",
                            ],
                            "known_issues": [
                                "frontend dependencies are absent; install dependencies before retrying implementation.",
                            ],
                            "follow_up_tasks": [
                                "Run pnpm --dir frontend install --frozen-lockfile before frontend tests.",
                            ],
                        },
                    }
                ],
            )
        )
        initial_state = RuntimeState(objective="repair frontend verification setup", task_graph=graph)
        initial_state.completed_tasks = ["T001"]
        initial_state.failed_tasks = ["T002", "T002-DEBUG-1"]

        with temp_project_dir() as tmp_dir:
            state = Orchestrator(
                StateManager(Path(tmp_dir) / "state.json"),
                repository_path=tmp_dir,
                worker=NoWorkerShouldRun(),  # type: ignore[arg-type]
            ).run("repair frontend verification setup", initial_state=initial_state, max_iterations=1)

        nodes = {node.id: node for node in state.task_graph.nodes}
        self.assertFalse(state.done)
        self.assertEqual(nodes["T002"].status, "blocked")
        self.assertEqual(nodes["T002-DEBUG-1"].status, "skipped")
        self.assertEqual(state.blockers[0]["type"], "environment")
        self.assertIn("dependency setup succeeds", state.blockers[0]["description"])
        self.assertTrue(any(event["type"] == "debug_environment_blocker" for event in state.iteration_history))

    def test_worker_usage_limit_blocks_without_debug_retry(self) -> None:
        class UsageLimitWorker:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
                self.calls.append(worker_input.task_id)
                return CodexWorkerResult(
                    task_id=worker_input.task_id,
                    status="blocked",
                    summary="Codex CLI usage limit reached: You've hit your usage limit; try again at 5:39 PM.",
                    known_issues=["Local Codex CLI usage limit reached; wait for reset."],
                    raw_output="{\"type\":\"error\",\"message\":\"You've hit your usage limit.\"}",
                )

        graph = TaskGraph(
            graph_id="usage-limit-blocker",
            version=1,
            nodes=[
                TaskNode(
                    id="T001",
                    title="Implement when model is available",
                    description="Should block without spawning debug work.",
                    type="frontend",
                    assigned_agent="frontend",
                    priority=90,
                )
            ],
        )
        worker = UsageLimitWorker()

        with temp_project_dir() as tmp_dir:
            state = Orchestrator(
                StateManager(Path(tmp_dir) / ".alchemy" / "state.json"),
                worker=worker,  # type: ignore[arg-type]
                repository_path=tmp_dir,
            ).run(
                "stop on usage limit",
                initial_state=RuntimeState(objective="stop on usage limit", task_graph=graph),
                max_iterations=3,
            )

        self.assertEqual(worker.calls, ["T001"])
        self.assertEqual(len(state.task_graph.nodes), 1)
        self.assertEqual(state.task_graph.nodes[0].status, "blocked")
        self.assertEqual(state.blockers[0]["type"], "environment")
        self.assertIn("local Codex", state.blockers[0]["description"])
        self.assertFalse(any(event["type"] == "debug_task_created" for event in state.iteration_history))

    def test_worker_raw_usage_limit_context_does_not_become_environment_blocker(self) -> None:
        class HistoricalUsageLimitWorker:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
                self.calls.append(worker_input.task_id)
                raw_output = "\n".join(
                    [
                        json.dumps({"type": "thread.started", "thread_id": "thread-context"}),
                        json.dumps({"type": "turn.started"}),
                        json.dumps(
                            {
                                "type": "item.completed",
                                "item": {
                                    "type": "command_execution",
                                    "status": "completed",
                                    "aggregated_output": "historical repair note: Codex usage limit was resolved",
                                },
                            }
                        ),
                    ]
                )
                return CodexWorkerResult(
                    task_id=worker_input.task_id,
                    status="failed",
                    summary="implementation needs a normal debug pass",
                    tests_failed=["unit tests"],
                    raw_output=raw_output,
                    commands_run=[
                        CommandResult(
                            command="codex exec --json",
                            exit_code=0,
                            stdout=raw_output,
                            stderr="",
                        )
                    ],
                )

        graph = TaskGraph(
            graph_id="usage-limit-context",
            version=1,
            nodes=[
                TaskNode(
                    id="T001",
                    title="Implement after historical usage limit",
                    description="Mentioning old usage limits in raw command output is not an environment blocker.",
                    type="frontend",
                    assigned_agent="frontend",
                    priority=90,
                )
            ],
        )
        worker = HistoricalUsageLimitWorker()

        with temp_project_dir() as tmp_dir:
            state = Orchestrator(
                StateManager(Path(tmp_dir) / ".alchemy" / "state.json"),
                worker=worker,  # type: ignore[arg-type]
                repository_path=tmp_dir,
            ).run(
                "do not overclassify raw usage text",
                initial_state=RuntimeState(objective="do not overclassify raw usage text", task_graph=graph),
                max_iterations=1,
            )

        self.assertEqual(worker.calls, ["T001"])
        self.assertFalse(state.blockers)
        self.assertTrue(any(event["type"] == "debug_task_created" for event in state.iteration_history))

    def test_existing_nested_debug_chain_is_collapsed_to_parent_retry(self) -> None:
        class CompletingWorker:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
                self.calls.append(worker_input.task_id)
                return CodexWorkerResult(
                    task_id=worker_input.task_id,
                    status="completed",
                    summary="completed",
                    tests_passed=["unit tests"],
                    confidence=0.9,
                )

        graph = TaskGraphEngine().create_default_graph("complete every documented roadmap phase")
        engine = TaskGraphEngine()
        engine.mark_completed(graph, "T001", {"type": "worker_result", "result": {"status": "completed"}})
        implementation = engine.get_node(graph, "T002")
        implementation.status = "failed"
        implementation.retry_count = 1
        graph.nodes.extend(
            [
                TaskNode(
                    id="T002-DEBUG-1",
                    title="Debug T002",
                    description="First-level debug failed but was reset to ready during recovery.",
                    type="debug",
                    assigned_agent="debug",
                    status="ready",
                    priority=110,
                    retry_count=1,
                ),
                TaskNode(
                    id="T002-DEBUG-1-DEBUG-1",
                    title="Debug T002-DEBUG-1",
                    description="Nested debug should not run.",
                    type="debug",
                    assigned_agent="debug",
                    status="pending",
                    priority=120,
                ),
            ]
        )
        initial_state = RuntimeState(objective="complete roadmap", task_graph=graph)
        initial_state.completed_tasks = ["T001"]
        initial_state.failed_tasks = ["T002", "T002-DEBUG-1"]

        worker = CompletingWorker()
        with temp_project_dir() as tmp_dir:
            state = Orchestrator(
                StateManager(Path(tmp_dir) / "state.json"),
                repository_path=tmp_dir,
                worker=worker,  # type: ignore[arg-type]
            ).run("complete roadmap", initial_state=initial_state, max_iterations=8)

        nodes = {node.id: node for node in state.task_graph.nodes}
        self.assertTrue(state.done)
        self.assertEqual(nodes["T002"].status, "completed")
        self.assertEqual(nodes["T002-DEBUG-1"].status, "skipped")
        self.assertEqual(nodes["T002-DEBUG-1-DEBUG-1"].status, "skipped")
        self.assertNotIn("T002-DEBUG-1-DEBUG-1", worker.calls)

    def test_completed_nested_debug_evidence_promotes_failed_parent_and_continues(self) -> None:
        class CompletingWorker:
            def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
                return CodexWorkerResult(
                    task_id=worker_input.task_id,
                    status="completed",
                    summary="downstream task completed",
                    tests_passed=["python -m pytest target tests"],
                    evidence=["verification passed"],
                    confidence=0.9,
                )

        graph = TaskGraphEngine().create_default_graph("complete every documented roadmap phase")
        engine = TaskGraphEngine()
        engine.mark_completed(
            graph,
            "T001",
            {
                "type": "worker_result",
                "result": {
                    "status": "completed",
                    "tests_failed": [],
                    "tests_passed": ["planning"],
                    "confidence": 0.9,
                },
            },
        )
        implementation = engine.get_node(graph, "T002")
        implementation.status = "failed"
        implementation.retry_count = implementation.max_attempts
        implementation.evidence.append(
            {
                "type": "worker_result",
                "result": {
                    "status": "failed",
                    "summary": "Codex worker did not return parseable codex_worker_result_v1 JSON.",
                    "tests_failed": ["worker output parse"],
                    "confidence": 0.0,
                },
            }
        )
        graph.nodes.extend(
            [
                TaskNode(
                    id="T002-DEBUG-1",
                    title="Debug T002",
                    description="Diagnose original T002 worker failure.",
                    type="debug",
                    assigned_agent="debug",
                    status="completed",
                    evidence=[
                        {
                            "type": "worker_result",
                            "result": {
                                "task_id": "T002-DEBUG-1",
                                "status": "completed",
                                "summary": "The requested verification command passes, but this diagnostic had low confidence.",
                                "commands_run": [{"command": "python -m pytest target", "exit_code": 0}],
                                "tests_passed": ["python -m pytest target: passed"],
                                "tests_failed": [],
                                "known_issues": ["Non-fatal pytest cache warning."],
                                "confidence": 0.0,
                            },
                        }
                    ],
                ),
                TaskNode(
                    id="T002-DEBUG-1-DEBUG-1",
                    title="Debug T002-DEBUG-1",
                    description="Diagnose nested debug response-format failure.",
                    type="debug",
                    assigned_agent="debug",
                    status="completed",
                    evidence=[
                        {
                            "type": "worker_result",
                            "result": {
                                "task_id": "T002-DEBUG-1-DEBUG-1",
                                "status": "completed",
                                "summary": "Previous failure was a worker response-format issue; target verification passes.",
                                "commands_run": [{"command": "python -m pytest target", "exit_code": 0}],
                                "tests_passed": ["python -m pytest target: passed"],
                                "tests_failed": [],
                                "known_issues": ["Non-fatal pytest cache warning."],
                                "confidence": 0.94,
                            },
                        }
                    ],
                ),
            ]
        )
        initial_state = RuntimeState(objective="complete roadmap", task_graph=graph)
        initial_state.completed_tasks = ["T001", "T002-DEBUG-1", "T002-DEBUG-1-DEBUG-1"]
        initial_state.failed_tasks = ["T002"]
        initial_state.blockers = [
            {
                "id": "B-T002-2",
                "type": "technical_limit",
                "description": "Retry policy exhausted after 2 attempt(s): Codex worker did not return parseable codex_worker_result_v1 JSON.",
                "task_ids": ["T002"],
                "can_continue_partially": False,
            }
        ]

        with temp_project_dir() as tmp_dir:
            state = Orchestrator(
                StateManager(Path(tmp_dir) / "state.json"),
                repository_path=tmp_dir,
                worker=CompletingWorker(),  # type: ignore[arg-type]
            ).run("complete roadmap", initial_state=initial_state, max_iterations=8)

        nodes = {node.id: node for node in state.task_graph.nodes}
        self.assertTrue(state.done)
        self.assertEqual(nodes["T002"].status, "completed")
        self.assertEqual(nodes["T003"].status, "completed")
        self.assertEqual(nodes["T004"].status, "completed")
        self.assertEqual(nodes["T005"].status, "completed")
        self.assertFalse(state.failed_tasks)
        self.assertFalse(state.blockers)
        self.assertTrue(any(event["type"] == "debug_repair_promoted" for event in state.iteration_history))

    def test_debug_diagnosis_with_unfinished_repair_does_not_promote_parent(self) -> None:
        graph = TaskGraphEngine().create_default_graph("complete every documented roadmap phase")
        engine = TaskGraphEngine()
        engine.mark_completed(
            graph,
            "T001",
            {
                "type": "worker_result",
                "result": {"status": "completed", "tests_passed": ["planning"], "tests_failed": []},
            },
        )
        implementation = engine.get_node(graph, "T002")
        implementation.status = "failed"
        implementation.retry_count = implementation.max_attempts
        implementation.evidence.append(
            {
                "type": "worker_result",
                "result": {
                    "status": "partial",
                    "summary": "Backend slice was started but the implementation remains incomplete.",
                    "tests_failed": [],
                    "known_issues": ["The underlying large refactor remains incomplete and still needs a bounded backend implementation retry."],
                    "confidence": 0.76,
                },
            }
        )
        graph.nodes.append(
            TaskNode(
                id="T002-DEBUG-1",
                title="Debug T002",
                description="Diagnose original T002 worker timeout.",
                type="debug",
                assigned_agent="debug",
                status="completed",
                evidence=[
                    {
                        "type": "worker_result",
                        "result": {
                            "task_id": "T002-DEBUG-1",
                            "status": "completed",
                            "summary": "Recorded timeout diagnosis and retry repair instructions.",
                            "commands_run": [{"command": "static artifact inspection", "exit_code": 0}],
                            "tests_passed": ["Static artifact inspection completed."],
                            "tests_failed": [],
                            "known_issues": [
                                "The underlying large refactor remains incomplete and still needs a bounded backend implementation retry."
                            ],
                            "confidence": 0.87,
                        },
                    }
                ],
            )
        )
        initial_state = RuntimeState(objective="complete roadmap", task_graph=graph)
        initial_state.completed_tasks = ["T001", "T002-DEBUG-1"]
        initial_state.failed_tasks = ["T002"]

        with temp_project_dir() as tmp_dir:
            state = Orchestrator(
                StateManager(Path(tmp_dir) / "state.json"),
                repository_path=tmp_dir,
            ).run("complete roadmap", initial_state=initial_state, max_iterations=1)

        nodes = {node.id: node for node in state.task_graph.nodes}
        self.assertEqual(nodes["T002"].status, "failed")
        self.assertIn("T002", state.failed_tasks)
        self.assertFalse(any(event["type"] == "debug_repair_promoted" for event in state.iteration_history))

    def test_obsolete_debug_tasks_are_pruned_after_parent_completes(self) -> None:
        graph = TaskGraphEngine().create_default_graph("complete every documented roadmap phase")
        engine = TaskGraphEngine()
        engine.mark_completed(
            graph,
            "T001",
            {
                "type": "worker_result",
                "result": {"status": "completed", "tests_passed": ["planning"], "tests_failed": []},
            },
        )
        graph.nodes.extend(
            [
                TaskNode(
                    id="T001-DEBUG-1",
                    title="Debug T001",
                    description="Obsolete debug branch.",
                    type="debug",
                    assigned_agent="debug",
                    status="failed",
                ),
                TaskNode(
                    id="T001-DEBUG-1-DEBUG-1",
                    title="Debug T001-DEBUG-1",
                    description="Obsolete nested debug branch.",
                    type="debug",
                    assigned_agent="debug",
                    status="active",
                ),
            ]
        )
        state = RuntimeState(objective="complete roadmap", task_graph=graph)
        state.active_tasks = ["T001-DEBUG-1-DEBUG-1"]
        state.failed_tasks = ["T001-DEBUG-1"]

        with temp_project_dir() as tmp_dir:
            orchestrator = Orchestrator(StateManager(Path(tmp_dir) / "state.json"), repository_path=tmp_dir)
            changed = orchestrator._prune_obsolete_debug_tasks(state)

        nodes = {node.id: node for node in state.task_graph.nodes}
        self.assertTrue(changed)
        self.assertEqual(nodes["T001-DEBUG-1"].status, "skipped")
        self.assertEqual(nodes["T001-DEBUG-1-DEBUG-1"].status, "skipped")
        self.assertFalse(state.active_tasks)
        self.assertFalse(state.failed_tasks)
        self.assertTrue(any(event["type"] == "obsolete_debug_pruned" for event in state.iteration_history))

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

    def test_marker_file_controller_blocks_before_dispatching_worker(self) -> None:
        class CountingWorker:
            def __init__(self) -> None:
                self.calls = 0

            def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
                self.calls += 1
                return CodexWorkerResult(task_id=worker_input.task_id, status="completed", summary="done")

        with temp_project_dir() as tmp_dir:
            state_path = Path(tmp_dir) / ".alchemy" / "state.json"
            state_path.parent.mkdir(parents=True, exist_ok=True)
            (state_path.parent / "supervisor_stop.json").write_text(
                json.dumps({"reason": "pause for controller fix"}),
                encoding="utf-8",
            )
            worker = CountingWorker()
            orchestrator = Orchestrator(
                StateManager(state_path),
                worker=worker,  # type: ignore[arg-type]
                controller=MarkerFileExecutionController(state_path.parent),
                repository_path=tmp_dir,
            )

            state = orchestrator.run("build a todo app with login", reset=True)

            self.assertEqual(worker.calls, 0)
            self.assertFalse(state.done)
            self.assertEqual(state.blockers[0]["id"], "B-RUN-STOPPED")
            self.assertIn("pause for controller fix", state.blockers[0]["description"])

    def test_marker_file_controller_requests_running_worker_stop(self) -> None:
        with temp_project_dir() as tmp_dir:
            controller = MarkerFileExecutionController(tmp_dir)
            self.assertFalse(controller.should_stop_worker("T001"))
            (Path(tmp_dir) / "operator_stop.json").write_text("{}", encoding="utf-8")

            self.assertTrue(controller.should_stop_worker("T001"))

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

    def test_worker_inputs_expand_package_lockfile_boundaries(self) -> None:
        class CaptureWorker:
            def __init__(self) -> None:
                self.inputs: list[CodexWorkerInput] = []

            def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
                self.inputs.append(worker_input)
                return CodexWorkerResult(task_id=worker_input.task_id, status="completed", summary="done")

        with temp_project_dir() as tmp_dir:
            graph = TaskGraphEngine().create_default_graph("objective")
            implementation = next(node for node in graph.nodes if node.type == "backend")
            implementation.relevant_files = ["frontend/package.json"]
            worker = CaptureWorker()
            Orchestrator(
                StateManager(Path(tmp_dir) / "state.json"),
                worker=worker,  # type: ignore[arg-type]
                repository_path=tmp_dir,
            ).run("objective", reset=True, task_graph=graph, max_iterations=2)

        inputs = {item.task_id: item for item in worker.inputs}
        self.assertEqual(
            inputs[implementation.id].allowed_files,
            [
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
                "frontend/package-lock.json",
                "frontend/npm-shrinkwrap.json",
                "frontend/yarn.lock",
                "frontend/bun.lockb",
            ],
        )

    def test_repair_convergence_stops_remaining_ready_tasks_after_target_check_passes(self) -> None:
        class RepairWorker:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
                self.calls.append(worker_input.task_id)
                return CodexWorkerResult(
                    task_id=worker_input.task_id,
                    status="completed",
                    summary="fixed target file and tests pass",
                    files_changed=["app.py"],
                    tests_passed=["python -m unittest discover -s tests"],
                    evidence=["app.py repaired"],
                    confidence=0.95,
                )

        graph = TaskGraph(
            graph_id="repair-convergence",
            version=1,
            nodes=[
                TaskNode(
                    id="T001",
                    title="Fix app.py from feedback",
                    description="Repair app.py.",
                    type="debug",
                    assigned_agent="debug",
                    completion_criteria=["app.py is repaired and tests pass."],
                    relevant_files=["app.py"],
                    commands_to_run=["python -m unittest discover -s tests"],
                    priority=90,
                ),
                TaskNode(
                    id="T002",
                    title="Duplicate app.py repair",
                    description="Another same-file repair that should be covered by convergence.",
                    type="debug",
                    assigned_agent="debug",
                    completion_criteria=["app.py repair scope is covered."],
                    relevant_files=["app.py"],
                    commands_to_run=["python -m unittest discover -s tests"],
                    priority=80,
                ),
                TaskNode(
                    id="T003",
                    title="Review repair",
                    description="Review repair evidence.",
                    type="review",
                    assigned_agent="reviewer",
                    dependencies=["T002"],
                    completion_criteria=["Reviewer approval is recorded."],
                    priority=70,
                ),
                TaskNode(
                    id="T004",
                    title="Record local delivery evidence",
                    description="Record repair delivery evidence.",
                    type="release",
                    assigned_agent="reviewer",
                    dependencies=["T003"],
                    completion_criteria=["Delivery evidence is recorded."],
                    priority=60,
                ),
            ],
            dependencies=[
                Dependency(source="T002", target="T003", type="requires_review"),
                Dependency(source="T003", target="T004", type="requires_review"),
            ],
        )
        state = RuntimeState(objective="repair app", task_graph=graph)
        state.repository = {
            "provider": "local",
            "path": ".",
            "repair_convergence": {
                "enabled": True,
                "status": "pending",
                "target_files": ["app.py"],
                "source_run_id": "run_001",
            },
        }

        with temp_project_dir() as tmp_dir:
            worker = RepairWorker()
            final_state = Orchestrator(
                StateManager(Path(tmp_dir) / "state.json"),
                repository_path=tmp_dir,
                worker=worker,  # type: ignore[arg-type]
            ).run("repair app", reset=True, initial_state=state, max_iterations=3)

        self.assertEqual(worker.calls, ["T001"])
        self.assertTrue(final_state.done)
        self.assertEqual(final_state.repository["repair_convergence"]["status"], "completed")
        self.assertEqual(final_state.repository["repair_convergence"]["trigger_task_id"], "T001")
        self.assertEqual([node.status for node in final_state.task_graph.nodes], ["completed"] * 4)
        self.assertEqual(final_state.iteration_history[-2]["type"], "repair_convergence_gate")
        self.assertTrue(str(final_state.github["pull_request_url"]).startswith("dry-run://repair-convergence/"))

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
            (repo / "docs").mkdir()
            (repo / "docs" / "probe.md").write_text("probe\n", encoding="utf-8")
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
        self.assertEqual(worker.calls, [])
        nodes = {node.id: node for node in state.task_graph.nodes}
        self.assertEqual(nodes["T001"].evidence[-1]["result"]["commands_run"][0]["command"], "static document inspection")
        self.assertEqual(nodes["T002"].evidence[-1]["result"]["commands_run"][0]["command"], "static document inspection")
        self.assertEqual(nodes["T003"].evidence[-1]["result"]["status"], "completed")

    def test_documentation_static_document_task_runs_without_worker(self) -> None:
        class FailingWorker:
            calls: list[str] = []

            def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
                self.calls.append(worker_input.task_id)
                return CodexWorkerResult(
                    task_id=worker_input.task_id,
                    status="failed",
                    summary="worker should not be called",
                    tests_failed=["worker called"],
                )

        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "docs").mkdir()
            (repo / "docs" / "PLAN.md").write_text("Phase 0 freeze evidence\n", encoding="utf-8")
            graph = TaskGraph(
                graph_id="doc-static",
                version=1,
                nodes=[
                    TaskNode(
                        id="T001",
                        title="Confirm docs",
                        description="Confirm docs freeze.",
                        type="documentation",
                        assigned_agent="architect",
                        completion_criteria=["Documentation evidence exists."],
                        relevant_files=["docs/**"],
                        commands_to_run=["static document inspection"],
                    ),
                    TaskNode(
                        id="T002",
                        title="Review docs",
                        description="Review docs",
                        type="review",
                        assigned_agent="reviewer",
                        dependencies=["T001"],
                        completion_criteria=["Reviewer approval is recorded."],
                    ),
                    TaskNode(
                        id="T003",
                        title="Release docs",
                        description="Record evidence",
                        type="release",
                        assigned_agent="reviewer",
                        dependencies=["T002"],
                        completion_criteria=["GitHub execution evidence is recorded."],
                    ),
                ],
                dependencies=[
                    Dependency(source="T001", target="T002", type="requires_review"),
                    Dependency(source="T002", target="T003", type="requires_review"),
                ],
            )
            worker = FailingWorker()
            state = Orchestrator(
                StateManager(repo / "state.json"),
                worker=worker,  # type: ignore[arg-type]
                repository_path=repo,
            ).run("doc static", reset=True, task_graph=graph, max_iterations=4)

        self.assertTrue(state.done)
        self.assertEqual(worker.calls, [])
        nodes = {node.id: node for node in state.task_graph.nodes}
        self.assertEqual(nodes["T001"].status, "completed")
        self.assertEqual(nodes["T001"].evidence[-1]["result"]["commands_run"][0]["command"], "static document inspection")

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

    def test_static_document_verification_expands_doc_globs(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "docs").mkdir()
            (repo / "docs" / "PLAN.md").write_text("Phase 0 freeze evidence\n", encoding="utf-8")
            task = TaskNode(
                id="T001",
                title="Verify docs glob",
                description="Verify docs glob evidence.",
                type="test",
                assigned_agent="test",
                completion_criteria=["Documentation evidence exists."],
                relevant_files=["docs/**"],
                commands_to_run=["static document inspection"],
            )
            result = Orchestrator(StateManager(repo / "state.json"), repository_path=repo)._static_document_result(task)

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.tests_failed, [])
        self.assertIn("Found required file: docs\\PLAN.md", "\n".join(result.evidence))

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
                window.__ALCHEMY_GAME_TEST__ = {
                  snapshot() { return { player_x: 0, player_y: 0, state: "playing", won: false }; },
                  step(dt) {},
                  advanceToVictory() { return { won: true }; },
                  restart() {}
                };
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

    def test_static_artifact_verifier_rejects_canvas_game_without_gameplay_probe_hook(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "index.html").write_text(
                """
                <!doctype html>
                <canvas id="game"></canvas>
                <script>
                const level = { tiles: [], player: {}, enemy: {}, coin: {}, flag: {} };
                function physics() {}
                function collision() {}
                document.addEventListener("keydown", () => {});
                requestAnimationFrame(function frame(){ requestAnimationFrame(frame); });
                </script>
                """,
                encoding="utf-8",
            )

            result = StaticWebArtifactVerifier().verify(repo, ["index.html"])

        self.assertEqual(result.status, "failed")
        self.assertIn("__ALCHEMY_GAME_TEST__", "\n".join(result.tests_failed))

    def test_static_artifact_verifier_skips_non_web_project_profiles(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "package.json").write_text('{"scripts":{"test":"node test.js"}}\n', encoding="utf-8")

            result = StaticWebArtifactVerifier().verify(repo, ["index.html"])

        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.profile["name"], "node_project")
        self.assertFalse(result.tests_failed)

    def test_static_artifact_verifier_skips_unknown_large_backend_profile(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "backend" / "internal").mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.test/billing-core\n", encoding="utf-8")
            (repo / "backend" / "internal" / "service.go").write_text("package internal\nconst Name = \"toad\"\n", encoding="utf-8")

            result = StaticWebArtifactVerifier().verify(repo, ["backend/**"])

        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.profile["name"], "unknown")
        self.assertFalse(result.tests_failed)

    def test_static_artifact_verifier_expands_python_glob_artifact_scope(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            app = repo / "alchemy_creative_agent_3_0" / "app"
            tests = repo / "alchemy_creative_agent_3_0" / "tests"
            docs = repo / "alchemy_creative_agent_3_0" / "docs"
            app.mkdir(parents=True)
            tests.mkdir(parents=True)
            docs.mkdir(parents=True)
            (app / "__init__.py").write_text("", encoding="utf-8")
            (app / "core.py").write_text("class CentralCreativeBrain: pass\n", encoding="utf-8")
            (tests / "test_core.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
            (docs / "README.md").write_text("# V3 docs\n", encoding="utf-8")

            result = StaticWebArtifactVerifier().verify(
                repo,
                [
                    "alchemy_creative_agent_3_0/**",
                    "alchemy_creative_agent_3_0/app/**",
                ],
            )

        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.profile["name"], "python_project")
        self.assertFalse(result.tests_failed)
        self.assertNotIn("Missing artifact file", "\n".join(result.tests_failed))

    def test_static_artifact_verifier_accepts_form_based_static_web_app(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "index.html").write_text(
                """
                <!doctype html>
                <main id="app">
                  <form>
                    <label>Todo <input name="todo"></label>
                    <button type="button">Add Todo</button>
                  </form>
                  <section id="todos"></section>
                </main>
                """,
                encoding="utf-8",
            )

            result = StaticWebArtifactVerifier().verify(repo, ["index.html"], requirements=["Build a todo form app"])

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.profile["name"], "static_web_app")
        self.assertIn("Static web app interactive controls are present.", result.evidence)

    def test_static_artifact_verifier_ignores_unmatched_globs_and_game_terms_for_crm_app(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "index.html").write_text(
                """
                <!doctype html>
                <main id="app">Toad risk dashboard</main>
                """,
                encoding="utf-8",
            )
            src = repo / "src"
            src.mkdir()
            (src / "Dashboard.vue").write_text("<template><canvas id='risk-score'></canvas></template>\n", encoding="utf-8")

            result = StaticWebArtifactVerifier().verify(
                repo,
                ["index.html", "src/**", "src/views/*Payment*.vue"],
                objective="Build a CRM billing and risk score dashboard.",
            )

        self.assertEqual(result.profile["name"], "static_web_app")
        self.assertEqual(result.status, "completed")
        failures = "\n".join(result.tests_failed)
        self.assertNotIn("Missing artifact file", failures)
        self.assertNotIn("Protected terms", failures)

    def test_artifact_profile_detector_classifies_common_projects(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "package.json").write_text('{"scripts":{"test":"node tests.js"}}\n', encoding="utf-8")

            profile = ArtifactProfileDetector().detect(repo, ["index.html"])

        self.assertEqual(profile.name, "node_project")

        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            frontend = repo / "frontend"
            frontend.mkdir()
            (frontend / "index.html").write_text('<!doctype html><div id="app"></div>\n', encoding="utf-8")

            profile = ArtifactProfileDetector().detect(
                repo,
                ["frontend/index.html"],
                objective="Build CRM billing, wallet ledger, invoice/payment, reconciliation, and analytics workflows.",
            )

        self.assertEqual(profile.name, "static_web_app")

        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "README.md").write_text("# Docs\n", encoding="utf-8")

            profile = ArtifactProfileDetector().detect(repo, ["README.md"])

        self.assertEqual(profile.name, "documentation_only")

    def test_artifact_profile_detector_does_not_treat_crm_frontend_metrics_as_game(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            frontend = repo / "frontend"
            (frontend / "src" / "views").mkdir(parents=True)
            (frontend / "index.html").write_text('<!doctype html><div id="app"></div>\n', encoding="utf-8")
            (frontend / "src" / "views" / "Dashboard.vue").write_text(
                """
                <template><canvas id="risk-score"></canvas></template>
                <script setup lang="ts">
                requestAnimationFrame(() => {
                  const score = 98
                  window.scrollTo({ top: score, behavior: 'smooth' })
                })
                </script>
                """,
                encoding="utf-8",
            )
            backend = repo / "backend" / "internal" / "service"
            backend.mkdir(parents=True)
            (backend / "risk_score_test.go").write_text(
                "package service\n\nfunc TestRiskScoreJump(t *testing.T) {}\n",
                encoding="utf-8",
            )

            profile = ArtifactProfileDetector().detect(
                repo,
                ["frontend/**", "backend/**"],
                objective="Build CRM billing, wallet ledger, invoice/payment, reconciliation, and analytics workflows.",
                requirements=["Admin users can query orders, configure payment providers, and inspect usage analytics."],
            )

        self.assertEqual(profile.name, "static_web_app")

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
                return {
                    "status": "completed",
                    "evidence": ["fake browser completed"],
                    "gameplay_probe": {
                        "status": "completed",
                        "tests_passed": ["Right movement changes player_x.", "Jump input changes player_y."],
                        "tests_failed": [],
                    },
                }

            result = BrowserArtifactRunner(fake_browser).verify(
                repo,
                ["index.html"],
                output_dir=repo / "evidence",
                profile_name="canvas_game",
            )

        self.assertEqual(result.status, "completed")
        self.assertGreater(result.pixel_diff["changed_pixels"], 0)
        self.assertIn("fake browser completed", result.evidence)
        self.assertEqual(result.gameplay_probe["status"], "completed")

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
                return {
                    "status": "completed",
                    "gameplay_probe": {
                        "status": "completed",
                        "tests_passed": ["Right movement changes player_x.", "Jump input changes player_y."],
                        "tests_failed": [],
                    },
                }

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

    def test_browser_artifact_runner_requires_gameplay_probe_for_canvas_games(self) -> None:
        from PIL import Image

        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "index.html").write_text("<!doctype html><canvas id='game'></canvas>", encoding="utf-8")

            def fake_browser(request: dict[str, object]) -> dict[str, object]:
                first = Path(str(request["initial_screenshot"]))
                second = Path(str(request["after_interaction_screenshot"]))
                initial = Image.new("RGB", (8, 8), "white")
                initial.putpixel((1, 1), (20, 20, 20))
                initial.save(first)
                image = Image.new("RGB", (8, 8), "white")
                image.putpixel((3, 3), (0, 0, 0))
                image.save(second)
                return {"status": "completed"}

            result = BrowserArtifactRunner(fake_browser).verify(
                repo,
                ["index.html"],
                output_dir=repo / "evidence",
                profile_name="canvas_game",
            )

        self.assertEqual(result.status, "failed")
        self.assertIn("gameplay probe", "\n".join(result.tests_failed))

    def test_browser_artifact_runner_fails_when_gameplay_probe_status_failed(self) -> None:
        from PIL import Image

        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "index.html").write_text("<!doctype html><canvas id='game'></canvas>", encoding="utf-8")

            def fake_browser(request: dict[str, object]) -> dict[str, object]:
                first = Path(str(request["initial_screenshot"]))
                second = Path(str(request["after_interaction_screenshot"]))
                initial = Image.new("RGB", (8, 8), "white")
                initial.putpixel((1, 1), (20, 20, 20))
                initial.save(first)
                image = Image.new("RGB", (8, 8), "white")
                image.putpixel((3, 3), (0, 0, 0))
                image.save(second)
                return {"status": "completed", "gameplay_probe": {"status": "failed"}}

            result = BrowserArtifactRunner(fake_browser).verify(
                repo,
                ["index.html"],
                output_dir=repo / "evidence",
                profile_name="canvas_game",
            )

        self.assertEqual(result.status, "failed")
        self.assertIn("Gameplay probe failed.", result.tests_failed)

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

    def test_browser_artifact_runner_records_static_web_semantic_probe(self) -> None:
        from PIL import Image

        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "index.html").write_text("<!doctype html><main id='app'><input><button>Add</button></main>", encoding="utf-8")

            def fake_browser(request: dict[str, object]) -> dict[str, object]:
                first = Path(str(request["initial_screenshot"]))
                second = Path(str(request["after_interaction_screenshot"]))
                image = Image.new("RGB", (6, 6), "white")
                image.putpixel((1, 1), (0, 0, 0))
                image.save(first)
                changed = Image.new("RGB", (6, 6), "white")
                changed.putpixel((2, 2), (0, 0, 0))
                changed.save(second)
                return {
                    "status": "completed",
                    "semantic_probe": {
                        "status": "completed",
                        "kind": "static_web_app",
                        "tests_passed": ["Static web controls are discoverable."],
                        "tests_failed": [],
                    },
                }

            result = BrowserArtifactRunner(fake_browser).verify(
                repo,
                ["index.html"],
                output_dir=repo / "evidence",
                profile_name="static_web_app",
            )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.semantic_probe["status"], "completed")
        self.assertIn("Static web controls are discoverable.", result.tests_passed)

    def test_browser_artifact_runner_passes_acceptance_scenarios_to_browser(self) -> None:
        from PIL import Image

        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "index.html").write_text("<!doctype html><main id='app'><input><button>Add</button></main>", encoding="utf-8")
            seen_scenarios: list[dict[str, object]] = []

            def fake_browser(request: dict[str, object]) -> dict[str, object]:
                seen_scenarios.extend(list(request.get("acceptance_scenarios", [])))  # type: ignore[arg-type]
                first = Path(str(request["initial_screenshot"]))
                second = Path(str(request["after_interaction_screenshot"]))
                image = Image.new("RGB", (6, 6), "white")
                image.putpixel((1, 1), (0, 0, 0))
                image.save(first)
                changed = Image.new("RGB", (6, 6), "white")
                changed.putpixel((2, 2), (0, 0, 0))
                changed.save(second)
                return {
                    "status": "completed",
                    "semantic_probe": {"status": "completed"},
                    "scenario_probe": {
                        "status": "completed",
                        "tests_passed": ["SCN-001: CRUD create controls are present."],
                        "tests_failed": [],
                    },
                }

            result = BrowserArtifactRunner(fake_browser).verify(
                repo,
                ["index.html"],
                output_dir=repo / "evidence",
                profile_name="static_web_app",
                acceptance_scenarios=[
                    {"id": "SCN-001", "kind": "crud", "required_behaviors": ["create"]},
                ],
            )

        self.assertEqual(seen_scenarios[0]["kind"], "crud")
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.scenario_probe["status"], "completed")
        self.assertIn("SCN-001: CRUD create controls are present.", result.tests_passed)

    def test_browser_artifact_runner_fails_when_static_web_semantic_probe_fails(self) -> None:
        from PIL import Image

        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "index.html").write_text("<!doctype html><main id='app'><button>Add</button></main>", encoding="utf-8")

            def fake_browser(request: dict[str, object]) -> dict[str, object]:
                first = Path(str(request["initial_screenshot"]))
                second = Path(str(request["after_interaction_screenshot"]))
                image = Image.new("RGB", (6, 6), "white")
                image.putpixel((1, 1), (0, 0, 0))
                image.save(first)
                image.save(second)
                return {"status": "completed", "semantic_probe": {"status": "failed"}}

            result = BrowserArtifactRunner(fake_browser).verify(
                repo,
                ["index.html"],
                output_dir=repo / "evidence",
                profile_name="static_web_app",
            )

        self.assertEqual(result.status, "failed")
        self.assertIn("Semantic probe failed.", result.tests_failed)

    def test_browser_artifact_runner_fails_when_acceptance_scenario_probe_fails(self) -> None:
        from PIL import Image

        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "index.html").write_text("<!doctype html><main id='app'><input></main>", encoding="utf-8")

            def fake_browser(request: dict[str, object]) -> dict[str, object]:
                first = Path(str(request["initial_screenshot"]))
                second = Path(str(request["after_interaction_screenshot"]))
                image = Image.new("RGB", (6, 6), "white")
                image.putpixel((1, 1), (0, 0, 0))
                image.save(first)
                image.save(second)
                return {
                    "status": "completed",
                    "semantic_probe": {"status": "completed"},
                    "scenario_probe": {
                        "status": "failed",
                        "tests_failed": ["SCN-001: CRUD create controls are missing."],
                    },
                }

            result = BrowserArtifactRunner(fake_browser).verify(
                repo,
                ["index.html"],
                output_dir=repo / "evidence",
                profile_name="static_web_app",
                acceptance_scenarios=[
                    {"id": "SCN-001", "kind": "crud", "required_behaviors": ["create"]},
                ],
            )

        self.assertEqual(result.status, "failed")
        self.assertIn("SCN-001: CRUD create controls are missing.", result.tests_failed)

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
                window.__ALCHEMY_GAME_TEST__ = {
                  snapshot() { return { player_x: 0, player_y: 0, state: "playing", won: false }; },
                  step(dt) {},
                  advanceToVictory() { return { won: true }; },
                  restart() {}
                };
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

    def test_orchestrator_skips_non_applicable_static_artifact_inspection_without_debugging(self) -> None:
        graph = TaskGraph(
            graph_id="backend-static-skip",
            version=1,
            nodes=[
                TaskNode(
                    id="T001",
                    title="Backend implementation",
                    description="Backend work is complete.",
                    type="integration",
                    assigned_agent="backend",
                    status="completed",
                    completion_criteria=["Backend implementation completed."],
                    evidence=[{"type": "worker_result", "result": {"status": "completed", "tests_failed": []}}],
                ),
                TaskNode(
                    id="T002",
                    title="Verify backend",
                    description="Static web artifact inspection is not applicable to this backend phase.",
                    type="test",
                    assigned_agent="test",
                    dependencies=["T001"],
                    completion_criteria=["Non-applicable static web checks are skipped."],
                    relevant_files=["backend/**"],
                    commands_to_run=["static artifact inspection"],
                ),
                TaskNode(
                    id="T003",
                    title="Review",
                    description="Review evidence.",
                    type="review",
                    assigned_agent="reviewer",
                    dependencies=["T002"],
                    completion_criteria=["Reviewer approval is recorded."],
                ),
                TaskNode(
                    id="T004",
                    title="Release",
                    description="Record evidence.",
                    type="release",
                    assigned_agent="reviewer",
                    dependencies=["T003"],
                    completion_criteria=["GitHub evidence is recorded."],
                ),
            ],
            dependencies=[
                Dependency(source="T001", target="T002", type="requires_test_pass"),
                Dependency(source="T002", target="T003", type="requires_review"),
                Dependency(source="T003", target="T004", type="requires_review"),
            ],
        )

        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "backend").mkdir()
            (repo / "backend" / "main.go").write_text("package main\n", encoding="utf-8")
            state = Orchestrator(StateManager(repo / "state.json"), repository_path=repo).run(
                "backend-only delivery",
                reset=True,
                task_graph=graph,
                max_iterations=6,
            )

        nodes = {node.id: node for node in state.task_graph.nodes}
        self.assertTrue(state.done)
        self.assertEqual(nodes["T002"].status, "skipped")
        self.assertFalse(any(node.type == "debug" for node in state.task_graph.nodes))
        self.assertEqual(nodes["T003"].status, "completed")
        self.assertEqual(nodes["T004"].status, "completed")

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

    def test_recovery_resets_interrupted_active_task(self) -> None:
        from runtime.recovery import RecoverySource, RuntimeRecovery

        state = RuntimeState(
            objective="resume interrupted task",
            task_graph=TaskGraph(
                graph_id="recovery-active",
                version=1,
                nodes=[
                    TaskNode(
                        id="T001",
                        title="Active implementation",
                        description="Implement",
                        type="integration",
                        assigned_agent="backend",
                        status="active",
                        completion_criteria=["Implemented."],
                        relevant_files=["backend/**"],
                    )
                ],
            ),
            active_tasks=["T001"],
            worker_lifecycle=[
                {
                    "task_id": "T001",
                    "status": "completed",
                    "worker_pid": 1234,
                    "cleanup_required": False,
                }
            ],
        )

        result = RuntimeRecovery().prepare(RecoverySource(state=state, source_path="state.json"))

        self.assertEqual(result.state.task_graph.nodes[0].status, "pending")
        self.assertEqual(result.state.active_tasks, [])
        self.assertEqual(result.checkpoint["reset_task_ids"], ["T001"])
        self.assertEqual(result.blockers, [])


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

    def test_requirement_coverage_records_gameplay_probe_evidence(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "index.html").write_text("<!doctype html><canvas id='game'></canvas>", encoding="utf-8")

            report = RequirementCoverageBuilder().build(
                repository_path=repo,
                context_bundle={
                    "requirement_map": {
                        "requirements": [
                            {
                                "id": "REQ-001",
                                "priority": "must",
                                "text": "Implement playable browser game",
                                "related_files": ["index.html"],
                                "planned_task_ids": ["T002", "T003"],
                            }
                        ]
                    }
                },
                task_graph={
                    "nodes": [
                        {"id": "T002", "type": "frontend", "status": "completed", "relevant_files": ["index.html"]},
                        {"id": "T003", "type": "test", "status": "completed", "relevant_files": ["index.html"]},
                    ]
                },
                runtime_state={"completed_tasks": ["T002", "T003"]},
                artifact_report={
                    "static_verification": {"status": "completed"},
                    "browser_verification": {
                        "status": "completed",
                        "gameplay_probe": {"status": "completed"},
                    },
                },
            )

        evidence = report.to_dict()["entries"][0]["verification_evidence"]
        self.assertIn("Gameplay probe: completed.", evidence)

    def test_requirement_coverage_records_semantic_probe_evidence(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "index.html").write_text("<!doctype html><main id='app'><button>Add</button></main>", encoding="utf-8")

            report = RequirementCoverageBuilder().build(
                repository_path=repo,
                context_bundle={
                    "requirement_map": {
                        "requirements": [
                            {
                                "id": "REQ-001",
                                "priority": "must",
                                "text": "Implement todo form",
                                "related_files": ["index.html"],
                                "planned_task_ids": ["T002", "T003"],
                            }
                        ]
                    }
                },
                task_graph={
                    "nodes": [
                        {"id": "T002", "type": "frontend", "status": "completed", "relevant_files": ["index.html"]},
                        {"id": "T003", "type": "test", "status": "completed", "relevant_files": ["index.html"]},
                    ]
                },
                runtime_state={"completed_tasks": ["T002", "T003"]},
                artifact_report={
                    "static_verification": {"status": "completed"},
                    "browser_verification": {
                        "status": "completed",
                        "semantic_probe": {"status": "completed"},
                    },
                },
            )

        evidence = report.to_dict()["entries"][0]["verification_evidence"]
        self.assertIn("Semantic probe: completed.", evidence)

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

    def test_requirement_coverage_accepts_documentation_only_evidence(self) -> None:
        with temp_project_dir() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "docs").mkdir()
            (repo / "docs" / "BILLING_CORE_DEV_PLAN.md").write_text("Phase 0 freeze record\n", encoding="utf-8")

            report = RequirementCoverageBuilder().build(
                repository_path=repo,
                context_bundle={
                    "requirement_map": {
                        "requirements": [
                            {
                                "id": "REQ-001",
                                "priority": "must",
                                "text": "明确第一版 demo 必须独立运行。",
                                "related_files": [],
                                "planned_task_ids": ["T002", "T003", "T004"],
                            }
                        ]
                    }
                },
                task_graph={
                    "nodes": [
                        {
                            "id": "T002",
                            "type": "documentation",
                            "status": "completed",
                            "relevant_files": ["docs/**"],
                            "evidence": [{"summary": "Updated the scoped documentation freeze contract."}],
                        },
                        {
                            "id": "T003",
                            "type": "test",
                            "status": "completed",
                            "relevant_files": ["docs/**"],
                            "evidence": [{"summary": "Static document inspection passed."}],
                        },
                        {
                            "id": "T004",
                            "type": "review",
                            "status": "completed",
                            "evidence": [{"summary": "Reviewer approved completed task evidence."}],
                        },
                    ]
                },
                runtime_state={"completed_tasks": ["T002", "T003", "T004"]},
                artifact_report={
                    "artifact_profile": {"name": "documentation_only"},
                    "artifact_files": ["docs/**"],
                    "static_verification": {"status": "skipped"},
                },
            )

        payload = report.to_dict()
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["coverage_score"], 1.0)
        self.assertEqual(payload["entries"][0]["coverage_status"], "covered")
        self.assertEqual(payload["missing_must_requirement_ids"], [])


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
