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
        self.assertIn("REQ-001, REQ-002, REQ-003", implementation_nodes[0]["description"])
        for requirement in requirements:
            self.assertEqual(requirement["planned_task_ids"][0], implementation_nodes[0]["id"])

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


if __name__ == "__main__":
    unittest.main()
