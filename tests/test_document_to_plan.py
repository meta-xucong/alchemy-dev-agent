from __future__ import annotations

import json
import shutil
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from context import ContextBundleBuilder
from intake import ProjectBriefBuilder
from intake.schema_validation import validate_context_bundle_contract
from planner import TaskGraphBuilder


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_COUNTER = 0
_TEMP_RUN_ID = str(time.time_ns())


@contextmanager
def temp_plan_dir() -> Iterator[Path]:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    path = TEST_TMP_ROOT / f"document-plan-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def write_workspace_repo(root: Path) -> None:
    (root / "src" / "api").mkdir(parents=True)
    (root / "src" / "pages").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "src" / "api" / "workspaces.ts").write_text("export async function listWorkspaces() {}\n", encoding="utf-8")
    (root / "src" / "pages" / "dashboard.tsx").write_text("export function Dashboard() { return null; }\n", encoding="utf-8")
    (root / "tests" / "workspaces.test.ts").write_text("test('workspace', () => {});\n", encoding="utf-8")
    (root / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")
    (root / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run", "build": "vite build", "lint": "eslint ."}}),
        encoding="utf-8",
    )


class DocumentToPlanTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_document_requirements_become_traceable_task_graph(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            repo.mkdir()
            write_workspace_repo(repo)
            spec = root / "workspace_feature_spec.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Workspace Feature",
                        "",
                        "## Requirements",
                        "- Must add workspace API support in src/api/workspaces.ts.",
                        "- Must add dashboard workspace switching in src/pages/dashboard.tsx.",
                        "- Should add workspace permission tests in tests/workspaces.test.ts.",
                        "",
                        "## Acceptance Criteria",
                        "- Users can create a workspace.",
                        "- Users can switch active workspace.",
                        "- Existing dashboard tests still pass.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Add workspace support",
                documents=[spec],
                repository_url="https://github.com/example/saas-dashboard",
                created_at="2026-06-18T00:00:00+00:00",
            )
            brief.repository.local_path = str(repo)

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle)
            bundle_payload = bundle.to_dict()
            graph_payload = graph.to_dict()

        self.assertEqual(validate_context_bundle_contract(bundle_payload), [])
        requirements = bundle_payload["requirement_map"]["requirements"]
        self.assertEqual(len(requirements), 3)
        self.assertEqual(requirements[0]["priority"], "must")
        self.assertIn("src/api/workspaces.ts", requirements[0]["related_files"])
        self.assertIn("src/pages/dashboard.tsx", requirements[1]["related_files"])
        self.assertNotIn("src/pages/dashboard.ts", requirements[1]["related_files"])
        self.assertIn("tests/workspaces.test.ts", requirements[2]["related_files"])
        self.assertEqual(requirements[0]["acceptance_criteria"][0], "Users can create a workspace.")
        self.assertEqual(bundle_payload["document_index"]["documents"][0]["key_requirements"][0], "Must add workspace API support in src/api/workspaces.ts.")

        nodes = {node["id"]: node for node in graph_payload["nodes"]}
        self.assertEqual(graph_payload["graph_id"], f"{bundle.project_id}-document-plan")
        self.assertEqual(nodes["T001"]["assigned_agent"], "architect")
        self.assertEqual(nodes["T002"]["type"], "backend")
        self.assertEqual(nodes["T003"]["type"], "frontend")
        self.assertEqual(nodes["T004"]["type"], "test")
        self.assertEqual(nodes["T005"]["assigned_agent"], "test")
        self.assertEqual(nodes["T006"]["assigned_agent"], "reviewer")
        self.assertIn("npm test", nodes["T005"]["commands_to_run"])
        self.assertIn("npm run build", nodes["T005"]["commands_to_run"])
        self.assertIn("npm run lint", nodes["T005"]["commands_to_run"])
        self.assertEqual(requirements[0]["planned_task_ids"], ["T002", "T005", "T006"])

    def test_acceptance_target_file_guides_same_document_requirements(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            repo.mkdir()
            (repo / "docs").mkdir()
            (repo / "runtime").mkdir()
            (repo / ".codex-longrun").mkdir()
            (repo / "docs" / "27_real_delivery_validation.md").write_text("existing\n", encoding="utf-8")
            (repo / "runtime" / "worktree.py").write_text("class Worktree: pass\n", encoding="utf-8")
            (repo / ".codex-longrun" / "state.json").write_text("{}\n", encoding="utf-8")
            (repo / "pyproject.toml").write_text("[project]\nname='probe'\n", encoding="utf-8")
            spec = root / "probe.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Probe",
                        "",
                        "## Requirements",
                        "- Must create `docs/28_representative_delivery_probe.md`.",
                        "- Must state that real worker execution happens inside an isolated git worktree.",
                        "- Must state that the source checkout must remain unchanged during worker execution.",
                        "- Must include a short verification section for generated evidence and tests.",
                        "",
                        "## Acceptance Criteria",
                        "- `docs/28_representative_delivery_probe.md` exists.",
                        "- The file mentions isolated git worktree.",
                        "- The file mentions source checkout safety.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Probe delivery",
                documents=[spec],
                repository_url="https://github.com/example/probe",
                created_at="2026-06-18T00:00:00+00:00",
            )
            brief.repository.local_path = str(repo)

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        requirements = bundle.to_dict()["requirement_map"]["requirements"]
        for requirement in requirements:
            self.assertEqual(requirement["related_files"], ["docs/28_representative_delivery_probe.md"])

        implementation_nodes = [node for node in graph["nodes"] if node["type"] == "documentation"]
        self.assertEqual(len(implementation_nodes), 1)
        self.assertEqual(implementation_nodes[0]["relevant_files"], ["docs/28_representative_delivery_probe.md"])
        self.assertEqual(implementation_nodes[0]["commands_to_run"], ["static document inspection"])
        self.assertIn("REQ-001, REQ-002, REQ-003, REQ-004", implementation_nodes[0]["description"])
        for requirement in requirements:
            self.assertEqual(requirement["planned_task_ids"][0], implementation_nodes[0]["id"])
        verify_nodes = [node for node in graph["nodes"] if node["title"] == "Verify implementation against project checks"]
        self.assertEqual(verify_nodes[0]["commands_to_run"], ["static document inspection"])
        self.assertEqual(verify_nodes[0]["relevant_files"], ["docs/28_representative_delivery_probe.md"])

    def test_one_line_generated_game_keeps_legacy_demo_graph(self) -> None:
        brief = ProjectBriefBuilder().build(
            objective="Build a small retro platform game",
            primary_input_mode="one_line_fallback",
            created_at="2026-06-18T00:00:00+00:00",
        )

        bundle = ContextBundleBuilder().build(brief)
        graph = TaskGraphBuilder().build(bundle).to_dict()

        self.assertEqual(graph["graph_id"], f"{bundle.project_id}-generated-app")
        self.assertEqual([node["id"] for node in graph["nodes"]], ["T001", "T002", "T003", "T004"])
        self.assertEqual(graph["nodes"][1]["relevant_files"], ["index.html"])

    def test_feedback_document_becomes_must_fix_requirement(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            repo.mkdir()
            (repo / "src").mkdir()
            (repo / "src" / "todo.js").write_text("export function addTodo() {}\n", encoding="utf-8")
            (repo / "index.html").write_text("<main id='app'></main>\n", encoding="utf-8")
            primary = root / "spec.md"
            primary.write_text("# Todo\n## Requirements\n- Must add todo creation in src/todo.js.\n", encoding="utf-8")
            feedback = root / "playtest_notes.md"
            feedback.write_text(
                "\n".join(
                    [
                        "# Playtest Notes",
                        "",
                        "## Feedback",
                        "- Bug: clicking Add Todo does not update src/todo.js state.",
                        "- Issue: empty todos can still be submitted.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Fix todo feedback",
                documents=[primary],
                attachments=[feedback],
                repository_url="https://github.com/example/todo",
                created_at="2026-06-18T00:00:00+00:00",
            )
            brief.repository.local_path = str(repo)

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()
            payload = bundle.to_dict()

        feedback_requirements = [
            requirement
            for requirement in payload["requirement_map"]["requirements"]
            if requirement["source_document_id"] == payload["document_index"]["documents"][1]["id"]
        ]
        self.assertEqual(len(feedback_requirements), 2)
        self.assertTrue(all(requirement["priority"] == "must" for requirement in feedback_requirements))
        self.assertIn("src/todo.js", feedback_requirements[0]["related_files"])
        implementation_nodes = [
            node
            for node in graph["nodes"]
            if node["type"] not in {"architecture", "test", "review", "release"}
        ]
        self.assertGreaterEqual(len(implementation_nodes), 1)

    def test_document_driven_platformer_spec_does_not_use_generated_fallback(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            repo.mkdir()
            spec = root / "super_mario_level1_spec.md"
            spec.write_text(
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
            brief = ProjectBriefBuilder().build(
                objective=(
                    "Build an original retro platformer first level from the provided "
                    "development document; do not copy protected Nintendo characters."
                ),
                documents=[spec],
                repository_url="https://github.com/meta-xucong/-super-mario-test",
                created_at="2026-06-18T00:00:00+00:00",
            )
            brief.repository.local_path = str(repo)

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()
            payload = bundle.to_dict()

        requirements = payload["requirement_map"]["requirements"]
        self.assertGreaterEqual(len(requirements), 10)
        self.assertTrue(all(requirement["source_document_id"] != "generated_one_line" for requirement in requirements))
        self.assertEqual(graph["graph_id"], f"{bundle.project_id}-document-plan")
        requirement_text = "\n".join(requirement["text"] for requirement in requirements)
        for expected in ["Engine", "Physics", "Renderer", "Input", "Entity", "TileMap", "AABB", "60 FPS", "旗帜"]:
            self.assertIn(expected, requirement_text)
        self.assertIn("basic walking enemy", requirement_text)
        self.assertNotIn("Goomba", requirement_text)
        self.assertNotIn("超级玛丽", requirement_text)
        implementation_files = {
            file
            for node in graph["nodes"]
            if node["type"] not in {"architecture", "test", "review", "release"}
            for file in node.get("relevant_files", [])
        }
        implementation_nodes = [
            node
            for node in graph["nodes"]
            if node["type"] not in {"architecture", "test", "review", "release"}
        ]
        self.assertEqual(len(implementation_nodes), 1)
        for expected_file in [
            "index.html",
            "src/main.js",
            "src/engine.js",
            "src/input.js",
            "src/physics.js",
            "src/tilemap.js",
            "src/entities.js",
            "src/renderer.js",
            "tests/static_checks.js",
        ]:
            self.assertIn(expected_file, implementation_files)

    def test_real_world_chinese_platformer_document_guidance_lines_are_requirements(self) -> None:
        text = "\n".join(
            [
                "## 内容说明",
                "本次提交包含：",
                "",
                "- 第一关（Level 1）完整设计文档",
                "- 游戏核心系统拆分（Engine / Physics / Renderer / Input / Entity）",
                "",
                "## 技术目标",
                "该文档用于指导实现：",
                "",
                "- 可完整通关的第一关",
                "- 基础敌人 AI（Goomba）",
                "",
                "## 下一步计划",
                "建议下一阶段实现：",
                "1. Game Engine 初始化",
                "2. Level 1 完整跑通",
            ]
        )

        from context.requirement_extractor import extract_requirement_lines

        lines = extract_requirement_lines(text)

        self.assertGreaterEqual(len(lines), 6)
        self.assertIn("基础敌人 AI（Goomba）", lines)
        self.assertIn("Game Engine 初始化", lines)


if __name__ == "__main__":
    unittest.main()
