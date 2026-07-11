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
from runtime.models import TaskGraph, TaskNode


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

    def test_worker_package_expands_package_lockfile_boundaries(self) -> None:
        graph = TaskGraph(
            graph_id="package-lock-boundary",
            version=1,
            nodes=[
                TaskNode(
                    id="T001",
                    title="Implement frontend package",
                    description="Update the frontend package.",
                    type="frontend",
                    assigned_agent="frontend",
                    relevant_files=["frontend/package.json"],
                )
            ]
        )
        state = RuntimeHandoff().build_state(
            project_brief={"objective": "Update frontend package", "repository": {"local_path": "."}},
            context_bundle={},
            task_graph=graph,
            repository_path=".",
        )

        worker_input = RuntimeHandoff().build_worker_inputs(state=state)[0]

        self.assertEqual(
            worker_input.allowed_files,
            [
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
                "frontend/package-lock.json",
                "frontend/npm-shrinkwrap.json",
                "frontend/yarn.lock",
                "frontend/bun.lockb",
            ],
        )

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

    def test_scoped_document_plan_worker_allowed_files_stay_in_v3_scope(self) -> None:
        with temp_handoff_dir() as root:
            repo = root / "repo"
            repo.mkdir()
            (repo / "alchemy_creative_agent_3_0" / "app").mkdir(parents=True)
            (repo / "alchemy_creative_agent_3_0" / "tests").mkdir(parents=True)
            (repo / "custom_media_agent_2_0").mkdir()
            (repo / "src_skeleton").mkdir()
            (repo / "tests").mkdir()
            (repo / "pyproject.toml").write_text("[project]\nname='media-agent'\n", encoding="utf-8")
            (repo / "custom_media_agent_2_0" / "legacy.py").write_text("LEGACY=True\n", encoding="utf-8")
            (repo / "src_skeleton" / "schemas.py").write_text("LEGACY=True\n", encoding="utf-8")
            (repo / "tests" / "test_legacy.py").write_text("def test_legacy():\n    assert True\n", encoding="utf-8")
            spec = root / "v3.md"
            spec.write_text(
                "\n".join(
                    [
                        "# V3 Foundation",
                        "## Requirements",
                        "- Must implement V3 foundation in alchemy_creative_agent_3_0/app/.",
                        "- Must not edit custom_media_agent_2_0/legacy.py or src_skeleton/schemas.py.",
                        "",
                        "All implementation code and tests must live under:",
                        "```text",
                        "alchemy_creative_agent_3_0/app/",
                        "alchemy_creative_agent_3_0/tests/",
                        "```",
                        "Do not edit any file under these paths:",
                        "```text",
                        "custom_media_agent_2_0/",
                        "src_skeleton/",
                        "tests/",
                        "```",
                        "Target files: alchemy_creative_agent_3_0/app/__init__.py, alchemy_creative_agent_3_0/app/creative_core/central_brain.py, alchemy_creative_agent_3_0/tests/test_end_to_end_planning.py",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Implement V3 Foundation",
                documents=[spec],
                repository_path=repo,
                created_at="2026-06-18T00:00:00+00:00",
            )
            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle)
            state = RuntimeHandoff().build_state(
                project_brief=brief,
                context_bundle=bundle,
                task_graph=graph,
                repository_path=repo,
            )
            packages = RuntimeHandoff().build_worker_inputs(state=state)

        package_by_id = {package.task_id: package for package in packages}
        implementation = package_by_id["T002"]
        self.assertEqual(
            implementation.allowed_files,
            [
                "alchemy_creative_agent_3_0/app/__init__.py",
                "alchemy_creative_agent_3_0/app/creative_core/central_brain.py",
                "alchemy_creative_agent_3_0/tests/test_end_to_end_planning.py",
            ],
        )
        self.assertEqual(implementation.allowed_files, implementation.relevant_files)
        self.assertTrue(all(path.startswith("alchemy_creative_agent_3_0/") for path in implementation.allowed_files))
        self.assertNotIn("custom_media_agent_2_0/legacy.py", implementation.allowed_files)
        self.assertEqual(package_by_id["T003"].allowed_files, [])
        self.assertEqual(package_by_id["T003"].commands_to_run, ["python -B -m pytest alchemy_creative_agent_3_0/tests"])

    def test_large_refactor_worker_package_uses_broad_repo_scope(self) -> None:
        with temp_handoff_dir() as root:
            repo = root / "repo"
            (repo / "backend" / "internal").mkdir(parents=True)
            (repo / "frontend" / "src").mkdir(parents=True)
            (repo / "backend" / "internal" / "billing.go").write_text("package internal\n", encoding="utf-8")
            (repo / "frontend" / "src" / "App.tsx").write_text("export const App = () => null;\n", encoding="utf-8")
            (repo / "go.mod").write_text("module example.com/app\n", encoding="utf-8")
            spec = root / "billing.md"
            spec.write_text(
                "\n".join(
                    [
                        "# Standalone Billing Core",
                        "## Requirements",
                        "- Must perform a whole-repository large refactor into a standalone service.",
                        "- Must remove token relay UI and backend routes.",
                        "- Must support wallet transactions and metering.",
                    ]
                ),
                encoding="utf-8",
            )
            brief = ProjectBriefBuilder().build(
                objective="Large refactor into standalone Billing Core",
                documents=[spec],
                repository_path=repo,
                created_at="2026-06-24T00:00:00+00:00",
            )
            bundle = ContextBundleBuilder().build(brief)
            graph = TaskGraphBuilder().build(bundle)
            state = RuntimeHandoff().build_state(
                project_brief=brief,
                context_bundle=bundle,
                task_graph=graph,
                repository_path=repo,
            )
            packages = RuntimeHandoff().build_worker_inputs(state=state)

        package_by_id = {package.task_id: package for package in packages}
        implementation = package_by_id["T002"]
        self.assertEqual(implementation.boundary_mode, "large_refactor")
        self.assertIn("backend/**", implementation.allowed_files)
        self.assertIn("frontend/**", implementation.allowed_files)
        self.assertIn("large_refactor integration task", " ".join(implementation.constraints))
        self.assertEqual(package_by_id["T003"].allowed_files, [])


if __name__ == "__main__":
    unittest.main()
