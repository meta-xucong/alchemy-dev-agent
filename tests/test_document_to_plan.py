from __future__ import annotations

import json
import shutil
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from context import ContextBundleBuilder, RepositoryIndexer
from context.models import ContextBundle, RepositoryFile, Requirement
from context.requirement_extractor import explicit_paths_from_text, extract_scope_controls
from intake import ProjectBriefBuilder
from intake.schema_validation import validate_context_bundle_contract
from planner import TaskGraphBuilder
from planner.task_graph_builder import focused_timeout_repair_for_task, should_group_as_single_web_game_delivery


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

    def test_new_canvas_game_documents_create_one_bootstrap_delivery_before_static_verification(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            repo.mkdir()
            spec = root / "game_spec.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Canvas Platformer",
                        "## Requirements",
                        "- Build a Vite browser canvas platformer game.",
                        "- Implement player running, jumping, and deterministic physics.",
                        "- Implement tilemap collision, enemies, coins, and a flag goal.",
                        "- Implement keyboard and gamepad controls with accessibility settings.",
                        "- Add original visual effects and sound feedback.",
                        "- Add automated game verification and a browser gameplay probe.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Build a modern browser platformer game.",
                documents=[spec],
                repository_path=repo,
                created_at="2026-07-11T00:00:00+00:00",
            )
            graph = TaskGraphBuilder().build(ContextBundleBuilder().build(brief)).to_dict()

        implementation_nodes = [
            node
            for node in graph["nodes"]
            if node["type"] not in {"architecture", "test", "review", "release"}
        ]
        self.assertEqual(len(implementation_nodes), 1)
        implementation = implementation_nodes[0]
        self.assertEqual(implementation["title"], "Implement complete web game delivery")
        self.assertEqual(implementation["assigned_agent"], "frontend")
        self.assertIn("index.html", implementation["relevant_files"])
        self.assertIn("src/engine.js", implementation["relevant_files"])
        self.assertIn("tests/static_checks.js", implementation["relevant_files"])
        self.assertEqual(
            implementation["commands_to_run"],
            ["npm test", "npm run build", "static artifact inspection"],
        )
        verifier = next(node for node in graph["nodes"] if node["title"] == "Verify implementation against project checks")
        self.assertEqual(verifier["dependencies"], [implementation["id"]])

    def test_large_refactor_boundary_keeps_greenfield_game_in_frontend_delivery(self) -> None:
        requirements = [
            Requirement(
                id=f"REQ-{index:03d}",
                source_document_id="spec",
                text=text,
            )
            for index, text in enumerate(
                [
                    "Build a Vite browser canvas platformer game.",
                    "Implement player movement and jumping physics.",
                    "Implement tilemap collision and enemies.",
                    "Implement accessible keyboard and gamepad controls.",
                    "Add automated browser gameplay verification.",
                ],
                start=1,
            )
        ]
        bundle = ContextBundle(
            project_id="game",
            objective="Build a browser platformer game.",
            requirements=requirements,
            scope_controls={"boundary_mode": ["large_refactor"]},
        )

        graph = TaskGraphBuilder().build(bundle).to_dict()
        implementation = next(node for node in graph["nodes"] if node["id"] == "T002")

        self.assertEqual(implementation["title"], "Implement complete web game delivery")
        self.assertEqual(implementation["assigned_agent"], "frontend")
        self.assertIn("src/main.js", implementation["relevant_files"])
        self.assertNotIn("backend/**", implementation["relevant_files"])

    def test_large_refactor_repair_of_existing_canvas_game_stays_frontend(self) -> None:
        bundle = ContextBundle(
            project_id="game-repair",
            objective="Repair browser gameplay acceptance.",
            requirements=[
                Requirement(
                    id="REQ-001",
                    source_document_id="repair",
                    text="Repair the browser gameplay hook so movement, jump, and restart are playable.",
                )
            ],
            repository_files=[
                RepositoryFile(path="index.html", kind="file"),
                RepositoryFile(path="package.json", kind="file"),
                RepositoryFile(path="src/main.js", kind="file"),
                RepositoryFile(path="src/engine.js", kind="file"),
                RepositoryFile(path="src/input.js", kind="file"),
                RepositoryFile(path="tests/static_checks.js", kind="file"),
            ],
            test_commands=["npm test", "npm run build"],
            scope_controls={"boundary_mode": ["large_refactor"]},
        )

        graph = TaskGraphBuilder().build(bundle).to_dict()
        implementation = next(node for node in graph["nodes"] if node["id"] == "T002")

        self.assertEqual(implementation["title"], "Implement complete web game delivery")
        self.assertEqual(implementation["assigned_agent"], "frontend")
        self.assertEqual(implementation["commands_to_run"], ["npm test", "npm run build", "static artifact inspection"])
        self.assertIn("src/main.js", implementation["relevant_files"])
        self.assertNotIn("backend/**", implementation["relevant_files"])

    def test_generated_one_line_repair_uses_existing_canvas_game_planning(self) -> None:
        bundle = ContextBundle(
            project_id="generated-game-repair",
            objective="Repair browser gameplay acceptance.",
            requirements=[
                Requirement(
                    id="REQ-001",
                    source_document_id="generated_one_line",
                    text="Repair the browser gameplay hook so movement, jump, and restart are playable.",
                )
            ],
            repository_files=[
                RepositoryFile(path="index.html", kind="file"),
                RepositoryFile(path="package.json", kind="file"),
                RepositoryFile(path="src/main.js", kind="file"),
                RepositoryFile(path="src/engine.js", kind="file"),
                RepositoryFile(path="src/input.js", kind="file"),
            ],
            test_commands=["npm test", "npm run build"],
        )

        graph = TaskGraphBuilder().build(bundle).to_dict()
        implementation = next(node for node in graph["nodes"] if node["id"] == "T002")

        self.assertEqual(implementation["title"], "Implement complete web game delivery")
        self.assertEqual(implementation["assigned_agent"], "frontend")
        self.assertEqual(implementation["commands_to_run"], ["npm test", "npm run build", "static artifact inspection"])

    def test_partial_web_game_scaffold_signals_are_still_one_delivery(self) -> None:
        requirements = [
            Requirement(
                id=f"REQ-{index:03d}",
                source_document_id="spec",
                text="Implement the documented game requirement.",
                related_files=[path],
            )
            for index, path in enumerate(
                ["index.html", "src/input.js", "src/physics.js", "src/engine.js", "tests/static_checks.js"],
                start=1,
            )
        ]

        self.assertTrue(should_group_as_single_web_game_delivery(requirements))

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

    def test_final_verification_document_builds_audit_test_graph(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend").mkdir(parents=True)
            (repo / "frontend").mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(
                json.dumps({"scripts": {"test": "vitest run", "build": "vite build"}}),
                encoding="utf-8",
            )
            spec = root / "final_verification.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Full-System Audit And Testing",
                        "",
                        "## Requirements",
                        "- Must challenge the completed roadmap against all development documents and report FINAL_AUDIT_STATUS: PASS or FAIL.",
                        "- Must run scenario, static, or browser simulation probes and report SIMULATION_TEST_STATUS: PASS or FAIL.",
                        "- Must run real repository tests, builds, or lints and report REAL_TEST_STATUS: PASS or FAIL.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-28T00:00:00+00:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        titles = [node["title"] for node in graph["nodes"]]
        self.assertIn("Audit final requirements and phase evidence", titles)
        self.assertIn("Run final simulation probes", titles)
        self.assertIn("Run final real repository checks", titles)
        self.assertNotIn("Implement large refactor integration", titles)
        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes["T001"]["title"], "Use deterministic final verification graph")
        self.assertEqual(nodes["T001"]["status"], "completed")
        self.assertEqual(nodes["T002"]["dependencies"], ["T001"])
        implementation_nodes = [
            node
            for node in graph["nodes"]
            if node["type"] not in {"architecture", "test", "review", "release"}
        ]
        self.assertEqual(implementation_nodes, [])

    def test_final_verification_repair_context_builds_editable_repair_task(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            (repo / "frontend" / "src" / "api").mkdir(parents=True)
            (repo / "frontend" / "src" / "i18n").mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Full-System Audit And Testing",
                        "",
                        "## T002 Debug Diagnosis And Retry Instructions",
                        "",
                        "## Requirements",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- Must grant edit access because the prior debug worker could not repair implementation defects because its allowed_files set was empty.",
                        "- Fresh database migrations must stop creating relay-era tables such as account pool, proxy, channel, channel monitor, and subscription structures.",
                        "- Backend Ent/schema/domain table contracts must be regenerated or reframed so forbidden relay-era tables are not part of the delivered Billing Core schema.",
                        "- Frontend admin API modules, i18n copy, tests, and reachable views must remove upstream account, proxy, channel, model-routing, channel-monitor, and subscription-plan surfaces.",
                        "- Must report FINAL_AUDIT_STATUS, SIMULATION_TEST_STATUS, REAL_TEST_STATUS, REQUIRED_ACTIONS, and BLOCKERS after repair.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-28T00:00:00+00:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes["T001"]["status"], "completed")
        self.assertEqual(nodes["T002"]["title"], "Repair final backend migration contracts")
        self.assertEqual(nodes["T002"]["type"], "integration")
        self.assertIn("backend/migrations/001_init.sql", nodes["T002"]["relevant_files"])
        self.assertIn("backend/migrations/003_subscription.sql", nodes["T002"]["relevant_files"])
        self.assertEqual(nodes["T003"]["title"], "Repair final backend Ent schema contracts")
        self.assertEqual(nodes["T003"]["dependencies"], ["T002"])
        self.assertIn("backend/ent/**", nodes["T003"]["relevant_files"])
        self.assertIn("backend/go.sum", nodes["T003"]["relevant_files"])
        self.assertIn("full backend test/build commands are reserved", nodes["T003"]["description"])
        self.assertEqual(nodes["T004"]["title"], "Repair final backend domain and repository contracts")
        self.assertIn("backend/internal/repository/**", nodes["T004"]["relevant_files"])
        self.assertIn("backend/go.sum", nodes["T004"]["relevant_files"])
        self.assertEqual(nodes["T005"]["title"], "Repair final backend service handler server contracts")
        self.assertIn("backend/internal/server/**", nodes["T005"]["relevant_files"])
        self.assertIn("backend/go.sum", nodes["T005"]["relevant_files"])
        self.assertEqual(nodes["T006"]["title"], "Repair final frontend API and i18n contracts")
        self.assertIn("frontend/src/api/**", nodes["T006"]["relevant_files"])
        self.assertIn("frontend/src/i18n/**", nodes["T006"]["relevant_files"])
        self.assertEqual(nodes["T007"]["title"], "Repair final frontend routes views and tests")
        self.assertEqual(nodes["T008"]["title"], "Audit final requirements and phase evidence")
        self.assertIn("T007", nodes["T008"]["dependencies"])

    def test_final_verification_backend_service_handler_timeout_is_narrowed_without_id_drift(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            (repo / "backend" / "internal" / "service").mkdir(parents=True)
            (repo / "backend" / "internal" / "handler").mkdir(parents=True)
            (repo / "backend" / "internal" / "server").mkdir(parents=True)
            (repo / "frontend" / "src" / "api").mkdir(parents=True)
            (repo / "frontend" / "src" / "i18n").mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_052.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_052",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- Must grant the repair worker edit access to backend migrations, Ent schema/generated files, backend domain/repository/service/handler/server contracts, and backend command wiring when those surfaces contain residual relay-era product concepts.",
                        "- Must grant the repair worker edit access to frontend API, i18n, router, view, component, composable, constants, type, store, and test files when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "- Must report FINAL_AUDIT_STATUS, SIMULATION_TEST_STATUS, REAL_TEST_STATUS, REQUIRED_ACTIONS, and BLOCKERS after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T005.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024, T025, T026, T027, T028, T029, T030, T031, T032, T033, T034, T035, T036, T037, T038, T039, T040, T041, T042, T043, T044, T045, T046, T047, T048, T049, T050, T051, T052, T053, T055, T056, T057, T058, T059.",
                        "- Preserve final frontend split tail graph shape: T056, T057, T058, T059.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T005 - Repair final backend service handler server contracts",
                        "- Previous relevant files: backend/internal/service/**, backend/internal/handler/**, backend/internal/server/**, backend/cmd/**, backend/go.mod, backend/go.sum.",
                        "- Worker summary: Codex worker timed out after 900 seconds plus 300 seconds of progress grace.",
                        "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-30T14:05:00+08:00",
            )

            graph = TaskGraphBuilder().build(ContextBundleBuilder().build(brief)).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes["T005"]["title"], "Repair final backend service contract leftovers")
        self.assertIn("backend/internal/service/**", nodes["T005"]["relevant_files"])
        self.assertIn("backend/internal/repository/**", nodes["T005"]["relevant_files"])
        self.assertNotIn("backend/internal/handler/**", nodes["T005"]["relevant_files"])
        self.assertNotIn("backend/internal/server/**", nodes["T005"]["relevant_files"])
        self.assertNotIn("backend/cmd/**", nodes["T005"]["relevant_files"])
        self.assertEqual(nodes["T006"]["status"], "completed")
        self.assertEqual(nodes["T060"]["title"], "Audit final requirements and phase evidence")
        self.assertIn("T005", nodes["T060"]["dependencies"])

    def test_final_verification_backend_domain_repository_timeout_is_narrowed_without_id_drift(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            (repo / "backend" / "internal" / "domain").mkdir(parents=True)
            (repo / "backend" / "internal" / "repository").mkdir(parents=True)
            (repo / "backend" / "internal" / "service").mkdir(parents=True)
            (repo / "backend" / "internal" / "handler").mkdir(parents=True)
            (repo / "backend" / "internal" / "server").mkdir(parents=True)
            (repo / "deploy").mkdir(parents=True)
            (repo / "frontend" / "src" / "api").mkdir(parents=True)
            (repo / "frontend" / "src" / "i18n").mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_056.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_055",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- Must grant the repair worker edit access to backend migrations, Ent schema/generated files, backend domain/repository/service/handler/server contracts, and backend command wiring when those surfaces contain residual relay-era product concepts.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "- Must report FINAL_AUDIT_STATUS, SIMULATION_TEST_STATUS, REAL_TEST_STATUS, REQUIRED_ACTIONS, and BLOCKERS after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T004.",
                        "- Focused timeout task IDs: T004.",
                        "- Completed tasks to preserve: T001, T002, T003, T007, T008, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024, T025, T026, T027, T028, T029, T030, T031, T032, T033, T034, T035, T036, T037, T038, T039, T040, T042, T043, T044, T045, T046, T047, T048, T049, T050, T051, T052, T053, T054, T055, T056, T057, T059.",
                        "- Preserve final frontend split tail graph shape: T056, T057, T058, T059.",
                        "- Preserve previous repair context from final_verification_repair_resume_055.md: AccountTypeUpstream/account_data backend repair, README/deploy/relay delivery artifact repair, frontend route repair.",
                        "",
                        "### Task T004 - Repair final backend domain and repository contracts",
                        "",
                        "- Previous relevant files: backend/internal/domain/**, backend/internal/repository/**, backend/go.mod, backend/go.sum.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                        "",
                        "## Previous Repair Context",
                        "",
                        "```markdown",
                        "- Known issues: backend/internal/handler/admin/account_data.go references service.AccountTypeUpstream.",
                        "- Known issues: Delivered README.md, deploy/docker-compose.yml, deploy/config.example.yaml, and deploy/relay still expose token relay/gateway/proxy behavior.",
                        "- Follow-up tasks: Clean or reframe README.md, deploy/docker-compose*.yml, deploy/config.example.yaml, and deploy/relay.",
                        "```",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-07-02T02:55:00+08:00",
            )

            graph = TaskGraphBuilder().build(ContextBundleBuilder().build(brief)).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes["T004"]["title"], "Repair final backend domain repository contract leftovers")
        self.assertIn("backend/internal/domain/constants.go", nodes["T004"]["relevant_files"])
        self.assertIn("backend/internal/repository/account_repo.go", nodes["T004"]["relevant_files"])
        self.assertNotIn("backend/internal/domain/**", nodes["T004"]["relevant_files"])
        self.assertNotIn("backend/internal/repository/**", nodes["T004"]["relevant_files"])
        self.assertEqual(nodes["T005"]["title"], "Repair final backend service handler server contracts")
        delivery = next(node for node in graph["nodes"] if node["title"] == "Repair final delivery artifact contracts")
        self.assertIn("deploy/**", delivery["relevant_files"])
        audit_node = next(node for node in graph["nodes"] if node["title"] == "Audit final requirements and phase evidence")
        self.assertIn("T004", audit_node["dependencies"])
        self.assertIn(delivery["id"], audit_node["dependencies"])

    def test_final_verification_backend_domain_repository_second_timeout_is_leaf_narrowed(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            (repo / "backend" / "internal" / "domain").mkdir(parents=True)
            (repo / "backend" / "internal" / "repository").mkdir(parents=True)
            (repo / "backend" / "internal" / "service").mkdir(parents=True)
            (repo / "backend" / "internal" / "handler").mkdir(parents=True)
            (repo / "backend" / "internal" / "server").mkdir(parents=True)
            (repo / "deploy").mkdir(parents=True)
            (repo / "frontend" / "src" / "api").mkdir(parents=True)
            (repo / "frontend" / "src" / "i18n").mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_058.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_056",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- Must grant the repair worker edit access to backend migrations, Ent schema/generated files, backend domain/repository/service/handler/server contracts, and backend command wiring when those surfaces contain residual relay-era product concepts.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "- Must report FINAL_AUDIT_STATUS, SIMULATION_TEST_STATUS, REAL_TEST_STATUS, REQUIRED_ACTIONS, and BLOCKERS after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T004.",
                        "- Focused timeout task IDs: T004.",
                        "- Focused timeout task titles: T004: Repair final backend domain repository contract leftovers.",
                        "- Completed tasks to preserve: T001, T002, T003, T007, T008, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024, T025, T026, T027, T028, T029, T030, T031, T032, T033, T034, T035, T036, T037, T038, T039, T040, T042, T043, T044, T045, T046, T047, T048, T049, T050, T051, T052, T053, T054, T055, T056, T057, T059.",
                        "- Preserve final frontend split tail graph shape: T056, T057, T058, T059.",
                        "- Preserve previous repair context from final_verification_repair_resume_057.md: AccountTypeUpstream/account_data backend repair, README/deploy/relay delivery artifact repair, frontend route repair.",
                        "",
                        "### Task T004 - Repair final backend domain repository contract leftovers",
                        "",
                        "- Previous relevant files: backend/internal/domain/constants.go, backend/internal/repository/account_repo.go, backend/internal/repository/channel_repo.go, backend/internal/repository/http_upstream.go, backend/internal/repository/proxy_repo.go, backend/go.mod, backend/go.sum.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                        "",
                        "## Previous Repair Context",
                        "",
                        "```markdown",
                        "- Known issues: backend/internal/handler/admin/account_data.go references service.AccountTypeUpstream.",
                        "- Known issues: Delivered README.md, deploy/docker-compose.yml, deploy/config.example.yaml, and deploy/relay still expose token relay/gateway/proxy behavior.",
                        "```",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-07-02T03:25:00+08:00",
            )

            graph = TaskGraphBuilder().build(ContextBundleBuilder().build(brief)).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes["T004"]["title"], "Repair final backend domain account repository contract leaf")
        self.assertEqual(
            nodes["T004"]["relevant_files"],
            [
                "backend/internal/domain/constants.go",
                "backend/internal/repository/account_repo.go",
                "backend/go.mod",
                "backend/go.sum",
            ],
        )
        self.assertEqual(nodes["T005"]["title"], "Repair final backend service handler server contracts")
        delivery = next(node for node in graph["nodes"] if node["title"] == "Repair final delivery artifact contracts")
        self.assertIn("README.md", delivery["relevant_files"])
        audit_node = next(node for node in graph["nodes"] if node["title"] == "Audit final requirements and phase evidence")
        self.assertIn("T004", audit_node["dependencies"])
        self.assertIn(delivery["id"], audit_node["dependencies"])

    def test_final_verification_frontend_api_i18n_timeout_is_split(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            (repo / "frontend" / "src" / "api").mkdir(parents=True)
            (repo / "frontend" / "src" / "constants").mkdir(parents=True)
            (repo / "frontend" / "src" / "i18n").mkdir(parents=True)
            (repo / "frontend" / "src" / "types").mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_006.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_010",
                        "",
                        "## Requirements",
                        "",
                        "- FINAL_AUDIT_STATUS=FAIL: final_verification T056 repair needs continuation before final handoff.",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- FINAL_AUDIT_STATUS=FAIL: final source-boundary repair needs continuation.",
                        "- Must split backend schema/domain repair by Ent schema, domain/repository, and service/handler/server wiring instead of replaying one broad worker.",
                        "- Must grant the repair worker edit access to frontend API, i18n, router, view, component, composable, constants, type, store, and test files when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T006.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T006 - Repair final frontend API and i18n contracts",
                        "- Previous relevant files: frontend/src/api/**, frontend/src/i18n/**, frontend/src/constants/**, frontend/src/types/**.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-29T01:40:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        for task_id in ("T001", "T002", "T003", "T004", "T005"):
            self.assertEqual(nodes[task_id]["status"], "completed")
        self.assertEqual(nodes["T006"]["title"], "Repair final frontend API module contracts")
        self.assertIn("frontend/src/api/**", nodes["T006"]["relevant_files"])
        self.assertNotIn("frontend/src/i18n/**", nodes["T006"]["relevant_files"])
        self.assertEqual(nodes["T007"]["title"], "Repair final frontend i18n locale contracts")
        self.assertIn("frontend/src/i18n/**", nodes["T007"]["relevant_files"])
        self.assertNotIn("frontend/src/api/**", nodes["T007"]["relevant_files"])
        self.assertEqual(nodes["T008"]["title"], "Repair final frontend constants and shared types contracts")
        self.assertIn("frontend/src/constants/**", nodes["T008"]["relevant_files"])
        self.assertIn("frontend/src/types/**", nodes["T008"]["relevant_files"])
        self.assertEqual(nodes["T009"]["title"], "Repair final frontend routes views and tests")
        self.assertEqual(nodes["T009"]["dependencies"], ["T008"])
        self.assertEqual(nodes["T010"]["title"], "Audit final requirements and phase evidence")
        self.assertIn("T009", nodes["T010"]["dependencies"])

    def test_final_verification_i18n_locale_timeout_is_leaf_narrowed(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            (repo / "frontend" / "src" / "api").mkdir(parents=True)
            (repo / "frontend" / "src" / "constants").mkdir(parents=True)
            (repo / "frontend" / "src" / "i18n" / "locales").mkdir(parents=True)
            (repo / "frontend" / "src" / "i18n" / "__tests__").mkdir(parents=True)
            (repo / "frontend" / "src" / "types").mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_070.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_081",
                        "",
                        "## Requirements",
                        "",
                        "- FINAL_AUDIT_STATUS=FAIL: final-verification repair needs continuation.",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- Must grant the repair worker edit access to frontend API, i18n, router, view, component, composable, constants, type, store, and test files when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T007.",
                        "- Focused timeout task IDs: T007.",
                        "- Repair final frontend i18n locale contracts timed out after exceeding the Codex worker timeout.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T007 - Repair final frontend i18n locale contracts",
                        "- Previous relevant files: frontend/src/i18n/**, frontend/package.json, frontend/pnpm-lock.yaml.",
                        "- Worker summary: T007 exceeded the Codex worker timeout.",
                        "",
                        "## Previous split context",
                        "",
                        "- Repair final frontend API module contracts",
                        "- Repair final frontend constants and shared types contracts",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-29T01:40:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        i18n_node = next(node for node in graph["nodes"] if node["title"] == "Repair final frontend i18n locale contracts")
        self.assertIn("frontend/src/i18n/locales/en.ts", i18n_node["relevant_files"])
        self.assertIn("frontend/src/i18n/locales/zh.ts", i18n_node["relevant_files"])
        self.assertIn("frontend/src/i18n/__tests__/**", i18n_node["relevant_files"])
        self.assertNotIn("frontend/src/i18n/**", i18n_node["relevant_files"])
        self.assertTrue(
            any(node["title"] == "Repair final frontend constants and shared types contracts" for node in graph["nodes"])
        )

    def test_final_verification_frontend_api_module_timeout_is_leaf_narrowed(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            (repo / "backend" / "internal" / "domain").mkdir(parents=True)
            (repo / "backend" / "internal" / "repository").mkdir(parents=True)
            (repo / "backend" / "internal" / "service").mkdir(parents=True)
            (repo / "backend" / "internal" / "handler").mkdir(parents=True)
            (repo / "backend" / "internal" / "server").mkdir(parents=True)
            (repo / "deploy").mkdir(parents=True)
            (repo / "frontend" / "src" / "api" / "admin").mkdir(parents=True)
            (repo / "frontend" / "src" / "api" / "__tests__").mkdir(parents=True)
            (repo / "frontend" / "src" / "i18n").mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_060.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_057",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- Must grant the repair worker edit access to frontend API, i18n, router, view, component, composable, constants, type, store, and test files when those surfaces contain upstream account, proxy, channel, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "- Must report FINAL_AUDIT_STATUS, SIMULATION_TEST_STATUS, REAL_TEST_STATUS, REQUIRED_ACTIONS, and BLOCKERS after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T006.",
                        "- Focused timeout task IDs: T006.",
                        "- Focused timeout task titles: T006: Repair final frontend API module contracts.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T007, T008, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024, T025, T026, T027, T028, T029, T030, T031, T032, T033, T034, T035, T036, T037, T038, T039, T040, T042, T043, T044, T045, T046, T047, T048, T049, T050, T051, T052, T053, T054, T055, T056, T057, T059.",
                        "- Preserve final frontend split tail graph shape: T056, T057, T058, T059.",
                        "- Preserve previous repair context from final_verification_repair_resume_059.md: AccountTypeUpstream/account_data backend repair, README/deploy/relay delivery artifact repair.",
                        "",
                        "### Task T006 - Repair final frontend API module contracts",
                        "",
                        "- Previous relevant files: frontend/src/api/**, frontend/src/types/**, frontend/package.json, frontend/pnpm-lock.yaml.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-07-02T04:10:00+08:00",
            )

            graph = TaskGraphBuilder().build(ContextBundleBuilder().build(brief)).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes["T004"]["status"], "completed")
        self.assertEqual(nodes["T005"]["status"], "completed")
        self.assertEqual(nodes["T006"]["title"], "Repair final frontend admin billing API contract leaf")
        self.assertIn("frontend/src/api/admin/payment.ts", nodes["T006"]["relevant_files"])
        self.assertIn("frontend/src/api/__tests__/retired-surfaces.spec.ts", nodes["T006"]["relevant_files"])
        self.assertNotIn("frontend/src/api/**", nodes["T006"]["relevant_files"])
        self.assertEqual(nodes["T007"]["status"], "completed")
        self.assertEqual(nodes["T008"]["status"], "completed")
        self.assertIn("T006", nodes["T009"]["dependencies"])
        delivery = next(node for node in graph["nodes"] if node["title"] == "Repair final delivery artifact contracts")
        self.assertIn("T006", delivery["dependencies"])

    def test_final_verification_frontend_api_leaf_timeout_is_payment_usage_narrowed(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            (repo / "backend" / "internal" / "domain").mkdir(parents=True)
            (repo / "backend" / "internal" / "repository").mkdir(parents=True)
            (repo / "backend" / "internal" / "service").mkdir(parents=True)
            (repo / "backend" / "internal" / "handler").mkdir(parents=True)
            (repo / "backend" / "internal" / "server").mkdir(parents=True)
            (repo / "deploy").mkdir(parents=True)
            (repo / "frontend" / "src" / "api" / "admin").mkdir(parents=True)
            (repo / "frontend" / "src" / "api" / "__tests__").mkdir(parents=True)
            (repo / "frontend" / "src" / "i18n").mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_061.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_058",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- Must grant the repair worker edit access to frontend API, i18n, router, view, component, composable, constants, type, store, and test files when those surfaces contain upstream account, proxy, channel, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "- Must report FINAL_AUDIT_STATUS, SIMULATION_TEST_STATUS, REAL_TEST_STATUS, REQUIRED_ACTIONS, and BLOCKERS after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T006.",
                        "- Focused timeout task IDs: T006.",
                        "- Focused timeout task titles: T006: Repair final frontend admin billing API contract leaf.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T007, T008, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024, T025, T026, T027, T028, T029, T030, T031, T032, T033, T034, T035, T036, T037, T038, T039, T040, T042, T043, T044, T045, T046, T047, T048, T049, T050, T051, T052, T053, T054, T055, T056, T057, T059.",
                        "- Preserve final frontend split tail graph shape: T056, T057, T058, T059.",
                        "",
                        "### Task T006 - Repair final frontend admin billing API contract leaf",
                        "",
                        "- Previous relevant files: frontend/src/api/admin/payment.ts, frontend/src/api/admin/usage.ts, frontend/src/api/admin/redeem.ts, frontend/src/api/admin/settings.ts, frontend/src/api/payment.ts, frontend/src/api/usage.ts, frontend/src/api/redeem.ts, frontend/src/api/retired.ts, frontend/src/api/__tests__/admin.payment.spec.ts, frontend/src/api/__tests__/admin.usage.spec.ts, frontend/src/api/__tests__/redeem.wallet-ledger.spec.ts, frontend/src/api/__tests__/retired-surfaces.spec.ts, frontend/package.json, frontend/pnpm-lock.yaml.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-07-02T04:45:00+08:00",
            )

            graph = TaskGraphBuilder().build(ContextBundleBuilder().build(brief)).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes["T006"]["title"], "Repair final frontend payment usage API contract leaf")
        self.assertIn("frontend/src/api/admin/payment.ts", nodes["T006"]["relevant_files"])
        self.assertIn("frontend/src/api/admin/usage.ts", nodes["T006"]["relevant_files"])
        self.assertNotIn("frontend/src/api/admin/redeem.ts", nodes["T006"]["relevant_files"])
        self.assertNotIn("frontend/src/api/retired.ts", nodes["T006"]["relevant_files"])
        self.assertEqual(nodes["T007"]["status"], "completed")
        self.assertIn("T006", nodes["T009"]["dependencies"])

    def test_final_verification_frontend_routes_timeout_preserves_prior_frontend_split(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views",
                "frontend/src/components",
                "frontend/src/composables",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True, exist_ok=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_007.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_011",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- FINAL_AUDIT_STATUS=FAIL: final source-boundary repair needs continuation.",
                        "- Must grant the repair worker edit access to frontend API, i18n, router, view, component, composable, constants, type, store, utility, and test files when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T009.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006, T007, T008.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T009 - Repair final frontend routes views and tests",
                        "- Previous relevant files: frontend/src/router/**, frontend/src/views/**, frontend/src/components/**, frontend/src/composables/**, frontend/src/stores/**, frontend/src/tests/**, frontend/tests/**.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-29T03:25:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        for task_id in ("T001", "T002", "T003", "T004", "T005", "T006", "T007", "T008"):
            self.assertEqual(nodes[task_id]["status"], "completed")
        self.assertEqual(nodes["T006"]["title"], "Repair final frontend API module contracts")
        self.assertEqual(nodes["T007"]["title"], "Repair final frontend i18n locale contracts")
        self.assertEqual(nodes["T008"]["title"], "Repair final frontend constants and shared types contracts")
        self.assertEqual(nodes["T009"]["title"], "Repair final frontend route and app shell contracts")
        self.assertIn("frontend/src/router/**", nodes["T009"]["relevant_files"])
        self.assertEqual(nodes["T010"]["title"], "Repair final frontend view and component contracts")
        self.assertIn("frontend/src/views/**", nodes["T010"]["relevant_files"])
        self.assertEqual(nodes["T011"]["title"], "Repair final frontend state composable utility contracts")
        self.assertIn("frontend/src/utils/**", nodes["T011"]["relevant_files"])
        self.assertEqual(nodes["T012"]["title"], "Repair final frontend test and fixture contracts")
        self.assertIn("frontend/tests/**", nodes["T012"]["relevant_files"])
        self.assertEqual(nodes["T013"]["title"], "Audit final requirements and phase evidence")
        self.assertIn("T012", nodes["T013"]["dependencies"])

    def test_final_verification_route_app_shell_timeout_is_narrowed_without_id_drift(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views",
                "frontend/src/components/layout",
                "frontend/src/composables",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True, exist_ok=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_045.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_047",
                        "",
                        "## Requirements",
                        "",
                        "- final_verification focused repair context.",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- FINAL_AUDIT_STATUS=FAIL: route/app-shell repair timed out before final handoff.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T009.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006, T007, T008, T010, T011.",
                        "- Preserve final frontend split tail graph shape: T056, T057, T058, T059.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T009 - Repair final frontend route and app shell contracts",
                        "- Previous relevant files: frontend/src/router/**, frontend/src/components/layout/**, frontend/src/App.vue, frontend/src/main.ts, frontend/src/stores/app.ts.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve T009 evidence and narrow this route/app-shell workflow before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-30T11:10:00+08:00",
            )

            graph = TaskGraphBuilder().build(ContextBundleBuilder().build(brief)).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes["T009"]["title"], "Repair final frontend route registration file")
        self.assertIn("frontend/src/router/index.ts", nodes["T009"]["relevant_files"])
        self.assertIn("frontend/src/components/layout/AppSidebar.vue", nodes["T009"]["relevant_files"])
        self.assertNotIn("frontend/src/router/**", nodes["T009"]["relevant_files"])
        self.assertEqual(nodes["T010"]["status"], "completed")
        self.assertEqual(nodes["T011"]["status"], "completed")
        audit = next(node for node in graph["nodes"] if node["title"] == "Audit final requirements and phase evidence")
        for task_id in ("T009", "T024", "T056", "T057"):
            self.assertIn(task_id, audit["dependencies"])

    def test_final_verification_frontend_view_component_timeout_is_split_again(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views",
                "frontend/src/components/account",
                "frontend/src/components/admin",
                "frontend/src/components/charts",
                "frontend/src/components/common",
                "frontend/src/components/Guide",
                "frontend/src/components/ui",
                "frontend/src/styles",
                "frontend/src/composables",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_008.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_012",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- FINAL_AUDIT_STATUS=FAIL: final source-boundary repair needs continuation.",
                        "- Must grant the repair worker edit access to backend migrations, Ent schema/generated files, backend domain/repository/service/handler/server contracts, and backend command wiring when those surfaces contain residual relay-era product concepts.",
                        "- Must split backend schema/domain repair by Ent schema, domain/repository, and service/handler/server wiring instead of replaying one broad worker.",
                        "- Must grant the repair worker edit access to frontend views and component families when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T010.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006, T007, T008, T009.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T006 - Repair final frontend API module contracts",
                        "### Task T007 - Repair final frontend i18n locale contracts",
                        "### Task T008 - Repair final frontend constants and shared types contracts",
                        "### Task T009 - Repair final frontend route and app shell contracts",
                        "### Task T010 - Repair final frontend view and component contracts",
                        "- Previous relevant files: frontend/src/views/**, frontend/src/components/**, frontend/src/styles/**, frontend/src/types/**, frontend/package.json, frontend/pnpm-lock.yaml.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve T009 and split this component/view workflow before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-29T04:30:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        for task_id in ("T001", "T002", "T003", "T004", "T005", "T006", "T007", "T008", "T009"):
            self.assertEqual(nodes[task_id]["status"], "completed")
        self.assertEqual(nodes["T009"]["title"], "Repair final frontend route and app shell contracts")
        self.assertEqual(nodes["T010"]["title"], "Repair final frontend account component contracts")
        self.assertIn("frontend/src/components/account/**", nodes["T010"]["relevant_files"])
        self.assertEqual(nodes["T011"]["title"], "Repair final frontend admin operation component contracts")
        self.assertIn("frontend/src/components/admin/**", nodes["T011"]["relevant_files"])
        self.assertEqual(nodes["T012"]["title"], "Repair final frontend analytics and shared component contracts")
        self.assertIn("frontend/src/components/charts/**", nodes["T012"]["relevant_files"])
        self.assertEqual(nodes["T013"]["title"], "Repair final frontend view page contracts")
        self.assertIn("frontend/src/views/**", nodes["T013"]["relevant_files"])
        self.assertEqual(nodes["T014"]["title"], "Repair final frontend state composable utility contracts")
        self.assertEqual(nodes["T015"]["title"], "Repair final frontend test and fixture contracts")
        self.assertEqual(nodes["T016"]["title"], "Audit final requirements and phase evidence")
        self.assertIn("T015", nodes["T016"]["dependencies"])

    def test_final_verification_admin_component_timeout_is_split_again(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views",
                "frontend/src/components/account",
                "frontend/src/components/auth",
                "frontend/src/components/admin/account",
                "frontend/src/components/admin/user",
                "frontend/src/components/admin/announcements",
                "frontend/src/components/admin/channel",
                "frontend/src/components/admin/group",
                "frontend/src/components/admin/proxy",
                "frontend/src/components/admin/monitor",
                "frontend/src/components/admin/usage",
                "frontend/src/components/admin/payment",
                "frontend/src/components/channels",
                "frontend/src/components/charts",
                "frontend/src/components/common",
                "frontend/src/components/Guide",
                "frontend/src/components/ui",
                "frontend/src/styles",
                "frontend/src/composables",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_009.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_013",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- FINAL_AUDIT_STATUS=FAIL: final source-boundary repair needs continuation.",
                        "- Must grant the repair worker edit access to backend migrations, Ent schema/generated files, backend domain/repository/service/handler/server contracts, and backend command wiring when those surfaces contain residual relay-era product concepts.",
                        "- Must split backend schema/domain repair by Ent schema, domain/repository, and service/handler/server wiring instead of replaying one broad worker.",
                        "- Must grant the repair worker edit access to frontend views and component families when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T011.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T006 - Repair final frontend API module contracts",
                        "### Task T007 - Repair final frontend i18n locale contracts",
                        "### Task T008 - Repair final frontend constants and shared types contracts",
                        "### Task T009 - Repair final frontend route and app shell contracts",
                        "### Task T010 - Repair final frontend account component contracts",
                        "### Task T011 - Repair final frontend admin operation component contracts",
                        "- Must continue focused task T011: Repair final frontend admin operation component contracts.",
                        "- Previous relevant files: frontend/src/components/admin/**, frontend/src/components/channels/**, frontend/src/types/**, frontend/package.json, frontend/pnpm-lock.yaml.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve T010 and split this admin component workflow before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-29T05:25:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        for task_id in ("T001", "T002", "T003", "T004", "T005", "T006", "T007", "T008", "T009", "T010"):
            self.assertEqual(nodes[task_id]["status"], "completed")
        self.assertEqual(nodes["T011"]["title"], "Repair final frontend admin account identity components")
        self.assertIn("frontend/src/components/admin/account/**", nodes["T011"]["relevant_files"])
        self.assertEqual(nodes["T012"]["title"], "Repair final frontend admin connector channel components")
        self.assertIn("frontend/src/components/channels/**", nodes["T012"]["relevant_files"])
        self.assertEqual(nodes["T013"]["title"], "Repair final frontend admin monitor components")
        self.assertIn("frontend/src/components/admin/monitor/**", nodes["T013"]["relevant_files"])
        self.assertEqual(nodes["T014"]["title"], "Repair final frontend admin usage payment components")
        self.assertIn("frontend/src/components/admin/payment/**", nodes["T014"]["relevant_files"])
        self.assertEqual(nodes["T015"]["title"], "Repair final frontend analytics and shared component contracts")
        self.assertEqual(nodes["T016"]["title"], "Repair final frontend view page contracts")
        self.assertEqual(nodes["T017"]["title"], "Repair final frontend state composable utility contracts")
        self.assertEqual(nodes["T018"]["title"], "Repair final frontend test and fixture contracts")
        self.assertEqual(nodes["T019"]["title"], "Audit final requirements and phase evidence")
        self.assertIn("T018", nodes["T019"]["dependencies"])

    def test_final_verification_admin_account_identity_timeout_is_split_again(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views",
                "frontend/src/components/account",
                "frontend/src/components/auth",
                "frontend/src/components/admin/account/__tests__",
                "frontend/src/components/admin/user/__tests__",
                "frontend/src/components/admin/announcements/__tests__",
                "frontend/src/components/admin/channel",
                "frontend/src/components/admin/group",
                "frontend/src/components/admin/proxy",
                "frontend/src/components/admin/monitor",
                "frontend/src/components/admin/usage",
                "frontend/src/components/admin/payment",
                "frontend/src/components/channels",
                "frontend/src/components/charts",
                "frontend/src/components/common",
                "frontend/src/components/Guide",
                "frontend/src/components/ui",
                "frontend/src/styles",
                "frontend/src/composables",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_010.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_014",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- FINAL_AUDIT_STATUS=FAIL: final source-boundary repair needs continuation.",
                        "- Must grant the repair worker edit access to backend migrations, Ent schema/generated files, backend domain/repository/service/handler/server contracts, and backend command wiring when those surfaces contain residual relay-era product concepts.",
                        "- Must split backend schema/domain repair by Ent schema, domain/repository, and service/handler/server wiring instead of replaying one broad worker.",
                        "- Must grant the repair worker edit access to frontend views and component families when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T011.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T011 - Repair final frontend admin account identity components",
                        "- Must continue focused task T011: Repair final frontend admin account identity components.",
                        "- Previous relevant files: frontend/src/components/admin/account/**, frontend/src/components/admin/user/**, frontend/src/components/admin/announcements/**, frontend/src/components/admin/AdminComplianceDialog.vue, frontend/src/types/**, frontend/package.json, frontend/pnpm-lock.yaml.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve T010 and split this admin account identity workflow before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-29T06:50:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        for task_id in ("T001", "T002", "T003", "T004", "T005", "T006", "T007", "T008", "T009", "T010"):
            self.assertEqual(nodes[task_id]["status"], "completed")
        self.assertEqual(nodes["T011"]["title"], "Repair final frontend admin account table components")
        self.assertIn("frontend/src/components/admin/account/AccountActionMenu.vue", nodes["T011"]["relevant_files"])
        self.assertEqual(nodes["T012"]["title"], "Repair final frontend admin account modal components")
        self.assertIn("frontend/src/components/admin/account/AccountTestModal.vue", nodes["T012"]["relevant_files"])
        self.assertEqual(nodes["T013"]["title"], "Repair final frontend admin user account components")
        self.assertIn("frontend/src/components/admin/user/UserCreateModal.vue", nodes["T013"]["relevant_files"])
        self.assertEqual(nodes["T014"]["title"], "Repair final frontend admin user balance quota components")
        self.assertIn("frontend/src/components/admin/user/UserBalanceHistoryModal.vue", nodes["T014"]["relevant_files"])
        self.assertEqual(nodes["T015"]["title"], "Repair final frontend admin announcement compliance components")
        self.assertIn("frontend/src/components/admin/AdminComplianceDialog.vue", nodes["T015"]["relevant_files"])
        self.assertEqual(nodes["T016"]["title"], "Repair final frontend admin connector channel components")
        self.assertEqual(nodes["T017"]["title"], "Repair final frontend admin monitor components")
        self.assertEqual(nodes["T018"]["title"], "Repair final frontend admin usage payment components")
        self.assertEqual(nodes["T019"]["title"], "Repair final frontend analytics and shared component contracts")
        self.assertEqual(nodes["T020"]["title"], "Repair final frontend view page contracts")
        self.assertEqual(nodes["T021"]["title"], "Repair final frontend state composable utility contracts")
        self.assertEqual(nodes["T022"]["title"], "Repair final frontend test and fixture contracts")
        self.assertEqual(nodes["T023"]["title"], "Audit final requirements and phase evidence")
        self.assertIn("T022", nodes["T023"]["dependencies"])

    def test_final_verification_admin_account_modal_timeout_is_split_again(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views",
                "frontend/src/components/account",
                "frontend/src/components/auth",
                "frontend/src/components/admin/account/__tests__",
                "frontend/src/components/admin/user/__tests__",
                "frontend/src/components/admin/announcements/__tests__",
                "frontend/src/components/admin/channel",
                "frontend/src/components/admin/group",
                "frontend/src/components/admin/proxy",
                "frontend/src/components/admin/monitor",
                "frontend/src/components/admin/usage",
                "frontend/src/components/admin/payment",
                "frontend/src/components/channels",
                "frontend/src/components/charts",
                "frontend/src/components/common",
                "frontend/src/components/Guide",
                "frontend/src/components/ui",
                "frontend/src/styles",
                "frontend/src/composables",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_011.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_015",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- FINAL_AUDIT_STATUS=FAIL: final source-boundary repair needs continuation.",
                        "- Must grant the repair worker edit access to backend migrations, Ent schema/generated files, backend domain/repository/service/handler/server contracts, and backend command wiring when those surfaces contain residual relay-era product concepts.",
                        "- Must split backend schema/domain repair by Ent schema, domain/repository, and service/handler/server wiring instead of replaying one broad worker.",
                        "- Must grant the repair worker edit access to frontend views and component families when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T012.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T012 - Repair final frontend admin account modal components",
                        "- Must continue focused task T012: Repair final frontend admin account modal components.",
                        "- Previous relevant files: frontend/src/components/admin/account/AccountTestModal.vue, frontend/src/components/admin/account/ImportDataModal.vue, frontend/src/components/admin/account/ReAuthAccountModal.vue, frontend/src/components/admin/account/ScheduledTestsPanel.vue, frontend/src/components/admin/account/__tests__/**, frontend/src/types/**, frontend/package.json, frontend/pnpm-lock.yaml.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve T011 and split this admin account modal workflow before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-29T07:25:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        for task_id in ("T001", "T002", "T003", "T004", "T005", "T006", "T007", "T008", "T009", "T010", "T011"):
            self.assertEqual(nodes[task_id]["status"], "completed")
        self.assertEqual(nodes["T012"]["title"], "Repair final frontend admin account test modal component")
        self.assertIn("frontend/src/components/admin/account/AccountTestModal.vue", nodes["T012"]["relevant_files"])
        self.assertEqual(nodes["T013"]["title"], "Repair final frontend admin account import modal component")
        self.assertIn("frontend/src/components/admin/account/ImportDataModal.vue", nodes["T013"]["relevant_files"])
        self.assertEqual(nodes["T014"]["title"], "Repair final frontend admin account reauth modal component")
        self.assertIn("frontend/src/components/admin/account/ReAuthAccountModal.vue", nodes["T014"]["relevant_files"])
        self.assertEqual(nodes["T015"]["title"], "Repair final frontend admin scheduled account tests panel")
        self.assertIn("frontend/src/components/admin/account/ScheduledTestsPanel.vue", nodes["T015"]["relevant_files"])
        self.assertEqual(nodes["T016"]["title"], "Repair final frontend admin user account components")
        self.assertEqual(nodes["T017"]["title"], "Repair final frontend admin user balance quota components")
        self.assertEqual(nodes["T018"]["title"], "Repair final frontend admin announcement compliance components")
        self.assertEqual(nodes["T019"]["title"], "Repair final frontend admin connector channel components")
        self.assertEqual(nodes["T020"]["title"], "Repair final frontend admin monitor components")
        self.assertEqual(nodes["T021"]["title"], "Repair final frontend admin usage payment components")
        self.assertEqual(nodes["T022"]["title"], "Repair final frontend analytics and shared component contracts")
        self.assertEqual(nodes["T023"]["title"], "Repair final frontend view page contracts")
        self.assertEqual(nodes["T024"]["title"], "Repair final frontend state composable utility contracts")
        self.assertEqual(nodes["T025"]["title"], "Repair final frontend test and fixture contracts")
        self.assertEqual(nodes["T026"]["title"], "Audit final requirements and phase evidence")
        self.assertIn("T025", nodes["T026"]["dependencies"])

    def test_final_verification_admin_user_account_timeout_is_split_again(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views",
                "frontend/src/components/account",
                "frontend/src/components/auth",
                "frontend/src/components/admin/account/__tests__",
                "frontend/src/components/admin/user/__tests__",
                "frontend/src/components/admin/announcements/__tests__",
                "frontend/src/components/admin/channel",
                "frontend/src/components/admin/group",
                "frontend/src/components/admin/proxy",
                "frontend/src/components/admin/monitor",
                "frontend/src/components/admin/usage",
                "frontend/src/components/admin/payment",
                "frontend/src/components/channels",
                "frontend/src/components/charts",
                "frontend/src/components/common",
                "frontend/src/components/Guide",
                "frontend/src/components/ui",
                "frontend/src/styles",
                "frontend/src/composables",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_012.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_016",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- FINAL_AUDIT_STATUS=FAIL: final source-boundary repair needs continuation.",
                        "- Must grant the repair worker edit access to frontend views and component families when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T016.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T016 - Repair final frontend admin user account components",
                        "- Must continue focused task T016: Repair final frontend admin user account components.",
                        "- Previous relevant files: frontend/src/components/admin/user/GroupReplaceModal.vue, frontend/src/components/admin/user/UserAllowedGroupsModal.vue, frontend/src/components/admin/user/UserApiKeysModal.vue, frontend/src/components/admin/user/UserCreateModal.vue, frontend/src/components/admin/user/UserEditModal.vue, frontend/src/types/**, frontend/package.json, frontend/pnpm-lock.yaml.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve T015 and split this admin user account workflow before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-29T08:35:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        for task_id in (
            "T001",
            "T002",
            "T003",
            "T004",
            "T005",
            "T006",
            "T007",
            "T008",
            "T009",
            "T010",
            "T011",
            "T012",
            "T013",
            "T014",
            "T015",
        ):
            self.assertEqual(nodes[task_id]["status"], "completed")
        self.assertEqual(nodes["T016"]["title"], "Repair final frontend admin user access group components")
        self.assertIn("frontend/src/components/admin/user/GroupReplaceModal.vue", nodes["T016"]["relevant_files"])
        self.assertEqual(nodes["T017"]["title"], "Repair final frontend admin user API key component")
        self.assertIn("frontend/src/components/admin/user/UserApiKeysModal.vue", nodes["T017"]["relevant_files"])
        self.assertEqual(nodes["T018"]["title"], "Repair final frontend admin user create edit components")
        self.assertIn("frontend/src/components/admin/user/UserCreateModal.vue", nodes["T018"]["relevant_files"])
        self.assertEqual(nodes["T019"]["title"], "Repair final frontend admin user balance quota components")
        self.assertEqual(nodes["T020"]["title"], "Repair final frontend admin announcement compliance components")
        self.assertEqual(nodes["T021"]["title"], "Repair final frontend admin connector channel components")
        self.assertEqual(nodes["T022"]["title"], "Repair final frontend admin monitor components")
        self.assertEqual(nodes["T023"]["title"], "Repair final frontend admin usage payment components")
        self.assertEqual(nodes["T024"]["title"], "Repair final frontend analytics and shared component contracts")
        self.assertEqual(nodes["T025"]["title"], "Repair final frontend view page contracts")
        self.assertEqual(nodes["T026"]["title"], "Repair final frontend state composable utility contracts")
        self.assertEqual(nodes["T027"]["title"], "Repair final frontend test and fixture contracts")
        self.assertEqual(nodes["T028"]["title"], "Audit final requirements and phase evidence")
        self.assertIn("T027", nodes["T028"]["dependencies"])

    def test_final_verification_admin_user_api_key_blocker_preserves_split_tail(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views",
                "frontend/src/components/account",
                "frontend/src/components/auth",
                "frontend/src/components/admin/account/__tests__",
                "frontend/src/components/admin/user/__tests__",
                "frontend/src/components/admin/announcements/__tests__",
                "frontend/src/components/admin/channel",
                "frontend/src/components/admin/group",
                "frontend/src/components/admin/proxy",
                "frontend/src/components/admin/monitor",
                "frontend/src/components/admin/usage",
                "frontend/src/components/admin/payment",
                "frontend/src/components/channels",
                "frontend/src/components/charts",
                "frontend/src/components/common",
                "frontend/src/components/Guide",
                "frontend/src/components/ui",
                "frontend/src/styles",
                "frontend/src/composables",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_013.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_017",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- FINAL_AUDIT_STATUS=FAIL: final source-boundary repair needs continuation.",
                        "- Must grant the repair worker edit access to backend migrations, Ent schema/generated files, backend domain/repository/service/handler/server contracts, and backend command wiring when those surfaces contain residual relay-era product concepts.",
                        "- Must split backend schema/domain repair by Ent schema, domain/repository, and service/handler/server wiring instead of replaying one broad worker.",
                        "- Must preserve completed final-verification tasks from the failed attempt unless a focused failed-task dependency requires a scoped edit.",
                        "- Must grant the repair worker edit access to frontend API, i18n, router, view, component, composable, constants, type, store, and test files when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T017.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T017 - Repair final frontend admin user API key component",
                        "- Must continue focused task T017: Repair final frontend admin user API key component.",
                        "- Previous relevant files: frontend/src/components/admin/user/UserApiKeysModal.vue, frontend/src/types/**, frontend/package.json, frontend/pnpm-lock.yaml.",
                        "- Worker summary: product copy mentioned usage limits while the worker rewrote CRM API key components.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-29T09:20:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        for task_id in (
            "T001",
            "T002",
            "T003",
            "T004",
            "T005",
            "T006",
            "T007",
            "T008",
            "T009",
            "T010",
            "T011",
            "T012",
            "T013",
            "T014",
            "T015",
            "T016",
        ):
            self.assertEqual(nodes[task_id]["status"], "completed")
        self.assertEqual(nodes["T017"]["title"], "Repair final frontend admin user API key component")
        self.assertEqual(nodes["T017"]["status"], "pending")
        self.assertEqual(nodes["T018"]["title"], "Repair final frontend admin user create edit components")
        self.assertEqual(nodes["T019"]["title"], "Repair final frontend admin user balance quota components")

    def test_final_verification_admin_user_create_edit_timeout_is_split_again(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views",
                "frontend/src/components/account",
                "frontend/src/components/auth",
                "frontend/src/components/admin/account/__tests__",
                "frontend/src/components/admin/user/__tests__",
                "frontend/src/components/admin/announcements/__tests__",
                "frontend/src/components/admin/channel",
                "frontend/src/components/admin/group",
                "frontend/src/components/admin/proxy",
                "frontend/src/components/admin/monitor",
                "frontend/src/components/admin/usage",
                "frontend/src/components/admin/payment",
                "frontend/src/components/channels",
                "frontend/src/components/charts",
                "frontend/src/components/common",
                "frontend/src/components/Guide",
                "frontend/src/components/ui",
                "frontend/src/styles",
                "frontend/src/composables",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_014.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_018",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- FINAL_AUDIT_STATUS=FAIL: final source-boundary repair needs continuation.",
                        "- Must grant the repair worker edit access to backend migrations, Ent schema/generated files, backend domain/repository/service/handler/server contracts, and backend command wiring when those surfaces contain residual relay-era product concepts.",
                        "- Must split backend schema/domain repair by Ent schema, domain/repository, and service/handler/server wiring instead of replaying one broad worker.",
                        "- Must grant the repair worker edit access to frontend API, i18n, router, view, component, composable, constants, type, store, and test files when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T018.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016, T017.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T018 - Repair final frontend admin user create edit components",
                        "- Must continue focused task T018: Repair final frontend admin user create edit components.",
                        "- Previous relevant files: frontend/src/components/admin/user/UserCreateModal.vue, frontend/src/components/admin/user/UserEditModal.vue, frontend/src/types/**, frontend/package.json, frontend/pnpm-lock.yaml.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve T017 and split this admin user create/edit workflow before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-29T10:35:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        for task_id in (
            "T001",
            "T002",
            "T003",
            "T004",
            "T005",
            "T006",
            "T007",
            "T008",
            "T009",
            "T010",
            "T011",
            "T012",
            "T013",
            "T014",
            "T015",
            "T016",
            "T017",
        ):
            self.assertEqual(nodes[task_id]["status"], "completed")
        self.assertEqual(nodes["T018"]["title"], "Repair final frontend admin user create modal component")
        self.assertIn("frontend/src/components/admin/user/UserCreateModal.vue", nodes["T018"]["relevant_files"])
        self.assertEqual(nodes["T019"]["title"], "Repair final frontend admin user edit modal component")
        self.assertIn("frontend/src/components/admin/user/UserEditModal.vue", nodes["T019"]["relevant_files"])
        self.assertEqual(nodes["T020"]["title"], "Repair final frontend admin user balance quota components")

    def test_final_verification_admin_usage_payment_timeout_is_split_again(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views",
                "frontend/src/components/account",
                "frontend/src/components/auth",
                "frontend/src/components/admin/account/__tests__",
                "frontend/src/components/admin/user/__tests__",
                "frontend/src/components/admin/announcements/__tests__",
                "frontend/src/components/admin/channel",
                "frontend/src/components/admin/group",
                "frontend/src/components/admin/proxy",
                "frontend/src/components/admin/monitor",
                "frontend/src/components/admin/usage",
                "frontend/src/components/admin/payment",
                "frontend/src/components/channels",
                "frontend/src/components/charts",
                "frontend/src/components/common",
                "frontend/src/components/Guide",
                "frontend/src/components/ui",
                "frontend/src/styles",
                "frontend/src/composables",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_015.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_019",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- FINAL_AUDIT_STATUS=FAIL: final source-boundary repair needs continuation.",
                        "- Must grant the repair worker edit access to backend migrations, Ent schema/generated files, backend domain/repository/service/handler/server contracts, and backend command wiring when those surfaces contain residual relay-era product concepts.",
                        "- Must split backend schema/domain repair by Ent schema, domain/repository, and service/handler/server wiring instead of replaying one broad worker.",
                        "- Must grant the repair worker edit access to frontend API, i18n, router, view, component, composable, constants, type, store, and test files when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T024.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T024 - Repair final frontend admin usage payment components",
                        "- Must continue focused task T024: Repair final frontend admin usage payment components.",
                        "- Previous relevant files: frontend/src/components/admin/usage/**, frontend/src/components/admin/payment/**, frontend/src/types/**, frontend/package.json, frontend/pnpm-lock.yaml.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve T023 and split this admin usage/payment workflow before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-29T12:10:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        for task_id in (
            "T001",
            "T002",
            "T003",
            "T004",
            "T005",
            "T006",
            "T007",
            "T008",
            "T009",
            "T010",
            "T011",
            "T012",
            "T013",
            "T014",
            "T015",
            "T016",
            "T017",
            "T018",
            "T019",
            "T020",
            "T021",
            "T022",
            "T023",
        ):
            self.assertEqual(nodes[task_id]["status"], "completed")
        self.assertEqual(nodes["T024"]["title"], "Repair final frontend admin usage component")
        self.assertIn("frontend/src/components/admin/usage/**", nodes["T024"]["relevant_files"])
        self.assertEqual(nodes["T025"]["title"], "Repair final frontend admin payment component")
        self.assertIn("frontend/src/components/admin/payment/**", nodes["T025"]["relevant_files"])
        self.assertEqual(nodes["T026"]["title"], "Repair final frontend analytics and shared component contracts")

    def test_final_verification_admin_payment_timeout_is_split_again(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views",
                "frontend/src/components/account",
                "frontend/src/components/auth",
                "frontend/src/components/admin/account/__tests__",
                "frontend/src/components/admin/user/__tests__",
                "frontend/src/components/admin/announcements/__tests__",
                "frontend/src/components/admin/channel",
                "frontend/src/components/admin/group",
                "frontend/src/components/admin/proxy",
                "frontend/src/components/admin/monitor",
                "frontend/src/components/admin/usage",
                "frontend/src/components/admin/payment",
                "frontend/src/components/channels",
                "frontend/src/components/charts",
                "frontend/src/components/common",
                "frontend/src/components/Guide",
                "frontend/src/components/ui",
                "frontend/src/styles",
                "frontend/src/composables",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_016.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_020",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- FINAL_AUDIT_STATUS=FAIL: final source-boundary repair needs continuation.",
                        "- Must grant the repair worker edit access to backend migrations, Ent schema/generated files, backend domain/repository/service/handler/server contracts, and backend command wiring when those surfaces contain residual relay-era product concepts.",
                        "- Must split backend schema/domain repair by Ent schema, domain/repository, and service/handler/server wiring instead of replaying one broad worker.",
                        "- Must grant the repair worker edit access to frontend API, i18n, router, view, component, composable, constants, type, store, and test files when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T025.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T025 - Repair final frontend admin payment component",
                        "- Must continue focused task T025: Repair final frontend admin payment component.",
                        "- Previous relevant files: frontend/src/components/admin/payment/AdminOrderTable.vue, frontend/src/components/admin/payment/AdminOrderDetail.vue, frontend/src/components/admin/payment/AdminRefundDialog.vue, frontend/src/components/admin/payment/DailyRevenueChart.vue, frontend/src/components/admin/payment/PaymentMethodChart.vue, frontend/src/components/admin/payment/OrderStatsCards.vue, frontend/src/components/admin/payment/TopUsersLeaderboard.vue, frontend/src/types/**, frontend/package.json, frontend/pnpm-lock.yaml.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve T024 and split this admin payment workflow before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-29T13:05:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        for task_id in (
            "T001",
            "T002",
            "T003",
            "T004",
            "T005",
            "T006",
            "T007",
            "T008",
            "T009",
            "T010",
            "T011",
            "T012",
            "T013",
            "T014",
            "T015",
            "T016",
            "T017",
            "T018",
            "T019",
            "T020",
            "T021",
            "T022",
            "T023",
            "T024",
        ):
            self.assertEqual(nodes[task_id]["status"], "completed")
        self.assertEqual(nodes["T025"]["title"], "Repair final frontend admin payment order detail components")
        self.assertIn("frontend/src/components/admin/payment/AdminOrderTable.vue", nodes["T025"]["relevant_files"])
        self.assertEqual(nodes["T026"]["title"], "Repair final frontend admin payment refund dialog component")
        self.assertIn("frontend/src/components/admin/payment/AdminRefundDialog.vue", nodes["T026"]["relevant_files"])
        self.assertEqual(nodes["T027"]["title"], "Repair final frontend admin payment analytics components")
        self.assertIn("frontend/src/components/admin/payment/DailyRevenueChart.vue", nodes["T027"]["relevant_files"])
        self.assertEqual(nodes["T028"]["title"], "Repair final frontend analytics and shared component contracts")

    def test_final_verification_admin_payment_refund_timeout_uses_file_leaf(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views",
                "frontend/src/components/account",
                "frontend/src/components/auth",
                "frontend/src/components/admin/account/__tests__",
                "frontend/src/components/admin/user/__tests__",
                "frontend/src/components/admin/announcements/__tests__",
                "frontend/src/components/admin/channel",
                "frontend/src/components/admin/group",
                "frontend/src/components/admin/proxy",
                "frontend/src/components/admin/monitor",
                "frontend/src/components/admin/usage",
                "frontend/src/components/admin/payment",
                "frontend/src/components/channels",
                "frontend/src/components/charts",
                "frontend/src/components/common",
                "frontend/src/components/Guide",
                "frontend/src/components/ui",
                "frontend/src/styles",
                "frontend/src/composables",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_017.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_021",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- FINAL_AUDIT_STATUS=FAIL: final source-boundary repair needs continuation.",
                        "- Must grant the repair worker edit access to backend migrations, Ent schema/generated files, backend domain/repository/service/handler/server contracts, and backend command wiring when those surfaces contain residual relay-era product concepts.",
                        "- Must split backend schema/domain repair by Ent schema, domain/repository, and service/handler/server wiring instead of replaying one broad worker.",
                        "- Must grant the repair worker edit access to frontend API, i18n, router, view, component, composable, constants, type, store, and test files when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T026.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024, T025.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T026 - Repair final frontend admin payment refund dialog component",
                        "- Must continue focused task T026: Repair final frontend admin payment refund dialog component.",
                        "- Previous relevant files: frontend/src/components/admin/payment/AdminRefundDialog.vue, frontend/src/types/**, frontend/package.json, frontend/pnpm-lock.yaml.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve T025 and narrow this refund dialog to a file-only leaf task before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-29T14:00:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        for task_id in (
            "T001",
            "T002",
            "T003",
            "T004",
            "T005",
            "T006",
            "T007",
            "T008",
            "T009",
            "T010",
            "T011",
            "T012",
            "T013",
            "T014",
            "T015",
            "T016",
            "T017",
            "T018",
            "T019",
            "T020",
            "T021",
            "T022",
            "T023",
            "T024",
            "T025",
        ):
            self.assertEqual(nodes[task_id]["status"], "completed")
        self.assertEqual(nodes["T026"]["title"], "Repair final frontend admin payment refund dialog file")
        self.assertEqual(nodes["T026"]["relevant_files"], ["frontend/src/components/admin/payment/AdminRefundDialog.vue"])
        self.assertEqual(nodes["T027"]["title"], "Repair final frontend admin payment analytics components")
        self.assertEqual(nodes["T028"]["title"], "Repair final frontend analytics and shared component contracts")

    def test_final_verification_view_page_timeout_is_split_again(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views/admin/orders",
                "frontend/src/views/auth/__tests__",
                "frontend/src/views/public",
                "frontend/src/views/setup",
                "frontend/src/views/user/__tests__",
                "frontend/src/components/account",
                "frontend/src/components/auth",
                "frontend/src/components/admin/account/__tests__",
                "frontend/src/components/admin/user/__tests__",
                "frontend/src/components/admin/announcements/__tests__",
                "frontend/src/components/admin/channel",
                "frontend/src/components/admin/group",
                "frontend/src/components/admin/proxy",
                "frontend/src/components/admin/monitor",
                "frontend/src/components/admin/usage",
                "frontend/src/components/admin/payment",
                "frontend/src/components/channels",
                "frontend/src/components/charts",
                "frontend/src/components/common",
                "frontend/src/components/Guide",
                "frontend/src/components/ui",
                "frontend/src/styles",
                "frontend/src/composables",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "frontend" / "src" / "views" / "NotFoundView.vue").write_text("<template />\n", encoding="utf-8")
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_019.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_023",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- FINAL_AUDIT_STATUS=FAIL: final source-boundary repair needs continuation.",
                        "- Must grant the repair worker edit access to backend migrations, Ent schema/generated files, backend domain/repository/service/handler/server contracts, and backend command wiring when those surfaces contain residual relay-era product concepts.",
                        "- Must split backend schema/domain repair by Ent schema, domain/repository, and service/handler/server wiring instead of replaying one broad worker.",
                        "- Must grant the repair worker edit access to frontend API, i18n, router, view, component, composable, constants, type, store, and test files when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T029.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024, T025, T026, T027, T028.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T029 - Repair final frontend view page contracts",
                        "- Must continue focused task T029: Repair final frontend view page contracts.",
                        "- Previous relevant files: frontend/src/views/**, frontend/src/components/**, frontend/src/styles/**, frontend/src/types/**, frontend/package.json, frontend/pnpm-lock.yaml.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve T028 and split this view page workflow by admin, user/payment, and auth/public/setup views before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-29T19:10:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        for task_id in (
            "T001",
            "T002",
            "T003",
            "T004",
            "T005",
            "T006",
            "T007",
            "T008",
            "T009",
            "T010",
            "T011",
            "T012",
            "T013",
            "T014",
            "T015",
            "T016",
            "T017",
            "T018",
            "T019",
            "T020",
            "T021",
            "T022",
            "T023",
            "T024",
            "T025",
            "T026",
            "T027",
            "T028",
        ):
            self.assertEqual(nodes[task_id]["status"], "completed")
        self.assertEqual(nodes["T029"]["title"], "Repair final frontend admin view page contracts")
        self.assertIn("frontend/src/views/admin/**", nodes["T029"]["relevant_files"])
        self.assertEqual(nodes["T030"]["title"], "Repair final frontend user payment view page contracts")
        self.assertIn("frontend/src/views/user/**", nodes["T030"]["relevant_files"])
        self.assertEqual(nodes["T031"]["title"], "Repair final frontend auth public setup view contracts")
        self.assertIn("frontend/src/views/auth/**", nodes["T031"]["relevant_files"])
        self.assertEqual(nodes["T032"]["title"], "Repair final frontend state composable utility contracts")

    def test_final_verification_admin_view_page_timeout_is_split_again(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views/admin/__tests__",
                "frontend/src/views/admin/affiliates",
                "frontend/src/views/admin/ops/components/__tests__",
                "frontend/src/views/admin/ops/utils/__tests__",
                "frontend/src/views/admin/orders",
                "frontend/src/views/admin/settings",
                "frontend/src/views/auth/__tests__",
                "frontend/src/views/public",
                "frontend/src/views/setup",
                "frontend/src/views/user/__tests__",
                "frontend/src/components/account",
                "frontend/src/components/admin/announcements",
                "frontend/src/components/admin/channel",
                "frontend/src/components/admin/group",
                "frontend/src/components/admin/monitor",
                "frontend/src/components/admin/payment",
                "frontend/src/components/admin/proxy",
                "frontend/src/components/admin/usage",
                "frontend/src/components/admin/user",
                "frontend/src/components/charts",
                "frontend/src/styles",
                "frontend/src/composables",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "frontend" / "src" / "views" / "NotFoundView.vue").write_text("<template />\n", encoding="utf-8")
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_020.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_024",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- FINAL_AUDIT_STATUS=FAIL: final source-boundary repair needs continuation.",
                        "- Must grant the repair worker edit access to frontend API, i18n, router, view, component, composable, constants, type, store, and test files when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T029.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024, T025, T026, T027, T028.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T029 - Repair final frontend admin view page contracts",
                        "- Must continue focused task T029: Repair final frontend admin view page contracts.",
                        "- Previous relevant files: frontend/src/views/admin/**, frontend/src/components/admin/**, frontend/src/styles/**, frontend/src/types/**, frontend/package.json, frontend/pnpm-lock.yaml.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve T028 and split admin view pages by dashboard/settings, user/usage/redeem, payment/order/plan, ops, and legacy admin cleanup before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-29T19:28:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        for task_id in (
            "T001",
            "T002",
            "T003",
            "T004",
            "T005",
            "T006",
            "T007",
            "T008",
            "T009",
            "T010",
            "T011",
            "T012",
            "T013",
            "T014",
            "T015",
            "T016",
            "T017",
            "T018",
            "T019",
            "T020",
            "T021",
            "T022",
            "T023",
            "T024",
            "T025",
            "T026",
            "T027",
            "T028",
        ):
            self.assertEqual(nodes[task_id]["status"], "completed")
        self.assertEqual(nodes["T029"]["title"], "Repair final frontend admin dashboard settings view contracts")
        self.assertIn("frontend/src/views/admin/DashboardView.vue", nodes["T029"]["relevant_files"])
        self.assertEqual(nodes["T030"]["title"], "Repair final frontend admin user usage redeem view contracts")
        self.assertIn("frontend/src/views/admin/UsersView.vue", nodes["T030"]["relevant_files"])
        self.assertEqual(nodes["T031"]["title"], "Repair final frontend admin payment order plan view contracts")
        self.assertIn("frontend/src/views/admin/orders/**", nodes["T031"]["relevant_files"])
        self.assertEqual(nodes["T032"]["title"], "Repair final frontend admin operations view contracts")
        self.assertIn("frontend/src/views/admin/ops/**", nodes["T032"]["relevant_files"])
        self.assertEqual(nodes["T033"]["title"], "Repair final frontend legacy admin view cleanup")
        self.assertIn("frontend/src/views/admin/AccountsView.vue", nodes["T033"]["relevant_files"])
        self.assertEqual(nodes["T034"]["title"], "Repair final frontend user payment view page contracts")
        self.assertEqual(nodes["T035"]["title"], "Repair final frontend auth public setup view contracts")
        self.assertEqual(nodes["T036"]["title"], "Repair final frontend state composable utility contracts")

    def test_final_verification_admin_dashboard_settings_timeout_is_split_again(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views/admin/__tests__",
                "frontend/src/views/admin/affiliates",
                "frontend/src/views/admin/ops/components",
                "frontend/src/views/admin/orders",
                "frontend/src/views/admin/settings",
                "frontend/src/views/auth",
                "frontend/src/views/public",
                "frontend/src/views/setup",
                "frontend/src/views/user",
                "frontend/src/components/account",
                "frontend/src/components/admin/announcements",
                "frontend/src/components/admin/channel",
                "frontend/src/components/admin/group",
                "frontend/src/components/admin/monitor",
                "frontend/src/components/admin/payment",
                "frontend/src/components/admin/proxy",
                "frontend/src/components/admin/usage",
                "frontend/src/components/admin/user",
                "frontend/src/components/charts",
                "frontend/src/styles",
                "frontend/src/composables",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "frontend" / "src" / "views" / "NotFoundView.vue").write_text("<template />\n", encoding="utf-8")
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_021.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_025",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- FINAL_AUDIT_STATUS=FAIL: final source-boundary repair needs continuation.",
                        "- Must grant the repair worker edit access to backend migrations, Ent schema/generated files, backend domain/repository/service/handler/server contracts, and backend command wiring when those surfaces contain residual relay-era product concepts.",
                        "- Must split backend schema/domain repair by Ent schema, domain/repository, and service/handler/server wiring instead of replaying one broad worker.",
                        "- Must grant the repair worker edit access to frontend API, i18n, router, view, component, composable, constants, type, store, and test files when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T029.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024, T025, T026, T027, T028.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T029 - Repair final frontend admin dashboard settings view contracts",
                        "- Must continue focused task T029: Repair final frontend admin dashboard settings view contracts.",
                        "- Previous relevant files: frontend/src/views/admin/DashboardView.vue, frontend/src/views/admin/SettingsView.vue, frontend/src/views/admin/AnnouncementsView.vue, frontend/src/views/admin/BackupView.vue, frontend/src/views/admin/PromoCodesView.vue, frontend/src/views/admin/settings/**, frontend/src/components/admin/announcements/**, frontend/src/components/admin/AdminComplianceDialog.vue, frontend/src/styles/**, frontend/src/types/**, frontend/package.json, frontend/pnpm-lock.yaml.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve T028 and split dashboard/settings by dashboard page, settings/email/compliance files, announcement/backup/promo files, and shared support files.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-29T19:55:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        for task_id in (
            "T001",
            "T002",
            "T003",
            "T004",
            "T005",
            "T006",
            "T007",
            "T008",
            "T009",
            "T010",
            "T011",
            "T012",
            "T013",
            "T014",
            "T015",
            "T016",
            "T017",
            "T018",
            "T019",
            "T020",
            "T021",
            "T022",
            "T023",
            "T024",
            "T025",
            "T026",
            "T027",
            "T028",
        ):
            self.assertEqual(nodes[task_id]["status"], "completed")
        self.assertEqual(nodes["T029"]["title"], "Repair final frontend admin dashboard view file")
        self.assertEqual(nodes["T029"]["relevant_files"][0], "frontend/src/views/admin/DashboardView.vue")
        self.assertEqual(nodes["T030"]["title"], "Repair final frontend admin settings email compliance files")
        self.assertIn("frontend/src/views/admin/SettingsView.vue", nodes["T030"]["relevant_files"])
        self.assertEqual(nodes["T031"]["title"], "Repair final frontend admin announcement backup promo files")
        self.assertIn("frontend/src/views/admin/AnnouncementsView.vue", nodes["T031"]["relevant_files"])
        self.assertEqual(nodes["T032"]["title"], "Repair final frontend admin dashboard settings support files")
        self.assertIn("frontend/package.json", nodes["T032"]["relevant_files"])
        self.assertEqual(nodes["T033"]["title"], "Repair final frontend admin user usage redeem view contracts")
        self.assertEqual(nodes["T034"]["title"], "Repair final frontend admin payment order plan view contracts")
        self.assertEqual(nodes["T035"]["title"], "Repair final frontend admin operations view contracts")
        self.assertEqual(nodes["T036"]["title"], "Repair final frontend legacy admin view cleanup")
        self.assertEqual(nodes["T037"]["title"], "Repair final frontend user payment view page contracts")

    def test_final_verification_auth_public_setup_timeout_is_split_again(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views/admin/__tests__",
                "frontend/src/views/admin/affiliates",
                "frontend/src/views/admin/ops/components",
                "frontend/src/views/admin/orders",
                "frontend/src/views/admin/settings",
                "frontend/src/views/auth",
                "frontend/src/views/public",
                "frontend/src/views/setup",
                "frontend/src/views/user",
                "frontend/src/components/account",
                "frontend/src/components/admin/announcements",
                "frontend/src/components/admin/channel",
                "frontend/src/components/admin/group",
                "frontend/src/components/admin/monitor",
                "frontend/src/components/admin/payment",
                "frontend/src/components/admin/proxy",
                "frontend/src/components/admin/usage",
                "frontend/src/components/admin/user",
                "frontend/src/components/charts",
                "frontend/src/styles",
                "frontend/src/composables",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "frontend" / "src" / "views" / "NotFoundView.vue").write_text("<template />\n", encoding="utf-8")
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_031.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_034",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- FINAL_AUDIT_STATUS=FAIL: final source-boundary repair needs continuation.",
                        "- Must grant the repair worker edit access to frontend API, i18n, router, view, component, composable, constants, type, store, and test files when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T044.",
                        f"- Completed tasks to preserve: {', '.join(f'T{index:03d}' for index in range(1, 44))}.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T044 - Repair final frontend auth public setup view contracts",
                        "- Must continue focused task T044: Repair final frontend auth public setup view contracts.",
                        "- Previous relevant files: frontend/src/views/auth/**, frontend/src/views/public/**, frontend/src/views/setup/**, frontend/src/views/NotFoundView.vue, frontend/src/styles/**, frontend/src/types/**, frontend/package.json, frontend/pnpm-lock.yaml.",
                        "- Worker summary: T044 exceeded the Codex worker timeout.",
                        "- Timeout note: preserve T043 and split auth, public legal, setup/not-found, and support files before replaying the same wide scope.",
                        "",
                        "## Previous Graph Titles",
                        "",
                        "- Repair final frontend API module contracts",
                        "- Repair final frontend i18n locale contracts",
                        "- Repair final frontend constants and shared types contracts",
                        "- Repair final frontend admin dashboard view file",
                        "- Repair final frontend admin settings view file",
                        "- Repair final frontend admin email template editor leaf file",
                        "- Repair final frontend admin compliance dialog file",
                        "- Repair final frontend admin settings support files",
                        "- Repair final frontend admin announcements view file",
                        "- Repair final frontend admin backup view file",
                        "- Repair final frontend admin promo codes view file",
                        "- Repair final frontend admin announcement components support files",
                        "- Repair final frontend admin dashboard settings support files",
                        "- Repair final frontend admin user usage redeem view contracts",
                        "- Repair final frontend admin payment order plan view contracts",
                        "- Repair final frontend admin operations view contracts",
                        "- Repair final frontend legacy admin view cleanup",
                        "- Repair final frontend user payment view page contracts",
                        "- Repair final frontend auth public setup view contracts",
                        "- Repair final frontend state composable utility contracts",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-30T02:05:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        titles = [node["title"] for node in graph["nodes"]]
        self.assertNotIn("Repair final frontend auth public setup view contracts", titles)
        split_titles = [
            "Repair final frontend auth view contracts",
            "Repair final frontend public legal view contracts",
            "Repair final frontend setup and not-found view contracts",
            "Repair final frontend auth public setup support files",
        ]
        split_nodes = [node for node in graph["nodes"] if node["title"] in split_titles]
        self.assertEqual([node["title"] for node in split_nodes], split_titles)
        self.assertEqual(split_nodes[0]["relevant_files"], ["frontend/src/views/auth/**"])
        self.assertEqual(split_nodes[1]["relevant_files"], ["frontend/src/views/public/**"])
        self.assertEqual(
            split_nodes[2]["relevant_files"],
            ["frontend/src/views/setup/**", "frontend/src/views/NotFoundView.vue"],
        )
        self.assertIn("frontend/src/styles/**", split_nodes[3]["relevant_files"])
        self.assertEqual(split_nodes[0]["status"], "pending")
        self.assertIn("Repair final frontend state composable utility contracts", titles)

    def test_final_verification_setup_not_found_timeout_is_split_again(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views/admin/__tests__",
                "frontend/src/views/admin/affiliates",
                "frontend/src/views/admin/ops/components",
                "frontend/src/views/admin/orders",
                "frontend/src/views/admin/settings",
                "frontend/src/views/auth",
                "frontend/src/views/public",
                "frontend/src/views/setup",
                "frontend/src/views/user",
                "frontend/src/components/account",
                "frontend/src/components/admin/announcements",
                "frontend/src/components/admin/channel",
                "frontend/src/components/admin/group",
                "frontend/src/components/admin/monitor",
                "frontend/src/components/admin/payment",
                "frontend/src/components/admin/proxy",
                "frontend/src/components/admin/usage",
                "frontend/src/components/admin/user",
                "frontend/src/components/charts",
                "frontend/src/styles",
                "frontend/src/composables",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "frontend" / "src" / "views" / "NotFoundView.vue").write_text("<template />\n", encoding="utf-8")
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_032.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_035",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- FINAL_AUDIT_STATUS=FAIL: final source-boundary repair needs continuation.",
                        "- Must grant the repair worker edit access to frontend API, i18n, router, view, component, composable, constants, type, store, and test files when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T046.",
                        f"- Completed tasks to preserve: {', '.join(f'T{index:03d}' for index in range(1, 46))}.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T046 - Repair final frontend setup and not-found view contracts",
                        "- Must continue focused task T046: Repair final frontend setup and not-found view contracts.",
                        "- Previous relevant files: frontend/src/views/setup/**, frontend/src/views/NotFoundView.vue.",
                        "- Worker summary: T046 exceeded the Codex worker timeout.",
                        "- Timeout note: preserve T045 and split setup views from the NotFound view file before replaying the same scope.",
                        "",
                        "## Previous Graph Titles",
                        "",
                        "- Repair final frontend auth view contracts",
                        "- Repair final frontend public legal view contracts",
                        "- Repair final frontend setup and not-found view contracts",
                        "- Repair final frontend auth public setup support files",
                        "- Repair final frontend state composable utility contracts",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-30T02:45:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        titles = [node["title"] for node in graph["nodes"]]
        self.assertNotIn("Repair final frontend setup and not-found view contracts", titles)
        split_titles = [
            "Repair final frontend setup view contracts",
            "Repair final frontend not-found view file",
        ]
        split_nodes = [node for node in graph["nodes"] if node["title"] in split_titles]
        self.assertEqual([node["title"] for node in split_nodes], split_titles)
        self.assertEqual(split_nodes[0]["relevant_files"], ["frontend/src/views/setup/**"])
        self.assertEqual(split_nodes[1]["relevant_files"], ["frontend/src/views/NotFoundView.vue"])
        self.assertEqual(split_nodes[0]["status"], "pending")
        self.assertIn("Repair final frontend auth public setup support files", titles)

    def test_final_verification_state_composable_utility_timeout_is_split_again(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views/admin/__tests__",
                "frontend/src/views/admin/affiliates",
                "frontend/src/views/admin/ops/components",
                "frontend/src/views/admin/orders",
                "frontend/src/views/admin/settings",
                "frontend/src/views/auth",
                "frontend/src/views/public",
                "frontend/src/views/setup",
                "frontend/src/views/user",
                "frontend/src/components/account",
                "frontend/src/components/admin/announcements",
                "frontend/src/components/admin/channel",
                "frontend/src/components/admin/group",
                "frontend/src/components/admin/monitor",
                "frontend/src/components/admin/payment",
                "frontend/src/components/admin/proxy",
                "frontend/src/components/admin/usage",
                "frontend/src/components/admin/user",
                "frontend/src/components/charts",
                "frontend/src/styles",
                "frontend/src/composables",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "frontend" / "src" / "views" / "NotFoundView.vue").write_text("<template />\n", encoding="utf-8")
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_033.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_036",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- FINAL_AUDIT_STATUS=FAIL: final source-boundary repair needs continuation.",
                        "- Must grant the repair worker edit access to frontend API, i18n, router, view, component, composable, constants, type, store, and test files when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T049.",
                        f"- Completed tasks to preserve: {', '.join(f'T{index:03d}' for index in range(1, 49))}.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T049 - Repair final frontend state composable utility contracts",
                        "- Must continue focused task T049: Repair final frontend state composable utility contracts.",
                        "- Previous relevant files: frontend/src/stores/**, frontend/src/composables/**, frontend/src/utils/**, frontend/src/constants/**, frontend/src/types/**, frontend/package.json, frontend/pnpm-lock.yaml.",
                        "- Worker summary: T049 exceeded the Codex worker timeout.",
                        "- Timeout note: preserve T048 and split stores, composables, and utility/constant/type support before replaying the same scope.",
                        "",
                        "## Previous Graph Titles",
                        "",
                        "- Repair final frontend API module contracts",
                        "- Repair final frontend i18n locale contracts",
                        "- Repair final frontend constants and shared types contracts",
                        "- Repair final frontend admin dashboard view file",
                        "- Repair final frontend admin settings view file",
                        "- Repair final frontend admin email template editor leaf file",
                        "- Repair final frontend admin compliance dialog file",
                        "- Repair final frontend admin settings support files",
                        "- Repair final frontend admin announcements view file",
                        "- Repair final frontend admin backup view file",
                        "- Repair final frontend admin promo codes view file",
                        "- Repair final frontend admin announcement components support files",
                        "- Repair final frontend admin dashboard settings support files",
                        "- Repair final frontend admin user usage redeem view contracts",
                        "- Repair final frontend admin payment order plan view contracts",
                        "- Repair final frontend admin operations view contracts",
                        "- Repair final frontend legacy admin view cleanup",
                        "- Repair final frontend user payment view page contracts",
                        "- Repair final frontend auth view contracts",
                        "- Repair final frontend public legal view contracts",
                        "- Repair final frontend setup view contracts",
                        "- Repair final frontend not-found view file",
                        "- Repair final frontend auth public setup support files",
                        "- Repair final frontend state composable utility contracts",
                        "- Repair final frontend test and fixture contracts",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-30T03:35:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        titles = [node["title"] for node in graph["nodes"]]
        self.assertNotIn("Repair final frontend state composable utility contracts", titles)
        split_titles = [
            "Repair final frontend store contracts",
            "Repair final frontend composable contracts",
            "Repair final frontend utility constant type contracts",
        ]
        split_nodes = [node for node in graph["nodes"] if node["title"] in split_titles]
        self.assertEqual([node["title"] for node in split_nodes], split_titles)
        self.assertIn("frontend/src/stores/**", split_nodes[0]["relevant_files"])
        self.assertIn("frontend/src/composables/**", split_nodes[1]["relevant_files"])
        self.assertIn("frontend/src/utils/**", split_nodes[2]["relevant_files"])
        self.assertEqual(split_nodes[0]["status"], "pending")
        self.assertIn("Repair final frontend test and fixture contracts", titles)

    def test_final_verification_composable_contracts_timeout_is_split_again(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views/admin/__tests__",
                "frontend/src/views/admin/ops/components",
                "frontend/src/views/admin/orders",
                "frontend/src/views/admin/settings",
                "frontend/src/views/auth",
                "frontend/src/views/public",
                "frontend/src/views/setup",
                "frontend/src/views/user",
                "frontend/src/components/account",
                "frontend/src/components/admin/announcements",
                "frontend/src/components/admin/payment",
                "frontend/src/components/admin/user",
                "frontend/src/components/charts",
                "frontend/src/styles",
                "frontend/src/composables/__tests__",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "frontend" / "src" / "views" / "NotFoundView.vue").write_text("<template />\n", encoding="utf-8")
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_034.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_037",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- FINAL_AUDIT_STATUS=FAIL: final source-boundary repair needs continuation.",
                        "- Must grant the repair worker edit access to frontend API, i18n, router, view, component, composable, constants, type, store, and test files when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T050.",
                        f"- Completed tasks to preserve: {', '.join(f'T{index:03d}' for index in range(1, 50))}.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T050 - Repair final frontend composable contracts",
                        "- Must continue focused task T050: Repair final frontend composable contracts.",
                        "- Previous relevant files: frontend/src/composables/**, frontend/src/types/**, frontend/package.json, frontend/pnpm-lock.yaml.",
                        "- Worker summary: T050 exceeded the Codex worker timeout.",
                        "- Timeout note: preserve T049 and split composables by OAuth, domain metering/entitlement, and shared table/navigation helpers before replaying the same scope.",
                        "",
                        "## Previous Graph Titles",
                        "",
                        "- Repair final frontend store contracts",
                        "- Repair final frontend composable contracts",
                        "- Repair final frontend utility constant type contracts",
                        "- Repair final frontend test and fixture contracts",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-30T04:05:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        titles = [node["title"] for node in graph["nodes"]]
        self.assertNotIn("Repair final frontend composable contracts", titles)
        self.assertEqual(nodes["T049"]["title"], "Repair final frontend store contracts")
        self.assertEqual(nodes["T049"]["status"], "completed")
        self.assertEqual(nodes["T050"]["title"], "Repair final frontend identity OAuth composables")
        self.assertIn("frontend/src/composables/useOpenAIOAuth.ts", nodes["T050"]["relevant_files"])
        self.assertEqual(nodes["T051"]["title"], "Repair final frontend metering entitlement composables")
        self.assertIn("frontend/src/composables/useModelWhitelist.ts", nodes["T051"]["relevant_files"])
        self.assertEqual(nodes["T052"]["title"], "Repair final frontend table navigation composables")
        self.assertIn("frontend/src/composables/useTableLoader.ts", nodes["T052"]["relevant_files"])
        self.assertEqual(nodes["T053"]["title"], "Repair final frontend utility constant type contracts")

    def test_final_verification_metering_entitlement_composables_timeout_is_split_again(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views/admin/__tests__",
                "frontend/src/views/admin/ops/components",
                "frontend/src/views/admin/orders",
                "frontend/src/views/admin/settings",
                "frontend/src/views/auth",
                "frontend/src/views/public",
                "frontend/src/views/setup",
                "frontend/src/views/user",
                "frontend/src/components/account",
                "frontend/src/components/admin/announcements",
                "frontend/src/components/admin/payment",
                "frontend/src/components/admin/user",
                "frontend/src/components/charts",
                "frontend/src/styles",
                "frontend/src/composables/__tests__",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "frontend" / "src" / "views" / "NotFoundView.vue").write_text("<template />\n", encoding="utf-8")
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_035.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_038",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- FINAL_AUDIT_STATUS=FAIL: final source-boundary repair needs continuation.",
                        "- Must grant the repair worker edit access to frontend API, i18n, router, view, component, composable, constants, type, store, and test files when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T051.",
                        f"- Completed tasks to preserve: {', '.join(f'T{index:03d}' for index in range(1, 51))}.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T051 - Repair final frontend metering entitlement composables",
                        "- Must continue focused task T051: Repair final frontend metering entitlement composables.",
                        "- Previous relevant files: frontend/src/composables/useChannelMonitorFormat.ts, frontend/src/composables/useModelWhitelist.ts, frontend/src/composables/useOnboardingTour.ts, frontend/src/composables/useQuotaNotifyState.ts, frontend/src/composables/__tests__/useModelWhitelist.spec.ts, frontend/src/types/**, frontend/package.json, frontend/pnpm-lock.yaml.",
                        "- Worker summary: T051 exceeded the Codex worker timeout.",
                        "- Timeout note: preserve T050 and split the domain composables into channel monitor format, model entitlement, and onboarding/quota scopes before replaying this task.",
                        "",
                        "## Previous Graph Titles",
                        "",
                        "- Repair final frontend store contracts",
                        "- Repair final frontend identity OAuth composables",
                        "- Repair final frontend metering entitlement composables",
                        "- Repair final frontend table navigation composables",
                        "- Repair final frontend utility constant type contracts",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-30T04:38:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        titles = [node["title"] for node in graph["nodes"]]
        self.assertNotIn("Repair final frontend metering entitlement composables", titles)
        self.assertEqual(nodes["T050"]["title"], "Repair final frontend identity OAuth composables")
        self.assertEqual(nodes["T050"]["status"], "completed")
        self.assertEqual(nodes["T051"]["title"], "Repair final frontend channel monitor format composable")
        self.assertEqual(nodes["T051"]["relevant_files"][0], "frontend/src/composables/useChannelMonitorFormat.ts")
        self.assertEqual(nodes["T052"]["title"], "Repair final frontend model entitlement composable")
        self.assertIn("frontend/src/composables/useModelWhitelist.ts", nodes["T052"]["relevant_files"])
        self.assertEqual(nodes["T053"]["title"], "Repair final frontend onboarding quota composables")
        self.assertIn("frontend/src/composables/useQuotaNotifyState.ts", nodes["T053"]["relevant_files"])
        self.assertEqual(nodes["T054"]["title"], "Repair final frontend table navigation composables")

    def test_final_verification_test_fixture_focus_preserves_deep_tail_graph(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views/admin/__tests__",
                "frontend/src/views/admin/ops/components",
                "frontend/src/views/admin/orders",
                "frontend/src/views/admin/settings",
                "frontend/src/views/auth",
                "frontend/src/views/public",
                "frontend/src/views/setup",
                "frontend/src/views/user",
                "frontend/src/components/account",
                "frontend/src/components/admin/announcements",
                "frontend/src/components/admin/payment",
                "frontend/src/components/admin/user",
                "frontend/src/components/charts",
                "frontend/src/styles",
                "frontend/src/composables/__tests__",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "frontend" / "src" / "views" / "NotFoundView.vue").write_text("<template />\n", encoding="utf-8")
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            completed = ", ".join(f"T{index:03d}" for index in range(1, 56))
            spec = root / "final_verification_repair_resume_036.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_039",
                        "",
                        "## Requirements",
                        "",
                        "- FINAL_AUDIT_STATUS=FAIL: final_verification T056 repair needs continuation before final handoff.",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- Must preserve backend migration, Ent schema, domain, repository, service, handler, server, and command wiring repair tasks before frontend tail repair.",
                        "- Must grant the repair worker edit access to frontend API, i18n, router, view, component, composable, constants, type, store, and test files when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T056.",
                        f"- Completed tasks to preserve: {completed}.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T056 - Repair final frontend test and fixture contracts",
                        "- Must continue focused task T056: Repair final frontend test and fixture contracts.",
                        "- Previous relevant files: frontend/src/**/__tests__/**, frontend/src/**/*.spec.ts, frontend/src/**/*.spec.tsx, frontend/tests/**, frontend/vitest.config.ts, frontend/package.json, frontend/pnpm-lock.yaml.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-30T05:58:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes["T006"]["title"], "Repair final frontend API module contracts")
        self.assertEqual(nodes["T050"]["title"], "Repair final frontend identity OAuth composables")
        self.assertEqual(nodes["T051"]["title"], "Repair final frontend channel monitor format composable")
        self.assertEqual(nodes["T052"]["title"], "Repair final frontend model entitlement composable")
        self.assertEqual(nodes["T053"]["title"], "Repair final frontend onboarding quota composables")
        self.assertEqual(nodes["T054"]["title"], "Repair final frontend table navigation composables")
        self.assertEqual(nodes["T055"]["title"], "Repair final frontend utility constant type contracts")
        self.assertEqual(nodes["T056"]["title"], "Repair final frontend API and integration test contracts")
        self.assertEqual(nodes["T057"]["title"], "Repair final frontend component and composable test contracts")
        self.assertEqual(nodes["T058"]["title"], "Repair final frontend view router i18n utility test contracts")
        self.assertEqual(nodes["T059"]["title"], "Repair final frontend test config and fixture contracts")
        self.assertEqual(nodes["T060"]["title"], "Audit final requirements and phase evidence")
        self.assertIn("frontend/src/api/**/*.spec.ts", nodes["T056"]["relevant_files"])
        self.assertNotIn("frontend/src/**/*.spec.ts", nodes["T056"]["relevant_files"])
        self.assertIn("frontend/src/components/**/*.spec.ts", nodes["T057"]["relevant_files"])
        self.assertNotIn("frontend/src/**/*.spec.tsx", nodes["T058"]["relevant_files"])
        self.assertEqual(nodes["T055"]["status"], "completed")
        self.assertNotEqual(nodes["T056"]["status"], "completed")

    def test_final_audit_focus_preserves_test_fixture_split_tail(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views/admin/__tests__",
                "frontend/src/views/admin/ops/components",
                "frontend/src/views/admin/orders",
                "frontend/src/views/admin/settings",
                "frontend/src/views/auth",
                "frontend/src/views/public",
                "frontend/src/views/setup",
                "frontend/src/views/user",
                "frontend/src/components/account",
                "frontend/src/components/admin/announcements",
                "frontend/src/components/admin/payment",
                "frontend/src/components/admin/user",
                "frontend/src/components/admin/usage/__tests__",
                "frontend/src/components/charts",
                "frontend/src/styles",
                "frontend/src/composables/__tests__",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "frontend" / "src" / "views" / "NotFoundView.vue").write_text("<template />\n", encoding="utf-8")
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            completed = ", ".join(f"T{index:03d}" for index in range(1, 60))
            spec = root / "final_verification_repair_resume_041.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_044",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "- Must report FINAL_AUDIT_STATUS, SIMULATION_TEST_STATUS, REAL_TEST_STATUS, REQUIRED_ACTIONS, and BLOCKERS after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T060.",
                        f"- Completed tasks to preserve: {completed}.",
                        "- Do not regenerate a broad phase graph when blocker task IDs identify a specific failed task.",
                        "- Convert out-of-scope full-suite failures into focused follow-up tasks with expanded allowed files.",
                        "",
                        "### Task T060 - Audit final requirements and phase evidence",
                        "",
                        "- Must continue focused task T060: Audit final requirements and phase evidence.",
                        "- Last task status: blocked.",
                        "- Worker summary: FINAL_AUDIT_STATUS=FAIL. Audit completed, but repairs require repository edits and allowed_files is empty.",
                        "- Tests failed: frontend/src/components/admin/usage/__tests__/UsageTable.spec.ts: 5 image usage tooltip tests fail.",
                        "- Follow-up tasks: Repair UsageTable image tooltip rendering; remove or reframe frontend /admin/ops route and API exposure; resolve residual retired schema and migration source-boundary surfaces.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-30T08:20:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes["T056"]["title"], "Repair final frontend API and integration test contracts")
        self.assertEqual(nodes["T057"]["title"], "Repair final frontend component and composable test contracts")
        self.assertEqual(nodes["T058"]["title"], "Repair final frontend view router i18n utility test contracts")
        self.assertEqual(nodes["T059"]["title"], "Repair final frontend test config and fixture contracts")
        self.assertEqual(nodes["T060"]["title"], "Audit final requirements and phase evidence")
        for task_id in ("T056", "T057", "T058", "T059"):
            self.assertEqual(nodes[task_id]["status"], "completed")
        self.assertNotEqual(nodes["T060"]["status"], "completed")

    def test_final_audit_focus_keeps_deep_tail_shape_when_tail_tasks_reopen(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views/admin/__tests__",
                "frontend/src/views/admin/ops/components",
                "frontend/src/views/admin/orders",
                "frontend/src/views/admin/settings",
                "frontend/src/views/auth",
                "frontend/src/views/public",
                "frontend/src/views/setup",
                "frontend/src/views/user",
                "frontend/src/components/account",
                "frontend/src/components/admin/announcements",
                "frontend/src/components/admin/payment",
                "frontend/src/components/admin/user",
                "frontend/src/components/admin/usage/__tests__",
                "frontend/src/components/charts",
                "frontend/src/styles",
                "frontend/src/composables/__tests__",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "frontend" / "src" / "views" / "NotFoundView.vue").write_text("<template />\n", encoding="utf-8")
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            reopened = {"T006", "T009", "T024", "T039", "T041", "T056", "T057"}
            completed = ", ".join(f"T{index:03d}" for index in range(1, 60) if f"T{index:03d}" not in reopened)
            spec = root / "final_verification_repair_resume_044.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_046",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "- Must report FINAL_AUDIT_STATUS, SIMULATION_TEST_STATUS, REAL_TEST_STATUS, REQUIRED_ACTIONS, and BLOCKERS after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T060.",
                        f"- Completed tasks to preserve: {completed}.",
                        "- Preserve final frontend split tail graph shape: T056, T057, T058, T059.",
                        "",
                        "### Task T060 - Audit final requirements and phase evidence",
                        "",
                        "- Worker summary: FINAL_AUDIT_STATUS=FAIL. /admin/ops and UsageTable findings remain.",
                        "- Tests failed: frontend/src/components/admin/usage/__tests__/UsageTable.spec.ts failed; frontend/src/api/admin/ops.ts still exposes old-domain API concepts.",
                        "- Follow-up tasks: Repair frontend/src/components/admin/usage/UsageTable.vue; remove or reframe /admin/ops frontend route/API/views.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-30T09:30:00+08:00",
            )

            graph = TaskGraphBuilder().build(ContextBundleBuilder().build(brief)).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes["T056"]["title"], "Repair final frontend API and integration test contracts")
        self.assertEqual(nodes["T057"]["title"], "Repair final frontend component and composable test contracts")
        self.assertEqual(nodes["T058"]["title"], "Repair final frontend view router i18n utility test contracts")
        self.assertEqual(nodes["T059"]["title"], "Repair final frontend test config and fixture contracts")
        self.assertNotEqual(nodes["T056"]["status"], "completed")
        self.assertNotEqual(nodes["T057"]["status"], "completed")
        self.assertEqual(nodes["T058"]["status"], "completed")
        self.assertEqual(nodes["T059"]["status"], "completed")
        self.assertEqual(nodes["T060"]["title"], "Audit final requirements and phase evidence")
        for task_id in ("T006", "T009", "T024", "T039", "T041", "T056", "T057"):
            self.assertIn(task_id, nodes["T060"]["dependencies"])
        for task_id in ("T006", "T009", "T024", "T039", "T041"):
            self.assertIn(task_id, nodes["T056"]["dependencies"])
        self.assertIn("T056", nodes["T057"]["dependencies"])

    def test_final_audit_focus_adds_delivery_artifact_repair(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for path in (
                "backend/internal/handler/admin",
                "backend/internal/service",
                "backend/internal/server",
                "backend/cmd/server",
                "deploy",
                "frontend/src/router/__tests__",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "README.md").write_text("# Billing Core\n", encoding="utf-8")
            (repo / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
            (repo / "deploy" / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            completed = ", ".join(f"T{index:03d}" for index in range(1, 60) if index != 5)
            spec = root / "final_verification_repair_resume_054.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_054",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- Must grant the repair worker edit access to backend migrations, Ent schema/generated files, backend domain/repository/service/handler/server contracts, and backend command wiring when those surfaces contain residual relay-era product concepts.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T060.",
                        f"- Completed tasks to preserve: {completed}.",
                        "- Preserve final frontend split tail graph shape: T056, T057, T058, T059.",
                        "",
                        "### Task T060 - Audit final requirements and phase evidence",
                        "",
                        "- Worker summary: FINAL_AUDIT_STATUS: FAIL with static delivery artifacts still exposing old product surfaces.",
                        "- Tests failed: backend go test fails because service.AccountTypeUpstream is undefined in backend/internal/handler/admin/account_data.go.",
                        "- Tests failed: frontend route test expects AdminOps /admin/ops while router/index.ts defines AdminAudit at /admin/audit.",
                        "- Known issues: Delivered README.md, deploy/docker-compose.yml, deploy/config.example.yaml, and deploy/relay still expose token relay/gateway/proxy behavior.",
                        "- Follow-up tasks: Clean or reframe README.md, deploy/docker-compose*.yml, deploy/config.example.yaml, and deploy/relay.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-07-02T01:45:00+08:00",
            )

            graph = TaskGraphBuilder().build(ContextBundleBuilder().build(brief)).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        delivery = next(node for node in graph["nodes"] if node["title"] == "Repair final delivery artifact contracts")
        self.assertEqual(nodes["T005"]["title"], "Repair final backend service handler server contracts")
        self.assertNotEqual(nodes["T005"]["status"], "completed")
        self.assertIn("backend/internal/handler/**", nodes["T005"]["relevant_files"])
        self.assertIn("README.md", delivery["relevant_files"])
        self.assertIn("deploy/**", delivery["relevant_files"])
        audit_node = next(node for node in graph["nodes"] if node["title"] == "Audit final requirements and phase evidence")
        self.assertIn(delivery["id"], audit_node["dependencies"])

    def test_final_gate_rerun_requirement_does_not_preserve_gate_tasks(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for path in (
                "backend/migrations",
                "backend/ent/schema",
                "backend/internal/service",
                "frontend/src/api",
                "frontend/src/components/__tests__",
                "frontend/src/composables/__tests__",
                "frontend/src/views/admin/settings",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            completed = ", ".join(f"T{index:03d}" for index in range(1, 21))
            spec = root / "final_verification_repair_resume_092.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_108",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "- Must report FINAL_AUDIT_STATUS, SIMULATION_TEST_STATUS, REAL_TEST_STATUS, REQUIRED_ACTIONS, and BLOCKERS after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T016, T017, T018, T019.",
                        f"- Completed tasks to preserve: {completed}.",
                        "- Final verification gate tasks must rerun after repair, not be preserved as completed: T016, T017, T018, T019.",
                        "- Preserve final frontend split tail graph shape: T056, T057, T058, T059.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-07-04T02:10:00+09:00",
            )

            graph = TaskGraphBuilder().build(ContextBundleBuilder().build(brief)).to_dict()

        gate_titles = {
            "Audit final requirements and phase evidence",
            "Run final simulation probes",
            "Run final real repository checks",
            "Review final handoff markers",
        }
        gate_nodes = [node for node in graph["nodes"] if node["title"] in gate_titles]
        self.assertEqual({node["title"] for node in gate_nodes}, gate_titles)
        for node in gate_nodes:
            self.assertNotEqual(node["status"], "completed")
            self.assertFalse(
                any(item["type"] == "focused_repair_preserved_task" for item in node["evidence"]),
                node["id"],
            )

    def test_final_gate_target_files_reopen_matching_preserved_repair_task(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for path in (
                "backend/migrations",
                "backend/ent/schema",
                "backend/internal/domain",
                "backend/internal/repository",
                "backend/internal/service",
                "backend/internal/handler",
                "backend/internal/server",
                "frontend/src/api",
                "frontend/src/i18n",
                "frontend/src/router",
                "frontend/src/components/layout",
                "frontend/src/views/admin/ops/components/__tests__",
                "deploy",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            resume = root / "final_verification_repair_resume_092.md"
            resume.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_108",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "- Must report FINAL_AUDIT_STATUS, SIMULATION_TEST_STATUS, REAL_TEST_STATUS, REQUIRED_ACTIONS, and BLOCKERS after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: none reported; infer the narrowest failing task from the gate evidence.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006, T007, T008.",
                    ]
                ),
                encoding="utf-8",
            )
            repair = root / "final_verification_repair_111.md"
            repair.write_text(
                "\n".join(
                    [
                        "# Auto Repair For Final Full-System Audit And Testing",
                        "",
                        "Repair attempt: 111",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Failing Verification Issues",
                        "",
                        "- FINAL_AUDIT_STATUS is failed.",
                        "- REAL_TEST_STATUS is failed.",
                        "- Must repair T011 verification issue (Run final real repository checks): REAL_TEST_STATUS=FAIL. Frontend build failed.",
                        "- Target files: frontend/src/router/index.ts, frontend/src/components/layout/AppSidebar.vue, frontend/src/views/admin/ops/components/__tests__/OpsSettingsDialog.spec.ts, frontend/src/views/admin/ops/components/__tests__/OpsSystemLogTable.spec.ts.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[resume, repair],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-07-04T07:05:00+09:00",
            )

            graph = TaskGraphBuilder().build(ContextBundleBuilder().build(brief)).to_dict()

        route_repair = next(node for node in graph["nodes"] if node["title"] == "Repair final frontend routes views and tests")
        self.assertNotEqual(route_repair["status"], "completed")
        audit_node = next(node for node in graph["nodes"] if node["title"] == "Audit final requirements and phase evidence")
        self.assertIn(route_repair["id"], audit_node["dependencies"])
        self.assertNotEqual(audit_node["status"], "completed")

    def test_final_gate_embedded_runtime_assets_create_focused_repair_task(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for path in (
                "backend/internal/web",
                "backend/internal/veyra/portal_dist",
                "extensions/veyra/portal",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "backend" / "internal" / "web" / "embed_on.go").write_text("package web\n", encoding="utf-8")
            (repo / "backend" / "internal" / "web" / "embed_test.go").write_text("package web\n", encoding="utf-8")
            (repo / "backend" / "internal" / "veyra" / "portal_dist" / "index.html").write_text(
                "<title>API Gateway</title>\n",
                encoding="utf-8",
            )
            (repo / "backend" / "internal" / "veyra" / "portal_dist" / "mobile.html").write_text(
                "sub2api-console\n",
                encoding="utf-8",
            )
            (repo / "backend" / "internal" / "veyra" / "portal_dist" / "app.js").write_text(
                "window.route = 'sub2api-console'\n",
                encoding="utf-8",
            )
            (repo / "extensions" / "veyra" / "portal" / "index.html").write_text(
                "Veyra portal API Gateway\n",
                encoding="utf-8",
            )
            spec = root / "final_verification_repair_resume_099.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_120",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Failing Verification Issues",
                        "",
                        "- Must repair T015 verification issue: FINAL_AUDIT_STATUS=FAIL. Embedded runtime assets expose legacy gateway identity.",
                        "- Tests failed: Semantic source-boundary probe failed: backend/internal/web/embed_on.go injects '<title>{site} - AI API Gateway</title>'; backend/internal/veyra/portal_dist/index.html and backend/internal/veyra/portal_dist/mobile.html expose data-route='sub2api-console'; backend/internal/veyra/portal_dist/app.js still ships the legacy sub2api-console route key; extensions/veyra/portal source files contain the same Veyra portal legacy copy.",
                        "- Target files: backend/internal/web/embed_on.go, backend/internal/web/embed_test.go, backend/internal/veyra/portal_dist/index.html, backend/internal/veyra/portal_dist/mobile.html, backend/internal/veyra/portal_dist/app.js, extensions/veyra/portal/**, frontend/package.json, final_verification_worker_report.json, attempt_119.json.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T015.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014.",
                        "",
                        "## Previous Final Verification Failure",
                        "",
                        "- Historical graph text mentioned Repair final frontend admin user create edit components.",
                        "- Historical graph text mentioned Repair final frontend admin monitor components.",
                        "- Historical graph text mentioned frontend/src/components/admin/user/UserCreateModal.vue.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-07-04T00:00:00+00:00",
            )

            graph = TaskGraphBuilder().build(ContextBundleBuilder().build(brief)).to_dict()

        embedded = next(node for node in graph["nodes"] if node["title"] == "Repair final embedded runtime asset contracts")
        self.assertEqual(embedded["status"], "pending")
        self.assertIn("backend/internal/web/embed_on.go", embedded["relevant_files"])
        self.assertIn("backend/internal/veyra/portal_dist/mobile.html", embedded["relevant_files"])
        self.assertIn("backend/internal/veyra/portal_dist/app.js", embedded["relevant_files"])
        self.assertIn("extensions/veyra/portal/**", embedded["relevant_files"])
        frontend_nodes = [node for node in graph["nodes"] if node["title"].startswith("Repair final frontend")]
        self.assertFalse(
            any(node["title"].startswith("Repair final frontend") and node["status"] != "completed" for node in graph["nodes"])
        )

    def test_final_gate_frontend_locale_and_backend_protocol_targets_are_focused(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for path in (
                "frontend/src/i18n/locales",
                "frontend/src/views/admin",
                "frontend/src/components/payment",
                "frontend/src/components/user",
                "backend/internal/veyra",
                "backend/internal/server/middleware",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_101.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "## Failing Verification Issues",
                        "",
                        "- Must repair T003 verification issue: FINAL_AUDIT_STATUS=FAIL. Previous embedded portal_dist/app.js blocker now pass, but final audit found remaining user-facing/model-gateway identity in frontend locale/component surfaces and residual backend sub2api protocol/intent names.",
                        "- Failed commands: Found frontend/src/i18n/locales/en.ts:83 Service account pool; :2254 Claude Code Client Restriction. Found backend/internal/veyra/intent.go:7 PortalIntentSub2API='sub2api'; backend/internal/server/middleware/admin_auth.go:36 Sec-WebSocket-Protocol: sub2api-admin.",
                        "- Follow-up tasks: Create a focused repair task with allowed_files including frontend/src/i18n/locales/en.ts, frontend/src/i18n/locales/zh.ts, frontend/src/views/admin/SettingsView.vue, frontend/src/components/payment/SubscriptionPlanCard.vue, and frontend/src/components/user/PlatformUsageBreakdown.vue. Create a backend repair task for backend/internal/veyra/intent.go, backend/internal/veyra/ticket_test.go, backend/internal/server/middleware/admin_auth.go.",
                        "- Target files: backend/internal/veyra/portal_dist/app.js, frontend/src/i18n/locales/en.ts, frontend/src/i18n/locales/zh.ts, frontend/src/views/admin/SettingsView.vue, frontend/src/components/payment/SubscriptionPlanCard.vue, frontend/src/components/user/PlatformUsageBreakdown.vue, backend/internal/veyra/intent.go, backend/internal/veyra/ticket_test.go, backend/internal/server/middleware/admin_auth.go.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T003.",
                        "- Completed tasks to preserve: T001.",
                        "",
                        "## Previous Final Verification Failure",
                        "",
                        "- Historical graph text mentioned Repair final frontend API and i18n contracts.",
                        "- Historical graph text mentioned Repair final frontend routes views and tests.",
                        "- Historical graph text mentioned Repair final backend service handler server contracts.",
                        "- Previous embedded runtime blocker appears repaired: 0 hits for sub2api-console.",
                    ]
                ),
                encoding="utf-8",
            )
            graph = TaskGraphBuilder().build(
                ContextBundleBuilder().build(
                    ProjectBriefBuilder().build(
                        objective="Final CRM handoff audit",
                        documents=[spec],
                        repository_path=repo,
                        constraints=["Scope boundary mode: large_refactor"],
                        created_at="2026-07-04T09:35:00+00:00",
                    )
                )
            ).to_dict()

        titles = [node["title"] for node in graph["nodes"]]
        self.assertIn("Repair final frontend locale component boundary contracts", titles)
        self.assertIn("Repair final backend runtime protocol identity contracts", titles)
        self.assertNotIn("Repair final frontend API and i18n contracts", titles)
        self.assertNotIn("Repair final frontend routes views and tests", titles)
        self.assertNotIn("Repair final backend service handler server contracts", titles)
        self.assertNotIn("Repair final embedded runtime asset contracts", titles)

    def test_final_gate_admin_ops_targets_are_focused(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for path in (
                "frontend/src/api/admin",
                "frontend/src/router",
                "frontend/src/views/admin/ops",
                "frontend/src/views/admin",
                "backend/internal/server",
            ):
                (repo / path).mkdir(parents=True, exist_ok=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_106.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "## Failing Verification Issues",
                        "",
                        "- Must repair T005 verification issue: FINAL_AUDIT_STATUS=FAIL. The routed frontend AdminAudit surface loads ops views/API code that still calls /admin/ops/** endpoints.",
                        "- Failed commands: Frontend source-boundary probe for reachable AdminAudit and /admin/ops API calls: ops_endpoint_hits=78; examples include frontend/src/api/admin/ops.ts /admin/ops/upstream-errors and /admin/ops/dashboard/overview.",
                        "- Follow-up tasks: grant edit access to frontend/src/router/index.ts, frontend/src/api/admin/ops.ts, frontend/src/views/admin/ops/**, and frontend/src/views/admin/UsageView.vue.",
                        "- Target files: frontend/src/router/index.ts, frontend/src/api/admin/ops.ts, frontend/src/views/admin/ops/**, frontend/src/views/admin/UsageView.vue, backend/internal/server/billing_core_routes_test.go.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: none reported; infer the narrowest failing task from the gate evidence.",
                        "- Completed tasks to preserve: T002, T003, T004, T009, T001.",
                        "",
                        "## Previous Final Verification Failure",
                        "",
                        "- Historical graph text mentioned Repair final backend service handler server contracts.",
                        "- Historical graph text mentioned Repair final frontend API and i18n contracts.",
                        "- Historical graph text mentioned Repair final frontend routes views and tests.",
                    ]
                ),
                encoding="utf-8",
            )
            graph = TaskGraphBuilder().build(
                ContextBundleBuilder().build(
                    ProjectBriefBuilder().build(
                        objective="Final CRM handoff audit",
                        documents=[spec],
                        repository_path=repo,
                        constraints=["Scope boundary mode: large_refactor"],
                        created_at="2026-07-04T20:10:00+08:00",
                    )
                )
            ).to_dict()

        titles = [node["title"] for node in graph["nodes"]]
        self.assertIn("Repair final frontend admin ops audit surface contracts", titles)
        self.assertNotIn("Repair final backend service handler server contracts", titles)
        self.assertNotIn("Repair final frontend API and i18n contracts", titles)
        self.assertNotIn("Repair final frontend routes views and tests", titles)
        self.assertNotIn("Repair final delivery artifact contracts", titles)

    def test_final_gate_forbidden_admin_surface_targets_are_focused(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for path in (
                "frontend/src/api/admin",
                "frontend/src/api/__tests__",
                "frontend/src/components/layout",
                "frontend/src/components/admin/announcements",
                "frontend/src/router",
                "frontend/src/stores",
                "frontend/src/views/admin/__tests__",
                "frontend/src/views/admin/announcements",
                "frontend/src/views/admin/ops",
                "backend",
            ):
                (repo / path).mkdir(parents=True, exist_ok=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_107.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_130",
                        "",
                        "## Failing Verification Issues",
                        "",
                        "- Must repair T003 verification issue: FINAL_AUDIT_STATUS=FAIL; SIMULATION_TEST_STATUS=FAIL; REAL_TEST_STATUS=FAIL. Active frontend source-boundary surfaces still reference backend-forbidden routes.",
                        "- Failed commands: pnpm exec vitest run: Failures in src/api/__tests__/admin.ops.spec.ts still expect /admin/ops endpoints while implementation calls /admin/analytics and /admin/audit.",
                        "- Follow-up tasks: Repair frontend announcement exposure; Replace /admin/groups API usage in active users/settings/usage/audit flows; Update frontend/src/api/__tests__/admin.ops.spec.ts.",
                        "- Target files: frontend/src/router/index.ts, frontend/src/components/layout/AppSidebar.vue, frontend/src/views/admin/__tests__/legacyAdminRoutes.spec.ts, frontend/src/api/__tests__/admin.ops.spec.ts, frontend/src/api/admin/groups.ts, App.vue.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: none reported; infer the narrowest failing task from the gate evidence.",
                        "- Completed tasks to preserve: T001.",
                        "",
                        "## Previous Final Verification Failure",
                        "",
                        "- Historical graph text mentioned Repair final backend service handler server contracts.",
                        "- Historical graph text mentioned Repair final frontend API and i18n contracts.",
                        "- Historical graph text mentioned Repair final frontend routes views and tests.",
                        "- Historical graph text mentioned Repair final frontend admin ops audit surface contracts.",
                    ]
                ),
                encoding="utf-8",
            )
            graph = TaskGraphBuilder().build(
                ContextBundleBuilder().build(
                    ProjectBriefBuilder().build(
                        objective="Final CRM handoff audit",
                        documents=[spec],
                        repository_path=repo,
                        constraints=["Scope boundary mode: large_refactor"],
                        created_at="2026-07-04T20:35:00+08:00",
                    )
                )
            ).to_dict()

        titles = [node["title"] for node in graph["nodes"]]
        self.assertIn("Repair final frontend forbidden admin route surface contracts", titles)
        self.assertNotIn("Repair final frontend admin ops audit surface contracts", titles)
        self.assertNotIn("Repair final backend service handler server contracts", titles)
        self.assertNotIn("Repair final frontend API and i18n contracts", titles)
        self.assertNotIn("Repair final frontend routes views and tests", titles)

    def test_final_verification_admin_settings_legacy_timeout_is_split(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for path in (
                "backend/internal/handler/admin",
                "backend/internal/service",
                "backend/internal/model",
                "backend/internal/dto",
                "backend/internal/config",
                "frontend/src/api/admin",
                "frontend/src/api/__tests__",
                "frontend/src/i18n/locales",
                "frontend/src/views/admin/__tests__",
            ):
                (repo / path).mkdir(parents=True, exist_ok=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_139.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "## Failing Verification Issues",
                        "",
                        "- Must repair T002 verification issue: Repair final admin settings legacy surface contracts exceeded the Codex worker timeout.",
                        "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                        "- FINAL_AUDIT_STATUS=FAIL: registered admin settings API/UI still expose OpenAI, gateway, channel, and subscription-era settings.",
                        "- Target files: backend/internal/handler/admin/settings.go, backend/internal/service/settings.go, frontend/src/api/admin/settings.ts, frontend/src/views/admin/SettingsView.vue, frontend/src/views/admin/__tests__/SettingsView.spec.ts.",
                    ]
                ),
                encoding="utf-8",
            )
            graph = TaskGraphBuilder().build(
                ContextBundleBuilder().build(
                    ProjectBriefBuilder().build(
                        objective="Final CRM handoff audit",
                        documents=[spec],
                        repository_path=repo,
                        constraints=["Scope boundary mode: large_refactor"],
                        created_at="2026-07-04T23:40:00+08:00",
                    )
                )
            ).to_dict()

        titles = [node["title"] for node in graph["nodes"]]
        self.assertIn("Repair final backend admin settings legacy contracts", titles)
        self.assertIn("Repair final frontend admin settings legacy contracts", titles)
        self.assertNotIn("Repair final admin settings legacy surface contracts", titles)

    def test_final_gate_route_sidebar_contract_overrides_stale_settings_timeout(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for path in (
                "frontend/src/router/__tests__",
                "frontend/src/components/layout/__tests__",
                "frontend/src/views/admin/announcements",
                "frontend/src/components/admin/announcements",
                "backend",
            ):
                (repo / path).mkdir(parents=True, exist_ok=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_115.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "## Failing Verification Issues",
                        "",
                        "- Must repair T004 verification issue: FINAL_AUDIT_STATUS=FAIL. Frontend production verification is blocked by a TypeScript build failure and route/sidebar contract failures around the final CRM surface.",
                        "- Failed commands: pnpm --dir frontend run build: AppSidebar.vue BellIcon is declared but its value is never read.; pnpm --dir frontend run test: crm-route-surface expects AdminAnnouncements at /admin/announcements; AppSidebar expected /admin/announcements nav path.",
                        "- Target files: frontend/src/router/index.ts, frontend/src/router/__tests__/crm-route-surface.spec.ts, frontend/src/components/layout/AppSidebar.vue, frontend/src/components/layout/__tests__/AppSidebar.spec.ts.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T004.",
                        "- Completed tasks to preserve: T001, T002, T003.",
                        "- Preserve previous repair context from final_verification_repair_resume_114.md: Focused timeout task titles: T002: Repair final admin settings legacy surface contracts.",
                    ]
                ),
                encoding="utf-8",
            )
            graph = TaskGraphBuilder().build(
                ContextBundleBuilder().build(
                    ProjectBriefBuilder().build(
                        objective="Final CRM handoff audit",
                        documents=[spec],
                        repository_path=repo,
                        constraints=["Scope boundary mode: large_refactor"],
                        created_at="2026-07-05T00:30:00+08:00",
                    )
                )
            ).to_dict()

        titles = [node["title"] for node in graph["nodes"]]
        self.assertIn("Repair final frontend route/sidebar contract leftovers", titles)
        self.assertNotIn("Repair final backend admin settings legacy contracts", titles)
        self.assertNotIn("Repair final frontend admin settings legacy contracts", titles)

    def test_final_simulation_backend_identity_strings_override_stale_frontend_context(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for path in (
                "backend/internal/repository",
                "backend/internal/pkg/logger",
                "backend/internal/pkg/sysutil",
                "backend/internal/handler/admin",
                "backend/internal/service",
                "frontend/src/router",
                "frontend/src/components/layout",
            ):
                (repo / path).mkdir(parents=True, exist_ok=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_116.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "## Failing Verification Issues",
                        "",
                        "- Must report FINAL_AUDIT_STATUS, SIMULATION_TEST_STATUS, REAL_TEST_STATUS, REQUIRED_ACTIONS, and BLOCKERS after repair.",
                        "- Must repair T004 verification issue: SIMULATION_TEST_STATUS=FAIL. Backend production static identity probe found residual legacy sub2api/new-api strings.",
                        "- Follow-up tasks: Allow edits to backend production files containing residual sub2api/new-api strings and update corresponding tests because allowed_files is empty.",
                        "- Evidence: backend/internal/repository/dashboard_cache.go, backend/internal/pkg/logger/options.go, backend/internal/pkg/sysutil/restart.go, backend/internal/handler/admin/ops_ws_handler.go, backend/internal/service/update_service.go.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T004.",
                        "- Completed tasks to preserve: T001, T002.",
                        "- Preserve previous repair context from final_verification_repair_resume_115.md: frontend route repair.",
                    ]
                ),
                encoding="utf-8",
            )
            graph = TaskGraphBuilder().build(
                ContextBundleBuilder().build(
                    ProjectBriefBuilder().build(
                        objective="Final CRM handoff audit",
                        documents=[spec],
                        repository_path=repo,
                        constraints=["Scope boundary mode: large_refactor"],
                        created_at="2026-07-05T00:42:00+08:00",
                    )
                )
            ).to_dict()

        titles = [node["title"] for node in graph["nodes"]]
        self.assertIn("Repair final backend production identity string leftovers", titles)
        self.assertNotIn("Repair final frontend route/sidebar contract leftovers", titles)
        self.assertNotIn("Repair final backend service handler server contracts", titles)

    def test_final_source_boundary_sweep_splits_backend_migration_and_frontend_leftovers(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for path in (
                "backend/cmd/server",
                "backend/internal/config",
                "backend/internal/server",
                "backend/migrations",
                "frontend/src/api",
                "frontend/src/composables",
                "frontend/src/stores",
                "frontend/src/types",
            ):
                (repo / path).mkdir(parents=True, exist_ok=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_119.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- Must grant the repair worker edit access to backend migrations, backend config, cmd/server wiring, repositories, services, handlers, server contracts, and frontend API/composable/type/store files.",
                        "",
                        "## Failing Verification Issues",
                        "",
                        "- Must repair T003 verification issue: FINAL_AUDIT_STATUS=FAIL; SIMULATION_TEST_STATUS=FAIL; REAL_TEST_STATUS=PASS.",
                        "- BLOCKERS=[allowed_files is empty so repository repairs were not permitted; production source still contains retired relay/gateway/upstream/proxy/account/subscription surfaces].",
                        "- Tests failed: SIMULATION_TEST_STATUS=FAIL: backend production static probe found 237 files with OpenAI/Claude/Gemini/Antigravity/Codex or gateway route identity terms.",
                        "- Tests failed: SIMULATION_TEST_STATUS=FAIL: backend production static probe found 241 files with gateway/proxy/model/upstream/channel-monitor capability terms.",
                        "- Tests failed: SIMULATION_TEST_STATUS=FAIL: backend migrations still contain forbidden fresh-install table references; 095_subscription_plans.sql creates subscription_plans and 005_schema_parity.sql alters accounts.",
                        "- Tests failed: SIMULATION_TEST_STATUS=FAIL: frontend source probe found 28 files with retired concepts, including retired API/composable facades.",
                        "- Known issues: Green route and unit tests do not prove source-boundary compliance because production source and wiring still retain retired capabilities.",
                        "- Target files: 095_subscription_plans.sql, 005_schema_parity.sql, backend/internal/config/config.go, backend/cmd/server/wire_gen.go, backend/internal/server/billing_core_routes_test.go.",
                    ]
                ),
                encoding="utf-8",
            )

            graph = TaskGraphBuilder().build(
                ContextBundleBuilder().build(
                    ProjectBriefBuilder().build(
                        objective="Resume Billing Core final verification.",
                        documents=[spec],
                        repository_path=repo,
                        constraints=["Scope boundary mode: large_refactor"],
                        created_at="2026-07-05T01:55:00+08:00",
                    )
                )
            ).to_dict()

        titles = [node["title"] for node in graph["nodes"]]
        self.assertIn("Repair final backend migration source-boundary leftovers", titles)
        self.assertIn("Repair final backend production source-boundary leftovers", titles)
        self.assertIn("Repair final frontend retired source-boundary leftovers", titles)
        self.assertNotIn("Repair final backend startup contract wiring", titles)
        backend_task = next(
            node for node in graph["nodes"] if node["title"] == "Repair final backend production source-boundary leftovers"
        )
        frontend_task = next(
            node for node in graph["nodes"] if node["title"] == "Repair final frontend retired source-boundary leftovers"
        )
        self.assertIn("backend/internal/config/**", backend_task["relevant_files"])
        self.assertIn("backend/cmd/server/**", backend_task["relevant_files"])
        self.assertIn("frontend/src/composables/**", frontend_task["relevant_files"])

    def test_final_frontend_retired_source_boundary_timeout_is_split(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for path in (
                "backend/cmd/server",
                "backend/internal/config",
                "backend/internal/server",
                "backend/migrations",
                "frontend/src/api",
                "frontend/src/composables",
                "frontend/src/stores",
                "frontend/src/types",
                "frontend/src/views",
                "frontend/src/components",
            ):
                (repo / path).mkdir(parents=True, exist_ok=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_120.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- Must grant the repair worker edit access to backend migrations, backend config, cmd/server wiring, repositories, services, handlers, server contracts, and frontend API/composable/type/store files.",
                        "",
                        "## Failing Verification Issues",
                        "",
                        "- Must repair T004 verification issue (Repair final frontend retired source-boundary leftovers): FINAL_AUDIT_STATUS=FAIL; Codex worker timed out after 900 seconds.",
                        "- BLOCKERS=[allowed_files is empty so repository repairs were not permitted; production source still contains retired relay/gateway/upstream/proxy/account/subscription surfaces].",
                        "- Tests failed: SIMULATION_TEST_STATUS=FAIL: backend production static probe found 237 files with OpenAI/Claude/Gemini/Antigravity/Codex or gateway route identity terms.",
                        "- Tests failed: SIMULATION_TEST_STATUS=FAIL: backend production static probe found 241 files with gateway/proxy/model/upstream/channel-monitor capability terms.",
                        "- Tests failed: SIMULATION_TEST_STATUS=FAIL: backend migrations still contain forbidden fresh-install table references.",
                        "- Tests failed: SIMULATION_TEST_STATUS=FAIL: frontend source probe found 28 files with retired concepts, including retired API/composable facades.",
                        "- Known issues: Green route and unit tests do not prove source-boundary compliance because production source and wiring still retain retired capabilities.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T004.",
                        "- Completed tasks to preserve: T001, T002, T003.",
                        "### Task T004 - Repair final frontend retired source-boundary leftovers",
                        "- Must continue focused task T004: Repair final frontend retired source-boundary leftovers.",
                        "- Last task status: failed.",
                        "- Previous relevant files: frontend/src/api/**, frontend/src/composables/**, frontend/src/stores/**, frontend/src/types/**, frontend/src/views/**, frontend/src/components/**, frontend/package.json.",
                        "- Timeout note: preserve evidence and split this workflow before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )

            graph = TaskGraphBuilder().build(
                ContextBundleBuilder().build(
                    ProjectBriefBuilder().build(
                        objective="Resume Billing Core final verification.",
                        documents=[spec],
                        repository_path=repo,
                        constraints=["Scope boundary mode: large_refactor"],
                        created_at="2026-07-05T02:20:00+08:00",
                    )
                )
            ).to_dict()

        titles = [node["title"] for node in graph["nodes"]]
        self.assertIn("Repair final frontend retired API type source-boundary leftovers", titles)
        self.assertIn("Repair final frontend retired composable store source-boundary leftovers", titles)
        self.assertIn("Repair final frontend retired view component source-boundary leftovers", titles)
        self.assertNotIn("Repair final frontend retired source-boundary leftovers", titles)
        api_task = next(
            node for node in graph["nodes"] if node["title"] == "Repair final frontend retired API type source-boundary leftovers"
        )
        store_task = next(
            node
            for node in graph["nodes"]
            if node["title"] == "Repair final frontend retired composable store source-boundary leftovers"
        )
        self.assertIn("frontend/src/api/**", api_task["relevant_files"])
        self.assertIn("frontend/src/composables/**", store_task["relevant_files"])

    def test_final_audit_remaining_source_boundary_after_frontend_split_creates_followups(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for path in (
                "backend/internal/handler",
                "backend/internal/service",
                "backend/internal/repository",
                "backend/internal/config",
                "backend/internal/server",
                "frontend/src/api",
                "frontend/src/views/user",
                "frontend/src/components/common",
                "frontend/src/components/payment",
                "frontend/src/components/user/dashboard",
                "frontend/src/i18n",
            ):
                (repo / path).mkdir(parents=True, exist_ok=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_122.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "## Failing Verification Issues",
                        "",
                        "- Must repair T007 verification issue: FINAL_AUDIT_STATUS: FAIL. The audit found unresolved source-boundary and real verification failures, and allowed_files is empty.",
                        "- SIMULATION_TEST_STATUS: FAIL. Static semantic probes found 62 production/delivery files and 17 non-test frontend files retaining retired relay-era surfaces.",
                        "- REAL_TEST_STATUS: FAIL. frontend pnpm exec vue-tsc --noEmit exited 2 with unresolved TypeScript errors.",
                        "- Backend production code still contains gateway, OpenAI gateway, proxy, channel monitor, upstream account, and subscription-plan implementation surfaces.",
                        "- Frontend typecheck fails after earlier compatibility removals because multiple consumers were not migrated.",
                        "- Examples: SubscriptionProgressMini.vue, SubscriptionPlanCard.vue, UserDashboardCharts.vue, paymentWechatResume.ts.",
                        "- Follow-up tasks: Grant edit scope for backend handler/service/repository/config/server surfaces and remove or quarantine remaining retired relay-era production code.",
                        "- Follow-up tasks: Grant edit scope for frontend API/views/components/i18n/stores/types and migrate remaining consumers to CRM billing terminology and current type contracts.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T007.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006.",
                        "- Task T002 - Repair final backend migration source-boundary leftovers was completed and should be preserved.",
                        "- Task T003 - Repair final backend production source-boundary leftovers was completed and should be preserved.",
                        "- Task T004 - Repair final frontend retired API type source-boundary leftovers was completed and should be preserved.",
                        "- Task T005 - Repair final frontend retired composable store source-boundary leftovers was completed and should be preserved.",
                        "- Task T006 - Repair final frontend retired view component source-boundary leftovers was completed and should be preserved.",
                    ]
                ),
                encoding="utf-8",
            )

            graph = TaskGraphBuilder().build(
                ContextBundleBuilder().build(
                    ProjectBriefBuilder().build(
                        objective="Resume Billing Core final verification.",
                        documents=[spec],
                        repository_path=repo,
                        constraints=["Scope boundary mode: large_refactor"],
                        created_at="2026-07-05T03:00:00+08:00",
                    )
                )
            ).to_dict()

        nodes = {node["title"]: node for node in graph["nodes"]}
        self.assertIn("Repair final backend legacy production quarantine leftovers", nodes)
        self.assertIn("Repair final frontend API settings typecheck leftovers", nodes)
        self.assertIn("Repair final frontend view component typecheck leftovers", nodes)
        self.assertIn("backend/internal/handler/**", nodes["Repair final backend legacy production quarantine leftovers"]["relevant_files"])
        self.assertIn("frontend/src/api/**", nodes["Repair final frontend API settings typecheck leftovers"]["relevant_files"])
        self.assertIn(
            "frontend/src/components/common/SubscriptionProgressMini.vue",
            nodes["Repair final frontend view component typecheck leftovers"]["relevant_files"],
        )
        audit_node = next(node for node in graph["nodes"] if node["title"] == "Audit final requirements and phase evidence")
        simulation_node = next(node for node in graph["nodes"] if node["title"] == "Run final simulation probes")
        self.assertNotEqual(audit_node["status"], "completed")
        self.assertNotEqual(simulation_node["status"], "completed")

    def test_final_backend_legacy_quarantine_timeout_is_split(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for path in (
                "backend/internal/handler",
                "backend/internal/service",
                "backend/internal/repository",
                "backend/internal/config",
                "backend/internal/server",
                "frontend/src/api",
                "frontend/src/views/user",
                "frontend/src/components/common",
                "frontend/src/components/payment",
                "frontend/src/components/user/dashboard",
                "frontend/src/i18n",
            ):
                (repo / path).mkdir(parents=True, exist_ok=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_123.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "## Failing Verification Issues",
                        "",
                        "- Must repair T002 verification issue (Repair final backend legacy production quarantine leftovers): Codex worker timed out after 900 seconds.",
                        "- FINAL_AUDIT_STATUS: FAIL. The audit found unresolved source-boundary and real verification failures, and allowed_files is empty.",
                        "- SIMULATION_TEST_STATUS: FAIL. Static semantic probes found 62 production/delivery files and 17 non-test frontend files retaining retired relay-era surfaces.",
                        "- REAL_TEST_STATUS: FAIL. frontend pnpm exec vue-tsc --noEmit exited 2 with unresolved TypeScript errors.",
                        "- Backend production code still contains gateway, OpenAI gateway, proxy, channel monitor, upstream account, and subscription-plan implementation surfaces.",
                        "- Frontend typecheck fails after earlier compatibility removals because multiple consumers were not migrated.",
                        "- Examples: SubscriptionProgressMini.vue, SubscriptionPlanCard.vue, UserDashboardCharts.vue, paymentWechatResume.ts.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T002.",
                        "- Focused timeout task IDs: T002.",
                        "- Focused timeout task titles: T002: Repair final backend legacy production quarantine leftovers.",
                        "- Previous relevant files: backend/internal/handler/**, backend/internal/service/**, backend/internal/repository/**, backend/internal/config/**, backend/internal/server/**.",
                    ]
                ),
                encoding="utf-8",
            )

            graph = TaskGraphBuilder().build(
                ContextBundleBuilder().build(
                    ProjectBriefBuilder().build(
                        objective="Resume Billing Core final verification.",
                        documents=[spec],
                        repository_path=repo,
                        constraints=["Scope boundary mode: large_refactor"],
                        created_at="2026-07-05T03:20:00+08:00",
                    )
                )
            ).to_dict()

        titles = [node["title"] for node in graph["nodes"]]
        self.assertIn("Repair final backend handler server quarantine leftovers", titles)
        self.assertIn("Repair final backend service repository quarantine leftovers", titles)
        self.assertIn("Repair final backend config runtime quarantine leftovers", titles)
        self.assertNotIn("Repair final backend legacy production quarantine leftovers", titles)

    def test_final_backend_handler_server_quarantine_timeout_uses_exact_files(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for path in (
                "backend/internal/handler/admin",
                "backend/internal/handler/dto",
                "backend/internal/server/middleware",
                "backend/cmd/server",
                "frontend/src/api",
                "frontend/src/views/user",
                "frontend/src/components/common",
                "frontend/src/components/payment",
                "frontend/src/components/user/dashboard",
                "frontend/src/i18n",
            ):
                (repo / path).mkdir(parents=True, exist_ok=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_124.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "## Failing Verification Issues",
                        "",
                        "- Must repair T002 verification issue (Repair final backend handler server quarantine leftovers): Codex worker timed out after 900 seconds.",
                        "- FINAL_AUDIT_STATUS: FAIL. The audit found unresolved source-boundary and real verification failures, and allowed_files is empty.",
                        "- SIMULATION_TEST_STATUS: FAIL. Static semantic probes found 62 production/delivery files and 17 non-test frontend files retaining retired relay-era surfaces.",
                        "- REAL_TEST_STATUS: FAIL. frontend pnpm exec vue-tsc --noEmit exited 2 with unresolved TypeScript errors.",
                        "- Backend production code still contains gateway, OpenAI gateway, proxy, channel monitor, upstream account, and subscription-plan implementation surfaces.",
                        "- Frontend typecheck fails after earlier compatibility removals because multiple consumers were not migrated.",
                        "- Examples: SubscriptionProgressMini.vue, SubscriptionPlanCard.vue, UserDashboardCharts.vue, paymentWechatResume.ts.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T002.",
                        "- Focused timeout task IDs: T002.",
                        "- Focused timeout task titles: T002: Repair final backend handler server quarantine leftovers.",
                    ]
                ),
                encoding="utf-8",
            )

            graph = TaskGraphBuilder().build(
                ContextBundleBuilder().build(
                    ProjectBriefBuilder().build(
                        objective="Resume Billing Core final verification.",
                        documents=[spec],
                        repository_path=repo,
                        constraints=["Scope boundary mode: large_refactor"],
                        created_at="2026-07-05T03:40:00+08:00",
                    )
                )
            ).to_dict()

        nodes = {node["title"]: node for node in graph["nodes"]}
        self.assertIn("Repair final backend admin handler quarantine exact files", nodes)
        self.assertIn("Repair final backend gateway protocol handler exact files", nodes)
        self.assertIn("Repair final backend server middleware quarantine exact files", nodes)
        self.assertNotIn("Repair final backend handler server quarantine leftovers", nodes)
        self.assertIn(
            "backend/internal/handler/admin/account_handler.go",
            nodes["Repair final backend admin handler quarantine exact files"]["relevant_files"],
        )
        self.assertIn(
            "backend/internal/handler/gateway_handler.go",
            nodes["Repair final backend gateway protocol handler exact files"]["relevant_files"],
        )

    def test_final_backend_provider_proxy_ops_quarantine_timeout_is_split(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "internal" / "service").mkdir(parents=True)
            (repo / "backend" / "internal" / "config").mkdir(parents=True)
            (repo / "backend" / "internal" / "pkg").mkdir(parents=True)
            (repo / "backend" / "internal" / "runtime").mkdir(parents=True)
            (repo / "backend" / "cmd" / "server").mkdir(parents=True)
            (repo / "frontend" / "src" / "api").mkdir(parents=True)
            (repo / "frontend" / "src" / "views").mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            spec = root / "final_verification_repair_resume_150.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "## Failing Verification Issues",
                        "",
                        "- Must repair T004 verification issue (Repair final backend provider proxy ops service quarantine exact files): Codex worker timed out after 900 seconds.",
                        "- FINAL_AUDIT_STATUS: FAIL. The audit found unresolved source-boundary and real verification failures, and allowed_files is empty.",
                        "- SIMULATION_TEST_STATUS: FAIL. Static semantic probes found 62 production/delivery files and 17 non-test frontend files retaining retired relay-era surfaces.",
                        "- REAL_TEST_STATUS: FAIL. frontend pnpm exec vue-tsc --noEmit exited 2 with unresolved TypeScript errors.",
                        "- Backend production code still contains gateway, OpenAI gateway, proxy, channel monitor, upstream account, and subscription-plan implementation surfaces.",
                        "- Frontend typecheck fails after earlier compatibility removals because multiple consumers were not migrated.",
                        "- Examples: SubscriptionProgressMini.vue, SubscriptionPlanCard.vue, UserDashboardCharts.vue, paymentWechatResume.ts.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T004.",
                        "- Focused timeout task IDs: T004.",
                        "- Focused timeout task titles: T004: Repair final backend provider proxy ops service quarantine exact files.",
                        "",
                        "## Previous Repair Context",
                        "",
                        "- Focused timeout task titles: T005: Repair final backend service repository quarantine leftovers.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                    ]
                ),
                encoding="utf-8",
            )

            graph = TaskGraphBuilder().build(
                ContextBundleBuilder().build(
                    ProjectBriefBuilder().build(
                        objective="Resume Billing Core final verification.",
                        documents=[spec],
                        repository_path=repo,
                        constraints=["Scope boundary mode: large_refactor"],
                        created_at="2026-07-05T05:12:00+08:00",
                    )
                )
            ).to_dict()

        nodes = {node["title"]: node for node in graph["nodes"]}
        self.assertIn("Repair final backend account OAuth service quarantine exact files", nodes)
        self.assertIn("Repair final backend channel monitor service quarantine exact files", nodes)
        self.assertIn("Repair final backend proxy upstream service quarantine exact files", nodes)
        self.assertIn("Repair final backend ops settings service quarantine exact files", nodes)
        self.assertIn("Repair final backend config runtime quarantine leftovers", nodes)
        self.assertNotIn("Repair final backend provider proxy ops service quarantine exact files", nodes)
        self.assertIn(
            "backend/internal/service/openai_oauth_service.go",
            nodes["Repair final backend account OAuth service quarantine exact files"]["relevant_files"],
        )
        self.assertIn(
            "backend/internal/service/channel_monitor_service.go",
            nodes["Repair final backend channel monitor service quarantine exact files"]["relevant_files"],
        )
        self.assertIn(
            "backend/internal/service/proxy_service.go",
            nodes["Repair final backend proxy upstream service quarantine exact files"]["relevant_files"],
        )
        self.assertIn(
            "backend/internal/service/ops_service.go",
            nodes["Repair final backend ops settings service quarantine exact files"]["relevant_files"],
        )

    def test_final_audit_i18n_source_boundary_failure_creates_locale_repair(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "frontend" / "src" / "i18n" / "locales").mkdir(parents=True)
            (repo / "frontend" / "src" / "views" / "admin").mkdir(parents=True)
            (repo / "frontend").mkdir(exist_ok=True)
            (repo / "frontend" / "package.json").write_text(
                json.dumps({"scripts": {"test": "vitest run"}}),
                encoding="utf-8",
            )
            spec = root / "final_verification_repair_resume_129.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_151",
                        "",
                        "## Failing Verification Issues",
                        "",
                        "- Must repair T009 verification issue (Audit final requirements and phase evidence): FINAL_AUDIT_STATUS=FAIL. The audit completed, but PASS cannot be reported because direct phase records contradict the final-verification summary, final verification still has pending downstream gates, and residual source-boundary terms remain. No repository files were edited because allowed_files is empty.",
                        "- Follow-up tasks: Reconcile final_verification_requirements.md against actual phase evidence; Grant scoped edit access for remaining frontend i18n/source-boundary cleanup; Run final simulation/static probes T010 and real repository checks T011 after audit blockers are resolved.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T009.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006, T007, T008.",
                    ]
                ),
                encoding="utf-8",
            )

            graph = TaskGraphBuilder().build(
                ContextBundleBuilder().build(
                    ProjectBriefBuilder().build(
                        objective="Resume Billing Core final verification.",
                        documents=[spec],
                        repository_path=repo,
                        constraints=["Scope boundary mode: large_refactor"],
                        created_at="2026-07-05T06:55:00+08:00",
                    )
                )
            ).to_dict()

        nodes = {node["title"]: node for node in graph["nodes"]}
        self.assertIn("Repair final frontend locale settings boundary contracts", nodes)
        audit_node = nodes["Audit final requirements and phase evidence"]
        self.assertIn("Do not fail this audit solely because downstream final-verification gates are still pending", audit_node["description"])

    def test_final_audit_admin_route_and_migration_failure_uses_exact_tasks(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for path in (
                "frontend/src/router",
                "frontend/src/components/layout",
                "frontend/src/views/admin/__tests__",
                "frontend/src/api/admin",
                "frontend/src/views/admin/ops",
                "backend/migrations",
                "backend/internal/server/routes",
                "backend/cmd/server",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "frontend" / "package.json").write_text(
                json.dumps({"scripts": {"test": "vitest run"}}),
                encoding="utf-8",
            )
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            spec = root / "final_verification_repair_resume_130.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_152",
                        "",
                        "## Failing Verification Issues",
                        "",
                        "- Must repair T010 verification issue (Audit final requirements and phase evidence): FINAL_AUDIT_STATUS=FAIL. Audit completed without repository edits because allowed_files is empty.",
                        "- Tests failed: FINAL_AUDIT_STATUS=FAIL: frontend exposes /admin/audit and calls /admin/audit, /admin/analytics, and /admin/observability API bases, but backend admin route registration only wires users, wallet, redeem-codes, settings, usage, and api-keys.; FINAL_AUDIT_STATUS=FAIL: active embedded migrations still add model-routing fields in backend/migrations/040_add_group_model_routing.sql and backend/migrations/041_add_model_routing_enabled.sql.",
                        "- Follow-up tasks: Grant scoped edit access for backend admin route wiring and matching frontend audit API/view surfaces, then rerun route/API congruence checks.; Grant scoped edit access for active migration files or the fresh migration source contract to remove model-routing/upstream/gateway remnants from embedded fresh migrations.",
                        "- Target files: frontend/src/router/index.ts, frontend/src/components/layout/AppSidebar.vue, frontend/src/views/admin/__tests__/legacyAdminRoutes.spec.ts, frontend/src/api/admin/ops.ts, backend/migrations/040_add_group_model_routing.sql, backend/migrations/041_add_model_routing_enabled.sql, backend/internal/server/routes/admin.go.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T010.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006, T007, T008, T009.",
                    ]
                ),
                encoding="utf-8",
            )

            graph = TaskGraphBuilder().build(
                ContextBundleBuilder().build(
                    ProjectBriefBuilder().build(
                        objective="Resume Billing Core final verification.",
                        documents=[spec],
                        repository_path=repo,
                        constraints=["Scope boundary mode: large_refactor"],
                        created_at="2026-07-05T07:16:00+08:00",
                    )
                )
            ).to_dict()

        titles = [node["title"] for node in graph["nodes"]]
        self.assertIn("Repair final frontend admin ops audit surface contracts", titles)
        self.assertIn("Repair final backend active migration model routing contracts", titles)
        self.assertNotIn("Repair final frontend route/sidebar contract leftovers", titles)
        self.assertNotIn("Repair final frontend route and app shell contracts", titles)
        admin_surface = next(
            node for node in graph["nodes"] if node["title"] == "Repair final frontend admin ops audit surface contracts"
        )
        self.assertEqual(admin_surface["assigned_agent"], "integration")
        self.assertIn("backend/internal/server/routes/admin.go", admin_surface["relevant_files"])
        self.assertIn("backend/internal/handler/admin/**", admin_surface["relevant_files"])
        self.assertIn("frontend/src/api/admin/ops.ts", admin_surface["relevant_files"])
        self.assertTrue(
            any("route/API congruence" in criterion for criterion in admin_surface["completion_criteria"])
        )

    def test_final_audit_dashboard_access_policy_and_user_quota_failure_uses_exact_tasks(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for path in (
                "backend/internal/server/routes",
                "backend/internal/handler/admin",
                "backend/internal/service",
                "backend/internal/repository",
                "backend/cmd/server",
                "frontend/src/api/admin",
                "frontend/src/api/__tests__",
                "frontend/src/views/admin/__tests__",
                "frontend/src/components/admin/user",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "frontend" / "package.json").write_text(
                json.dumps({"scripts": {"test": "vitest run"}}),
                encoding="utf-8",
            )
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            spec = root / "final_verification_repair_resume_132.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_154",
                        "",
                        "## Failing Verification Issues",
                        "",
                        "- Must repair T003 verification issue (Audit final requirements and phase evidence): FINAL_AUDIT_STATUS=FAIL. The audit found active frontend/backend contract defects in admin dashboard, access-policy, and user group/quota surfaces.",
                        "- Tests failed: FINAL_AUDIT_STATUS=FAIL: active frontend AdminDashboard calls /admin/dashboard/* endpoints, but backend admin route registration does not register /admin/dashboard.; FINAL_AUDIT_STATUS=FAIL: active frontend Users/Settings/user components call /admin/access-policies through adminAPI.groups, but backend admin route registration does not register /admin/access-policies.; FINAL_AUDIT_STATUS=FAIL: the source plan forbids replace-group and platform-quota relay-era admin user APIs; frontend/src/api/admin/users.ts still exports /admin/users/:id/replace-group and /admin/users/:id/platform-quotas surfaces, with replace-group reachable from UsersView via GroupReplaceModal.",
                        "- Known issues: No repository files were edited because allowed_files is empty.",
                        "- Follow-up tasks: Choose one contract for AdminDashboard: register compatible backend /admin/dashboard endpoints or retarget DashboardView/dashboard API to registered /admin/analytics/dashboard endpoints.; Choose one contract for access policies: register backend /admin/access-policies or remove/retarget frontend adminAPI.groups usage from active pages/components.; Remove or replace active replace-group and platform-quota frontend user APIs/UI, or prove they are renamed CRM access-policy behavior and register/test the backend contract.; Add focused tests that compare active frontend admin API bases against backend registered route groups.",
                        "- Target files: frontend/src/api/admin/users.ts.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T003.",
                        "- Completed tasks to preserve: T001, T002.",
                    ]
                ),
                encoding="utf-8",
            )

            graph = TaskGraphBuilder().build(
                ContextBundleBuilder().build(
                    ProjectBriefBuilder().build(
                        objective="Resume Billing Core final verification.",
                        documents=[spec],
                        repository_path=repo,
                        constraints=["Scope boundary mode: large_refactor"],
                        created_at="2026-07-05T07:58:00+08:00",
                    )
                )
            ).to_dict()

        titles = [node["title"] for node in graph["nodes"]]
        self.assertIn("Repair final admin dashboard access policy route contracts", titles)
        self.assertIn("Repair final admin user group quota surface contracts", titles)
        self.assertNotIn("Repair final frontend routes views and tests", titles)
        self.assertNotIn("Repair final backend service handler server contracts", titles)
        dashboard = next(
            node for node in graph["nodes"] if node["title"] == "Repair final admin dashboard access policy route contracts"
        )
        user_quota = next(
            node for node in graph["nodes"] if node["title"] == "Repair final admin user group quota surface contracts"
        )
        self.assertEqual(dashboard["assigned_agent"], "integration")
        self.assertIn("backend/internal/server/routes/admin.go", dashboard["relevant_files"])
        self.assertIn("frontend/src/api/admin/dashboard.ts", dashboard["relevant_files"])
        self.assertIn("frontend/src/api/admin/groups.ts", dashboard["relevant_files"])
        self.assertEqual(user_quota["assigned_agent"], "integration")
        self.assertIn("frontend/src/api/admin/users.ts", user_quota["relevant_files"])
        self.assertIn("frontend/src/components/admin/user/GroupReplaceModal.vue", user_quota["relevant_files"])

    def test_final_audit_platform_rpm_capacity_failure_uses_exact_task(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for path in (
                "backend/internal/server/routes",
                "backend/internal/handler/admin",
                "backend/internal/handler",
                "backend/internal/service",
                "backend/internal/config",
                "frontend/src/api/admin",
                "frontend/src/api/__tests__",
                "frontend/src/views/admin/__tests__",
                "frontend/src/i18n/locales",
            ):
                (repo / path).mkdir(parents=True, exist_ok=True)
            (repo / "frontend" / "package.json").write_text(
                json.dumps({"scripts": {"test": "vitest run"}}),
                encoding="utf-8",
            )
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            spec = root / "final_verification_repair_resume_133.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_155",
                        "",
                        "## Failing Verification Issues",
                        "",
                        "- Must repair T004 verification issue (Audit final requirements and phase evidence): FINAL_AUDIT_STATUS=FAIL. The current repo has direct evidence that the prior admin dashboard/access-policy/audit route defects were repaired, but the final requirements still fail on active platform-quota/RPM quota surfaces and a frontend/backend contract mismatch. REQUIRED_ACTIONS: remove or CRM-reframe the platform-quota and RPM quota interfaces. BLOCKERS: allowed_files is empty.",
                        "- Tests failed: FINAL_AUDIT_STATUS=FAIL: frontend/src/api/user.ts:192-193 still exports getMyPlatformQuotas calling /user/platform-quotas, while backend route registration has no matching platform-quotas route.; FINAL_AUDIT_STATUS=FAIL: active admin settings and API surfaces still expose platform-quota and RPM quota controls: frontend/src/views/admin/SettingsView.vue:3207,3362,3388; frontend/src/api/admin/settings.ts:489,528; frontend/src/api/admin/groups.ts:293,303; backend/internal/server/routes/admin.go:99,100.",
                        "- Follow-up tasks: Grant scoped edit access for the affected frontend API/types/settings view/i18n/tests and backend admin/user/settings route-handler-service surfaces.; Remove /user/platform-quotas or replace it with a CRM-approved capacity endpoint and keep frontend/backend contracts congruent.; Remove RPM quota endpoints/settings or rework them into source-approved generic capacity semantics with tests.",
                        "- Target files: frontend/src/views/admin/SettingsView.vue, frontend/src/api/user.ts, frontend/src/api/admin/settings.ts, frontend/src/api/admin/groups.ts, backend/internal/server/routes/admin.go.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T004.",
                        "- Completed tasks to preserve: T001.",
                    ]
                ),
                encoding="utf-8",
            )

            graph = TaskGraphBuilder().build(
                ContextBundleBuilder().build(
                    ProjectBriefBuilder().build(
                        objective="Resume Billing Core final verification.",
                        documents=[spec],
                        repository_path=repo,
                        constraints=["Scope boundary mode: large_refactor"],
                        created_at="2026-07-05T08:33:00+08:00",
                    )
                )
            ).to_dict()

        titles = [node["title"] for node in graph["nodes"]]
        self.assertIn("Repair final platform RPM capacity surface contracts", titles)
        self.assertNotIn("Repair final admin dashboard access policy route contracts", titles)
        self.assertNotIn("Repair final admin user group quota surface contracts", titles)
        capacity = next(
            node for node in graph["nodes"] if node["title"] == "Repair final platform RPM capacity surface contracts"
        )
        self.assertEqual(capacity["assigned_agent"], "integration")
        self.assertIn("frontend/src/api/user.ts", capacity["relevant_files"])
        self.assertIn("frontend/src/api/admin/settings.ts", capacity["relevant_files"])
        self.assertIn("frontend/src/views/admin/SettingsView.vue", capacity["relevant_files"])
        self.assertIn("backend/internal/server/routes/admin.go", capacity["relevant_files"])

    def test_final_audit_rpm_override_leftovers_do_not_reopen_completed_capacity_tasks(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for path in (
                "backend/internal/server/routes",
                "frontend/src/api/admin",
                "frontend/src/api/__tests__",
            ):
                (repo / path).mkdir(parents=True, exist_ok=True)
            (repo / "frontend" / "package.json").write_text(
                json.dumps({"scripts": {"test": "vitest run"}}),
                encoding="utf-8",
            )
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            spec = root / "final_verification_repair_resume_138.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_160",
                        "",
                        "## Failing Verification Issues",
                        "",
                        "- Must repair T004 verification issue (Audit final requirements and phase evidence): FINAL_AUDIT_STATUS=FAIL. The T002/T003 focused backend account-capacity repairs are evidenced and their focused tests pass, but the final source-boundary audit found a remaining retired RPM override frontend API surface and a backend route-contract test that still requires the retired route.",
                        "- Failed commands: go test ./internal/server -run ^TestAdminDashboardAndAccessPolicyRoutesMatchFrontendAPIBases$ -count=1: FAIL: required admin dashboard/access-policy route missing: PUT /api/v1/admin/access-policies/:id/rpm-overrides.",
                        "- Tests failed: TestAdminDashboardAndAccessPolicyRoutesMatchFrontendAPIBases fails because the test still requires retired PUT /api/v1/admin/access-policies/:id/rpm-overrides.",
                        "- Follow-up tasks: Grant edit access to frontend/src/api/admin/groups.ts and remove or rename RPM override methods to final account-capacity semantics.; Grant edit access to backend/internal/server/admin_dashboard_access_policy_routes_test.go and update the route contract to reject the retired /rpm-overrides route.",
                        "- Target files: frontend/src/api/admin/groups.ts, backend/internal/server/admin_dashboard_access_policy_routes_test.go, backend/internal/server/routes/admin.go.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T004.",
                        "- Completed tasks to preserve: T001.",
                    ]
                ),
                encoding="utf-8",
            )

            graph = TaskGraphBuilder().build(
                ContextBundleBuilder().build(
                    ProjectBriefBuilder().build(
                        objective="Resume Billing Core final verification.",
                        documents=[spec],
                        repository_path=repo,
                        constraints=["Scope boundary mode: large_refactor"],
                        created_at="2026-07-05T10:20:00+08:00",
                    )
                )
            ).to_dict()

        titles = [node["title"] for node in graph["nodes"]]
        self.assertIn("Repair final RPM override route contract leftovers", titles)
        self.assertNotIn("Repair final platform RPM capacity surface contracts", titles)
        self.assertNotIn("Repair final backend admin RPM route settings contracts", titles)
        self.assertNotIn("Repair final backend admin user capacity handler contracts", titles)
        repair = next(
            node for node in graph["nodes"] if node["title"] == "Repair final RPM override route contract leftovers"
        )
        self.assertEqual(repair["id"], "T002")
        self.assertEqual(repair["assigned_agent"], "integration")
        self.assertIn("frontend/src/api/admin/groups.ts", repair["relevant_files"])
        self.assertIn("backend/internal/server/admin_dashboard_access_policy_routes_test.go", repair["relevant_files"])
        self.assertEqual(graph["nodes"][2]["title"], "Audit final requirements and phase evidence")

    def test_final_simulation_suite_failure_preserves_prior_repair_and_adds_narrow_tasks(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for path in (
                "backend/internal/handler/admin",
                "backend/internal/handler/dto",
                "frontend/src/components/admin/usage/__tests__",
                "frontend/src/types",
                "frontend/src/api/admin",
                "frontend/src/api/__tests__",
            ):
                (repo / path).mkdir(parents=True, exist_ok=True)
            (repo / "frontend" / "package.json").write_text(
                json.dumps({"scripts": {"test": "vitest run"}}),
                encoding="utf-8",
            )
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            spec = root / "final_verification_repair_resume_139.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_161",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "- Must report FINAL_AUDIT_STATUS, SIMULATION_TEST_STATUS, REAL_TEST_STATUS, REQUIRED_ACTIONS, and BLOCKERS after repair.",
                        "",
                        "## Failing Verification Issues",
                        "",
                        "- Must repair T004 verification issue (Run final simulation probes): SIMULATION_TEST_STATUS=FAIL. Final verification probes were run without repository edits. Full frontend and backend suites fail; focused contract probes pass. Repairs could not be applied because allowed_files is empty.",
                        "- Failed commands: pnpm --dir frontend test: UsageTable.spec.ts failed; cd backend; go test ./...: 14 backend tests failed across admin and dto packages.",
                        "- Tests failed: frontend/src/components/admin/usage/__tests__/UsageTable.spec.ts: 4 tooltip tests fail because Image count is missing.; backend/internal/handler/admin::TestExportDataIncludesSecrets; backend/internal/handler/dto::TestUsageLogFromService_UsesRequestedModelAndKeepsUpstreamAdminOnly.",
                        "- Follow-up tasks: Open a repair task with write access to the failing frontend UsageTable component/test files and backend admin/dto implementation or tests.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T004.",
                        "- Completed tasks to preserve: T002.",
                        "- Task T002 - Repair final RPM override route contract leftovers was completed and should be preserved.",
                        "",
                        "## Previous Repair Context",
                        "",
                        "- Preserve previous repair context from final_verification_repair_resume_138.md: rpm-overrides route contract repair.",
                        "- Required admin dashboard/access-policy route missing: PUT /api/v1/admin/access-policies/:id/rpm-overrides.",
                        "- Target files: frontend/src/api/admin/groups.ts, backend/internal/server/admin_dashboard_access_policy_routes_test.go.",
                    ]
                ),
                encoding="utf-8",
            )

            graph = TaskGraphBuilder().build(
                ContextBundleBuilder().build(
                    ProjectBriefBuilder().build(
                        objective="Resume Billing Core final verification.",
                        documents=[spec],
                        repository_path=repo,
                        constraints=["Scope boundary mode: large_refactor"],
                        created_at="2026-07-05T10:55:00+08:00",
                    )
                )
            ).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes["T002"]["title"], "Repair final RPM override route contract leftovers")
        self.assertEqual(nodes["T002"]["status"], "completed")
        self.assertEqual(nodes["T003"]["title"], "Repair final frontend UsageTable simulation contracts")
        self.assertEqual(nodes["T004"]["title"], "Repair final backend admin simulation contracts")
        self.assertEqual(nodes["T005"]["title"], "Repair final backend DTO usage simulation contracts")
        self.assertEqual(nodes["T006"]["title"], "Audit final requirements and phase evidence")
        self.assertIn("frontend/src/components/admin/usage/UsageTable.vue", nodes["T003"]["relevant_files"])
        self.assertIn("backend/internal/handler/dto/mappers_usage_test.go", nodes["T005"]["relevant_files"])

    def test_final_simulation_settings_advanced_scheduler_failure_uses_exact_task(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "internal" / "handler" / "admin").mkdir(parents=True)
            (repo / "backend" / "internal" / "handler" / "dto").mkdir(parents=True)
            (repo / "backend" / "internal" / "service").mkdir(parents=True)
            (repo / "frontend").mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_141.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_163",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "- Must report FINAL_AUDIT_STATUS, SIMULATION_TEST_STATUS, REAL_TEST_STATUS, REQUIRED_ACTIONS, and BLOCKERS after repair.",
                        "",
                        "## Failing Verification Issues",
                        "",
                        "- Must repair T007 verification issue (Run final simulation probes): SIMULATION_TEST_STATUS=FAIL. Backend go test ./... failed in internal/handler/admin.",
                        "- Tests failed: TestSettingHandler_UpdateSettings_PersistsPaymentVisibleMethodsAndAdvancedScheduler expected repo.values[\"openai_advanced_scheduler_enabled\"] == \"true\", actual \"false\".",
                        "- Known issue: setting_handler.go uses json tag `advanced_credential_scheduler_enabled` for OpenAIAdvancedSchedulerEnabled, but service setting key is `openai_advanced_scheduler_enabled`.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T007.",
                        "- Completed tasks to preserve: T002, T003, T005, T006.",
                        "- Task T002 - Repair final RPM override route contract leftovers was completed and should be preserved.",
                        "- Task T003 - Repair final frontend UsageTable simulation contracts was completed and should be preserved.",
                        "- Task T005 - Repair final backend DTO usage simulation contracts was completed and should be preserved.",
                    ]
                ),
                encoding="utf-8",
            )

            graph = TaskGraphBuilder().build(
                ContextBundleBuilder().build(
                    ProjectBriefBuilder().build(
                        objective="Resume Billing Core final verification.",
                        documents=[spec],
                        repository_path=repo,
                        constraints=["Scope boundary mode: large_refactor"],
                        created_at="2026-07-05T11:35:00+08:00",
                    )
                )
            ).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        titles = [node["title"] for node in graph["nodes"]]
        self.assertEqual(nodes["T002"]["status"], "completed")
        self.assertEqual(nodes["T003"]["title"], "Repair final backend settings advanced scheduler contract")
        self.assertEqual(nodes["T003"]["status"], "pending")
        self.assertEqual(nodes["T004"]["title"], "Audit final requirements and phase evidence")
        self.assertEqual(nodes["T005"]["title"], "Run final simulation probes")
        self.assertNotIn("Repair final backend admin simulation contracts", titles)
        self.assertIn("backend/internal/handler/admin/setting_handler.go", nodes["T003"]["relevant_files"])

    def test_final_audit_settings_api_contract_failure_adds_exact_task(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "internal" / "server").mkdir(parents=True)
            (repo / "backend" / "internal" / "handler" / "admin").mkdir(parents=True)
            (repo / "backend" / "internal" / "handler" / "dto").mkdir(parents=True)
            (repo / "frontend").mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_142.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_164",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "- Must report FINAL_AUDIT_STATUS, SIMULATION_TEST_STATUS, REAL_TEST_STATUS, REQUIRED_ACTIONS, and BLOCKERS after repair.",
                        "",
                        "## Failing Verification Issues",
                        "",
                        "- Must repair T004 verification issue (Audit final requirements and phase evidence): FINAL_AUDIT_STATUS=FAIL.",
                        "- Failed commands: go test -tags unit ./internal/server -run ^TestAPIContracts$ -count=1: GET /api/v1/admin/settings expected advanced_credential_scheduler_enabled=false but got nil; response should not contain openai_advanced_scheduler_enabled, but it does.",
                        "- Follow-up tasks: Allow edits to backend/internal/server/api_contract_test.go and align the admin settings API contract with the current OpenAIAdvancedSchedulerEnabled JSON key.",
                        "- Target files: backend/internal/server/api_contract_test.go, full_roadmap_report.json.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T004.",
                        "- Completed tasks to preserve: T001, T002, T003.",
                        "- Task T003 - Repair final backend settings advanced scheduler contract was completed and should be preserved.",
                    ]
                ),
                encoding="utf-8",
            )

            graph = TaskGraphBuilder().build(
                ContextBundleBuilder().build(
                    ProjectBriefBuilder().build(
                        objective="Resume Billing Core final verification.",
                        documents=[spec],
                        repository_path=repo,
                        constraints=["Scope boundary mode: large_refactor"],
                        created_at="2026-07-05T11:53:00+08:00",
                    )
                )
            ).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        titles = [node["title"] for node in graph["nodes"]]
        api_contract_index = titles.index("Repair final backend settings API contract test")
        audit_index = titles.index("Audit final requirements and phase evidence")
        self.assertLess(api_contract_index, audit_index)
        api_contract_node = next(node for node in graph["nodes"] if node["title"] == "Repair final backend settings API contract test")
        self.assertEqual(api_contract_node["status"], "pending")
        self.assertNotIn("Repair final backend admin simulation contracts", titles)
        self.assertIn("backend/internal/server/api_contract_test.go", api_contract_node["relevant_files"])

    def test_final_simulation_frontend_user_quota_typecheck_failure_adds_exact_task(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "frontend" / "src" / "components" / "user").mkdir(parents=True)
            (repo / "frontend" / "src" / "types").mkdir(parents=True)
            (repo / "frontend" / "src" / "api" / "admin").mkdir(parents=True)
            (repo / "backend").mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"typecheck": "vue-tsc --noEmit"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_143.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_165",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "- Must report FINAL_AUDIT_STATUS, SIMULATION_TEST_STATUS, REAL_TEST_STATUS, REQUIRED_ACTIONS, and BLOCKERS after repair.",
                        "",
                        "## Failing Verification Issues",
                        "",
                        "- Must repair T006 verification issue (Run final simulation probes): SIMULATION_TEST_STATUS=FAIL.",
                        "- Failed commands: pnpm --dir frontend run typecheck: src/components/user/UserPlatformQuotaCell.vue(32,15): Module '@/api/admin/users' has no exported member PlatformQuotaItem. Also missing PlatformQuotaPlatform. vue-tsc --noEmit failed.",
                        "- Tests failed: TS2614 missing exported members PlatformQuotaItem and PlatformQuotaPlatform from '@/api/admin/users'.",
                        "- Known issues: frontend/src/components/user/UserPlatformQuotaCell.vue has a type-only import from '@/api/admin/users' for PlatformQuotaItem and PlatformQuotaPlatform, but those names are exported from '@/types' instead.",
                        "- Target files: frontend/src/components/user/UserPlatformQuotaCell.vue, frontend/src/types/index.ts, frontend/src/api/admin/users.ts.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T006.",
                        "- Completed tasks to preserve: T001, T002, T003, T004.",
                        "- Task T004 - Repair final backend settings API contract test was completed and should be preserved.",
                    ]
                ),
                encoding="utf-8",
            )

            graph = TaskGraphBuilder().build(
                ContextBundleBuilder().build(
                    ProjectBriefBuilder().build(
                        objective="Resume Billing Core final verification.",
                        documents=[spec],
                        repository_path=repo,
                        constraints=["Scope boundary mode: large_refactor"],
                        created_at="2026-07-05T12:08:00+08:00",
                    )
                )
            ).to_dict()

        titles = [node["title"] for node in graph["nodes"]]
        typecheck_index = titles.index("Repair final frontend user quota typecheck import")
        simulation_index = titles.index("Run final simulation probes")
        self.assertLess(typecheck_index, simulation_index)
        typecheck_node = next(node for node in graph["nodes"] if node["title"] == "Repair final frontend user quota typecheck import")
        self.assertEqual(typecheck_node["status"], "pending")
        self.assertIn("frontend/src/components/user/UserPlatformQuotaCell.vue", typecheck_node["relevant_files"])

    def test_final_audit_platform_quota_source_boundary_does_not_reopen_typecheck_import(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "frontend" / "src" / "views" / "admin").mkdir(parents=True)
            (repo / "frontend" / "src" / "i18n" / "locales").mkdir(parents=True)
            (repo / "frontend" / "src" / "api" / "admin").mkdir(parents=True)
            (repo / "frontend" / "src" / "components" / "user").mkdir(parents=True)
            (repo / "backend").mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_144.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_166",
                        "",
                        "## Failing Verification Issues",
                        "",
                        "- Must repair T006 verification issue (Audit final requirements and phase evidence): FINAL_AUDIT_STATUS=FAIL. The failure is source-boundary drift in active frontend settings/user quota surfaces.",
                        "- Tests failed: Source-boundary audit: active frontend settings and user quota surfaces still expose Platform Quotas/default_platform_quotas/platform_quotas language and behavior despite plan forbidding first-version platform quota/model entitlement behavior.",
                        "- Follow-up tasks: Grant edit scope for frontend/src/views/admin/SettingsView.vue, frontend/src/i18n/locales/en.ts, frontend/src/i18n/locales/zh.ts, frontend/src/api/admin/settings.ts, related frontend tests, and UserPlatformQuotaCell/type aliases if keeping the account-capacity feature.",
                        "- Target files: frontend/src/views/admin/SettingsView.vue, frontend/src/i18n/locales/en.ts, frontend/src/i18n/locales/zh.ts, frontend/src/api/admin/settings.ts, frontend/src/types/index.ts, frontend/src/components/user/UserPlatformQuotaCell.vue.",
                        "",
                        "## Previous Repair Context",
                        "",
                        "- Prior typecheck failure mentioned UserPlatformQuotaCell.vue, PlatformQuotaItem, PlatformQuotaPlatform, and TS2614, but it was already repaired.",
                    ]
                ),
                encoding="utf-8",
            )

            graph = TaskGraphBuilder().build(
                ContextBundleBuilder().build(
                    ProjectBriefBuilder().build(
                        objective="Resume Billing Core final verification.",
                        documents=[spec],
                        repository_path=repo,
                        constraints=["Scope boundary mode: large_refactor"],
                        created_at="2026-07-05T12:21:00+08:00",
                    )
                )
            ).to_dict()

        titles = [node["title"] for node in graph["nodes"]]
        self.assertIn("Repair final platform RPM capacity surface contracts", titles)
        self.assertNotIn("Repair final frontend user quota typecheck import", titles)

    def test_final_verification_admin_settings_email_timeout_is_split_again(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views/admin/__tests__",
                "frontend/src/views/admin/affiliates",
                "frontend/src/views/admin/ops/components",
                "frontend/src/views/admin/orders",
                "frontend/src/views/admin/settings",
                "frontend/src/views/auth",
                "frontend/src/views/public",
                "frontend/src/views/setup",
                "frontend/src/views/user",
                "frontend/src/components/account",
                "frontend/src/components/admin/announcements",
                "frontend/src/components/admin/channel",
                "frontend/src/components/admin/group",
                "frontend/src/components/admin/monitor",
                "frontend/src/components/admin/payment",
                "frontend/src/components/admin/proxy",
                "frontend/src/components/admin/usage",
                "frontend/src/components/admin/user",
                "frontend/src/components/charts",
                "frontend/src/styles",
                "frontend/src/composables",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "frontend" / "src" / "views" / "NotFoundView.vue").write_text("<template />\n", encoding="utf-8")
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_022.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_026",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- FINAL_AUDIT_STATUS=FAIL: final source-boundary repair needs continuation.",
                        "- Must grant the repair worker edit access to backend migrations, Ent schema/generated files, backend domain/repository/service/handler/server contracts, and backend command wiring when those surfaces contain residual relay-era product concepts.",
                        "- Must split backend schema/domain repair by Ent schema, domain/repository, and service/handler/server wiring instead of replaying one broad worker.",
                        "- Must grant the repair worker edit access to frontend API, i18n, router, view, component, composable, constants, type, store, and test files when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T030.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024, T025, T026, T027, T028, T029.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T030 - Repair final frontend admin settings email compliance files",
                        "- Must continue focused task T030: Repair final frontend admin settings email compliance files.",
                        "- Previous relevant files: frontend/src/views/admin/SettingsView.vue, frontend/src/views/admin/settings/EmailTemplateEditor.vue, frontend/src/components/admin/AdminComplianceDialog.vue, frontend/src/styles/onboarding.css, frontend/src/types/index.ts.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve T029 and split settings/email/compliance by exact file plus support files before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-29T20:30:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        for task_id in (
            "T001",
            "T002",
            "T003",
            "T004",
            "T005",
            "T006",
            "T007",
            "T008",
            "T009",
            "T010",
            "T011",
            "T012",
            "T013",
            "T014",
            "T015",
            "T016",
            "T017",
            "T018",
            "T019",
            "T020",
            "T021",
            "T022",
            "T023",
            "T024",
            "T025",
            "T026",
            "T027",
            "T028",
            "T029",
        ):
            self.assertEqual(nodes[task_id]["status"], "completed")
        self.assertEqual(nodes["T030"]["title"], "Repair final frontend admin settings view file")
        self.assertIn("frontend/src/views/admin/SettingsView.vue", nodes["T030"]["relevant_files"])
        self.assertEqual(nodes["T031"]["title"], "Repair final frontend admin email template editor file")
        self.assertIn("frontend/src/views/admin/settings/EmailTemplateEditor.vue", nodes["T031"]["relevant_files"])
        self.assertEqual(nodes["T032"]["title"], "Repair final frontend admin compliance dialog file")
        self.assertIn("frontend/src/components/admin/AdminComplianceDialog.vue", nodes["T032"]["relevant_files"])
        self.assertEqual(nodes["T033"]["title"], "Repair final frontend admin settings support files")
        self.assertIn("frontend/src/styles/onboarding.css", nodes["T033"]["relevant_files"])
        self.assertEqual(nodes["T034"]["title"], "Repair final frontend admin announcement backup promo files")
        self.assertEqual(nodes["T035"]["title"], "Repair final frontend admin dashboard settings support files")
        self.assertEqual(nodes["T036"]["title"], "Repair final frontend admin user usage redeem view contracts")

    def test_final_verification_admin_email_template_timeout_uses_file_leaf(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views/admin/__tests__",
                "frontend/src/views/admin/affiliates",
                "frontend/src/views/admin/ops/components",
                "frontend/src/views/admin/orders",
                "frontend/src/views/admin/settings",
                "frontend/src/views/auth",
                "frontend/src/views/public",
                "frontend/src/views/setup",
                "frontend/src/views/user",
                "frontend/src/components/account",
                "frontend/src/components/admin/announcements",
                "frontend/src/components/admin/channel",
                "frontend/src/components/admin/group",
                "frontend/src/components/admin/monitor",
                "frontend/src/components/admin/payment",
                "frontend/src/components/admin/proxy",
                "frontend/src/components/admin/usage",
                "frontend/src/components/admin/user",
                "frontend/src/components/charts",
                "frontend/src/styles",
                "frontend/src/composables",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "frontend" / "src" / "views" / "NotFoundView.vue").write_text("<template />\n", encoding="utf-8")
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_023.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_027",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- FINAL_AUDIT_STATUS=FAIL: final source-boundary repair needs continuation.",
                        "- Must grant the repair worker edit access to backend migrations, Ent schema/generated files, backend domain/repository/service/handler/server contracts, and backend command wiring when those surfaces contain residual relay-era product concepts.",
                        "- Must split backend schema/domain repair by Ent schema, domain/repository, and service/handler/server wiring instead of replaying one broad worker.",
                        "- Must grant the repair worker edit access to frontend API, i18n, router, view, component, composable, constants, type, store, and test files when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T031.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024, T025, T026, T027, T028, T029, T030.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T031 - Repair final frontend admin email template editor file",
                        "- Must continue focused task T031: Repair final frontend admin email template editor file.",
                        "- Previous relevant files: frontend/src/views/admin/settings/EmailTemplateEditor.vue, frontend/src/styles/onboarding.css, frontend/src/types/index.ts.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve T030 and narrow the email template editor task to its Vue file only; shared styles and types stay in the later support-file task.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-29T21:10:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        for task_id in (
            "T001",
            "T002",
            "T003",
            "T004",
            "T005",
            "T006",
            "T007",
            "T008",
            "T009",
            "T010",
            "T011",
            "T012",
            "T013",
            "T014",
            "T015",
            "T016",
            "T017",
            "T018",
            "T019",
            "T020",
            "T021",
            "T022",
            "T023",
            "T024",
            "T025",
            "T026",
            "T027",
            "T028",
            "T029",
            "T030",
        ):
            self.assertEqual(nodes[task_id]["status"], "completed")
        self.assertEqual(nodes["T031"]["title"], "Repair final frontend admin email template editor leaf file")
        self.assertEqual(nodes["T031"]["relevant_files"], ["frontend/src/views/admin/settings/EmailTemplateEditor.vue"])
        self.assertEqual(nodes["T032"]["title"], "Repair final frontend admin compliance dialog file")
        self.assertIn("frontend/src/components/admin/AdminComplianceDialog.vue", nodes["T032"]["relevant_files"])
        self.assertEqual(nodes["T033"]["title"], "Repair final frontend admin settings support files")
        self.assertIn("frontend/src/styles/onboarding.css", nodes["T033"]["relevant_files"])
        self.assertEqual(nodes["T034"]["title"], "Repair final frontend admin announcement backup promo files")
        self.assertEqual(nodes["T035"]["title"], "Repair final frontend admin dashboard settings support files")

    def test_final_verification_admin_announcement_backup_promo_timeout_is_split_again(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views/admin/__tests__",
                "frontend/src/views/admin/affiliates",
                "frontend/src/views/admin/ops/components",
                "frontend/src/views/admin/orders",
                "frontend/src/views/admin/settings",
                "frontend/src/views/auth",
                "frontend/src/views/public",
                "frontend/src/views/setup",
                "frontend/src/views/user",
                "frontend/src/components/account",
                "frontend/src/components/admin/announcements",
                "frontend/src/components/admin/channel",
                "frontend/src/components/admin/group",
                "frontend/src/components/admin/monitor",
                "frontend/src/components/admin/payment",
                "frontend/src/components/admin/proxy",
                "frontend/src/components/admin/usage",
                "frontend/src/components/admin/user",
                "frontend/src/components/charts",
                "frontend/src/styles",
                "frontend/src/composables",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "frontend" / "src" / "views" / "NotFoundView.vue").write_text("<template />\n", encoding="utf-8")
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_024.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_028",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- FINAL_AUDIT_STATUS=FAIL: final source-boundary repair needs continuation.",
                        "- Must grant the repair worker edit access to backend migrations, Ent schema/generated files, backend domain/repository/service/handler/server contracts, and backend command wiring when those surfaces contain residual relay-era product concepts.",
                        "- Must split backend schema/domain repair by Ent schema, domain/repository, and service/handler/server wiring instead of replaying one broad worker.",
                        "- Must grant the repair worker edit access to frontend API, i18n, router, view, component, composable, constants, type, store, and test files when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T034.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024, T025, T026, T027, T028, T029, T030, T031, T032, T033.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T034 - Repair final frontend admin announcement backup promo files",
                        "- Must continue focused task T034: Repair final frontend admin announcement backup promo files.",
                        "- Previous relevant files: frontend/src/views/admin/AnnouncementsView.vue, frontend/src/views/admin/BackupView.vue, frontend/src/views/admin/PromoCodesView.vue, frontend/src/components/admin/announcements/**, frontend/src/styles/onboarding.css, frontend/src/types/index.ts.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve T033 and split announcement, backup, promo-code, and announcement component/support files before replaying the same scope.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-29T21:45:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        titles = [node["title"] for node in graph["nodes"]]
        self.assertIn("Repair final frontend API module contracts", titles)
        self.assertIn("Repair final frontend i18n locale contracts", titles)
        self.assertIn("Repair final frontend constants and shared types contracts", titles)
        self.assertNotIn("Repair final frontend API and i18n contracts", titles)
        self.assertIn("Repair final frontend admin email template editor leaf file", titles)
        self.assertNotIn("Repair final frontend admin announcement backup promo files", titles)
        split_titles = [
            "Repair final frontend admin announcements view file",
            "Repair final frontend admin backup view file",
            "Repair final frontend admin promo codes view file",
            "Repair final frontend admin announcement components support files",
        ]
        split_nodes = [node for node in graph["nodes"] if node["title"] in split_titles]
        self.assertEqual([node["title"] for node in split_nodes], split_titles)
        self.assertEqual(split_nodes[0]["relevant_files"], ["frontend/src/views/admin/AnnouncementsView.vue"])
        self.assertEqual(split_nodes[1]["relevant_files"], ["frontend/src/views/admin/BackupView.vue"])
        self.assertEqual(split_nodes[2]["relevant_files"], ["frontend/src/views/admin/PromoCodesView.vue"])
        self.assertIn("frontend/src/components/admin/announcements/**", split_nodes[3]["relevant_files"])
        self.assertIn("Repair final frontend admin dashboard settings support files", titles)
        self.assertIn("Repair final frontend admin user usage redeem view contracts", titles)

    def test_final_verification_drifted_promo_task_reopens_announcement_split(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "migrations").mkdir(parents=True)
            (repo / "backend" / "ent" / "schema").mkdir(parents=True)
            for path in (
                "frontend/src/api",
                "frontend/src/constants",
                "frontend/src/i18n",
                "frontend/src/types",
                "frontend/src/router",
                "frontend/src/views/admin/__tests__",
                "frontend/src/views/admin/affiliates",
                "frontend/src/views/admin/ops/components",
                "frontend/src/views/admin/orders",
                "frontend/src/views/admin/settings",
                "frontend/src/views/auth",
                "frontend/src/views/public",
                "frontend/src/views/setup",
                "frontend/src/views/user",
                "frontend/src/components/account",
                "frontend/src/components/admin/announcements",
                "frontend/src/components/admin/channel",
                "frontend/src/components/admin/group",
                "frontend/src/components/admin/monitor",
                "frontend/src/components/admin/payment",
                "frontend/src/components/admin/proxy",
                "frontend/src/components/admin/usage",
                "frontend/src/components/admin/user",
                "frontend/src/components/charts",
                "frontend/src/styles",
                "frontend/src/composables",
                "frontend/src/stores",
                "frontend/src/utils",
                "frontend/tests",
            ):
                (repo / path).mkdir(parents=True)
            (repo / "frontend" / "src" / "views" / "NotFoundView.vue").write_text("<template />\n", encoding="utf-8")
            (repo / "backend" / "go.mod").write_text("module example.com/billing\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
            spec = root / "final_verification_repair_resume_025.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Final Verification Repair Resume",
                        "",
                        "Repair attempt: run_attempt_029",
                        "",
                        "## Requirements",
                        "",
                        "- Must repair the previous final-verification source-boundary findings before reporting PASS.",
                        "- FINAL_AUDIT_STATUS=FAIL: final source-boundary repair needs continuation.",
                        "- Must grant the repair worker edit access to backend migrations, Ent schema/generated files, backend domain/repository/service/handler/server contracts, and backend command wiring when those surfaces contain residual relay-era product concepts.",
                        "- Must split backend schema/domain repair by Ent schema, domain/repository, and service/handler/server wiring instead of replaying one broad worker.",
                        "- Must grant the repair worker edit access to frontend API, i18n, router, view, component, composable, constants, type, store, and test files when those surfaces contain upstream account, proxy, channel-monitor, model-routing, or subscription-plan behavior.",
                        "- Must rerun final audit, simulation/static probes, and real repository checks after repair.",
                        "",
                        "## Focused Repair Scope",
                        "",
                        "- Primary failed task IDs: T034.",
                        "- Completed tasks to preserve: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024, T025, T026, T027, T028, T029, T030, T031, T032, T033.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "",
                        "### Task T034 - Repair final frontend admin promo codes view file",
                        "- Must continue focused task T034: Repair final frontend admin promo codes view file.",
                        "- Last task status: blocked.",
                        "- Previous relevant files: frontend/src/views/admin/PromoCodesView.vue.",
                        "- Worker summary: Codex worker was cancelled by operator stop request.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Final CRM handoff audit",
                documents=[spec],
                repository_path=repo,
                constraints=["Scope boundary mode: large_refactor"],
                created_at="2026-06-29T22:10:00+08:00",
            )

            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle).to_dict()

        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes["T006"]["title"], "Repair final frontend API module contracts")
        self.assertEqual(nodes["T007"]["title"], "Repair final frontend i18n locale contracts")
        self.assertEqual(nodes["T008"]["title"], "Repair final frontend constants and shared types contracts")
        self.assertEqual(nodes["T034"]["title"], "Repair final frontend admin announcements view file")
        self.assertEqual(nodes["T034"]["status"], "pending")
        self.assertEqual(nodes["T035"]["title"], "Repair final frontend admin backup view file")
        self.assertEqual(nodes["T036"]["title"], "Repair final frontend admin promo codes view file")
        self.assertEqual(nodes["T037"]["title"], "Repair final frontend admin announcement components support files")

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
        self.assertNotIn("Align Ent migration contracts", titles)
        self.assertIn("Inventory Ent migration contract deltas", titles)
        self.assertIn("Patch Ent migration contract deltas", titles)
        self.assertIn("Align server and domain table contracts", titles)
        self.assertIn("Regenerate Ent clients and migration artifacts", titles)

        nodes_by_id = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes_by_id["T001"]["status"], "completed")
        self.assertEqual(nodes_by_id["T002"]["status"], "completed")
        inventory_task = next(node for node in implementation_nodes if node["title"] == "Inventory Ent migration contract deltas")
        patch_task = next(node for node in implementation_nodes if node["title"] == "Patch Ent migration contract deltas")
        self.assertEqual(inventory_task["relevant_files"], ["backend/ent/migrate/schema.go", "backend/go.mod"])
        self.assertEqual(inventory_task.get("commands_to_run", []), [])
        self.assertEqual(patch_task["relevant_files"], ["backend/ent/migrate/schema.go", "backend/go.mod"])
        self.assertTrue(any("go test" in command for command in patch_task["commands_to_run"]))

        server_task = next(node for node in implementation_nodes if node["title"] == "Align server and domain table contracts")
        self.assertIn("backend/internal/server/**", server_task["relevant_files"])
        self.assertIn("backend/internal/domain/**", server_task["relevant_files"])
        self.assertNotIn("backend/ent/migrate/**", server_task["relevant_files"])
        self.assertNotIn("backend/internal/service/**", server_task["relevant_files"])

    def test_schema_migration_contract_timeout_repair_adds_checkpoint_tasks(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for directory in (
                "backend/ent/schema",
                "backend/ent/migrate",
                "backend/internal/domain",
                "backend/internal/server",
                "backend/cmd/server",
            ):
                (repo / directory).mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/backend\n", encoding="utf-8")
            (repo / "backend" / "ent" / "schema" / "billing.go").write_text("package schema\n", encoding="utf-8")
            (repo / "backend" / "ent" / "migrate" / "schema.go").write_text("package migrate\n", encoding="utf-8")
            (repo / "backend" / "internal" / "domain" / "tables.go").write_text("package domain\n", encoding="utf-8")
            (repo / "backend" / "internal" / "server" / "routes.go").write_text("package server\n", encoding="utf-8")
            (repo / "backend" / "cmd" / "server" / "main.go").write_text("package main\n", encoding="utf-8")
            phase = root / "phase.md"
            phase.write_text(
                "\n".join(
                    [
                        "# Phase 8: Schema pruning and build",
                        "- Must prune Ent schema for CRM billing only.",
                        "- Must regenerate Ent clients.",
                        "- Must update migrations.",
                        "- Must prove a fresh DB migration succeeds.",
                        "- Fresh DB migration must not create token relay tables.",
                        "- `go test ./backend/internal/...` must pass.",
                        "- Frontend build/typecheck must pass.",
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
                        "## Focused Repair Scope",
                        "- Primary failed task IDs: T002.",
                        "- Completed tasks to preserve: T001.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                    ]
                ),
                encoding="utf-8",
            )
            t004_repair = root / "phase_repair_004.md"
            t004_repair.write_text(
                "\n".join(
                    [
                        "# Auto Repair For Phase 8",
                        "## Repairable Blockers",
                        "- B-T003-1: T003 exceeded the Codex worker timeout. Stop instead of launching a same-scope debug task. (tasks: T003)",
                        "## Focused Repair Scope",
                        "- Primary failed task IDs: T003.",
                        "- Completed tasks to preserve: T001, T002.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "### Task T003 - Align Ent migration contracts",
                        "- Previous relevant files: backend/ent/migrate/**, backend/go.mod.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Repair Billing Core migration-only timeout.",
                documents=[phase, t002_repair, t004_repair],
                repository_path=repo,
                created_at="2026-06-28T07:15:00+08:00",
            )

            graph = TaskGraphBuilder().build(ContextBundleBuilder().build(brief)).to_dict()

        implementation_nodes = [
            node
            for node in graph["nodes"]
            if node["type"] not in {"architecture", "test", "review", "release"}
        ]
        titles = [node["title"] for node in implementation_nodes]
        self.assertNotIn("Align Ent migration contracts", titles)
        self.assertIn("Inventory Ent migration contract deltas", titles)
        self.assertIn("Patch Ent migration contract deltas", titles)
        self.assertIn("Align server and domain table contracts", titles)

        inventory = next(node for node in implementation_nodes if node["title"] == "Inventory Ent migration contract deltas")
        patch = next(node for node in implementation_nodes if node["title"] == "Patch Ent migration contract deltas")
        self.assertEqual(inventory["relevant_files"], ["backend/ent/migrate/schema.go", "backend/go.mod"])
        self.assertEqual(inventory.get("commands_to_run", []), [])
        self.assertEqual(patch["relevant_files"], ["backend/ent/migrate/schema.go", "backend/go.mod"])
        self.assertTrue(any("go test" in command for command in patch["commands_to_run"]))

    def test_schema_ent_regeneration_timeout_repair_splits_regeneration_task(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for directory in (
                "backend/ent/schema",
                "backend/ent/migrate",
                "backend/internal/repository",
                "backend/internal/service",
                "backend/internal/server",
                "backend/cmd/server",
            ):
                (repo / directory).mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/backend\n", encoding="utf-8")
            (repo / "backend" / "go.sum").write_text("", encoding="utf-8")
            (repo / "backend" / "ent" / "generate.go").write_text("package ent\n", encoding="utf-8")
            (repo / "backend" / "ent" / "schema" / "billing.go").write_text("package schema\n", encoding="utf-8")
            (repo / "backend" / "ent" / "migrate" / "schema.go").write_text("package migrate\n", encoding="utf-8")
            phase = root / "phase.md"
            phase.write_text(
                "\n".join(
                    [
                        "# Phase 8: Schema pruning and build",
                        "- Must prune Ent schema for CRM billing only.",
                        "- Must regenerate Ent clients.",
                        "- Must update migrations.",
                        "- Must prove a fresh DB migration succeeds.",
                        "- Fresh DB migration must not create token relay tables.",
                        "- `go test ./backend/internal/...` must pass.",
                        "- Frontend build/typecheck must pass.",
                        "Scope boundary mode: large_refactor",
                    ]
                ),
                encoding="utf-8",
            )
            t006_repair = root / "phase_repair_005.md"
            t006_repair.write_text(
                "\n".join(
                    [
                        "# Auto Repair For Phase 8",
                        "## Repairable Blockers",
                        "- B-T006-1: T006 exceeded the Codex worker timeout. Stop instead of launching a same-scope debug task. (tasks: T006)",
                        "## Focused Repair Scope",
                        "- Primary failed task IDs: T006.",
                        "- Completed tasks to preserve: T003, T004, T005, T001, T002.",
                        "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                        "### Task T006 - Regenerate Ent clients and migration artifacts",
                        "- Previous relevant files: backend/ent/**, backend/migrations/**, backend/internal/repository/**, backend/go.mod, backend/go.sum.",
                        "- Worker summary: Codex worker timed out after 900 seconds.",
                        "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Repair Billing Core Ent regeneration timeout.",
                documents=[phase, t006_repair],
                repository_path=repo,
                created_at="2026-06-28T08:30:00+08:00",
            )

            graph = TaskGraphBuilder().build(ContextBundleBuilder().build(brief)).to_dict()

        implementation_nodes = [
            node
            for node in graph["nodes"]
            if node["type"] not in {"architecture", "test", "review", "release"}
        ]
        titles = [node["title"] for node in implementation_nodes]
        self.assertNotIn("Regenerate Ent clients and migration artifacts", titles)
        self.assertIn("Inventory Ent regeneration inputs", titles)
        self.assertIn("Regenerate Ent generated clients", titles)
        self.assertIn("Align repository callers after Ent regeneration", titles)

        inventory = next(node for node in implementation_nodes if node["title"] == "Inventory Ent regeneration inputs")
        self.assertIn("backend/ent/generate.go", inventory["relevant_files"])
        self.assertIn("backend/ent/schema/**", inventory["relevant_files"])
        self.assertEqual(inventory.get("commands_to_run", []), [])
        self.assertTrue(any("inventoried without editing" in criterion for criterion in inventory["completion_criteria"]))
        regenerate = next(node for node in implementation_nodes if node["title"] == "Regenerate Ent generated clients")
        self.assertEqual(regenerate["commands_to_run"], ["cd backend && go test ./ent/..."])
        self.assertTrue(any("caller-alignment task" in criterion for criterion in regenerate["completion_criteria"]))
        callers = next(node for node in implementation_nodes if node["title"] == "Align repository callers after Ent regeneration")
        self.assertIn("backend/internal/repository/**", callers["relevant_files"])
        self.assertNotIn("backend/ent/**", callers["relevant_files"])

    def test_schema_ent_caller_timeout_repair_splits_caller_alignment_task(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for directory in (
                "backend/ent/schema",
                "backend/ent/migrate",
                "backend/internal/domain",
                "backend/internal/repository",
                "backend/internal/service",
                "backend/internal/server",
                "backend/internal/handler",
                "backend/cmd/server",
            ):
                (repo / directory).mkdir(parents=True)
            (repo / "backend" / "go.mod").write_text("module example.com/backend\n", encoding="utf-8")
            (repo / "backend" / "go.sum").write_text("", encoding="utf-8")
            (repo / "backend" / "ent" / "generate.go").write_text("package ent\n", encoding="utf-8")
            (repo / "backend" / "ent" / "schema" / "billing.go").write_text("package schema\n", encoding="utf-8")
            (repo / "backend" / "ent" / "migrate" / "schema.go").write_text("package migrate\n", encoding="utf-8")
            phase = root / "phase.md"
            phase.write_text(
                "\n".join(
                    [
                        "# Phase 8: Schema pruning and build",
                        "- Must prune Ent schema for CRM billing only.",
                        "- Must regenerate Ent clients.",
                        "- Must update migrations.",
                        "- Must clean unused service/repository/test code.",
                        "- Must prove a fresh DB migration succeeds.",
                        "- Fresh DB migration must not create token relay tables.",
                        "- `go test ./backend/internal/...` must pass.",
                        "- Frontend build/typecheck must pass.",
                        "Scope boundary mode: large_refactor",
                    ]
                ),
                encoding="utf-8",
            )
            repair_docs = {
                "phase_repair_002.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T002.",
                    "- Completed tasks to preserve: T001.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                    "### Task T002 - Prune legacy Ent schemas and table contracts",
                    "- Worker summary: Codex worker timed out after 900 seconds.",
                    "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                ],
                "phase_repair_004.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T003.",
                    "- Completed tasks to preserve: T001, T002.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                    "### Task T003 - Align Ent migration contracts",
                    "- Worker summary: Codex worker timed out after 900 seconds.",
                    "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                ],
                "phase_repair_005.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T006.",
                    "- Completed tasks to preserve: T003, T004, T005, T001, T002.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                    "### Task T006 - Regenerate Ent clients and migration artifacts",
                    "- Worker summary: Codex worker timed out after 900 seconds.",
                    "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                ],
                "phase_repair_007.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T008.",
                    "- Completed tasks to preserve: T006, T007, T001, T002, T003, T004, T005.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                    "### Task T008 - Align repository callers after Ent regeneration",
                    "- Previous relevant files: backend/internal/repository/**, backend/internal/service/**, backend/internal/server/**, backend/cmd/server/**, backend/go.mod.",
                    "- Worker summary: Codex worker timed out after 900 seconds.",
                    "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                ],
            }
            for name, lines in repair_docs.items():
                (root / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
            brief = ProjectBriefBuilder().build(
                objective="Repair Billing Core Ent caller alignment timeout.",
                documents=[phase, *(root / name for name in repair_docs)],
                repository_path=repo,
                created_at="2026-06-28T11:30:00+08:00",
            )

            graph = TaskGraphBuilder().build(ContextBundleBuilder().build(brief)).to_dict()

        implementation_nodes = [
            node
            for node in graph["nodes"]
            if node["type"] not in {"architecture", "test", "review", "release"}
        ]
        titles = [node["title"] for node in implementation_nodes]
        self.assertNotIn("Align repository callers after Ent regeneration", titles)
        self.assertIn("Inventory Ent caller alignment failures", titles)
        self.assertIn("Align repository Ent callers", titles)
        self.assertIn("Align service Ent caller contracts", titles)
        self.assertIn("Align server and handler Ent wiring", titles)

        nodes_by_id = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes_by_id["T006"]["title"], "Inventory Ent regeneration inputs")
        self.assertEqual(nodes_by_id["T006"]["status"], "completed")
        self.assertEqual(nodes_by_id["T007"]["title"], "Regenerate Ent generated clients")
        self.assertEqual(nodes_by_id["T007"]["status"], "completed")
        self.assertEqual(nodes_by_id["T008"]["title"], "Inventory Ent caller alignment failures")
        self.assertEqual(nodes_by_id["T008"].get("commands_to_run", []), [])

        repository_task = next(node for node in implementation_nodes if node["title"] == "Align repository Ent callers")
        self.assertEqual(repository_task["commands_to_run"], ["cd backend && go test ./internal/repository/..."])
        self.assertEqual(repository_task["relevant_files"], ["backend/internal/repository/**", "backend/go.mod"])
        service_task = next(node for node in implementation_nodes if node["title"] == "Align service Ent caller contracts")
        self.assertIn("backend/internal/service/**", service_task["relevant_files"])
        self.assertIn("backend/internal/repository/**", service_task["relevant_files"])
        server_task = next(node for node in implementation_nodes if node["title"] == "Align server and handler Ent wiring")
        self.assertIn("backend/internal/server/**", server_task["relevant_files"])
        self.assertIn("backend/internal/handler/**", server_task["relevant_files"])
        self.assertNotIn("backend/ent/**", server_task["relevant_files"])

    def test_schema_repository_caller_timeout_repair_splits_repository_alignment_task(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for directory in (
                "backend/ent/schema",
                "backend/ent/migrate",
                "backend/internal/domain",
                "backend/internal/repository",
                "backend/internal/service",
                "backend/internal/server",
                "backend/internal/handler",
                "backend/cmd/server",
            ):
                (repo / directory).mkdir(parents=True)
            for file in (
                "backend/internal/repository/account_repo.go",
                "backend/internal/repository/proxy_repo.go",
                "backend/internal/repository/channel_monitor_repo.go",
                "backend/internal/repository/error_passthrough_repo.go",
                "backend/internal/repository/tls_fingerprint_profile_repo.go",
                "backend/internal/repository/user_platform_quota_repo.go",
                "backend/internal/repository/wire.go",
            ):
                (repo / file).write_text("package repository\n", encoding="utf-8")
            (repo / "backend" / "go.mod").write_text("module example.com/backend\n", encoding="utf-8")
            (repo / "backend" / "go.sum").write_text("", encoding="utf-8")
            (repo / "backend" / "ent" / "generate.go").write_text("package ent\n", encoding="utf-8")
            (repo / "backend" / "ent" / "schema" / "billing.go").write_text("package schema\n", encoding="utf-8")
            (repo / "backend" / "ent" / "migrate" / "schema.go").write_text("package migrate\n", encoding="utf-8")
            phase = root / "phase.md"
            phase.write_text(
                "\n".join(
                    [
                        "# Phase 8: Schema pruning and build",
                        "- Must prune Ent schema for CRM billing only.",
                        "- Must regenerate Ent clients.",
                        "- Must update migrations.",
                        "- Must clean unused service/repository/test code.",
                        "- Must prove a fresh DB migration succeeds.",
                        "- Fresh DB migration must not create token relay tables.",
                        "- `go test ./backend/internal/...` must pass.",
                        "- Frontend build/typecheck must pass.",
                        "Scope boundary mode: large_refactor",
                    ]
                ),
                encoding="utf-8",
            )
            repair_docs = {
                "phase_repair_002.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T002.",
                    "- Completed tasks to preserve: T001.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                ],
                "phase_repair_004.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T003.",
                    "- Completed tasks to preserve: T001, T002.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                ],
                "phase_repair_005.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T006.",
                    "- Completed tasks to preserve: T003, T004, T005, T001, T002.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                ],
                "phase_repair_007.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T008.",
                    "- Completed tasks to preserve: T006, T007, T001, T002, T003, T004, T005.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                    "### Task T008 - Align repository callers after Ent regeneration",
                    "- Worker summary: Codex worker timed out after 900 seconds.",
                ],
                "phase_repair_008.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T009.",
                    "- Completed tasks to preserve: T008, T001, T002, T003, T004, T005, T006, T007.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                    "### Task T009 - Align repository Ent callers",
                    "- Previous relevant files: backend/internal/repository/**, backend/go.mod.",
                    "- Worker summary: Codex worker timed out after 900 seconds.",
                    "- Known issues: account_repo.go still references Proxy edges; proxy/channel_monitor/error_passthrough/tls_fingerprint/user_platform_quota repositories still call removed generated Ent clients; repository wire still registers retired providers.",
                    "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                ],
            }
            for name, lines in repair_docs.items():
                (root / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
            brief = ProjectBriefBuilder().build(
                objective="Repair Billing Core repository caller timeout.",
                documents=[phase, *(root / name for name in repair_docs)],
                repository_path=repo,
                created_at="2026-06-28T12:05:00+08:00",
            )

            graph = TaskGraphBuilder().build(ContextBundleBuilder().build(brief)).to_dict()

        implementation_nodes = [
            node
            for node in graph["nodes"]
            if node["type"] not in {"architecture", "test", "review", "release"}
        ]
        titles = [node["title"] for node in implementation_nodes]
        self.assertNotIn("Align repository Ent callers", titles)
        self.assertIn("Align account repository Ent callers", titles)
        self.assertIn("Remove retired generated-client repositories", titles)
        self.assertIn("Align remaining repository compile contracts", titles)

        nodes_by_id = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes_by_id["T008"]["title"], "Inventory Ent caller alignment failures")
        self.assertEqual(nodes_by_id["T008"]["status"], "completed")
        self.assertEqual(nodes_by_id["T009"]["title"], "Align account repository Ent callers")
        account_task = nodes_by_id["T009"]
        self.assertEqual(account_task["commands_to_run"], ["cd backend && go test ./internal/repository -run '^$'"])
        self.assertIn("backend/internal/repository/account_repo.go", account_task["relevant_files"])
        retired_task = next(
            node for node in implementation_nodes if node["title"] == "Remove retired generated-client repositories"
        )
        self.assertIn("backend/internal/repository/proxy*.go", retired_task["relevant_files"])
        self.assertIn("backend/internal/repository/wire.go", retired_task["relevant_files"])
        remaining_task = next(
            node for node in implementation_nodes if node["title"] == "Align remaining repository compile contracts"
        )
        self.assertIn("backend/internal/repository/*.go", remaining_task["relevant_files"])
        self.assertNotIn("backend/internal/service/**", remaining_task["relevant_files"])

    def test_schema_backend_cleanup_timeout_repair_splits_cleanup_task(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for directory in (
                "backend/ent/schema",
                "backend/ent/migrate",
                "backend/internal/config",
                "backend/internal/domain",
                "backend/internal/repository",
                "backend/internal/service",
                "backend/internal/server",
                "backend/internal/handler",
                "backend/internal/testutil",
                "backend/cmd/server",
            ):
                (repo / directory).mkdir(parents=True)
            for file in (
                "backend/internal/service/admin_service.go",
                "backend/internal/service/payment_service.go",
                "backend/internal/repository/account_repo.go",
                "backend/internal/handler/gateway_handler.go",
                "backend/internal/server/router.go",
                "backend/cmd/server/main.go",
            ):
                (repo / file).write_text("package backend\n", encoding="utf-8")
            (repo / "backend" / "go.mod").write_text("module example.com/backend\n", encoding="utf-8")
            (repo / "backend" / "go.sum").write_text("", encoding="utf-8")
            (repo / "backend" / "ent" / "generate.go").write_text("package ent\n", encoding="utf-8")
            (repo / "backend" / "ent" / "schema" / "billing.go").write_text("package schema\n", encoding="utf-8")
            (repo / "backend" / "ent" / "migrate" / "schema.go").write_text("package migrate\n", encoding="utf-8")
            phase = root / "phase.md"
            phase.write_text(
                "\n".join(
                    [
                        "# Phase 8: Schema pruning and build",
                        "- Must prune Ent schema for CRM billing only.",
                        "- Must regenerate Ent clients.",
                        "- Must update migrations.",
                        "- Must clean unused service/repository/test code.",
                        "- Must prove a fresh DB migration succeeds.",
                        "- Fresh DB migration must not create token relay tables.",
                        "- `go test ./backend/internal/...` must pass.",
                        "- Frontend build/typecheck must pass.",
                        "Scope boundary mode: large_refactor",
                    ]
                ),
                encoding="utf-8",
            )
            repair_docs = {
                "phase_repair_002.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T002.",
                    "- Completed tasks to preserve: T001.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                ],
                "phase_repair_004.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T003.",
                    "- Completed tasks to preserve: T001, T002.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                ],
                "phase_repair_005.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T006.",
                    "- Completed tasks to preserve: T003, T004, T005, T001, T002.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                ],
                "phase_repair_007.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T008.",
                    "- Completed tasks to preserve: T006, T007, T001, T002, T003, T004, T005.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                    "### Task T008 - Align repository callers after Ent regeneration",
                    "- Worker summary: Codex worker timed out after 900 seconds.",
                ],
                "phase_repair_008.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T009.",
                    "- Completed tasks to preserve: T008, T001, T002, T003, T004, T005, T006, T007.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                    "### Task T009 - Align repository Ent callers",
                    "- Worker summary: Codex worker timed out after 900 seconds.",
                    "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                ],
                "phase_repair_009.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T014.",
                    "- Completed tasks to preserve: T009, T010, T011, T012, T013, T001, T002, T003, T004, T005, T006, T007, T008.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                    "### Task T014 - Clean legacy backend services repositories and tests",
                    "- Previous relevant files: backend/internal/service/**, backend/internal/repository/**, backend/internal/handler/**, backend/internal/server/**, backend/internal/config/**, backend/go.mod, backend/cmd/server/main.go.",
                    "- Worker summary: Codex worker timed out after 900 seconds.",
                    "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                ],
            }
            for name, lines in repair_docs.items():
                (root / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
            brief = ProjectBriefBuilder().build(
                objective="Repair Billing Core backend cleanup timeout.",
                documents=[phase, *(root / name for name in repair_docs)],
                repository_path=repo,
                created_at="2026-06-28T13:20:00+08:00",
            )

            graph = TaskGraphBuilder().build(ContextBundleBuilder().build(brief)).to_dict()

        implementation_nodes = [
            node
            for node in graph["nodes"]
            if node["type"] not in {"architecture", "test", "review", "release"}
        ]
        titles = [node["title"] for node in implementation_nodes]
        self.assertNotIn("Clean legacy backend services repositories and tests", titles)
        self.assertIn("Inventory legacy backend cleanup leftovers", titles)
        self.assertIn("Clean service and repository legacy contracts", titles)
        self.assertIn("Clean handler and server legacy routes", titles)
        self.assertIn("Compile residual backend cleanup contracts", titles)

        nodes_by_id = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes_by_id["T013"]["title"], "Align server and handler Ent wiring")
        self.assertEqual(nodes_by_id["T013"]["status"], "completed")
        self.assertEqual(nodes_by_id["T014"]["title"], "Inventory legacy backend cleanup leftovers")
        self.assertEqual(nodes_by_id["T014"].get("commands_to_run", []), [])
        self.assertIn("backend/internal/handler/**", nodes_by_id["T014"]["relevant_files"])
        self.assertEqual(nodes_by_id["T015"]["title"], "Clean service and repository legacy contracts")
        self.assertEqual(
            nodes_by_id["T015"]["commands_to_run"],
            ["cd backend && go test ./internal/service/... ./internal/repository/... -run '^$'"],
        )
        self.assertIn("backend/internal/service/**", nodes_by_id["T015"]["relevant_files"])
        self.assertNotIn("backend/internal/handler/**", nodes_by_id["T015"]["relevant_files"])
        self.assertEqual(nodes_by_id["T016"]["title"], "Clean handler and server legacy routes")
        self.assertIn("backend/internal/server/**", nodes_by_id["T016"]["relevant_files"])
        self.assertEqual(nodes_by_id["T017"]["title"], "Compile residual backend cleanup contracts")
        self.assertEqual(nodes_by_id["T017"]["commands_to_run"], ["cd backend && go test ./internal/... -run '^$'"])
        self.assertEqual(nodes_by_id["T018"]["title"], "Stabilize schema and build verification contracts")

    def test_schema_handler_server_cleanup_timeout_repair_splits_route_task(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for directory in (
                "backend/ent/schema",
                "backend/ent/migrate",
                "backend/internal/config",
                "backend/internal/domain",
                "backend/internal/repository",
                "backend/internal/service",
                "backend/internal/server",
                "backend/internal/handler",
                "backend/internal/testutil",
                "backend/cmd/server",
            ):
                (repo / directory).mkdir(parents=True)
            for file in (
                "backend/internal/service/admin_service.go",
                "backend/internal/repository/account_repo.go",
                "backend/internal/handler/gateway_handler.go",
                "backend/internal/handler/admin_handler.go",
                "backend/internal/server/router.go",
                "backend/cmd/server/main.go",
            ):
                (repo / file).write_text("package backend\n", encoding="utf-8")
            (repo / "backend" / "go.mod").write_text("module example.com/backend\n", encoding="utf-8")
            (repo / "backend" / "go.sum").write_text("", encoding="utf-8")
            (repo / "backend" / "ent" / "generate.go").write_text("package ent\n", encoding="utf-8")
            (repo / "backend" / "ent" / "schema" / "billing.go").write_text("package schema\n", encoding="utf-8")
            (repo / "backend" / "ent" / "migrate" / "schema.go").write_text("package migrate\n", encoding="utf-8")
            phase = root / "phase.md"
            phase.write_text(
                "\n".join(
                    [
                        "# Phase 8: Schema pruning and build",
                        "- Must prune Ent schema for CRM billing only.",
                        "- Must regenerate Ent clients.",
                        "- Must update migrations.",
                        "- Must clean unused service/repository/test code.",
                        "- Must prove a fresh DB migration succeeds.",
                        "- Fresh DB migration must not create token relay tables.",
                        "- `go test ./backend/internal/...` must pass.",
                        "- Frontend build/typecheck must pass.",
                        "Scope boundary mode: large_refactor",
                    ]
                ),
                encoding="utf-8",
            )
            repair_docs = {
                "phase_repair_002.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T002.",
                    "- Completed tasks to preserve: T001.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                ],
                "phase_repair_004.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T003.",
                    "- Completed tasks to preserve: T001, T002.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                ],
                "phase_repair_005.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T006.",
                    "- Completed tasks to preserve: T003, T004, T005, T001, T002.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                ],
                "phase_repair_007.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T008.",
                    "- Completed tasks to preserve: T006, T007, T001, T002, T003, T004, T005.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                    "### Task T008 - Align repository callers after Ent regeneration",
                    "- Worker summary: Codex worker timed out after 900 seconds.",
                ],
                "phase_repair_008.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T009.",
                    "- Completed tasks to preserve: T008, T001, T002, T003, T004, T005, T006, T007.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                    "### Task T009 - Align repository Ent callers",
                    "- Worker summary: Codex worker timed out after 900 seconds.",
                    "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                ],
                "phase_repair_009.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T014.",
                    "- Completed tasks to preserve: T009, T010, T011, T012, T013, T001, T002, T003, T004, T005, T006, T007, T008.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                    "### Task T014 - Clean legacy backend services repositories and tests",
                    "- Previous relevant files: backend/internal/service/**, backend/internal/repository/**, backend/internal/handler/**, backend/internal/server/**, backend/internal/config/**, backend/go.mod, backend/cmd/server/main.go.",
                    "- Worker summary: Codex worker timed out after 900 seconds.",
                    "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                ],
                "phase_repair_010.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T016.",
                    "- Completed tasks to preserve: T014, T015, T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                    "### Task T016 - Clean handler and server legacy routes",
                    "- Previous relevant files: backend/internal/handler/**, backend/internal/server/**, backend/internal/service/**, backend/internal/config/**, backend/cmd/server/**, backend/go.mod.",
                    "- Worker summary: Codex worker timed out after 900 seconds.",
                    "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                ],
            }
            for name, lines in repair_docs.items():
                (root / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
            brief = ProjectBriefBuilder().build(
                objective="Repair Billing Core handler/server cleanup timeout.",
                documents=[phase, *(root / name for name in repair_docs)],
                repository_path=repo,
                created_at="2026-06-28T14:20:00+08:00",
            )

            graph = TaskGraphBuilder().build(ContextBundleBuilder().build(brief)).to_dict()

        implementation_nodes = [
            node
            for node in graph["nodes"]
            if node["type"] not in {"architecture", "test", "review", "release"}
        ]
        titles = [node["title"] for node in implementation_nodes]
        self.assertNotIn("Clean handler and server legacy routes", titles)
        self.assertIn("Inventory handler and server cleanup leftovers", titles)
        self.assertIn("Clean handler legacy route contracts", titles)
        self.assertIn("Clean server route and command wiring", titles)
        self.assertIn("Compile handler and server cleanup contracts", titles)

        nodes_by_id = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes_by_id["T014"]["title"], "Inventory legacy backend cleanup leftovers")
        self.assertEqual(nodes_by_id["T014"]["status"], "completed")
        self.assertEqual(nodes_by_id["T015"]["title"], "Clean service and repository legacy contracts")
        self.assertEqual(nodes_by_id["T015"]["status"], "completed")
        self.assertEqual(nodes_by_id["T016"]["title"], "Inventory handler and server cleanup leftovers")
        self.assertEqual(nodes_by_id["T016"].get("commands_to_run", []), [])
        self.assertEqual(nodes_by_id["T017"]["title"], "Clean handler legacy route contracts")
        self.assertEqual(nodes_by_id["T017"]["commands_to_run"], ["cd backend && go test ./internal/handler/... -run '^$'"])
        self.assertEqual(nodes_by_id["T018"]["title"], "Clean server route and command wiring")
        self.assertEqual(
            nodes_by_id["T018"]["commands_to_run"],
            ["cd backend && go test ./internal/server/... ./cmd/server/... -run '^$'"],
        )
        self.assertEqual(nodes_by_id["T019"]["title"], "Compile handler and server cleanup contracts")
        self.assertEqual(
            nodes_by_id["T019"]["commands_to_run"],
            ["cd backend && go test ./internal/handler/... ./internal/server/... ./cmd/server/... -run '^$'"],
        )
        self.assertEqual(nodes_by_id["T020"]["title"], "Compile residual backend cleanup contracts")
        self.assertEqual(nodes_by_id["T021"]["title"], "Stabilize schema and build verification contracts")

    def test_schema_final_verification_timeout_repair_splits_verify_task(self) -> None:
        with temp_plan_dir() as root:
            repo = root / "repo"
            for directory in (
                "backend/ent/schema",
                "backend/ent/migrate",
                "backend/internal/config",
                "backend/internal/domain",
                "backend/internal/repository",
                "backend/internal/service",
                "backend/internal/server",
                "backend/internal/handler",
                "backend/internal/testutil",
                "backend/cmd/server",
                "frontend/src/api",
                "frontend/src/components",
            ):
                (repo / directory).mkdir(parents=True)
            for file in (
                "backend/internal/service/admin_service.go",
                "backend/internal/repository/account_repo.go",
                "backend/internal/handler/gateway_handler.go",
                "backend/internal/server/router.go",
                "backend/cmd/server/main.go",
            ):
                (repo / file).write_text("package backend\n", encoding="utf-8")
            (repo / "backend" / "go.mod").write_text("module example.com/backend\n", encoding="utf-8")
            (repo / "backend" / "go.sum").write_text("", encoding="utf-8")
            (repo / "backend" / "ent" / "generate.go").write_text("package ent\n", encoding="utf-8")
            (repo / "backend" / "ent" / "schema" / "billing.go").write_text("package schema\n", encoding="utf-8")
            (repo / "backend" / "ent" / "migrate" / "schema.go").write_text("package migrate\n", encoding="utf-8")
            (repo / "frontend" / "package.json").write_text(
                json.dumps(
                    {
                        "scripts": {
                            "test": "vitest run",
                            "build": "vite build",
                            "lint": "eslint src",
                        }
                    }
                ),
                encoding="utf-8",
            )
            (repo / "frontend" / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
            phase = root / "phase.md"
            phase.write_text(
                "\n".join(
                    [
                        "# Phase 8: Schema pruning and build",
                        "- Must prune Ent schema for CRM billing only.",
                        "- Must regenerate Ent clients.",
                        "- Must update migrations.",
                        "- Must clean unused service/repository/test code.",
                        "- Must prove a fresh DB migration succeeds.",
                        "- Fresh DB migration must not create token relay tables.",
                        "- `go test ./backend/internal/...` must pass.",
                        "- Frontend build/typecheck must pass.",
                        "Scope boundary mode: large_refactor",
                    ]
                ),
                encoding="utf-8",
            )
            repair_docs = {
                "phase_repair_002.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T002.",
                    "- Completed tasks to preserve: T001.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                ],
                "phase_repair_004.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T003.",
                    "- Completed tasks to preserve: T001, T002.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                ],
                "phase_repair_005.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T006.",
                    "- Completed tasks to preserve: T003, T004, T005, T001, T002.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                ],
                "phase_repair_007.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T008.",
                    "- Completed tasks to preserve: T006, T007, T001, T002, T003, T004, T005.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                    "### Task T008 - Align repository callers after Ent regeneration",
                    "- Worker summary: Codex worker timed out after 900 seconds.",
                ],
                "phase_repair_008.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T009.",
                    "- Completed tasks to preserve: T008, T001, T002, T003, T004, T005, T006, T007.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                    "### Task T009 - Align repository Ent callers",
                    "- Worker summary: Codex worker timed out after 900 seconds.",
                    "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                ],
                "phase_repair_009.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T014.",
                    "- Completed tasks to preserve: T009, T010, T011, T012, T013, T001, T002, T003, T004, T005, T006, T007, T008.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                    "### Task T014 - Clean legacy backend services repositories and tests",
                    "- Previous relevant files: backend/internal/service/**, backend/internal/repository/**, backend/internal/handler/**, backend/internal/server/**, backend/internal/config/**, backend/go.mod, backend/cmd/server/main.go.",
                    "- Worker summary: Codex worker timed out after 900 seconds.",
                    "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                ],
                "phase_repair_010.md": [
                    "# Auto Repair For Phase 8",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T016.",
                    "- Completed tasks to preserve: T014, T015, T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                    "### Task T016 - Clean handler and server legacy routes",
                    "- Previous relevant files: backend/internal/handler/**, backend/internal/server/**, backend/internal/service/**, backend/internal/config/**, backend/cmd/server/**, backend/go.mod.",
                    "- Worker summary: Codex worker timed out after 900 seconds.",
                    "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                ],
                "phase_repair_011.md": [
                    "# Auto Repair For Phase 8",
                    "## Failing Verification Issues",
                    "- Must repair T022 verification issue (Verify implementation against project checks): Codex worker timed out after 900 seconds.",
                    "## Focused Repair Scope",
                    "- Primary failed task IDs: T022.",
                    "- Completed tasks to preserve: T016, T017, T018, T019, T020, T021, T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015.",
                    "- Treat a worker timeout as a stop boundary, then resume by checkpointing evidence or splitting the task rather than replaying the same wide scope.",
                    "### Task T022 - Verify implementation against project checks",
                    "- Previous relevant files: backend/internal/handler/admin/account_data_handler_test.go, backend/internal/service/wallet_service_test.go, frontend/src/api/__tests__/payment.spec.ts, frontend/src/components/__tests__/Dashboard.spec.ts.",
                    "- Worker summary: Codex worker timed out after 900 seconds.",
                    "- Timeout note: preserve the last evidence and split this workflow before increasing the hard timeout.",
                ],
            }
            for name, lines in repair_docs.items():
                (root / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
            brief = ProjectBriefBuilder().build(
                objective="Repair Billing Core final verification timeout.",
                documents=[phase, *(root / name for name in repair_docs)],
                repository_path=repo,
                created_at="2026-06-28T15:20:00+08:00",
            )

            graph = TaskGraphBuilder().build(ContextBundleBuilder().build(brief)).to_dict()
            resume_doc = root / "phase_repair_resume_001.md"
            resume_doc.write_text(
                "\n".join(
                    [
                        "# Auto Repair For Phase 8",
                        "Repair attempt: iteration-limit context",
                        "## Focused Repair Scope",
                        "- Primary failed task IDs: T026, T027.",
                        "- Completed tasks to preserve: T022, T023, T024, T025, T016, T017, T018, T019, T020, T021, T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015.",
                        "- Continue from the next incomplete review or delivery-evidence task instead of replaying split verification.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            resumed_brief = ProjectBriefBuilder().build(
                objective="Resume Billing Core after split verification iteration limit.",
                documents=[phase, *(root / name for name in repair_docs), resume_doc],
                repository_path=repo,
                created_at="2026-06-28T16:45:00+08:00",
            )

            resumed_graph = TaskGraphBuilder().build(ContextBundleBuilder().build(resumed_brief)).to_dict()

        nodes_by_id = {node["id"]: node for node in graph["nodes"]}
        titles = [node["title"] for node in graph["nodes"]]
        self.assertNotIn("Verify implementation against project checks", titles)
        self.assertEqual(nodes_by_id["T021"]["title"], "Stabilize schema and build verification contracts")
        self.assertEqual(nodes_by_id["T021"]["status"], "completed")
        self.assertEqual(nodes_by_id["T022"]["title"], "Verify backend tests")
        self.assertEqual(nodes_by_id["T022"]["commands_to_run"], ["cd backend && go test ./..."])
        self.assertIn("backend/**", nodes_by_id["T022"]["relevant_files"])
        self.assertEqual(nodes_by_id["T023"]["title"], "Verify frontend tests")
        self.assertEqual(nodes_by_id["T023"]["dependencies"], ["T022"])
        self.assertEqual(nodes_by_id["T023"]["commands_to_run"], ["pnpm --dir frontend test"])
        self.assertEqual(nodes_by_id["T024"]["title"], "Verify backend build")
        self.assertEqual(nodes_by_id["T024"]["dependencies"], ["T023"])
        self.assertEqual(nodes_by_id["T024"]["commands_to_run"], ["cd backend && go build ./..."])
        self.assertEqual(nodes_by_id["T025"]["title"], "Verify frontend build and lint")
        self.assertEqual(nodes_by_id["T025"]["dependencies"], ["T024"])
        self.assertEqual(
            nodes_by_id["T025"]["commands_to_run"],
            ["pnpm --dir frontend run build", "pnpm --dir frontend run lint"],
        )
        self.assertEqual(nodes_by_id["T026"]["title"], "Review delivery readiness")
        self.assertEqual(nodes_by_id["T026"]["dependencies"], ["T025"])
        resumed_nodes_by_id = {node["id"]: node for node in resumed_graph["nodes"]}
        self.assertEqual(resumed_nodes_by_id["T022"]["title"], "Verify backend tests")
        self.assertEqual(resumed_nodes_by_id["T022"]["status"], "completed")
        self.assertEqual(resumed_nodes_by_id["T025"]["title"], "Verify frontend build and lint")
        self.assertEqual(resumed_nodes_by_id["T025"]["status"], "completed")
        self.assertEqual(resumed_nodes_by_id["T026"]["title"], "Review delivery readiness")
        self.assertEqual(resumed_nodes_by_id["T026"]["status"], "pending")
        self.assertNotEqual(resumed_nodes_by_id["T026"]["title"], "Verify implementation against project checks")

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
