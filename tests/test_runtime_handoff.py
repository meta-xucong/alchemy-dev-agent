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
from planner import TaskGraphBuilder
from runtime import Orchestrator, RuntimeHandoff, StateManager


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_COUNTER = 0
_TEMP_RUN_ID = str(time.time_ns())


@contextmanager
def temp_handoff_dir() -> Iterator[Path]:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    path = TEST_TMP_ROOT / f"runtime-handoff-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
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


def build_document_plan(root: Path):
    repo = root / "repo"
    repo.mkdir()
    write_repo(repo)
    spec = root / "workspace_feature_spec.md"
    spec.write_text(
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
    brief = ProjectBriefBuilder().build(
        objective="Add workspace support",
        documents=[spec],
        repository_url="https://github.com/example/saas-dashboard",
        created_at="2026-06-18T00:00:00+00:00",
    )
    brief.repository.local_path = str(repo)
    bundle = ContextBundleBuilder().build(brief)
    graph = TaskGraphBuilder().build(bundle)
    return brief, bundle, graph, repo


class RuntimeHandoffTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_handoff_builds_runtime_state_and_worker_packages(self) -> None:
        with temp_handoff_dir() as root:
            brief, bundle, graph, repo = build_document_plan(root)
            state = RuntimeHandoff().build_state(
                project_brief=brief,
                context_bundle=bundle,
                task_graph=graph,
                repository_path=repo,
            )
            packages = RuntimeHandoff().build_worker_inputs(state=state)

        self.assertEqual(state.objective, "Add workspace support")
        self.assertEqual(state.repository["path"], str(repo))
        self.assertEqual(state.repository["source"]["visibility"], "public")
        self.assertEqual(state.task_graph.graph_id, f"{bundle.project_id}-document-plan")
        self.assertEqual(state.blockers, [])
        self.assertIn("Document requirements are traced to completed task IDs.", state.done_criteria)
        self.assertEqual(state.task_graph.nodes[-1].type, "release")

        package_by_id = {package.task_id: package for package in packages}
        self.assertEqual(package_by_id["T002"].repository_path, str(repo))
        self.assertEqual(package_by_id["T002"].agent_context["assigned_agent"], "backend")
        self.assertIn("src/api/workspaces.ts", package_by_id["T002"].relevant_files)
        self.assertIn("Users can create a workspace.", package_by_id["T002"].acceptance_criteria)
        self.assertIn("npm test", package_by_id["T002"].commands_to_run)

    def test_document_plan_runs_through_orchestrator_dry_run(self) -> None:
        with temp_handoff_dir() as root:
            brief, bundle, graph, repo = build_document_plan(root)
            state = RuntimeHandoff().build_state(
                project_brief=brief,
                context_bundle=bundle,
                task_graph=graph,
                repository_path=repo,
            )
            state_path = root / ".alchemy" / "state.json"
            orchestrator = Orchestrator(StateManager(state_path), repository_path=repo)

            final_state = orchestrator.run(
                state.objective,
                reset=True,
                initial_state=state,
                max_iterations=20,
            )
            payload = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertTrue(final_state.done)
        self.assertTrue(payload["done"])
        self.assertEqual(payload["task_graph"]["graph_id"], f"{bundle.project_id}-document-plan")
        self.assertEqual(payload["evaluation"]["reason"], "DONE condition met.")
        self.assertIn("pull_request_url", payload["github"])
        completed_ids = set(payload["completed_tasks"])
        self.assertTrue({"T001", "T002", "T003", "T004", "T005", "T006"}.issubset(completed_ids))


if __name__ == "__main__":
    unittest.main()
