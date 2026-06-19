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

from autodev import DocumentRunPipeline
from autodev.delivery_report import build_delivery_report
from autodev.document_run import assign_release_branch, build_artifact_report, build_generated_ci_report
from autodev.development_cycle import build_development_cycle_report
from runtime.models import RuntimeState, TaskGraph, TaskNode
from runtime.control import ControlDecision
from runtime.artifact_verifier import BrowserArtifactRunner


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_COUNTER = 0
_TEMP_RUN_ID = str(time.time_ns())


@contextmanager
def temp_document_run_dir() -> Iterator[Path]:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    path = TEST_TMP_ROOT / f"document-run-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def write_repo(root: Path) -> None:
    (root / "src" / "api").mkdir(parents=True)
    (root / "src" / "pages").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "api" / "workspaces.ts").write_text("export const api = true;\n", encoding="utf-8")
    (root / "src" / "pages" / "dashboard.tsx").write_text("export const ui = true;\n", encoding="utf-8")
    (root / "tests" / "workspaces.test.ts").write_text("test('workspace', () => {});\n", encoding="utf-8")
    (root / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")


def write_spec(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# Workspace Feature",
                "## Requirements",
                "- Must add workspace API support in src/api/workspaces.ts.",
                "- Must add dashboard workspace switching in src/pages/dashboard.tsx.",
                "## Acceptance Criteria",
                "- Users can create a workspace.",
                "- Users can switch active workspace.",
            ]
        ),
        encoding="utf-8",
    )


def write_platformer_spec(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "## 目的",
                "本 PR 添加《超级玛丽类横版游戏》第一关完整工程化开发文档。",
                "",
                "## 内容说明",
                "- 游戏核心系统拆分（Engine / Physics / Renderer / Input / Entity）",
                "- TileMap 关卡定义规范",
                "- 碰撞系统设计（AABB + Tile Collision）",
                "- 游戏状态机设计",
                "- 分数系统与通关条件",
                "- 文件结构规范",
                "",
                "## 技术目标",
                "- 可完整通关的第一关",
                "- 60 FPS Canvas 渲染",
                "- 基于 TileMap 的关卡系统",
                "- 基础敌人 AI（Goomba）",
                "- 玩家跳跃与物理系统",
                "- 胜利判定（旗帜触发）",
                "",
                "## 下一步计划",
                "1. Game Engine 初始化",
                "2. Player 移动与物理",
                "3. TileMap 渲染系统",
                "4. 碰撞系统",
                "5. Enemy AI",
                "6. Level 1 完整跑通",
            ]
        ),
        encoding="utf-8",
    )


class DocumentRunPipelineTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_pipeline_generates_done_report(self) -> None:
        with temp_document_run_dir() as root:
            repo = root / "repo"
            repo.mkdir()
            write_repo(repo)
            spec = root / "workspace_feature_spec.md"
            write_spec(spec)
            output = root / "run"

            result = DocumentRunPipeline().run(
                objective="Add workspace support",
                documents=[spec],
                repository_url="https://github.com/example/saas-dashboard",
                repository_path=repo,
                output_dir=output,
            )
            payload = result.to_dict()
            self.assertEqual(payload["status"], "done")
            self.assertEqual(payload["runtime_state"]["evaluation"]["reason"], "DONE condition met.")
            self.assertTrue((output / "document_run_report.json").exists())
            self.assertTrue((output / "state.json").exists())
            self.assertGreaterEqual(len(payload["worker_packages"]), 5)
            self.assertEqual(payload["project_brief"]["repository"]["visibility"], "public")
            self.assertEqual(payload["context_bundle"]["requirement_map"]["requirements"][0]["planned_task_ids"][0], "T002")
        self.assertIn("pull_request_url", payload["runtime_state"]["github"])
        self.assertEqual(payload["preflight"]["status"], "passed")
        self.assertIn("artifact_report", payload)
        self.assertEqual(payload["artifact_report"]["artifact_profile"]["name"], "node_project")
        self.assertIn("requirement_coverage", payload)
        self.assertGreater(payload["requirement_coverage"]["coverage_score"], 0)
        self.assertFalse(payload["requirement_coverage"]["missing_must_requirement_ids"])
        self.assertIn("delivery_report", payload)
        self.assertEqual(payload["delivery_report"]["status"], "done")
        self.assertTrue(payload["delivery_report"]["ready_for_review"])
        self.assertIn("development_cycle", payload)
        self.assertIn(payload["development_cycle"]["status"], {"passed", "partial"})
        step_names = [step["name"] for step in payload["development_cycle"]["steps"]]
        self.assertIn("brain_refinement", step_names)
        self.assertIn("full_review", step_names)

    def test_cli_outputs_done_report(self) -> None:
        with temp_document_run_dir() as root:
            repo = root / "repo"
            repo.mkdir()
            write_repo(repo)
            spec = root / "workspace_feature_spec.md"
            write_spec(spec)
            output = root / "run"

            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "autodev.document_run",
                    "--objective",
                    "Add workspace support",
                    "--document",
                    str(spec),
                    "--repository",
                    "https://github.com/example/saas-dashboard",
                    "--repository-path",
                    str(repo),
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "done")
            self.assertTrue((output / "document_run_report.json").exists())
            self.assertEqual(payload["runtime_state"]["done"], True)
            self.assertEqual(payload["preflight"]["status"], "passed")

    def test_real_codex_missing_executable_blocks_before_execution(self) -> None:
        with temp_document_run_dir() as root:
            repo = root / "repo"
            repo.mkdir()
            write_repo(repo)
            spec = root / "workspace_feature_spec.md"
            write_spec(spec)
            output = root / "run"

            result = DocumentRunPipeline().run(
                objective="Add workspace support",
                documents=[spec],
                repository_url="https://github.com/example/saas-dashboard",
                repository_path=repo,
                output_dir=output,
                real_codex=True,
                codex_executable="definitely-missing-codex-for-test",
            )
            payload = result.to_dict()

            self.assertEqual(payload["status"], "blocked")
            self.assertEqual(payload["preflight"]["status"], "blocked")
            self.assertFalse(payload["runtime_state"]["done"])
            self.assertEqual(payload["runtime_state"]["blockers"][0]["id"], "B-PREFLIGHT")
            self.assertTrue((output / "state.json").exists())

    def test_pipeline_can_resume_from_stopped_run_state(self) -> None:
        class StopAfterFirstTask:
            def __init__(self) -> None:
                self.calls = 0

            def before_task(self, task_id: str) -> ControlDecision:
                self.calls += 1
                if self.calls > 1:
                    return ControlDecision("stop", f"stop before {task_id}")
                return ControlDecision()

        with temp_document_run_dir() as root:
            repo = root / "repo"
            repo.mkdir()
            write_repo(repo)
            spec = root / "workspace_feature_spec.md"
            write_spec(spec)
            first_output = root / "run-001"
            resumed_output = root / "run-002"

            first = DocumentRunPipeline().run(
                objective="Add workspace support",
                documents=[spec],
                repository_url="https://github.com/example/saas-dashboard",
                repository_path=repo,
                output_dir=first_output,
                controller=StopAfterFirstTask(),
            )
            self.assertEqual(first.status, "blocked")
            self.assertIn("B-RUN-STOPPED", [blocker["id"] for blocker in first.runtime_state["blockers"]])

            resumed = DocumentRunPipeline().run(
                objective="Add workspace support",
                documents=[spec],
                repository_url="https://github.com/example/saas-dashboard",
                repository_path=repo,
                output_dir=resumed_output,
                resume_from=first_output,
            )

            self.assertEqual(resumed.status, "done")
            self.assertTrue(resumed.runtime_state["done"])
            self.assertIn("recovery", resumed.to_dict())
            self.assertTrue(resumed.recovery["checkpoint"]["continued_task_ids"])
            self.assertTrue((resumed_output / "state.json").exists())

    def test_docs_only_platformer_document_run_uses_document_requirements(self) -> None:
        with temp_document_run_dir() as root:
            repo = root / "repo"
            repo.mkdir()
            spec = root / "super_mario_level1_spec.md"
            write_platformer_spec(spec)
            output = root / "run"

            result = DocumentRunPipeline().run(
                objective=(
                    "Build an original retro platformer first level from the provided development document; "
                    "do not copy protected Nintendo characters."
                ),
                documents=[spec],
                repository_url="https://github.com/meta-xucong/-super-mario-test",
                repository_path=repo,
                output_dir=output,
            )
            payload = result.to_dict()

        requirements = payload["context_bundle"]["requirement_map"]["requirements"]
        self.assertEqual(payload["status"], "blocked")
        self.assertGreaterEqual(len(requirements), 10)
        self.assertTrue(all(requirement["source_document_id"] != "generated_one_line" for requirement in requirements))
        self.assertEqual(payload["task_graph"]["graph_id"].endswith("-document-plan"), True)
        verify_nodes = [
            node
            for node in payload["task_graph"]["nodes"]
            if node["title"] == "Verify implementation against project checks"
        ]
        self.assertEqual(verify_nodes[0]["commands_to_run"], ["static artifact inspection"])
        self.assertIn("index.html", verify_nodes[0]["relevant_files"])
        self.assertIn("Missing artifact file", json.dumps(payload["runtime_state"], ensure_ascii=False))
        self.assertEqual(payload["artifact_report"]["artifact_profile"]["name"], "canvas_game")
        self.assertEqual(payload["artifact_report"]["static_verification"]["status"], "failed")
        self.assertEqual(payload["requirement_coverage"]["status"], "failed")
        self.assertTrue(payload["requirement_coverage"]["missing_must_requirement_ids"])

    def test_document_run_records_external_browser_evidence(self) -> None:
        from PIL import Image

        with temp_document_run_dir() as root:
            repo = root / "repo"
            repo.mkdir()
            write_repo(repo)
            spec = root / "workspace_feature_spec.md"
            write_spec(spec)
            first = root / "initial.png"
            second = root / "after.png"
            Image.new("RGB", (6, 6), "white").save(first)
            changed = Image.new("RGB", (6, 6), "white")
            changed.putpixel((1, 1), (0, 0, 0))
            changed.save(second)
            output = root / "run"

            result = DocumentRunPipeline().run(
                objective="Add workspace support",
                documents=[spec],
                repository_url="https://github.com/example/saas-dashboard",
                repository_path=repo,
                output_dir=output,
                browser_url="http://127.0.0.1:9999/index.html",
                browser_initial_screenshot=first,
                browser_after_screenshot=second,
            )
            payload = result.to_dict()

        browser = payload["artifact_report"]["browser_verification"]
        self.assertEqual(browser["status"], "completed")
        self.assertGreater(browser["pixel_diff"]["changed_pixels"], 0)
        self.assertEqual(browser["url"], "http://127.0.0.1:9999/index.html")

    def test_build_artifact_report_can_auto_capture_browser_evidence(self) -> None:
        from PIL import Image

        with temp_document_run_dir() as root:
            repo = root / "repo"
            repo.mkdir()
            (repo / "index.html").write_text(
                """
                <!doctype html>
                <canvas id="game"></canvas>
                <script>
                const level = { player: {}, enemy: {}, coin: {}, tile: [], flag: {} };
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

            def fake_browser(request: dict[str, object]) -> dict[str, object]:
                first = Path(str(request["initial_screenshot"]))
                second = Path(str(request["after_interaction_screenshot"]))
                initial = Image.new("RGB", (8, 8), "white")
                initial.putpixel((1, 1), (20, 20, 20))
                initial.save(first)
                changed = Image.new("RGB", (8, 8), "white")
                changed.putpixel((2, 2), (0, 0, 0))
                changed.save(second)
                return {
                    "status": "completed",
                    "gameplay_probe": {
                        "status": "completed",
                        "tests_passed": ["Right movement changes player_x.", "Jump input changes player_y."],
                        "tests_failed": [],
                    },
                }

            report = build_artifact_report(
                repository_path=repo,
                task_graph={
                    "nodes": [
                        {
                            "commands_to_run": ["static artifact inspection"],
                            "relevant_files": ["index.html"],
                        }
                    ]
                },
                output_dir=root / "run",
                auto_browser_verify=True,
                browser_artifact_runner=BrowserArtifactRunner(fake_browser),
            )

        browser = report["browser_verification"]
        self.assertEqual(browser["status"], "completed")
        self.assertGreater(browser["pixel_diff"]["changed_pixels"], 0)
        self.assertEqual(browser["gameplay_probe"]["status"], "completed")
        self.assertEqual(report["artifact_profile"]["name"], "canvas_game")

    def test_generated_ci_report_writes_static_web_workflow_for_real_github(self) -> None:
        with temp_document_run_dir() as root:
            repo = root / "repo"
            repo.mkdir()
            (repo / "index.html").write_text("<!doctype html><canvas></canvas>", encoding="utf-8")

            report = build_generated_ci_report(
                repository_path=repo,
                artifact_report={"artifact_profile": {"name": "canvas_game"}},
                real_github=True,
                github_collect_ci=True,
                generate_static_ci=True,
            )

        self.assertEqual(report["status"], "generated")
        self.assertEqual(report["workflow_path"], ".github/workflows/alchemy-static-checks.yml")

    def test_artifact_report_generates_and_passes_acceptance_scenarios(self) -> None:
        from PIL import Image

        with temp_document_run_dir() as root:
            repo = root / "repo"
            repo.mkdir()
            (repo / "index.html").write_text(
                "<!doctype html><main id='app'><form><input name='todo'><button>Add Todo</button></form><ul><li>Seed task</li></ul></main>",
                encoding="utf-8",
            )
            seen_scenarios: list[dict[str, object]] = []

            def fake_browser(request: dict[str, object]) -> dict[str, object]:
                seen_scenarios.extend(list(request.get("acceptance_scenarios", [])))  # type: ignore[arg-type]
                first = Path(str(request["initial_screenshot"]))
                second = Path(str(request["after_interaction_screenshot"]))
                initial = Image.new("RGB", (8, 8), "white")
                initial.putpixel((1, 1), (20, 20, 20))
                initial.save(first)
                changed = Image.new("RGB", (8, 8), "white")
                changed.putpixel((2, 2), (0, 0, 0))
                changed.save(second)
                return {
                    "status": "completed",
                    "semantic_probe": {"status": "completed"},
                    "scenario_probe": {
                        "status": "completed",
                        "tests_passed": ["SCN-001: CRUD create controls are present."],
                    },
                }

            report = build_artifact_report(
                repository_path=repo,
                task_graph={
                    "nodes": [
                        {
                            "commands_to_run": ["static artifact inspection"],
                            "relevant_files": ["index.html"],
                        }
                    ]
                },
                context_bundle={
                    "requirement_map": {
                        "requirements": [
                            {
                                "id": "REQ-001",
                                "text": "Users can create todo records.",
                                "acceptance_criteria": ["CRUD create updates the visible todo list."],
                            }
                        ]
                    }
                },
                output_dir=root / "run",
                auto_browser_verify=True,
                browser_artifact_runner=BrowserArtifactRunner(fake_browser),
            )

        self.assertEqual(report["acceptance_scenarios"]["status"], "generated")
        self.assertEqual(seen_scenarios[0]["kind"], "crud")
        self.assertEqual(report["browser_verification"]["scenario_probe"]["status"], "completed")

    def test_document_run_generates_native_ui_acceptance_tests(self) -> None:
        with temp_document_run_dir() as root:
            repo = root / "repo"
            repo.mkdir()
            (repo / "index.html").write_text(
                "<!doctype html><main id='app'><form><input name='todo'><button>Add Todo</button></form><ul><li>Seed task</li></ul></main>",
                encoding="utf-8",
            )
            spec = root / "todo_spec.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Todo App",
                        "## Requirements",
                        "- Must deliver todo creation in index.html.",
                        "## Acceptance Criteria",
                        "- CRUD create updates the visible todo list.",
                    ]
                ),
                encoding="utf-8",
            )
            output = root / "run"

            result = DocumentRunPipeline().run(
                objective="Deliver todo app",
                documents=[spec],
                repository_path=repo,
                output_dir=output,
            )
            payload = result.to_dict()
            target = output / "generated_tests" / "playwright" / "alchemy_acceptance.spec.ts"
            self.assertTrue(target.exists())

        self.assertEqual(payload["native_ui_tests"]["status"], "generated")
        self.assertEqual(payload["native_ui_tests"]["framework"], "playwright")
        self.assertEqual(payload["artifact_report"]["native_ui_tests"]["status"], "generated")
        self.assertEqual(payload["runtime_state"]["repository"]["native_ui_tests"]["status"], "generated")
        self.assertEqual(payload["delivery_report"]["artifact"]["native_ui_tests"]["status"], "generated")
        self.assertIn("Native UI acceptance tests: generated.", payload["requirement_coverage"]["entries"][0]["verification_evidence"])

    def test_development_cycle_report_marks_manual_engineering_loop_evidence(self) -> None:
        report = build_development_cycle_report(
            project_brief={
                "documents": [{"path": "spec.md"}],
                "generated_from_one_liner": False,
            },
            context_bundle={
                "document_index": {"documents": [{"path": "spec.md"}]},
                "requirement_map": {
                    "requirements": [
                        {"id": "REQ-001", "planned_task_ids": ["T002", "T003", "T004"]},
                    ]
                },
            },
            task_graph={
                "nodes": [
                    {"id": "T001", "type": "architecture", "status": "completed"},
                    {"id": "T002", "type": "frontend", "status": "completed"},
                    {"id": "T003", "type": "test", "status": "completed"},
                    {"id": "T004", "type": "review", "status": "completed"},
                    {"id": "T005", "type": "release", "status": "completed"},
                ]
            },
            runtime_state={
                "completed_tasks": ["T001", "T002", "T003", "T004", "T005"],
                "iteration_history": [{"type": "evaluation", "summary": "DONE condition met."}],
                "evaluation": {"done": True, "test_pass_rate": 1.0},
                "github": {
                    "status": "pushed",
                    "pull_request_url": "https://example.test/pr/1",
                    "ci_status": "passed",
                    "merge": {"status": "merged", "summary": "Pull request was merged."},
                },
                "task_graph": {
                    "nodes": [
                        {"id": "T004", "type": "review", "status": "completed"},
                    ]
                },
            },
            artifact_report={"static_verification": {"status": "passed"}},
            requirement_coverage={"status": "passed"},
            delivery_report={"status": "done", "ready_for_review": True, "github": {"ci_status": "passed"}},
        )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["score"], 1.0)
        statuses = {step["name"]: step["status"] for step in report["steps"]}
        self.assertEqual(statuses["merge"], "passed")

    def test_development_cycle_requires_gameplay_probe_for_canvas_games(self) -> None:
        report = build_development_cycle_report(
            project_brief={"documents": [{"path": "spec.md"}]},
            context_bundle={
                "document_index": {"documents": [{"path": "spec.md"}]},
                "requirement_map": {"requirements": [{"id": "REQ-001", "planned_task_ids": ["T002"]}]},
            },
            task_graph={
                "nodes": [
                    {"id": "T001", "type": "architecture"},
                    {"id": "T003", "type": "test"},
                    {"id": "T004", "type": "review"},
                ]
            },
            runtime_state={
                "completed_tasks": ["T001", "T002", "T003", "T004"],
                "iteration_history": [{"type": "evaluation"}],
                "evaluation": {"done": True, "test_pass_rate": 1.0},
                "github": {"status": "pushed", "pull_request_url": "https://example.test/pr/2", "ci_status": "passed"},
                "task_graph": {"nodes": [{"id": "T004", "type": "review", "status": "completed"}]},
            },
            artifact_report={
                "artifact_profile": {"name": "canvas_game"},
                "static_verification": {"status": "passed"},
                "browser_verification": {
                    "status": "completed",
                    "gameplay_probe": {"status": "failed"},
                },
            },
            requirement_coverage={"status": "passed"},
            delivery_report={"status": "done", "ready_for_review": True, "github": {"ci_status": "passed"}},
        )

        statuses = {step["name"]: step["status"] for step in report["steps"]}
        gaps = {step["name"]: step["gaps"] for step in report["steps"]}
        self.assertEqual(statuses["testing"], "missing")
        self.assertIn("Canvas gameplay probe did not complete.", gaps["testing"])

    def test_development_cycle_accepts_completed_static_artifact_status(self) -> None:
        report = build_development_cycle_report(
            project_brief={"documents": [{"path": "spec.md"}]},
            context_bundle={
                "document_index": {"documents": [{"path": "spec.md"}]},
                "requirement_map": {"requirements": [{"id": "REQ-001", "planned_task_ids": ["T002"]}]},
            },
            task_graph={"nodes": [{"id": "T001", "type": "architecture"}, {"id": "T003", "type": "test"}, {"id": "T004", "type": "review"}]},
            runtime_state={
                "completed_tasks": ["T001", "T002", "T003", "T004"],
                "iteration_history": [{"type": "evaluation"}],
                "evaluation": {"done": True, "test_pass_rate": 1.0},
                "github": {"status": "pushed", "pull_request_url": "https://example.test/pr/2", "ci_status": "passed"},
                "task_graph": {"nodes": [{"id": "T004", "type": "review", "status": "completed"}]},
            },
            artifact_report={"static_verification": {"status": "completed"}},
            requirement_coverage={"status": "passed"},
            delivery_report={"status": "done", "ready_for_review": True, "github": {"ci_status": "passed"}},
        )

        statuses = {step["name"]: step["status"] for step in report["steps"]}
        self.assertEqual(statuses["testing"], "passed")

    def test_delivery_report_does_not_wait_for_generated_ci_after_passed_checks(self) -> None:
        report = build_delivery_report(
            status="done",
            runtime_state={
                "evaluation": {"done": True, "reason": "DONE condition met.", "final_gate_score": 0.9},
                "github": {"ci_status": "passed"},
                "blockers": [],
            },
            artifact_report={},
            requirement_coverage={"status": "passed", "entries": []},
            generated_ci={"status": "generated"},
        )

        self.assertNotIn("Wait for generated GitHub Actions checks to pass on the PR.", report["next_actions"])

    def test_delivery_report_blocks_partial_must_and_failed_browser_probe(self) -> None:
        report = build_delivery_report(
            status="done",
            runtime_state={
                "evaluation": {
                    "done": False,
                    "reason": "Must requirements have only partial coverage: REQ-001.",
                    "final_gate_score": 0.85,
                    "hard_failures": ["Must requirements have only partial coverage: REQ-001."],
                },
                "github": {"ci_status": "passed"},
                "blockers": [],
            },
            artifact_report={
                "artifact_profile": {"name": "static_web_app"},
                "browser_verification": {
                    "status": "failed",
                    "scenario_probe": {"status": "failed"},
                },
            },
            requirement_coverage={
                "status": "failed",
                "entries": [{"coverage_status": "partial"}],
                "coverage_score": 0.5,
                "missing_must_requirement_ids": [],
                "partial_must_requirement_ids": ["REQ-001"],
            },
            generated_ci={"status": "skipped"},
        )

        self.assertFalse(report["ready_for_review"])
        self.assertIn("Must requirements have only partial coverage: REQ-001.", report["readiness_issues"])
        self.assertIn("Browser artifact verification failed.", report["readiness_issues"])
        self.assertIn("Acceptance scenario browser probe failed.", report["next_actions"])

    def test_delivery_report_summarizes_gameplay_probe_status(self) -> None:
        report = build_delivery_report(
            status="done",
            runtime_state={
                "evaluation": {"done": True, "reason": "DONE condition met.", "final_gate_score": 0.9},
                "github": {"ci_status": "passed"},
                "blockers": [],
            },
            artifact_report={
                "artifact_profile": {"name": "canvas_game"},
                "browser_verification": {
                    "status": "completed",
                    "gameplay_probe": {"status": "completed", "tests_passed": ["Victory path can be reached."]},
                },
            },
            requirement_coverage={"status": "passed", "entries": []},
            generated_ci={"status": "generated"},
        )

        self.assertEqual(report["artifact"]["gameplay_status"], "completed")
        self.assertEqual(report["artifact"]["gameplay_probe"]["tests_passed"], ["Victory path can be reached."])

    def test_delivery_report_summarizes_semantic_probe_status(self) -> None:
        report = build_delivery_report(
            status="done",
            runtime_state={
                "evaluation": {"done": True, "reason": "DONE condition met.", "final_gate_score": 0.9},
                "github": {"ci_status": "passed"},
                "blockers": [],
            },
            artifact_report={
                "artifact_profile": {"name": "static_web_app"},
                "browser_verification": {
                    "status": "completed",
                    "semantic_probe": {"status": "completed", "tests_passed": ["Static web controls are discoverable."]},
                },
            },
            requirement_coverage={"status": "passed", "entries": []},
            generated_ci={"status": "generated"},
        )

        self.assertEqual(report["artifact"]["semantic_status"], "completed")
        self.assertEqual(report["artifact"]["semantic_probe"]["tests_passed"], ["Static web controls are discoverable."])

    def test_delivery_report_summarizes_acceptance_scenario_probe_status(self) -> None:
        report = build_delivery_report(
            status="done",
            runtime_state={
                "evaluation": {"done": True, "reason": "DONE condition met.", "final_gate_score": 0.9},
                "github": {"ci_status": "passed"},
                "blockers": [],
            },
            artifact_report={
                "artifact_profile": {"name": "static_web_app"},
                "acceptance_scenarios": {"status": "generated", "scenarios": [{"id": "SCN-001", "kind": "crud"}]},
                "browser_verification": {
                    "status": "completed",
                    "scenario_probe": {"status": "completed", "tests_passed": ["SCN-001: CRUD create controls are present."]},
                },
            },
            requirement_coverage={"status": "passed", "entries": []},
            generated_ci={"status": "generated"},
        )

        self.assertEqual(report["artifact"]["scenario_status"], "completed")
        self.assertEqual(report["artifact"]["acceptance_scenarios"]["status"], "generated")
        self.assertEqual(report["artifact"]["scenario_probe"]["tests_passed"], ["SCN-001: CRUD create controls are present."])

    def test_delivery_report_summarizes_native_ui_tests(self) -> None:
        report = build_delivery_report(
            status="done",
            runtime_state={
                "evaluation": {"done": True, "reason": "DONE condition met.", "final_gate_score": 0.9},
                "github": {"ci_status": "passed"},
                "blockers": [],
            },
            artifact_report={
                "artifact_profile": {"name": "static_web_app"},
                "native_ui_tests": {"status": "generated", "framework": "playwright"},
            },
            requirement_coverage={"status": "passed", "entries": []},
            generated_ci={"status": "generated"},
        )

        self.assertEqual(report["artifact"]["native_ui_tests"]["status"], "generated")
        self.assertEqual(report["artifact"]["native_ui_tests"]["framework"], "playwright")

    def test_assign_release_branch_binds_real_worktree_branch_to_release_task(self) -> None:
        state = RuntimeState(
            objective="Deliver generated app",
            task_graph=TaskGraph(
                graph_id="branch-binding",
                version=1,
                nodes=[
                    TaskNode(
                        id="T001",
                        title="Review",
                        description="Review",
                        type="review",
                        assigned_agent="reviewer",
                    ),
                    TaskNode(
                        id="T002",
                        title="Record delivery",
                        description="Release",
                        type="release",
                        assigned_agent="reviewer",
                    ),
                ],
            ),
        )

        assign_release_branch(state, "agent/example-real-run")

        self.assertEqual(state.task_graph.nodes[1].branch, "agent/example-real-run")


if __name__ == "__main__":
    unittest.main()
