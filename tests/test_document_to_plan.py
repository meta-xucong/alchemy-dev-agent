from __future__ import annotations

import json
import shutil
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from context import ContextBundleBuilder, RepositoryIndexer
from context.models import Requirement
from context.requirement_extractor import explicit_paths_from_text, extract_scope_controls
from intake import ProjectBriefBuilder
from intake.schema_validation import validate_context_bundle_contract
from planner import TaskGraphBuilder
from planner.task_graph_builder import focused_timeout_repair_for_task


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
        summaries = bundle_payload["repository_map"]["code_summaries"]
        self.assertGreaterEqual(len(summaries), 2)
        summary_by_path = {summary["path"]: summary for summary in summaries}
        self.assertIn("exports", summary_by_path["src/api/workspaces.ts"]["signals"])
        self.assertIn("tests", summary_by_path["tests/workspaces.test.ts"]["signals"])

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

    def test_explicit_path_extraction_keeps_paths_with_sentence_punctuation(self) -> None:
        text = "Must update src/api/workspaces.ts. Should render src/pages/dashboard.tsx, and tests/workspaces.test.ts."

        self.assertEqual(
            explicit_paths_from_text(text),
            ["src/api/workspaces.ts", "src/pages/dashboard.tsx", "tests/workspaces.test.ts"],
        )

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
        feedback_nodes = [node for node in implementation_nodes if node["type"] == "debug"]
        self.assertGreaterEqual(len(feedback_nodes), 1)
        self.assertEqual(feedback_nodes[0]["assigned_agent"], "debug")

    def test_context_bundle_records_requirement_contradiction_warning(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            repo.mkdir()
            (repo / "index.html").write_text("<main id='app'></main>\n", encoding="utf-8")
            spec = root / "spec.md"
            spec.write_text(
                "\n".join(
                    [
                        "# App",
                        "",
                        "## Requirements",
                        "- Must work offline.",
                        "- Must be online.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Build app",
                documents=[spec],
                repository_path=repo,
                created_at="2026-06-18T00:00:00+00:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            payload = bundle.to_dict()

        self.assertEqual(validate_context_bundle_contract(payload), [])
        contradiction_blockers = [
            blocker for blocker in payload["blockers"] if blocker["code"] == "requirement_contradiction"
        ]
        self.assertEqual(len(contradiction_blockers), 1)
        self.assertEqual(contradiction_blockers[0]["severity"], "warning")
        self.assertIn("REQ-001", contradiction_blockers[0]["message"])
        self.assertIn("REQ-002", contradiction_blockers[0]["message"])

    def test_feedback_priority_stays_must_even_when_text_says_should(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            repo.mkdir()
            (repo / "index.html").write_text("<main id='app'></main>\n", encoding="utf-8")
            primary = root / "spec.md"
            primary.write_text("# Todo\n## Requirements\n- Must add todo creation in index.html.\n", encoding="utf-8")
            feedback = root / "feedback.md"
            feedback.write_text(
                "# Feedback\n\n## Feedback\n- Bug: empty todo submission should remain blocked in index.html.\n",
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Fix todo feedback",
                documents=[primary],
                attachments=[feedback],
                repository_path=repo,
                created_at="2026-06-18T00:00:00+00:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            payload = bundle.to_dict()

        feedback_requirements = [
            requirement
            for requirement in payload["requirement_map"]["requirements"]
            if requirement["source_role"] == "feedback"
        ]
        self.assertEqual(feedback_requirements[0]["priority"], "must")
        repository_files = payload["repository_map"]["files"]
        html_file = next(file for file in repository_files if file["path"] == "index.html")
        self.assertEqual(html_file["kind"], "source")

    def test_auto_feedback_target_files_seed_debug_task_allowed_files(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            repo.mkdir()
            (repo / "app.py").write_text("def add(a, b):\n    raise NotImplementedError()\n", encoding="utf-8")
            primary = root / "spec.md"
            primary.write_text("# Add\n## Requirements\n- Must implement add(a, b) in app.py.\n", encoding="utf-8")
            feedback = root / "auto_feedback.md"
            feedback.write_text(
                "\n".join(
                    [
                        "# Auto Feedback",
                        "",
                        "## Required Repairs",
                        "",
                        "1. Implement missing must requirement: REQ-ADD-001",
                        "   - Target files: app.py",
                        "",
                        "## Acceptance Evidence Required",
                        "",
                        "- Requirement REQ-ADD-001 is covered.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Fix add feedback",
                documents=[primary],
                attachments=[feedback],
                repository_path=repo,
                created_at="2026-06-18T00:00:00+00:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()
            payload = bundle.to_dict()

        feedback_requirements = [
            requirement
            for requirement in payload["requirement_map"]["requirements"]
            if requirement["source_role"] == "feedback"
        ]
        self.assertTrue(feedback_requirements)
        self.assertTrue(all("app.py" in requirement["related_files"] for requirement in feedback_requirements))
        debug_nodes = [node for node in graph["nodes"] if node["type"] == "debug"]
        self.assertTrue(debug_nodes)
        self.assertTrue(all("app.py" in node["relevant_files"] for node in debug_nodes))
        implementation_nodes = [
            node
            for node in graph["nodes"]
            if node["type"] not in {"architecture", "test", "review", "release"}
        ]
        self.assertEqual(len(implementation_nodes), 1)
        self.assertEqual(implementation_nodes[0]["type"], "debug")

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

    def test_scope_lock_constrains_v3_foundation_task_graph(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            repo.mkdir()
            (repo / "alchemy_creative_agent_3_0" / "docs").mkdir(parents=True)
            (repo / "alchemy_creative_agent_3_0" / "app").mkdir(parents=True)
            (repo / "alchemy_creative_agent_3_0" / "tests").mkdir(parents=True)
            (repo / "custom_media_agent_2_0" / "app" / "agents").mkdir(parents=True)
            (repo / "src_skeleton" / "app").mkdir(parents=True)
            (repo / "tests").mkdir()
            (repo / "pyproject.toml").write_text("[project]\nname='media-agent'\n", encoding="utf-8")
            (repo / "custom_media_agent_2_0" / "app" / "agents" / "runtime.py").write_text("LEGACY = True\n", encoding="utf-8")
            (repo / "src_skeleton" / "app" / "schemas.py").write_text("LEGACY = True\n", encoding="utf-8")
            (repo / "tests" / "test_legacy.py").write_text("def test_legacy():\n    assert True\n", encoding="utf-8")
            prompt = root / "06_CODEX_TASK_PROMPT.md"
            prompt.write_text(
                "\n".join(
                    [
                        "# V3 Foundation",
                        "",
                        "## Requirements",
                        "- Must build V3 independent runtime under alchemy_creative_agent_3_0/app/.",
                        "- Must add V3 tests under alchemy_creative_agent_3_0/tests/.",
                        "- Do not use custom_media_agent_2_0/app/agents/runtime.py.",
                        "- Do not use src_skeleton/app/schemas.py.",
                        "",
                        "## Acceptance Criteria",
                        "- V3_FOUNDATION_STATUS: COMPLETE.",
                        "- INDEPENDENCE_STATUS: PASS.",
                    ]
                ),
                encoding="utf-8",
            )
            scope = root / "scope_lock.md"
            scope.write_text(
                "\n".join(
                    [
                        "# Scope Lock",
                        "",
                        "All implementation code and tests must live under:",
                        "",
                        "```text",
                        "alchemy_creative_agent_3_0/app/",
                        "alchemy_creative_agent_3_0/tests/",
                        "```",
                        "",
                        "## Protected Areas",
                        "Do not edit any file under these paths:",
                        "",
                        "```text",
                        "src_skeleton/",
                        "custom_media_agent_2_0/",
                        "tests/",
                        "docs/",
                        "```",
                        "",
                        "## Target Files",
                        "Target files: alchemy_creative_agent_3_0/app/__init__.py, alchemy_creative_agent_3_0/app/creative_core/central_brain.py, alchemy_creative_agent_3_0/tests/test_end_to_end_planning.py, alchemy_creative_agent_3_0/tests/test_no_v2_imports.py",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Implement Alchemy Creative Agent 3.0 Foundation.",
                documents=[prompt, scope],
                repository_path=repo,
                created_at="2026-06-18T00:00:00+00:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()
            payload = bundle.to_dict()

        scope_payload = payload["scope_controls"]
        self.assertEqual(
            scope_payload["target_files"],
            [
                "alchemy_creative_agent_3_0/app/__init__.py",
                "alchemy_creative_agent_3_0/app/creative_core/central_brain.py",
                "alchemy_creative_agent_3_0/tests/test_end_to_end_planning.py",
                "alchemy_creative_agent_3_0/tests/test_no_v2_imports.py",
            ],
        )
        implementation_nodes = [
            node
            for node in graph["nodes"]
            if node["type"] not in {"architecture", "test", "review", "release"}
        ]
        self.assertEqual(len(implementation_nodes), 1)
        self.assertEqual(implementation_nodes[0]["title"], "Implement scoped V3 foundation target files")
        for path in implementation_nodes[0]["relevant_files"]:
            self.assertTrue(path.startswith("alchemy_creative_agent_3_0/app/") or path.startswith("alchemy_creative_agent_3_0/tests/"))
            self.assertNotIn("custom_media_agent_2_0", path)
            self.assertNotIn("src_skeleton", path)
        verify_nodes = [node for node in graph["nodes"] if node["type"] == "test"]
        self.assertEqual(verify_nodes[0]["commands_to_run"], ["python -B -m pytest alchemy_creative_agent_3_0/tests"])
        self.assertNotIn("tests/test_legacy.py", verify_nodes[0].get("relevant_files", []))
        for node in graph["nodes"]:
            for path in node.get("relevant_files", []):
                self.assertNotIn("custom_media_agent_2_0", path)
                self.assertNotIn("src_skeleton", path)

    def test_scope_control_parser_reads_directory_blocks_and_target_files(self) -> None:
        controls = extract_scope_controls(
            "\n".join(
                [
                    "All implementation code and tests must live under:",
                    "```text",
                    "alchemy_creative_agent_3_0/app/",
                    "alchemy_creative_agent_3_0/tests/",
                    "```",
                    "Do not edit any file under these paths:",
                    "",
                    "```text",
                    "custom_media_agent_2_0/",
                    "src_skeleton/",
                    "```",
                    "Target files: alchemy_creative_agent_3_0/app/__init__.py, alchemy_creative_agent_3_0/tests/test_no_v2_imports.py",
                ]
            )
        )

        self.assertIn("alchemy_creative_agent_3_0/app/", controls.allowed_prefixes)
        self.assertIn("alchemy_creative_agent_3_0/tests/", controls.allowed_prefixes)
        self.assertIn("custom_media_agent_2_0/", controls.protected_prefixes)
        self.assertIn("src_skeleton/", controls.protected_prefixes)
        self.assertEqual(
            controls.target_files,
            [
                "alchemy_creative_agent_3_0/app/__init__.py",
                "alchemy_creative_agent_3_0/tests/test_no_v2_imports.py",
            ],
        )

    def test_repair_narrative_allowed_scope_does_not_seed_scope_controls(self) -> None:
        repair_text = "\n".join(
            [
                "- B-T006-2: Worker completed a CRM-ready API key workflow in allowed scope.",
                "- Previous relevant files: frontend/package.json, frontend/src/router/index.ts.",
                "- The route is outside allowed_files: frontend/src/components/layout/AppSidebar.vue.",
                "- Keep the phase scope controls and protected paths unchanged.",
            ]
        )

        controls = extract_scope_controls(repair_text)

        self.assertEqual(controls.allowed_prefixes, [])
        self.assertEqual(controls.protected_prefixes, [])
        self.assertEqual(controls.target_files, [])
        self.assertIn(
            "frontend/src/components/layout/AppSidebar.vue",
            explicit_paths_from_text(repair_text),
        )

    def test_v3_independence_text_infers_owned_scope_and_protected_legacy_paths(self) -> None:
        controls = extract_scope_controls(
            "\n".join(
                [
                    "# Alchemy Creative Agent 3.0",
                    "Build the independent V3 skeleton under:",
                    "alchemy_creative_agent_3_0/app/",
                    "V3.0 must be fully independent from V1/V2.",
                    "Do not import or call any V1/V2 runtime modules.",
                ]
            )
        )

        self.assertIn("alchemy_creative_agent_3_0/", controls.allowed_prefixes)
        self.assertIn("alchemy_creative_agent_3_0/app/", controls.allowed_prefixes)
        self.assertIn("custom_media_agent_2_0/", controls.protected_prefixes)
        self.assertIn("src_skeleton/", controls.protected_prefixes)

    def test_large_refactor_document_builds_single_integration_task(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "internal" / "service").mkdir(parents=True)
            (repo / "frontend" / "src").mkdir(parents=True)
            (repo / "docs").mkdir()
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "backend" / "internal" / "service" / "gateway.go").write_text("package service\n", encoding="utf-8")
            (repo / "frontend" / "src" / "App.tsx").write_text("export function App() { return null }\n", encoding="utf-8")
            spec = root / "billing.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Billing Core Development Plan",
                        "## Requirements",
                        "- Must remove token relay gateway behavior from backend and frontend.",
                        "- Must support identity, billing, wallet, metering, and statistics.",
                        "- Must boot from its own configuration.",
                        "",
                        "## Acceptance Criteria",
                        "- Fresh install works with only its own config.",
                        "- No token relay route remains registered.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="整体改造为独立运行的 Billing Core 程序",
                documents=[spec],
                repository_path=repo,
                created_at="2026-06-24T00:00:00+00:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()
            payload = bundle.to_dict()

        self.assertEqual(payload["scope_controls"]["boundary_mode"], "large_refactor")
        implementation_nodes = [
            node
            for node in graph["nodes"]
            if node["type"] not in {"architecture", "test", "review", "release"}
        ]
        self.assertEqual(len(implementation_nodes), 1)
        implementation = implementation_nodes[0]
        self.assertEqual(implementation["type"], "integration")
        self.assertEqual(implementation["boundary_mode"], "large_refactor")
        self.assertIn("backend/**", implementation["relevant_files"])
        self.assertIn("frontend/**", implementation["relevant_files"])

    def test_large_refactor_constraint_with_underscore_builds_single_integration_task(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "internal").mkdir(parents=True)
            (repo / "frontend" / "src").mkdir(parents=True)
            (repo / "backend" / "internal" / "gateway.go").write_text("package internal\n", encoding="utf-8")
            (repo / "frontend" / "src" / "router.ts").write_text("export const routes = []\n", encoding="utf-8")
            spec = root / "phase.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Phase 1",
                        "## Requirements",
                        "- Must update module, README, Docker/service name, and frontend title.",
                        "- Must keep backend and frontend builds available.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Convert the product into a standalone billing core.",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-24T00:00:00+00:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()
            payload = bundle.to_dict()

        self.assertEqual(payload["scope_controls"]["boundary_mode"], "large_refactor")
        implementation_nodes = [
            node
            for node in graph["nodes"]
            if node["type"] not in {"architecture", "test", "review", "release"}
        ]
        self.assertEqual(len(implementation_nodes), 1)
        implementation = implementation_nodes[0]
        self.assertEqual(implementation["type"], "integration")
        self.assertEqual(implementation["boundary_mode"], "large_refactor")
        self.assertIn("backend/**", implementation["relevant_files"])
        self.assertIn("frontend/**", implementation["relevant_files"])

    def test_large_refactor_frontend_phase_survives_repository_index_cap(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "internal").mkdir(parents=True)
            (repo / "frontend" / "src").mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/backend\n", encoding="utf-8")
            for index in range(25):
                (repo / "backend" / "internal" / f"service_{index:03d}.go").write_text("package internal\n", encoding="utf-8")
            (repo / "frontend" / "src" / "router.ts").write_text("export const routes = [];\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "phase.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Phase 7: 前端收口",
                        "## Requirements",
                        "- 删除 router 中旧页面。",
                        "- 删除菜单和可直达页面。",
                        "- 清理 API service 引用。",
                        "- 改造 Wallet、Recharge、Usage、Admin Users、Payment Providers 页面。",
                        "- 普通用户能完成余额查看、兑换、充值订单、API Key、用量查询。",
                        "- 管理员能完成用户管理、余额调整、订单查询、支付配置、兑换码管理、用量查询。",
                        "- 前端没有 token 中转站产品文案。",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Convert Billing Core into a standalone CRM billing product.",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-24T00:00:00+00:00",
            )

            bundle = ContextBundleBuilder(repository_indexer=RepositoryIndexer(max_files=5)).build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        implementation_nodes = [
            node
            for node in graph["nodes"]
            if node["type"] not in {"architecture", "test", "review", "release"}
        ]
        self.assertGreaterEqual(len(implementation_nodes), 5)
        titles = [node["title"] for node in implementation_nodes]
        self.assertIn("Close frontend router, menu, and direct pages", titles)
        self.assertIn("Clean frontend API service references", titles)
        self.assertIn("Convert wallet recharge and payment surfaces", titles)
        self.assertIn("Convert redeem code pages to balance-only flows", titles)
        self.assertIn("Close usage API key and admin user workflows", titles)
        self.assertIn("Sweep frontend product copy and i18n", titles)

        for implementation in implementation_nodes:
            self.assertEqual(implementation["assigned_agent"], "frontend")
            self.assertEqual(implementation["boundary_mode"], "large_refactor")
            self.assertTrue(any(path.startswith("frontend/") for path in implementation["relevant_files"]))
            self.assertNotEqual(implementation["commands_to_run"], ["static artifact inspection"])
            self.assertIn("npm --prefix frontend test", implementation["commands_to_run"])
            self.assertNotIn("cd backend && go test ./...", implementation["commands_to_run"])

        api_task = next(node for node in implementation_nodes if node["title"] == "Clean frontend API service references")
        self.assertIn("frontend/src/api/**", api_task["relevant_files"])
        verifier = next(node for node in graph["nodes"] if node["type"] == "test")
        self.assertIn("cd backend && go test ./...", verifier["commands_to_run"])
        for implementation in implementation_nodes:
            self.assertIn(implementation["id"], verifier["dependencies"])

    def test_large_refactor_frontend_phase_uses_pnpm_lock_commands(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend").mkdir(parents=True)
            (repo / "frontend" / "src").mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/backend\n", encoding="utf-8")
            (repo / "frontend" / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
            (repo / "frontend" / "src" / "router.ts").write_text("export const routes = [];\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "phase.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Phase 7: 前端收口",
                        "## Requirements",
                        "- 删除 router 中旧页面。",
                        "- 删除菜单和可直达页面。",
                        "- 清理 API service 引用。",
                        "- 改造 Wallet、Recharge、Usage、Admin Users、Payment Providers 页面。",
                        "- 普通用户能完成余额查看、兑换、充值订单、API Key、用量查询。",
                        "- 管理员能完成用户管理、余额调整、订单查询、支付配置、兑换码管理、用量查询。",
                        "- 前端没有 token 中转站产品文案。",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Convert Billing Core into a standalone CRM billing product.",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-24T00:00:00+00:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        implementation_nodes = [
            node
            for node in graph["nodes"]
            if node["type"] not in {"architecture", "test", "review", "release"}
        ]
        self.assertGreaterEqual(len(implementation_nodes), 5)
        for implementation in implementation_nodes:
            self.assertEqual(implementation["commands_to_run"][0], "pnpm --dir frontend install --frozen-lockfile")
            self.assertIn("pnpm --dir frontend test", implementation["commands_to_run"])
            self.assertNotIn("npm --prefix frontend test", implementation["commands_to_run"])
        payment_task = next(node for node in implementation_nodes if node["title"] == "Convert wallet recharge and payment surfaces")
        self.assertIn("frontend/src/views/admin/orders/**", payment_task["relevant_files"])

    def test_large_refactor_frontend_repair_docs_do_not_collapse_to_scoped_router_task(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend").mkdir(parents=True)
            (repo / "frontend" / "src" / "router").mkdir(parents=True)
            (repo / "frontend" / "src" / "components" / "account").mkdir(parents=True)
            (repo / "frontend" / "src" / "components" / "admin" / "usage").mkdir(parents=True)
            (repo / "frontend" / "src" / "components" / "layout").mkdir(parents=True)
            (repo / "frontend" / "src" / "composables").mkdir(parents=True)
            (repo / "frontend" / "src" / "constants").mkdir(parents=True)
            (repo / "frontend" / "src" / "views" / "admin").mkdir(parents=True)
            (repo / "frontend" / "src" / "views" / "auth").mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/backend\n", encoding="utf-8")
            (repo / "frontend" / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            (repo / "frontend" / "src" / "router" / "index.ts").write_text("export const routes = [];\n", encoding="utf-8")
            (repo / "frontend" / "src" / "components" / "account" / "AccountUsageCell.vue").write_text("<template />\n", encoding="utf-8")
            (repo / "frontend" / "src" / "components" / "admin" / "usage" / "UsageTable.vue").write_text("<template />\n", encoding="utf-8")
            (repo / "frontend" / "src" / "components" / "layout" / "AppSidebar.vue").write_text("<template />\n", encoding="utf-8")
            (repo / "frontend" / "src" / "composables" / "usePersistedPageSize.ts").write_text("export const pageSize = 1000;\n", encoding="utf-8")
            (repo / "frontend" / "src" / "constants" / "channelMonitor.ts").write_text("export const legacy = true;\n", encoding="utf-8")
            (repo / "frontend" / "src" / "views" / "admin" / "DashboardView.vue").write_text("<template />\n", encoding="utf-8")
            (repo / "frontend" / "src" / "views" / "auth" / "EmailVerifyView.vue").write_text("<template />\n", encoding="utf-8")
            phase = root / "phase.md"
            phase.write_text(
                "\n".join(
                    [
                        "# Phase: Frontend closure",
                        "## Requirements",
                        "- Must close frontend router, menu, and direct pages.",
                        "- Must clean frontend API service references.",
                        "- Must convert wallet recharge, payment provider, and order surfaces.",
                        "- Must convert redeem code pages to balance-only flows.",
                        "- Must close usage API key and admin users workflows.",
                        "- Must sweep token relay product copy and i18n.",
                        "",
                        "## Boundary Mode",
                        "Scope boundary mode: large_refactor",
                    ]
                ),
                encoding="utf-8",
            )
            repair = root / "phase_repair.md"
            repair.write_text(
                "\n".join(
                    [
                        "# Auto Repair",
                        "## Focused Repair Scope",
                        "- B-T006-2: Worker completed the API key workflow in allowed scope.",
                        "- Previous relevant files: frontend/package.json, frontend/src/router/index.ts.",
                        "- Convert out-of-scope full-suite failures into focused follow-up tasks with expanded allowed files.",
                        "- Fix AccountUsageCell with frontend/src/components/account/AccountUsageCell.vue.",
                        "- Fix admin UsageTable with frontend/src/components/admin/usage/UsageTable.vue.",
                        "- Fix EmailVerifyView affiliate payload with frontend/src/views/auth/EmailVerifyView.vue.",
                        "- Fix persisted page-size default with frontend/src/composables/usePersistedPageSize.ts.",
                        "- Guard DashboardView cost formatting with frontend/src/views/admin/DashboardView.vue.",
                        "- Wire API key navigation through frontend/src/components/layout/AppSidebar.vue.",
                        "- Expand allowed_files to include frontend/src/components/**, frontend/src/composables/**, and frontend/src/constants/**, then remove remaining direct retired API callers.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Repair Billing Core frontend closure.",
                documents=[phase, repair],
                repository_path=repo,
                created_at="2026-06-27T00:00:00+00:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        self.assertEqual(bundle.scope_controls["boundary_mode"], "large_refactor")
        self.assertEqual(bundle.scope_controls["allowed_prefixes"], [])
        implementation_nodes = [
            node
            for node in graph["nodes"]
            if node["type"] not in {"architecture", "test", "review", "release"}
        ]
        self.assertGreaterEqual(len(implementation_nodes), 5)
        self.assertNotIn("Implement scoped V3 foundation target files", [node["title"] for node in implementation_nodes])
        for implementation in implementation_nodes:
            self.assertEqual(implementation["assigned_agent"], "frontend")
            self.assertEqual(implementation["boundary_mode"], "large_refactor")
            self.assertNotIn("cd backend && go test ./...", implementation["commands_to_run"])

        api_task = next(node for node in implementation_nodes if node["title"] == "Clean frontend API service references")
        self.assertIn("frontend/src/api/**", api_task["relevant_files"])
        self.assertIn("frontend/src/components/**", api_task["relevant_files"])
        self.assertIn("frontend/src/composables/**", api_task["relevant_files"])
        self.assertIn("frontend/src/constants/**", api_task["relevant_files"])

        usage_task = next(node for node in implementation_nodes if node["title"] == "Close usage API key and admin user workflows")
        self.assertIn("frontend/src/components/account/**", usage_task["relevant_files"])
        self.assertIn("frontend/src/components/admin/usage/**", usage_task["relevant_files"])
        self.assertIn("frontend/src/components/layout/AppSidebar.vue", usage_task["relevant_files"])
        self.assertIn("frontend/src/composables/**", usage_task["relevant_files"])
        self.assertIn("frontend/src/views/admin/DashboardView.vue", usage_task["relevant_files"])
        self.assertIn("frontend/src/views/auth/**", usage_task["relevant_files"])

    def test_large_refactor_frontend_timeout_repair_splits_copy_sweep_task(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend").mkdir(parents=True)
            (repo / "frontend" / "src" / "i18n").mkdir(parents=True)
            (repo / "frontend" / "src" / "views").mkdir(parents=True)
            (repo / "frontend" / "src" / "components").mkdir(parents=True)
            (repo / "frontend" / "src" / "stores").mkdir(parents=True)
            (repo / "frontend" / "src" / "constants").mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/backend\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            (repo / "frontend" / "src" / "i18n" / "en.ts").write_text("export default { tokenRelay: 'Token relay' }\n", encoding="utf-8")
            (repo / "frontend" / "src" / "views" / "HomeView.vue").write_text("<template>token relay</template>\n", encoding="utf-8")
            phase = root / "phase.md"
            phase.write_text(
                "\n".join(
                    [
                        "# Phase: Frontend closure",
                        "## Requirements",
                        "- Must close frontend router, menu, and direct pages.",
                        "- Must clean frontend API service references.",
                        "- Must convert wallet recharge, payment provider, and order surfaces.",
                        "- Must convert redeem code pages to balance-only flows.",
                        "- Must close usage API key and admin users workflows.",
                        "- Must sweep token relay product copy and i18n.",
                        "",
                        "## Boundary Mode",
                        "Scope boundary mode: large_refactor",
                    ]
                ),
                encoding="utf-8",
            )
            repair = root / "phase_repair_timeout.md"
            repair.write_text(
                "\n".join(
                    [
                        "# Auto Repair",
                        "## Focused Repair Scope",
                        "- Primary failed task IDs: T007.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Repair Billing Core frontend copy timeout.",
                documents=[phase, repair],
                repository_path=repo,
                created_at="2026-06-27T19:40:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        implementation_nodes = [
            node
            for node in graph["nodes"]
            if node["type"] not in {"architecture", "test", "review", "release"}
        ]
        titles = [node["title"] for node in implementation_nodes]
        self.assertIn("Sweep frontend i18n product copy", titles)
        self.assertIn("Sweep frontend view and component product copy", titles)
        self.assertNotIn("Sweep frontend product copy and i18n", titles)
        nodes_by_id = {node["id"]: node for node in graph["nodes"]}
        for task_id in ("T001", "T002", "T003", "T004", "T005", "T006"):
            self.assertEqual(nodes_by_id[task_id]["status"], "completed")
            self.assertTrue(
                any(item["type"] == "focused_repair_preserved_task" for item in nodes_by_id[task_id]["evidence"])
            )
        self.assertEqual(nodes_by_id["T007"]["status"], "pending")
        self.assertEqual(nodes_by_id["T008"]["status"], "pending")

        i18n_task = next(node for node in implementation_nodes if node["title"] == "Sweep frontend i18n product copy")
        self.assertIn("frontend/src/i18n/**", i18n_task["relevant_files"])
        self.assertNotIn("frontend/src/views/**", i18n_task["relevant_files"])

        view_task = next(
            node for node in implementation_nodes if node["title"] == "Sweep frontend view and component product copy"
        )
        self.assertIn("frontend/src/views/**", view_task["relevant_files"])
        self.assertIn("frontend/src/components/**", view_task["relevant_files"])
        self.assertIn("frontend/src/constants/**", view_task["relevant_files"])

    def test_large_refactor_frontend_timeout_repair_splits_remaining_closure_task(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend").mkdir(parents=True)
            (repo / "frontend" / "src" / "api").mkdir(parents=True)
            (repo / "frontend" / "src" / "components" / "layout").mkdir(parents=True)
            (repo / "frontend" / "src" / "composables").mkdir(parents=True)
            (repo / "frontend" / "src" / "constants").mkdir(parents=True)
            (repo / "frontend" / "src" / "i18n").mkdir(parents=True)
            (repo / "frontend" / "src" / "router").mkdir(parents=True)
            (repo / "frontend" / "src" / "stores").mkdir(parents=True)
            (repo / "frontend" / "src" / "views").mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/backend\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(
                json.dumps({"scripts": {"test": "vitest run"}}),
                encoding="utf-8",
            )
            phase = root / "phase.md"
            phase.write_text(
                "\n".join(
                    [
                        "# Phase: Frontend closure",
                        "## Requirements",
                        "- Must close frontend router, menu, and direct pages.",
                        "- Must clean frontend API service references.",
                        "- Must convert wallet recharge, payment provider, and order surfaces.",
                        "- Must convert redeem code pages to balance-only flows.",
                        "- Must close usage API key and admin users workflows.",
                        "- Must sweep token relay product copy and i18n.",
                        "- Must close residual CRM frontend usability gaps and visible escape hatches.",
                        "",
                        "## Boundary Mode",
                        "Scope boundary mode: large_refactor",
                    ]
                ),
                encoding="utf-8",
            )
            repair = root / "phase_repair_t009_timeout.md"
            repair.write_text(
                "\n".join(
                    [
                        "# Auto Repair",
                        "## Focused Repair Scope",
                        "- Primary failed task IDs: T009.",
                        "- Completed tasks to preserve: T007, T008, T001, T002, T003, T004, T005, T006.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T009 - Complete remaining frontend closure requirements",
                        "- Previous relevant files: frontend/**, frontend/package.json.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Repair Billing Core remaining frontend closure timeout.",
                documents=[phase, repair],
                repository_path=repo,
                created_at="2026-06-27T21:20:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        implementation_nodes = [
            node
            for node in graph["nodes"]
            if node["type"] not in {"architecture", "test", "review", "release"}
        ]
        titles = [node["title"] for node in implementation_nodes]
        self.assertNotIn("Complete remaining frontend closure requirements", titles)
        self.assertIn("Complete remaining frontend shell and route closure", titles)
        self.assertIn("Complete remaining frontend state and API closure", titles)
        self.assertIn("Complete remaining frontend view workflow closure", titles)

        nodes_by_id = {node["id"]: node for node in graph["nodes"]}
        for task_id in ("T001", "T002", "T003", "T004", "T005", "T006", "T007", "T008"):
            self.assertEqual(nodes_by_id[task_id]["status"], "completed")
            self.assertTrue(
                any(item["type"] == "focused_repair_preserved_task" for item in nodes_by_id[task_id]["evidence"])
            )
        for task_id in ("T009", "T010", "T011"):
            self.assertEqual(nodes_by_id[task_id]["status"], "pending")
            self.assertNotIn("frontend/**", nodes_by_id[task_id]["relevant_files"])

        shell_task = next(
            node for node in implementation_nodes if node["title"] == "Complete remaining frontend shell and route closure"
        )
        self.assertIn("frontend/src/router/**", shell_task["relevant_files"])
        self.assertIn("frontend/src/components/layout/**", shell_task["relevant_files"])

        state_task = next(
            node for node in implementation_nodes if node["title"] == "Complete remaining frontend state and API closure"
        )
        self.assertIn("frontend/src/api/**", state_task["relevant_files"])
        self.assertIn("frontend/src/composables/**", state_task["relevant_files"])
        self.assertIn("frontend/src/constants/**", state_task["relevant_files"])

        view_task = next(
            node for node in implementation_nodes if node["title"] == "Complete remaining frontend view workflow closure"
        )
        self.assertIn("frontend/src/views/**", view_task["relevant_files"])
        self.assertIn("frontend/src/components/**", view_task["relevant_files"])

    def test_large_refactor_schema_timeout_repair_splits_backend_build_task(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for directory in (
                ".github/workflows",
                "backend/ent/schema",
                "backend/ent/migrate",
                "backend/internal/config",
                "backend/internal/domain",
                "backend/internal/handler",
                "backend/internal/repository",
                "backend/internal/server",
                "backend/internal/service",
                "frontend/src",
            ):
                (repo / directory).mkdir(parents=True)
            (repo / ".github" / "workflows" / "backend-ci.yml").write_text("name: backend\n", encoding="utf-8")
            (repo / "backend" / "go.mod").write_text("module example.com/backend\n", encoding="utf-8")
            (repo / "backend" / "go.sum").write_text("", encoding="utf-8")
            (repo / "backend" / "ent" / "schema" / "user.go").write_text("package schema\n", encoding="utf-8")
            (repo / "backend" / "internal" / "service" / "payment.go").write_text("package service\n", encoding="utf-8")
            (repo / "frontend" / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(
                json.dumps({"scripts": {"test": "vitest run", "build": "vite build", "typecheck": "vue-tsc"}}),
                encoding="utf-8",
            )
            phase = root / "phase.md"
            phase.write_text(
                "\n".join(
                    [
                        "# Phase 8: Schema pruning and build",
                        "## Requirements",
                        "- Must prune Ent schema for CRM billing only.",
                        "- Must regenerate Ent clients.",
                        "- Must update migrations.",
                        "- Must clean unused service/repository/test code.",
                        "- Must prove a fresh DB migration succeeds.",
                        "- Fresh DB migration must not create token relay tables.",
                        "- `go test ./backend/internal/...` must pass or leave only documented legacy tests.",
                        "- Frontend build/typecheck must pass.",
                        "",
                        "## Boundary Mode",
                        "Scope boundary mode: large_refactor",
                    ]
                ),
                encoding="utf-8",
            )
            repair = root / "phase_repair_001.md"
            repair.write_text(
                "\n".join(
                    [
                        "# Auto Repair For Phase 8",
                        "## Focused Repair Scope",
                        "- Primary failed task IDs: T002.",
                        "- Completed tasks to preserve: T001.",
                        "- Do not regenerate a broad phase graph when blocker task IDs identify a specific failed task.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T002 - Implement large refactor integration",
                        "- Previous relevant files: .github/**, backend/**, frontend/**, backend/go.mod, frontend/package.json, frontend/pnpm-lock.yaml.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Repair Billing Core schema pruning timeout.",
                documents=[phase, repair],
                repository_path=repo,
                created_at="2026-06-28T03:45:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        implementation_nodes = [
            node
            for node in graph["nodes"]
            if node["type"] not in {"architecture", "test", "review", "release"}
        ]
        titles = [node["title"] for node in implementation_nodes]
        self.assertNotIn("Implement large refactor integration", titles)
        self.assertNotIn("Prune legacy Ent schemas and table contracts", titles)
        self.assertIn("Prune Ent schema definitions", titles)
        self.assertIn("Align Ent migration and server table contracts", titles)
        self.assertIn("Regenerate Ent clients and migration artifacts", titles)
        self.assertIn("Clean legacy backend services repositories and tests", titles)
        self.assertIn("Stabilize schema and build verification contracts", titles)

        nodes_by_id = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes_by_id["T001"]["status"], "completed")
        for node in implementation_nodes:
            self.assertEqual(node["assigned_agent"], "backend")
            self.assertEqual(node["boundary_mode"], "large_refactor")
            self.assertNotIn("backend/**", node["relevant_files"])
            self.assertNotIn("frontend/**", node["relevant_files"])

        schema_task = next(node for node in implementation_nodes if node["title"] == "Prune Ent schema definitions")
        self.assertIn("backend/ent/schema/**", schema_task["relevant_files"])
        self.assertIn("backend/go.mod", schema_task["relevant_files"])
        self.assertNotIn("backend/ent/migrate/**", schema_task["relevant_files"])
        self.assertTrue(any("go test" in command for command in schema_task["commands_to_run"]))

        build_task = next(
            node for node in implementation_nodes if node["title"] == "Stabilize schema and build verification contracts"
        )
        self.assertIn("frontend/package.json", build_task["relevant_files"])
        self.assertIn("frontend/pnpm-lock.yaml", build_task["relevant_files"])
        self.assertTrue(any("pnpm --dir frontend" in command for command in build_task["commands_to_run"]))

    def test_schema_prune_timeout_repair_splits_timed_out_schema_task_again(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for directory in (
                "backend/ent/schema",
                "backend/ent/migrate",
                "backend/internal/domain",
                "backend/internal/server",
                "backend/internal/service",
                "frontend/src",
            ):
                (repo / directory).mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/backend\n", encoding="utf-8")
            (repo / "backend" / "ent" / "schema" / "relay.go").write_text("package schema\n", encoding="utf-8")
            (repo / "backend" / "ent" / "migrate" / "schema.go").write_text("package migrate\n", encoding="utf-8")
            (repo / "backend" / "internal" / "server" / "routes.go").write_text("package server\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            phase = root / "phase.md"
            phase.write_text(
                "\n".join(
                    [
                        "# Phase 8: Schema pruning and build",
                        "## Requirements",
                        "- Must prune Ent schema for CRM billing only.",
                        "- Must regenerate Ent clients.",
                        "- Must update migrations.",
                        "- Must clean unused service/repository/test code.",
                        "- Must prove a fresh DB migration succeeds.",
                        "- Fresh DB migration must not create token relay tables.",
                        "- `go test ./backend/internal/...` must pass or leave only documented legacy tests.",
                        "- Frontend build/typecheck must pass.",
                        "",
                        "## Boundary Mode",
                        "Scope boundary mode: large_refactor",
                    ]
                ),
                encoding="utf-8",
            )
            repair = root / "phase_repair_002.md"
            repair.write_text(
                "\n".join(
                    [
                        "# Auto Repair For Phase 8",
                        "## Focused Repair Scope",
                        "- Primary failed task IDs: T002.",
                        "- Completed tasks to preserve: T001.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T002 - Prune legacy Ent schemas and table contracts",
                        "- Previous relevant files: backend/ent/schema/**, backend/ent/migrate/**, backend/internal/domain/**, backend/internal/server/**, backend/cmd/server/**, backend/go.mod, backend/ent/migrate/schema.go.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Repair Billing Core schema prune timeout.",
                documents=[phase, repair],
                repository_path=repo,
                created_at="2026-06-28T05:05:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        implementation_nodes = [
            node
            for node in graph["nodes"]
            if node["type"] not in {"architecture", "test", "review", "release"}
        ]
        titles = [node["title"] for node in implementation_nodes]
        self.assertNotIn("Prune legacy Ent schemas and table contracts", titles)
        self.assertIn("Prune Ent schema definitions", titles)
        self.assertIn("Align Ent migration and server table contracts", titles)

        nodes_by_id = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes_by_id["T001"]["status"], "completed")
        schema_task = next(node for node in implementation_nodes if node["title"] == "Prune Ent schema definitions")
        self.assertIn("backend/ent/schema/**", schema_task["relevant_files"])
        self.assertNotIn("backend/ent/migrate/**", schema_task["relevant_files"])
        self.assertNotIn("backend/internal/server/**", schema_task["relevant_files"])

        migration_task = next(
            node for node in implementation_nodes if node["title"] == "Align Ent migration and server table contracts"
        )
        self.assertIn("backend/ent/migrate/**", migration_task["relevant_files"])
        self.assertIn("backend/internal/server/**", migration_task["relevant_files"])
        self.assertNotIn("backend/internal/service/**", migration_task["relevant_files"])

    def test_schema_migration_timeout_repair_splits_timed_out_contract_task_again(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for directory in (
                "backend/ent/schema",
                "backend/ent/migrate",
                "backend/internal/domain",
                "backend/internal/server",
                "backend/cmd/server",
                "backend/internal/service",
                "frontend/src",
            ):
                (repo / directory).mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/backend\n", encoding="utf-8")
            (repo / "backend" / "ent" / "schema" / "billing.go").write_text("package schema\n", encoding="utf-8")
            (repo / "backend" / "ent" / "migrate" / "schema.go").write_text("package migrate\n", encoding="utf-8")
            (repo / "backend" / "internal" / "domain" / "tables.go").write_text("package domain\n", encoding="utf-8")
            (repo / "backend" / "internal" / "server" / "routes.go").write_text("package server\n", encoding="utf-8")
            (repo / "backend" / "cmd" / "server" / "main.go").write_text("package main\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"build": "vite build"}}), encoding="utf-8")
            phase = root / "phase.md"
            phase.write_text(
                "\n".join(
                    [
                        "# Phase 8: Schema pruning and build",
                        "## Requirements",
                        "- Must prune Ent schema for CRM billing only.",
                        "- Must regenerate Ent clients.",
                        "- Must update migrations.",
                        "- Must clean unused service/repository/test code.",
                        "- Must prove a fresh DB migration succeeds.",
                        "- Fresh DB migration must not create token relay tables.",
                        "- `go test ./backend/internal/...` must pass.",
                        "- Frontend build/typecheck must pass.",
                        "",
                        "## Boundary Mode",
                        "Scope boundary mode: large_refactor",
                    ]
                ),
                encoding="utf-8",
            )
            t002_repair = root / "phase_repair_002.md"
            t002_repair.write_text(
                "\n".join(
                    [
                        "# Auto Repair For Phase 8",
                        "## Repairable Blockers",
                        "- B-T002-1: T002 exceeded the Codex worker timeout. Stop instead of launching a same-scope debug task. (tasks: T002)",
                        "",
                        "## Focused Repair Scope",
                        "- Primary failed task IDs: T002.",
                        "- Completed tasks to preserve: T001.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "### Task T002 - Prune legacy Ent schemas and table contracts",
                        "- Previous relevant files: backend/ent/schema/**, backend/ent/migrate/**, backend/internal/domain/**, backend/internal/server/**, backend/cmd/server/**, backend/go.mod, backend/ent/migrate/schema.go.",
                        "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            t003_repair = root / "phase_repair_003.md"
            t003_repair.write_text(
                "\n".join(
                    [
                        "# Auto Repair For Phase 8",
                        "## Repairable Blockers",
                        "- B-T003-1: T003 exceeded the Codex worker timeout. Stop instead of launching a same-scope debug task. (tasks: T003)",
                        "",
                        "## Focused Repair Scope",
                        "- Primary failed task IDs: T003.",
                        "- Completed tasks to preserve: T002, T001.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "### Task T003 - Align Ent migration and server table contracts",
                        "- Previous relevant files: backend/ent/migrate/**, backend/internal/domain/**, backend/internal/server/**, backend/cmd/server/**, backend/go.mod, backend/ent/migrate/schema.go.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Repair Billing Core migration/server contract timeout.",
                documents=[phase, t002_repair, t003_repair],
                repository_path=repo,
                created_at="2026-06-28T06:35:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        implementation_nodes = [
            node
            for node in graph["nodes"]
            if node["type"] not in {"architecture", "test", "review", "release"}
        ]
        titles = [node["title"] for node in implementation_nodes]
        self.assertNotIn("Align Ent migration and server table contracts", titles)
        self.assertIn("Align Ent migration contracts", titles)
        self.assertIn("Align server and domain table contracts", titles)
        self.assertIn("Regenerate Ent clients and migration artifacts", titles)

        nodes_by_id = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes_by_id["T001"]["status"], "completed")
        self.assertEqual(nodes_by_id["T002"]["status"], "completed")
        migration_task = next(node for node in implementation_nodes if node["title"] == "Align Ent migration contracts")
        self.assertIn("backend/ent/migrate/**", migration_task["relevant_files"])
        self.assertNotIn("backend/internal/server/**", migration_task["relevant_files"])
        self.assertNotIn("backend/internal/domain/**", migration_task["relevant_files"])

        server_task = next(node for node in implementation_nodes if node["title"] == "Align server and domain table contracts")
        self.assertIn("backend/internal/server/**", server_task["relevant_files"])
        self.assertIn("backend/internal/domain/**", server_task["relevant_files"])
        self.assertNotIn("backend/ent/migrate/**", server_task["relevant_files"])
        self.assertNotIn("backend/internal/service/**", server_task["relevant_files"])

    def test_large_refactor_frontend_timeout_repair_splits_state_api_closure_task(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for directory in (
                "backend",
                "frontend/src/api",
                "frontend/src/components",
                "frontend/src/composables",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/router",
                "frontend/src/stores",
                "frontend/src/types",
                "frontend/src/utils",
                "frontend/src/views",
            ):
                (repo / directory).mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/backend\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(
                json.dumps({"scripts": {"test": "vitest run"}}),
                encoding="utf-8",
            )
            phase = root / "phase.md"
            phase.write_text(
                "\n".join(
                    [
                        "# Phase: Frontend closure",
                        "## Requirements",
                        "- Must close frontend router, menu, and direct pages.",
                        "- Must clean frontend API service references.",
                        "- Must convert wallet recharge, payment provider, and order surfaces.",
                        "- Must convert redeem code pages to balance-only flows.",
                        "- Must close usage API key and admin users workflows.",
                        "- Must sweep token relay product copy and i18n.",
                        "- Must close residual CRM frontend usability gaps and visible escape hatches.",
                        "",
                        "## Boundary Mode",
                        "Scope boundary mode: large_refactor",
                    ]
                ),
                encoding="utf-8",
            )
            repair_t009 = root / "phase_repair_007.md"
            repair_t009.write_text(
                "\n".join(
                    [
                        "# Auto Repair",
                        "## Focused Repair Scope",
                        "- Primary failed task IDs: T009.",
                        "- Completed tasks to preserve: T007, T008, T001, T002, T003, T004, T005, T006.",
                        "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            repair_t010 = root / "phase_repair_resume_004.md"
            repair_t010.write_text(
                "\n".join(
                    [
                        "# Auto Repair",
                        "## Focused Repair Scope",
                        "- Primary failed task IDs: T010.",
                        "- Completed tasks to preserve: T009, T001, T002, T003, T004, T005, T006, T007, T008.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T010 - Complete remaining frontend state and API closure",
                        "- Previous relevant files: frontend/src/api/**, frontend/src/stores/**, frontend/src/composables/**, frontend/src/constants/**, frontend/src/types/**, frontend/src/utils/**, frontend/package.json.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Repair Billing Core frontend state/API closure timeout.",
                documents=[phase, repair_t009, repair_t010],
                repository_path=repo,
                created_at="2026-06-27T22:20:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        implementation_nodes = [
            node
            for node in graph["nodes"]
            if node["type"] not in {"architecture", "test", "review", "release"}
        ]
        titles = [node["title"] for node in implementation_nodes]
        self.assertNotIn("Complete remaining frontend state and API closure", titles)
        self.assertIn("Complete remaining frontend API service closure", titles)
        self.assertIn("Complete remaining frontend store and composable closure", titles)
        self.assertIn("Complete remaining frontend constants and type closure", titles)
        self.assertIn("Complete remaining frontend view workflow closure", titles)

        nodes_by_id = {node["id"]: node for node in graph["nodes"]}
        for task_id in ("T001", "T002", "T003", "T004", "T005", "T006", "T007", "T008", "T009"):
            self.assertEqual(nodes_by_id[task_id]["status"], "completed")
        for task_id in ("T010", "T011", "T012"):
            self.assertEqual(nodes_by_id[task_id]["status"], "pending")
            self.assertNotIn("frontend/**", nodes_by_id[task_id]["relevant_files"])

        api_task = next(
            node for node in implementation_nodes if node["title"] == "Complete remaining frontend API service closure"
        )
        self.assertIn("frontend/src/api/**", api_task["relevant_files"])
        self.assertIn("frontend/src/types/**", api_task["relevant_files"])

        store_task = next(
            node
            for node in implementation_nodes
            if node["title"] == "Complete remaining frontend store and composable closure"
        )
        self.assertIn("frontend/src/stores/**", store_task["relevant_files"])
        self.assertIn("frontend/src/composables/**", store_task["relevant_files"])
        self.assertIn("frontend/src/utils/**", store_task["relevant_files"])

        constants_task = next(
            node
            for node in implementation_nodes
            if node["title"] == "Complete remaining frontend constants and type closure"
        )
        self.assertIn("frontend/src/constants/**", constants_task["relevant_files"])
        self.assertIn("frontend/src/types/**", constants_task["relevant_files"])

    def test_focused_timeout_repair_matches_task_inside_primary_failed_id_list(self) -> None:
        requirements = [
            Requirement(
                id="REQ-001",
                source_document_id="repair",
                text=(
                    "Primary failed task IDs: T012, T010.\n"
                    "Task T010 previously exceeded the Codex worker timeout and must remain split/checkpointed."
                ),
            )
        ]

        self.assertTrue(focused_timeout_repair_for_task(requirements, "T010"))

    def test_completed_verification_repair_creates_unpreserved_frontend_task(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for directory in (
                "backend",
                "frontend/src/components/admin",
                "frontend/src/views/user",
                "frontend/src/router",
            ):
                (repo / directory).mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/backend\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(
                json.dumps({"scripts": {"build": "vite build", "test": "vitest run"}}),
                encoding="utf-8",
            )
            (repo / "frontend" / "src" / "components" / "admin" / "AdminComplianceDialog.vue").write_text(
                "<script setup lang=\"ts\"></script>\n",
                encoding="utf-8",
            )
            (repo / "frontend" / "src" / "router" / "index.ts").write_text(
                "export const routes = [];\n",
                encoding="utf-8",
            )
            phase = root / "phase.md"
            phase.write_text(
                "\n".join(
                    [
                        "# Phase: Frontend closure",
                        "## Requirements",
                        "- Must close frontend router, menu, and direct pages.",
                        "- Must close residual CRM frontend usability gaps and visible escape hatches.",
                        "",
                        "## Boundary Mode",
                        "Scope boundary mode: large_refactor",
                    ]
                ),
                encoding="utf-8",
            )
            repair = root / "phase_repair.md"
            repair.write_text(
                "\n".join(
                    [
                        "# Auto Repair",
                        "## Failing Verification Issues",
                        "- Must repair T014 verification issue: pnpm --dir frontend run build failed because Rollup could not resolve docs/legal/admin-compliance.zh.md from frontend/src/components/admin/AdminComplianceDialog.vue.",
                        "- Target files: docs/legal/admin-compliance.zh.md, docs/legal/admin-compliance.en.md, frontend/src/components/admin/AdminComplianceDialog.vue.",
                        "",
                        "## Focused Repair Scope",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Repair Billing Core frontend build verification.",
                documents=[phase, repair],
                repository_path=repo,
                created_at="2026-06-27T23:50:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        nodes_by_id = {node["id"]: node for node in graph["nodes"]}
        repair_task = next(node for node in graph["nodes"] if node["title"] == "Repair failing frontend verification assets")

        self.assertEqual(repair_task["id"], "T017")
        self.assertEqual(repair_task["status"], "pending")
        self.assertIn("docs/legal/admin-compliance.zh.md", repair_task["relevant_files"])
        self.assertIn("docs/legal/admin-compliance.en.md", repair_task["relevant_files"])
        self.assertIn("frontend/src/components/admin/AdminComplianceDialog.vue", repair_task["relevant_files"])
        self.assertEqual(nodes_by_id["T018"]["title"], "Preserve completed frontend closure coverage")
        self.assertEqual(nodes_by_id["T018"]["status"], "completed")
        self.assertTrue(
            any(item["type"] == "focused_repair_preserved_coverage" for item in nodes_by_id["T018"]["evidence"])
        )
        self.assertEqual(nodes_by_id["T019"]["title"], "Verify implementation against project checks")
        self.assertEqual(nodes_by_id["T020"]["title"], "Review delivery readiness")
        self.assertNotIn("Complete remaining frontend closure requirements", [node["title"] for node in graph["nodes"]])

    def test_docs_only_scope_builds_documentation_task_with_lightweight_verification(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "docs").mkdir(parents=True)
            (repo / "backend").mkdir()
            (repo / "backend" / "go.mod").write_text("module example.com/docs\n", encoding="utf-8")
            (repo / "docs" / "PLAN.md").write_text("# Plan\n", encoding="utf-8")
            spec = root / "phase.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Phase 0: Documentation Freeze",
                        "## Requirements",
                        "- Must confirm the development plan in docs/PLAN.md.",
                        "",
                        "## Scope Controls",
                        "Allowed implementation scope:",
                        "```text",
                        "docs/",
                        "```",
                        "",
                        "Protected paths:",
                        "```text",
                        "backend/",
                        "```",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Freeze planning documentation.",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: strict"],
                created_at="2026-06-24T00:00:00+00:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        implementation = next(node for node in graph["nodes"] if node["id"] == "T002")
        verifier = next(node for node in graph["nodes"] if node["type"] == "test")
        self.assertEqual(implementation["type"], "documentation")
        self.assertEqual(implementation["relevant_files"], ["docs/**"])
        self.assertEqual(implementation["commands_to_run"], ["static document inspection"])
        self.assertEqual(verifier["commands_to_run"], ["static document inspection"])
        self.assertEqual(verifier["relevant_files"], ["docs/**"])

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
