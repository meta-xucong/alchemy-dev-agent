from __future__ import annotations

import http.client
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from server.api import make_handler
from server.jobs import JobExecutionController, JobStore
from server.project_service import ApiError, ProjectService


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_RUN_ID = str(time.time_ns())
_TEMP_COUNTER = 0


def temp_root() -> Path:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    root = TEST_TMP_ROOT / f"api-server-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    root.mkdir(parents=True, exist_ok=False)
    return root


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


class ApiServerTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_project_service_creates_plans_runs_and_reads_delivery(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        write_repo(repo)
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        service = ProjectService(storage_root=root / "server")

        created = service.create_project(
            {
                "objective": "Add workspace support",
                "files": [{"path": str(spec), "role": "primary_requirements", "required": True}],
                "repository": "https://github.com/example/saas-dashboard",
                "repository_path": str(repo),
            }
        )
        project = created["project"]
        project_id = str(project["project_id"])

        self.assertEqual(project["status"], "intake_ready")
        self.assertEqual(len(service.list_files(project_id)["files"]), 1)

        plan = service.build_plan(project_id)
        self.assertEqual(plan["project"]["status"], "planned")
        self.assertGreaterEqual(len(plan["task_graph"]["nodes"]), 5)

        run = service.run_project(project_id, {})
        self.assertEqual(run["status"], "done")
        self.assertEqual(run["run_id"], "run_001")
        self.assertTrue((root / "server" / "projects" / project_id / "runs" / "run_001" / "run.json").exists())

        delivery = service.get_delivery(project_id)
        self.assertEqual(delivery["status"], "done")
        self.assertEqual(delivery["runtime_state"]["done"], True)
        self.assertEqual(delivery["delivery_report"]["status"], "done")
        self.assertTrue(delivery["delivery_report"]["ready_for_review"])
        evidence = delivery["delivery_evidence"]
        self.assertEqual(evidence["status"], "ready")
        self.assertTrue(evidence["ready_for_review"])
        self.assertGreaterEqual(len(evidence["cards"]), 6)
        self.assertEqual(evidence["requirements"]["missing_must"], 0)
        self.assertIn("github", evidence)
        self.assertIn("development_cycle", evidence)
        events = service.get_run_events(project_id, "run_001")
        self.assertEqual(events["run_id"], "run_001")
        self.assertGreater(len(events["events"]), 0)

    def test_project_service_delete_project_removes_managed_project_folder(self) -> None:
        root = temp_root()
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        service = ProjectService(storage_root=root / "server")

        created = service.create_project(
            {
                "objective": "Delete unwanted result",
                "documents": [str(spec)],
            }
        )
        project_id = str(created["project"]["project_id"])
        project_dir = service.project_dir(project_id)
        generated = project_dir / "runs" / "run_001" / "generated_repository"
        generated.mkdir(parents=True)
        (generated / "index.html").write_text("<main>discard me</main>\n", encoding="utf-8")

        result = service.delete_project(project_id)

        self.assertEqual(result["status"], "deleted")
        self.assertEqual(result["project_id"], project_id)
        self.assertFalse(project_dir.exists())
        self.assertEqual(service.list_projects()["projects"], [])

    def test_project_service_delete_project_rejects_active_run(self) -> None:
        root = temp_root()
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        service = ProjectService(storage_root=root / "server")

        created = service.create_project(
            {
                "objective": "Do not delete while running",
                "documents": [str(spec)],
            }
        )
        project_id = str(created["project"]["project_id"])
        service.job_store(project_id).create(project_id, "run_001")

        with self.assertRaises(ApiError) as raised:
            service.delete_project(project_id)

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.code, "project_has_active_run")
        self.assertTrue(service.project_dir(project_id).exists())

    def test_project_service_exposes_artifact_manifest_and_content(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        write_repo(repo)
        (repo / ".github" / "workflows").mkdir(parents=True)
        (repo / "index.html").write_text("<main>Playable artifact</main>\n", encoding="utf-8")
        (repo / ".github" / "workflows" / "alchemy-static-checks.yml").write_text("name: checks\n", encoding="utf-8")
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        service = ProjectService(storage_root=root / "server")
        created = service.create_project(
            {
                "objective": "Add workspace support",
                "documents": [str(spec)],
                "repository_path": str(repo),
            }
        )
        project_id = str(created["project"]["project_id"])
        run = service.run_project(project_id, {})
        run_dir = service.project_dir(project_id) / "runs" / str(run["run_id"])
        screenshot = run_dir / "browser_initial.png"
        test_draft = run_dir / "generated_tests" / "playwright" / "alchemy_acceptance.spec.ts"
        test_draft.parent.mkdir(parents=True, exist_ok=True)
        screenshot.write_bytes(b"\x89PNG\r\n\x1a\n")
        test_draft.write_text("test('acceptance', async () => {});\n", encoding="utf-8")
        run["artifact_report"] = {
            "browser_verification": {"screenshots": {"initial": str(screenshot)}},
            "native_ui_tests": {"status": "generated", "files": [str(test_draft)]},
            "artifact_files": ["index.html"],
        }
        run["generated_ci"] = {
            "status": "generated",
            "workflow_path": ".github/workflows/alchemy-static-checks.yml",
        }
        run["runtime_state"]["repository"]["path"] = str(repo)
        service._write_json(run_dir / "run.json", run)

        manifest = service.get_run_artifacts(project_id, str(run["run_id"]))

        self.assertEqual(len(manifest["items"]), 4)
        self.assertEqual(
            {item["kind"] for item in manifest["items"]},
            {"screenshot", "native_ui_test", "artifact_file", "generated_ci"},
        )
        self.assertTrue(all("_absolute_path" not in item for item in manifest["items"]))
        artifact_id = next(str(item["artifact_id"]) for item in manifest["items"] if item["kind"] == "artifact_file")
        content = service.get_run_artifact_content(project_id, str(run["run_id"]), artifact_id)
        self.assertEqual(content.data.decode("utf-8").strip(), "<main>Playable artifact</main>")
        self.assertEqual(content.media_type, "text/html; charset=utf-8")
        delivery = service.get_delivery(project_id)
        self.assertEqual(delivery["artifact_manifest"]["items"], manifest["items"])

    def test_project_service_exposes_beginner_run_status_and_delivery_actions(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        write_repo(repo)
        (repo / "index.html").write_text("<main>Playable artifact</main>\n", encoding="utf-8")
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        service = ProjectService(storage_root=root / "server")
        created = service.create_project(
            {
                "objective": "Add workspace support",
                "documents": [str(spec)],
                "repository_path": str(repo),
            }
        )
        project_id = str(created["project"]["project_id"])
        run = service.run_project(project_id, {})
        run_dir = service.project_dir(project_id) / "runs" / str(run["run_id"])
        run["artifact_report"] = {"artifact_files": ["index.html"]}
        run["runtime_state"]["repository"]["path"] = str(repo)
        service._write_json(run_dir / "run.json", run)

        status = service.get_run_status(project_id, str(run["run_id"]))

        self.assertEqual(status["status"], "done")
        self.assertEqual(status["phase"], "ready")
        self.assertEqual(status["progress_percent"], 100)
        self.assertEqual(status["central_review"]["status"], "ready")
        self.assertEqual(status["central_review"]["decision"], "handoff")
        self.assertGreaterEqual(status["tasks"]["total"], 1)
        self.assertFalse(status["is_stalled"])
        actions = {str(action["id"]): action for action in status["delivery_actions"]}
        self.assertIn("open_result", actions)
        self.assertTrue(str(actions["open_result"]["url"]).startswith(f"/projects/{project_id}/runs/{run['run_id']}/preview/"))
        self.assertTrue(str(actions["open_result"]["artifact_url"]).startswith(f"/projects/{project_id}/runs/{run['run_id']}/artifacts/"))
        self.assertIn("open_folder", actions)
        self.assertIn("publish_github", actions)
        self.assertFalse(actions["publish_github"]["enabled"])
        delivery = service.get_delivery(project_id)
        self.assertEqual(delivery["central_review"]["status"], "ready")
        self.assertEqual(delivery["central_review"]["decision"], "handoff")

    def test_project_service_lists_project_history_with_latest_run_summary(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        write_repo(repo)
        (repo / "index.html").write_text("<main>Playable artifact</main>\n", encoding="utf-8")
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        service = ProjectService(storage_root=root / "server")
        first = service.create_project(
            {
                "objective": "Add workspace support",
                "documents": [str(spec)],
                "repository_path": str(repo),
            }
        )
        first_id = str(first["project"]["project_id"])
        run = service.run_project(first_id, {})
        run_dir = service.project_dir(first_id) / "runs" / str(run["run_id"])
        run["artifact_report"] = {"artifact_files": ["index.html"]}
        run["runtime_state"]["repository"]["path"] = str(repo)
        service._write_json(run_dir / "run.json", run)
        second = service.create_project({"objective": "Second project", "documents": [str(spec)]})

        history = service.list_projects()

        projects = history["projects"]
        self.assertEqual(len(projects), 2)
        by_id = {str(project["project_id"]): project for project in projects}
        first_summary = by_id[first_id]
        self.assertEqual(first_summary["run_count"], 1)
        self.assertEqual(first_summary["latest_run_id"], "run_001")
        self.assertEqual(first_summary["latest_run_status"], "done")
        self.assertIn("latest_score", first_summary)
        self.assertTrue(str(first_summary["console_url"]).endswith(f"project_id={first_id}&run_id=run_001"))
        self.assertTrue(Path(str(first_summary["workspace_path"])).exists())
        self.assertEqual(by_id[str(second["project"]["project_id"])]["run_count"], 0)

    def test_project_service_open_result_folder_uses_safe_local_folder(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        write_repo(repo)
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        opened: list[Path] = []
        service = ProjectService(storage_root=root / "server", folder_opener=lambda path: opened.append(path))
        created = service.create_project(
            {
                "objective": "Add workspace support",
                "documents": [str(spec)],
                "repository_path": str(repo),
            }
        )
        project_id = str(created["project"]["project_id"])
        run = service.run_project(project_id, {})

        result = service.open_run_result_folder(project_id, str(run["run_id"]))

        self.assertEqual(result["status"], "opened")
        self.assertEqual(opened, [repo.resolve()])

    def test_project_service_open_result_folder_uses_runtime_github_source_folder(self) -> None:
        root = temp_root()
        repo = root / "server" / "projects" / "proj_manual" / "repo"
        repo.mkdir(parents=True)
        write_repo(repo)
        opened: list[Path] = []
        service = ProjectService(storage_root=root / "server", folder_opener=lambda path: opened.append(path))
        created = service.create_project(
            {
                "project_id": "proj_manual",
                "objective": "Build from GitHub",
                "primary_input_mode": "document_driven",
                "repository": "https://github.com/example/repo",
            }
        )
        project_id = str(created["project"]["project_id"])
        run_id = "run_001"
        run_dir = service.project_dir(project_id) / "runs" / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "run.json").write_text(
            json.dumps(
                {
                    "project_id": project_id,
                    "run_id": run_id,
                    "status": "done",
                    "runtime_state": {
                        "repository": {
                            "source": {
                                "local_path": str(repo),
                            }
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        result = service.open_run_result_folder(project_id, run_id)

        self.assertEqual(result["status"], "opened")
        self.assertEqual(opened, [repo.resolve()])

    def test_project_service_late_run_status_does_not_override_blocked_intake(self) -> None:
        root = temp_root()
        service = ProjectService(storage_root=root / "server")
        created = service.create_project(
            {
                "objective": "Add workspace support",
                "primary_input_mode": "document_driven",
            }
        )
        project_id = str(created["project"]["project_id"])
        stale_record = service.load_project(project_id)
        blocked = service.load_project(project_id)
        blocked.status = "intake_blocked"
        service._write_json(service.project_dir(project_id) / "project.json", blocked.to_dict())

        updated = service._update_project_status(stale_record, "done")

        self.assertEqual(updated.status, "intake_blocked")
        self.assertEqual(service.load_project(project_id).status, "intake_blocked")

    def test_project_service_records_local_repository_provider(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        write_repo(repo)
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        service = ProjectService(storage_root=root / "server")

        created = service.create_project(
            {
                "objective": "Add workspace support",
                "documents": [str(spec)],
                "repository_path": str(repo),
            }
        )
        project_id = str(created["project"]["project_id"])
        plan = service.build_plan(project_id)

        self.assertEqual(created["brief"]["repository"]["provider"], "local")
        self.assertEqual(created["brief"]["repository"]["local_path"], str(repo))
        repository_files = plan["context"]["repository_map"]["files"]
        self.assertIn("src/pages/dashboard.tsx", [file["path"] for file in repository_files])

    def test_project_service_run_payload_records_workspace_contract(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        write_repo(repo)
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        service = ProjectService(storage_root=root / "server")
        created = service.create_project(
            {
                "objective": "Add workspace support",
                "documents": [str(spec)],
                "repository": "https://github.com/example/saas-dashboard",
                "repository_path": str(repo),
            }
        )
        project_id = str(created["project"]["project_id"])

        run = service.run_project(project_id, {"isolate_real_run": False, "keep_worktree": False})

        self.assertEqual(run["status"], "done")
        self.assertEqual(run["workspace"]["status"], "skipped")
        self.assertEqual(run["workspace"]["enabled"], False)

    def test_project_service_unified_run_uses_full_roadmap_mode_by_default(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        write_repo(repo)
        spec = root / "roadmap.md"
        spec.write_text(
            "\n".join(
                [
                    "# Roadmap",
                    "## V1.0 Foundation",
                    "- Must build foundation.",
                    "## V1.1 Core",
                    "- Must build core.",
                ]
            ),
            encoding="utf-8",
        )
        captured: dict[str, object] = {}

        class FakeFullRoadmapResult:
            def to_dict(self) -> dict[str, object]:
                return {
                    "status": "done",
                    "roadmap": {
                        "root_objective": "Build all phases",
                        "phases": [
                            {"phase_id": "phase_001", "title": "V1.0 Foundation", "status": "completed"},
                            {"phase_id": "phase_002", "title": "V1.1 Core", "status": "completed"},
                        ],
                    },
                    "roadmap_audit": {"status": "passed"},
                    "project_analysis": {
                        "start_decision": "start",
                        "confidence": 0.91,
                        "ready_to_start": True,
                        "valid_phases": [
                            {"phase_id": "phase_001", "title": "V1.0 Foundation"},
                            {"phase_id": "phase_002", "title": "V1.1 Core"},
                        ],
                        "ignored_phase_candidates": [{"text": "V1 should not be treated as policy.", "reason": "constraint_or_policy_sentence"}],
                    },
                    "phase_records": [
                        {"phase_id": "phase_001", "title": "V1.0 Foundation", "status": "done"},
                        {"phase_id": "phase_002", "title": "V1.1 Core", "status": "done"},
                    ],
                    "final_audit": {"status": "passed", "ready_for_final_handoff": True},
                    "blockers": [],
                    "output_dir": str(root / "server"),
                }

        class FakeFullRoadmapExecutor:
            def run(self, **kwargs):
                captured.update(kwargs)
                return FakeFullRoadmapResult()

        service = ProjectService(storage_root=root / "server")
        with mock.patch("server.project_service.FullRoadmapExecutor", return_value=FakeFullRoadmapExecutor()):
            result = service.run_unified_request(
                {
                    "objective": "Build all phases",
                    "documents": [str(spec)],
                    "repository_path": str(repo),
                    "full_roadmap": True,
                    "async": False,
                }
            )

        self.assertEqual(result["status"], "done")
        self.assertTrue(captured["run_payload"]["full_roadmap"])
        run = result["run"]
        self.assertEqual(run["delivery_report"]["roadmap"]["phase_total"], 2)
        self.assertEqual(run["delivery_report"]["project_analysis"]["start_decision"], "start")
        self.assertEqual(run["delivery_report"]["project_analysis"]["valid_phase_count"], 2)
        self.assertEqual(run["delivery_report"]["project_analysis"]["ignored_candidate_count"], 1)
        self.assertEqual(run["runtime_state"]["done"], True)
        self.assertEqual(run["runtime_state"]["project_analysis"]["start_decision"], "start")
        self.assertEqual(len(run["task_graph"]["nodes"]), 2)
        status = service.get_run_status(str(result["project_id"]), str(result["run_id"]))
        self.assertTrue(status["roadmap_progress"]["enabled"])
        self.assertEqual(status["roadmap_progress"]["total"], 2)
        self.assertEqual(status["roadmap_progress"]["completed"], 2)
        self.assertEqual(status["roadmap_progress"]["progress_percent"], 100)

    def test_project_service_full_roadmap_takes_priority_over_one_line_fallback(self) -> None:
        root = temp_root()
        captured: dict[str, object] = {}

        class FakeFullRoadmapResult:
            def to_dict(self) -> dict[str, object]:
                return {
                    "status": "done",
                    "roadmap": {
                        "root_objective": "Build a complete app",
                        "phases": [
                            {"phase_id": "phase_001", "title": "Generated Requirements", "status": "completed"},
                            {"phase_id": "phase_002", "title": "Implementation", "status": "completed"},
                        ],
                    },
                    "roadmap_audit": {"status": "passed"},
                    "project_analysis": {
                        "start_decision": "start",
                        "confidence": 0.88,
                        "ready_to_start": True,
                        "valid_phases": [
                            {"phase_id": "phase_001", "title": "Generated Requirements"},
                            {"phase_id": "phase_002", "title": "Implementation"},
                        ],
                        "ignored_phase_candidates": [],
                    },
                    "phase_records": [
                        {"phase_id": "phase_001", "title": "Generated Requirements", "status": "done"},
                        {"phase_id": "phase_002", "title": "Implementation", "status": "done"},
                    ],
                    "final_audit": {"status": "passed", "ready_for_final_handoff": True},
                    "blockers": [],
                    "output_dir": str(root / "server"),
                }

        class FakeFullRoadmapExecutor:
            def run(self, **kwargs):
                captured.update(kwargs)
                return FakeFullRoadmapResult()

        service = ProjectService(storage_root=root / "server")
        with mock.patch("server.project_service.FullRoadmapExecutor", return_value=FakeFullRoadmapExecutor()):
            result = service.run_unified_request(
                {
                    "objective": "Build a complete app",
                    "expand_one_line": False,
                    "full_roadmap": True,
                    "async": False,
                }
            )

        self.assertEqual(result["status"], "done")
        self.assertEqual(captured["primary_input_mode"], "one_line_fallback")
        self.assertTrue(captured["run_payload"]["full_roadmap"])
        self.assertEqual(result["run"]["delivery_report"]["roadmap"]["phase_total"], 2)

    def test_project_status_maps_in_progress_to_needs_iteration(self) -> None:
        from server.project_service import project_status_for_run

        self.assertEqual(project_status_for_run("in_progress"), "needs_iteration")

    def test_project_service_run_payload_records_github_ci_wait_contract(self) -> None:
        root = temp_root()
        captured = {"kwargs": {}}

        class FakeRunResult:
            status = "done"

            def to_dict(self) -> dict[str, object]:
                return {"status": "done", "runtime_state": {"done": True}}

        class FakePipeline:
            def run(self, **kwargs) -> FakeRunResult:
                captured["kwargs"] = kwargs
                return FakeRunResult()

        service = ProjectService(storage_root=root / "server")
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        created = service.create_project({"objective": "Add workspace support", "documents": [str(spec)]})
        project_id = str(created["project"]["project_id"])
        service.build_plan(project_id)

        with mock.patch("server.project_service.DocumentRunPipeline", return_value=FakePipeline()):
            run = service.run_project(
                project_id,
                {
                    "github_collect_ci": False,
                    "github_ci_wait_seconds": 33,
                    "github_ci_poll_interval_seconds": 4,
                    "auto_browser_verify": True,
                    "generate_static_ci": False,
                    "write_native_ui_tests": True,
                    "auto_merge": True,
                },
            )

        self.assertEqual(run["status"], "done")
        self.assertEqual(captured["kwargs"]["github_collect_ci"], False)
        self.assertEqual(captured["kwargs"]["github_ci_wait_seconds"], 33.0)
        self.assertEqual(captured["kwargs"]["github_ci_poll_interval_seconds"], 4.0)
        self.assertEqual(captured["kwargs"]["auto_browser_verify"], True)
        self.assertEqual(captured["kwargs"]["generate_static_ci"], False)
        self.assertEqual(captured["kwargs"]["write_native_ui_tests"], True)
        self.assertEqual(captured["kwargs"]["auto_merge"], True)

    def test_project_service_reopens_delivered_run_with_feedback(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        write_repo(repo)
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        feedback = root / "playtest_feedback.md"
        feedback.write_text(
            "# Feedback\n\n## Feedback\n- Bug: clicking Create workspace does not update src/pages/dashboard.tsx.\n",
            encoding="utf-8",
        )
        service = ProjectService(storage_root=root / "server")
        created = service.create_project(
            {
                "objective": "Add workspace support",
                "documents": [str(spec)],
                "repository_path": str(repo),
            }
        )
        project_id = str(created["project"]["project_id"])
        first_run = service.run_project(project_id, {})

        reopened = service.reopen_with_feedback(
            project_id,
            {
                "source_run_id": first_run["run_id"],
                "feedback_files": [str(feedback)],
                "run": {"auto_browser_verify": False},
            },
        )

        self.assertEqual(reopened["run_id"], "run_002")
        self.assertEqual(reopened["feedback_reopen"]["source_run_id"], "run_001")
        self.assertEqual(reopened["feedback_reopen"]["worktree_branch_prefix"], "agent/feedback-recovery")
        self.assertEqual(reopened["recovery_comparison"]["source_run_id"], "run_001")
        self.assertEqual(reopened["recovery_comparison"]["current_run_id"], "run_002")
        self.assertIn(reopened["recovery_comparison"]["status"], {"improved", "same_passed", "unchanged", "mixed"})
        graph = reopened["task_graph"]
        debug_nodes = [node for node in graph["nodes"] if node["type"] == "debug"]
        self.assertGreaterEqual(len(debug_nodes), 1)
        self.assertEqual(debug_nodes[0]["assigned_agent"], "debug")
        self.assertIn(str(feedback), service.load_project(project_id).attachments)
        delivery = service.get_delivery(project_id)
        run_delivery = service.get_delivery_for_run(project_id, "run_002")
        self.assertEqual(delivery["recovery_comparison"]["source_run_id"], "run_001")
        self.assertEqual(delivery["delivery_evidence"]["recovery_comparison"]["current_run_id"], "run_002")
        self.assertIn("repair_suggestions", delivery["recovery_comparison"])
        self.assertIn("repair_suggestions", delivery["delivery_evidence"])
        self.assertEqual(run_delivery["latest_run_id"], "run_002")
        self.assertEqual(run_delivery["delivery_evidence"]["recovery_comparison"]["current_run_id"], "run_002")

    def test_project_service_auto_iteration_generates_repair_plan_and_reopens(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        write_repo(repo)
        (repo / "index.html").write_text("<main>Playable artifact</main>\n", encoding="utf-8")
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        service = ProjectService(storage_root=root / "server")
        created = service.create_project(
            {
                "objective": "Add workspace support",
                "documents": [str(spec)],
                "repository_path": str(repo),
            }
        )
        project_id = str(created["project"]["project_id"])
        run = service.run_project(project_id, {})
        run_id = str(run["run_id"])
        run_dir = service.project_dir(project_id) / "runs" / run_id
        run["artifact_report"] = {"artifact_files": ["index.html"]}
        run["runtime_state"]["repository"]["path"] = str(repo)
        run["delivery_report"]["ready_for_review"] = False
        run["delivery_report"]["status"] = "needs_iteration"
        run["delivery_report"]["final_gate"]["score"] = 0.8
        run["delivery_report"]["final_gate"]["dimension_scores"] = {"test_health": 0.6}
        service._write_json(run_dir / "run.json", run)

        delivery_preview = service.get_delivery_for_run(project_id, run_id)
        self.assertEqual(delivery_preview["central_review"]["decision"], "iterate")
        self.assertEqual(delivery_preview["auto_iteration"]["status"], "skipped")
        self.assertEqual(delivery_preview["repair_plan"]["status"], "ready")
        self.assertTrue(delivery_preview["repair_plan"]["auto_execution"]["allowed"])
        self.assertFalse((run_dir / "repair_plan.json").exists())
        self.assertFalse((run_dir / "auto_iteration_report.json").exists())

        preview = service.preview_auto_iteration(project_id, run_id)

        self.assertEqual(preview["status"], "skipped")
        self.assertTrue(preview["auto_execution_available"])
        self.assertEqual(preview["repair_plan"]["status"], "ready")
        self.assertTrue(preview["repair_plan"]["items"])
        self.assertTrue(all("target_files" in item for item in preview["repair_plan"]["items"]))

        started = service.start_auto_iteration(project_id, run_id, {"run": {"auto_browser_verify": False}})

        self.assertEqual(started["status"], "started")
        self.assertEqual(started["repair_run_id"], "run_002")
        self.assertEqual(started["repair_plan"]["status"], "started")
        self.assertTrue((run_dir / "repair_plan.json").exists())
        self.assertTrue((run_dir / "repair_plan.md").exists())
        self.assertTrue((run_dir / "auto_feedback.md").exists())
        self.assertTrue((run_dir / "auto_iteration_report.json").exists())
        repair_run = service.get_run(project_id, "run_002")
        self.assertEqual(repair_run["central_auto_iteration"]["source_run_id"], "run_001")
        self.assertEqual(repair_run["feedback_reopen"]["source_run_id"], "run_001")
        self.assertEqual(repair_run["recovery_comparison"]["current_run_id"], "run_002")
        delivery = service.get_delivery_for_run(project_id, "run_001")
        self.assertEqual(delivery["auto_iteration"]["status"], "started")
        self.assertEqual(delivery["repair_plan"]["status"], "started")

    def test_project_service_auto_iteration_can_start_async_repair_run(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        write_repo(repo)
        (repo / "index.html").write_text("<main>Playable artifact</main>\n", encoding="utf-8")
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        service = ProjectService(storage_root=root / "server")
        created = service.create_project(
            {
                "objective": "Add workspace support",
                "documents": [str(spec)],
                "repository_path": str(repo),
            }
        )
        project_id = str(created["project"]["project_id"])
        run = service.run_project(project_id, {})
        run_id = str(run["run_id"])
        run_dir = service.project_dir(project_id) / "runs" / run_id
        run["artifact_report"] = {"artifact_files": ["index.html"]}
        run["runtime_state"]["repository"]["path"] = str(repo)
        run["delivery_report"]["ready_for_review"] = False
        run["delivery_report"]["status"] = "needs_iteration"
        run["delivery_report"]["final_gate"]["score"] = 0.8
        run["delivery_report"]["final_gate"]["dimension_scores"] = {"test_health": 0.6}
        service._write_json(run_dir / "run.json", run)

        started = service.start_auto_iteration(
            project_id,
            run_id,
            {"async": True, "run": {"auto_browser_verify": False}},
        )

        self.assertEqual(started["status"], "started")
        self.assertEqual(started["repair_run_id"], "run_002")
        self.assertEqual(started["job"]["status"], "queued")
        self.assertTrue((service.project_dir(project_id) / "runs" / "run_002" / "repair_source.json").exists())
        job = wait_for_job(service, project_id, "run_002")
        self.assertEqual(job["status"], "done")
        repair_run = service.get_run(project_id, "run_002")
        self.assertEqual(repair_run["feedback_reopen"]["source_run_id"], "run_001")
        self.assertEqual(service.get_delivery_for_run(project_id, "run_001")["auto_iteration"]["status"], "started")

    def test_auto_iteration_feedback_preserves_requirement_target_files(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        (repo / "app.py").write_text("def add(a, b):\n    raise NotImplementedError()\n", encoding="utf-8")
        spec = root / "add_spec.md"
        spec.write_text("# Add\n## Requirements\n- Must implement add(a, b) in app.py.\n", encoding="utf-8")
        service = ProjectService(storage_root=root / "server")
        created = service.create_project(
            {
                "objective": "Implement add",
                "documents": [str(spec)],
                "repository_path": str(repo),
            }
        )
        project_id = str(created["project"]["project_id"])
        run = service.run_project(project_id, {})
        run_id = str(run["run_id"])
        run_dir = service.project_dir(project_id) / "runs" / run_id
        run["runtime_state"]["repository"]["path"] = str(repo)
        run["artifact_report"] = {"artifact_files": ["app.py"], "artifact_profile": {"name": "python_project"}}
        run["requirement_coverage"] = {
            "status": "partial",
            "missing_must_requirement_ids": ["REQ-ADD-001"],
            "partial_must_requirement_ids": [],
            "requirement_map": {
                "requirements": [
                    {
                        "id": "REQ-ADD-001",
                        "priority": "must",
                        "status": "missing",
                        "summary": "Implement add(a, b) in app.py.",
                        "related_files": ["app.py"],
                    }
                ]
            },
        }
        run["delivery_report"]["ready_for_review"] = False
        run["delivery_report"]["status"] = "needs_iteration"
        run["delivery_report"]["final_gate"]["score"] = 0.72
        service._write_json(run_dir / "run.json", run)

        preview = service.preview_auto_iteration(project_id, run_id)

        target_items = [item for item in preview["repair_plan"]["items"] if "app.py" in item["target_files"]]
        self.assertTrue(target_items)

        service.start_auto_iteration(project_id, run_id, {"run": {"auto_browser_verify": False}})
        auto_feedback = (run_dir / "auto_feedback.md").read_text(encoding="utf-8")
        self.assertIn("Target files: app.py", auto_feedback)
        repair_run = service.get_run(project_id, "run_002")
        convergence = repair_run["runtime_state"]["repository"]["repair_convergence"]
        self.assertEqual(convergence["status"], "completed")
        self.assertEqual(convergence["target_files"], ["app.py"])
        self.assertEqual(convergence["source_run_id"], "run_001")
        self.assertTrue(repair_run["runtime_state"]["done"])

    def test_auto_iteration_real_codex_repair_converges_after_target_file_and_tests_pass(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
        (repo / "app.py").write_text("def add(a, b):\n    raise NotImplementedError()\n", encoding="utf-8")
        (repo / "tests").mkdir()
        (repo / "tests" / "test_app.py").write_text(
            "import unittest\nfrom app import add\n\nclass AddTests(unittest.TestCase):\n"
            "    def test_adds_numbers(self):\n        self.assertEqual(add(2, 3), 5)\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True, text=True)
        spec = root / "add_spec.md"
        spec.write_text("# Add\n## Requirements\n- Must implement add(a, b) in app.py.\n", encoding="utf-8")
        service = ProjectService(storage_root=root / "server")
        created = service.create_project(
            {
                "objective": "Implement add",
                "documents": [str(spec)],
                "repository_path": str(repo),
            }
        )
        project_id = str(created["project"]["project_id"])
        run = service.run_project(project_id, {})
        run_id = str(run["run_id"])
        run_dir = service.project_dir(project_id) / "runs" / run_id
        run["runtime_state"]["repository"]["path"] = str(repo)
        run["artifact_report"] = {"artifact_files": ["app.py"], "artifact_profile": {"name": "python_project"}}
        run["requirement_coverage"] = {
            "status": "partial",
            "missing_must_requirement_ids": ["REQ-ADD-001"],
            "partial_must_requirement_ids": [],
            "requirement_map": {
                "requirements": [
                    {
                        "id": "REQ-ADD-001",
                        "priority": "must",
                        "status": "missing",
                        "summary": "Implement add(a, b) in app.py.",
                        "related_files": ["app.py"],
                    }
                ]
            },
        }
        run["delivery_report"]["ready_for_review"] = False
        run["delivery_report"]["status"] = "needs_iteration"
        run["delivery_report"]["final_gate"]["score"] = 0.72
        service._write_json(run_dir / "run.json", run)

        fake_codex = root / ("fake-codex.cmd" if os.name == "nt" else "fake-codex")
        fake_script = root / "fake_codex.py"
        fake_script.write_text(
            "import json, pathlib, re, sys\n"
            "if '--version' in sys.argv or '-V' in sys.argv:\n"
            "    print('fake-codex 0.1')\n"
            "    raise SystemExit(0)\n"
            "repo = pathlib.Path.cwd()\n"
            "prompt = sys.stdin.read()\n"
            "match = re.search(r'\"task_id\"\\s*:\\s*\"([^\"]+)\"', prompt)\n"
            "task_id = match.group(1) if match else 'T000'\n"
            "if task_id == 'T001':\n"
            "    print(json.dumps({\n"
            "        'task_id': task_id,\n"
            "        'status': 'completed',\n"
            "        'summary': 'planned repair',\n"
            "        'files_changed': [],\n"
            "        'commands_run': [],\n"
            "        'tests_passed': ['planning evidence'],\n"
            "        'tests_failed': [],\n"
            "        'evidence': ['implementation task should edit app.py'],\n"
            "        'known_issues': [],\n"
            "        'follow_up_tasks': [],\n"
            "        'confidence': 0.95,\n"
            "    }))\n"
            "    raise SystemExit(0)\n"
            "(repo / 'app.py').write_text('def add(a, b):\\n    return a + b\\n', encoding='utf-8')\n"
            "cache = repo / '__pycache__'\n"
            "cache.mkdir(exist_ok=True)\n"
            "(cache / 'app.cpython-312.pyc').write_bytes(b'cache')\n"
            "payload = {\n"
            "    'task_id': task_id,\n"
            "    'status': 'completed',\n"
            "    'summary': 'implemented add',\n"
            "    'files_changed': ['app.py'],\n"
            "    'commands_run': [{'command': 'python -m unittest discover -s tests', 'exit_code': 0}],\n"
            "    'tests_passed': ['python -m unittest discover -s tests'],\n"
            "    'tests_failed': [],\n"
            "    'evidence': ['app.py returns a + b'],\n"
            "    'known_issues': [],\n"
            "    'follow_up_tasks': [],\n"
            "    'confidence': 0.95,\n"
            "}\n"
            "print(json.dumps(payload))\n",
            encoding="utf-8",
        )
        if os.name == "nt":
            fake_codex.write_text(f"@echo off\n\"{sys.executable}\" \"{fake_script}\" %*\n", encoding="utf-8")
        else:
            fake_codex.write_text(f"#!/bin/sh\nexec \"{sys.executable}\" \"{fake_script}\" \"$@\"\n", encoding="utf-8")
            fake_codex.chmod(0o755)

        service.start_auto_iteration(
            project_id,
            run_id,
            {
                "run": {
                    "real_codex": True,
                    "codex_executable": str(fake_codex),
                    "auto_browser_verify": False,
                    "isolate_real_run": False,
                }
            },
        )

        repair_run = service.get_run(project_id, "run_002")
        convergence = repair_run["runtime_state"]["repository"]["repair_convergence"]
        self.assertEqual(convergence["status"], "completed")
        self.assertEqual(convergence["trigger_task_id"], "T002")
        self.assertTrue(repair_run["runtime_state"]["done"])
        self.assertIn("return a + b", (repo / "app.py").read_text(encoding="utf-8"))

    def test_project_service_auto_iteration_blocks_handoff_runs(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        write_repo(repo)
        (repo / "index.html").write_text("<main>Playable artifact</main>\n", encoding="utf-8")
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        service = ProjectService(storage_root=root / "server")
        created = service.create_project(
            {
                "objective": "Add workspace support",
                "documents": [str(spec)],
                "repository_path": str(repo),
            }
        )
        project_id = str(created["project"]["project_id"])
        run = service.run_project(project_id, {})
        run_id = str(run["run_id"])
        run_dir = service.project_dir(project_id) / "runs" / run_id
        run["artifact_report"] = {"artifact_files": ["index.html"]}
        run["runtime_state"]["repository"]["path"] = str(repo)
        service._write_json(run_dir / "run.json", run)

        result = service.start_auto_iteration(project_id, run_id)

        self.assertEqual(result["status"], "blocked")
        self.assertIsNone(result["repair_run_id"])
        self.assertIn("handoff", result["auto_iteration_report"]["reason"].lower())
        self.assertTrue((run_dir / "auto_iteration_report.json").exists())

    def test_project_service_async_run_records_job_controls_and_events(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        write_repo(repo)
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        service = ProjectService(storage_root=root / "server")
        created = service.create_project(
            {
                "objective": "Add workspace support",
                "documents": [str(spec)],
                "repository": "https://github.com/example/saas-dashboard",
                "repository_path": str(repo),
            }
        )
        project_id = str(created["project"]["project_id"])

        started = service.start_run(project_id, {})
        run_id = str(started["run_id"])
        job = wait_for_job(service, project_id, run_id)

        self.assertEqual(job["status"], "done")
        run = service.get_run(project_id, run_id)
        self.assertEqual(run["status"], "done")
        events = service.get_run_events(project_id, run_id)
        event_types = {str(event.get("type", "")) for event in events["events"]}
        self.assertIn("queued", event_types)
        self.assertIn("running", event_types)
        self.assertIn("done", event_types)

    def test_job_store_save_uses_complete_json_payload(self) -> None:
        root = temp_root()
        store = JobStore(root)
        job = store.create("proj_test", "run_001")
        job.status = "running"

        store.save(job)
        loaded = store.load("run_001")

        self.assertEqual(loaded.status, "running")
        self.assertFalse(list((root / "runs" / "run_001").glob("job.json.tmp-*")))

    def test_job_store_save_retries_transient_replace_permission_error(self) -> None:
        root = temp_root()
        store = JobStore(root)
        job = store.create("proj_test", "run_001")
        job.status = "running"
        original_replace = Path.replace
        attempts = {"count": 0}

        def flaky_replace(path: Path, target: Path) -> Path:
            if path.name.startswith("job.json.tmp-") and attempts["count"] == 0:
                attempts["count"] += 1
                raise PermissionError("temporary lock")
            return original_replace(path, target)

        with mock.patch.object(Path, "replace", flaky_replace):
            store.save(job)

        self.assertEqual(attempts["count"], 1)
        self.assertEqual(store.load("run_001").status, "running")
        self.assertFalse(list((root / "runs" / "run_001").glob("job.json.tmp-*")))

    def test_project_service_json_helpers_are_atomic_and_retry_partial_reads(self) -> None:
        root = temp_root()
        service = ProjectService(storage_root=root / "server")
        path = root / "payload.json"
        path.write_text("", encoding="utf-8")
        original_read_text = Path.read_text
        attempts = {"count": 0}

        def flaky_read_text(target: Path, *args: object, **kwargs: object) -> str:
            if target == path and attempts["count"] == 0:
                attempts["count"] += 1
                path.write_text('{"status": "ready"}\n', encoding="utf-8")
                return ""
            return original_read_text(target, *args, **kwargs)

        with mock.patch.object(Path, "read_text", flaky_read_text):
            self.assertEqual(service._read_json(path), {"status": "ready"})

        service._write_json(path, {"status": "done"})

        self.assertEqual(service._read_json(path), {"status": "done"})
        self.assertFalse(list(root.glob("payload.json.tmp-*")))

    def test_project_service_job_controller_stops_at_task_boundary(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        write_repo(repo)
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        service = ProjectService(storage_root=root / "server")
        created = service.create_project(
            {
                "objective": "Add workspace support",
                "documents": [str(spec)],
                "repository": "https://github.com/example/saas-dashboard",
                "repository_path": str(repo),
            }
        )
        project_id = str(created["project"]["project_id"])
        service.build_plan(project_id)
        record = service.load_project(project_id)
        run_id = service.next_run_id(project_id)
        store = service.job_store(project_id)
        store.create(project_id, run_id)
        store.update_control(run_id, "stop_requested", True, "Stop before execution.")

        result = service._execute_run(record, run_id, {}, controller=JobExecutionController(store, run_id))

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["runtime_state"]["blockers"][0]["id"], "B-RUN-STOPPED")
        events = service.get_run_events(project_id, run_id)
        event_types = {str(event.get("type", "")) for event in events["events"]}
        self.assertIn("stop_boundary", event_types)

    def test_project_service_resume_paused_run_starts_recovery_run(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        write_repo(repo)
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        service = ProjectService(storage_root=root / "server")
        created = service.create_project(
            {
                "objective": "Add workspace support",
                "documents": [str(spec)],
                "repository": "https://github.com/example/saas-dashboard",
                "repository_path": str(repo),
            }
        )
        project_id = str(created["project"]["project_id"])
        service.build_plan(project_id)
        record = service.load_project(project_id)
        run_id = service.next_run_id(project_id)
        store = service.job_store(project_id)
        job = store.create(project_id, run_id)
        store.update_control(run_id, "stop_requested", True, "Stop before execution.")
        result = service._execute_run(record, run_id, {}, controller=JobExecutionController(store, run_id))
        store.set_result(run_id, service.project_dir(project_id) / "runs" / run_id / "run.json", "paused")

        resumed = service.resume_run(project_id, run_id, {})
        resumed_run_id = str(resumed["resumed_run_id"])
        resumed_job = wait_for_job(service, project_id, resumed_run_id)
        resumed_run = service.get_run(project_id, resumed_run_id)

        self.assertEqual(resumed_job["status"], "done")
        self.assertEqual(resumed_run["status"], "done")
        self.assertEqual(resumed_run["recovery"]["checkpoint"]["source_run_id"], run_id)
        self.assertTrue(resumed_run["runtime_state"]["done"])

    def test_http_api_create_plan_run_and_fetch_report(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        write_repo(repo)
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        service = ProjectService(storage_root=root / "server")
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        conn = http.client.HTTPConnection(host, port, timeout=30)
        try:
            created = request_json(
                conn,
                "POST",
                "/projects",
                {
                    "objective": "Add workspace support",
                    "documents": [str(spec)],
                    "repository": "https://github.com/example/saas-dashboard",
                    "repository_path": str(repo),
                },
                expected=201,
            )
            project_id = str(created["project"]["project_id"])
            planned = request_json(conn, "POST", f"/projects/{project_id}/plan", {}, expected=200)
            self.assertEqual(planned["project"]["status"], "planned")

            run = request_json(conn, "POST", f"/projects/{project_id}/runs", {}, expected=201)
            self.assertEqual(run["status"], "done")

            fetched = request_json(conn, "GET", f"/projects/{project_id}/runs/{run['run_id']}", expected=200)
            self.assertEqual(fetched["runtime_state"]["done"], True)
            events = request_json(conn, "GET", f"/projects/{project_id}/runs/{run['run_id']}/events", expected=200)
            self.assertGreater(len(events["events"]), 0)
        finally:
            conn.close()
            server.shutdown()
            thread.join(timeout=10)
            server.server_close()

    def test_http_api_delete_project_removes_history_and_local_folder(self) -> None:
        root = temp_root()
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        service = ProjectService(storage_root=root / "server")
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        conn = http.client.HTTPConnection(host, port, timeout=30)
        try:
            created = request_json(
                conn,
                "POST",
                "/projects",
                {
                    "objective": "Delete through HTTP",
                    "documents": [str(spec)],
                },
                expected=201,
            )
            project_id = str(created["project"]["project_id"])
            project_dir = service.project_dir(project_id)
            self.assertTrue(project_dir.exists())

            deleted = request_json(conn, "DELETE", f"/projects/{project_id}", expected=200)

            self.assertEqual(deleted["status"], "deleted")
            self.assertEqual(deleted["project_id"], project_id)
            self.assertFalse(project_dir.exists())
            history = request_json(conn, "GET", "/projects", expected=200)
            self.assertEqual(history["projects"], [])
            missing = request_json(conn, "GET", f"/projects/{project_id}", expected=404)
            self.assertEqual(missing["error"]["code"], "project_not_found")
        finally:
            conn.close()
            server.shutdown()
            thread.join(timeout=10)
            server.server_close()

    def test_http_api_serves_run_artifact_manifest_and_content(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        write_repo(repo)
        (repo / "index.html").write_text(
            '<main>HTTP artifact</main><link rel="stylesheet" href="src/styles.css"><script src="src/main.js"></script>\n',
            encoding="utf-8",
        )
        (repo / "src" / "main.js").write_text("window.__artifactLoaded = true;\n", encoding="utf-8")
        (repo / "src" / "styles.css").write_text("main { color: red; }\n", encoding="utf-8")
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        service = ProjectService(storage_root=root / "server")
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        conn = http.client.HTTPConnection(host, port, timeout=30)
        try:
            created = request_json(
                conn,
                "POST",
                "/projects",
                {
                    "objective": "Add workspace support",
                    "documents": [str(spec)],
                    "repository_path": str(repo),
                },
                expected=201,
            )
            project_id = str(created["project"]["project_id"])
            run = request_json(conn, "POST", f"/projects/{project_id}/runs", {}, expected=201)
            run_id = str(run["run_id"])
            run_dir = service.project_dir(project_id) / "runs" / run_id
            stored = service.get_run(project_id, run_id)
            stored["artifact_report"] = {"artifact_files": ["index.html"]}
            stored["runtime_state"]["repository"]["path"] = str(repo)
            service._write_json(run_dir / "run.json", stored)

            manifest = request_json(conn, "GET", f"/projects/{project_id}/runs/{run_id}/artifacts", expected=200)
            self.assertGreaterEqual(len(manifest["items"]), 1)
            artifact_id = next(str(item["artifact_id"]) for item in manifest["items"] if item["kind"] == "artifact_file")
            conn.request("GET", f"/projects/{project_id}/runs/{run_id}/artifacts/{artifact_id}")
            response = conn.getresponse()
            body = response.read().decode("utf-8")

            self.assertEqual(response.status, 200)
            self.assertIn("text/html", response.getheader("Content-Type", ""))
            self.assertIn("HTTP artifact", body)

            preview = request_text(conn, "GET", f"/projects/{project_id}/runs/{run_id}/preview/index.html", expected=200)
            self.assertIn("src/main.js", preview)
            script = request_text(conn, "GET", f"/projects/{project_id}/runs/{run_id}/preview/src/main.js", expected=200)
            style = request_text(conn, "GET", f"/projects/{project_id}/runs/{run_id}/preview/src/styles.css", expected=200)
            self.assertIn("__artifactLoaded", script)
            self.assertIn("color: red", style)
            blocked = request_json(conn, "GET", f"/projects/{project_id}/runs/{run_id}/preview/../project.json", expected=404)
            self.assertEqual(blocked["error"]["code"], "preview_file_not_found")
        finally:
            conn.close()
            server.shutdown()
            thread.join(timeout=10)
            server.server_close()

    def test_http_api_serves_run_status_and_open_folder_action(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        write_repo(repo)
        (repo / "index.html").write_text("<main>HTTP result</main>\n", encoding="utf-8")
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        opened: list[Path] = []
        service = ProjectService(storage_root=root / "server", folder_opener=lambda path: opened.append(path))
        created = service.create_project(
            {
                "objective": "Add workspace support",
                "documents": [str(spec)],
                "repository_path": str(repo),
            }
        )
        project_id = str(created["project"]["project_id"])
        run = service.run_project(project_id, {})
        run_id = str(run["run_id"])
        run_dir = service.project_dir(project_id) / "runs" / run_id
        stored = service.get_run(project_id, run_id)
        stored["artifact_report"] = {"artifact_files": ["index.html"]}
        stored["runtime_state"]["repository"]["path"] = str(repo)
        service._write_json(run_dir / "run.json", stored)

        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        conn = http.client.HTTPConnection(host, port, timeout=30)
        try:
            status = request_json(conn, "GET", f"/projects/{project_id}/runs/{run_id}/status", expected=200)
            self.assertEqual(status["phase"], "ready")
            self.assertEqual(status["progress_percent"], 100)
            self.assertEqual(status["central_review"]["decision"], "handoff")
            self.assertTrue(any(action["id"] == "open_result" for action in status["delivery_actions"]))

            opened_result = request_json(conn, "POST", f"/projects/{project_id}/runs/{run_id}/open-folder", expected=200)
            self.assertEqual(opened_result["status"], "opened")
            self.assertEqual(opened, [repo.resolve()])
        finally:
            conn.close()
            server.shutdown()
            thread.join(timeout=10)
            server.server_close()

    def test_http_api_reopens_with_feedback(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        write_repo(repo)
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        feedback = root / "feedback.md"
        feedback.write_text("# Feedback\n\n## Feedback\n- Bug: dashboard create flow fails in src/pages/dashboard.tsx.\n", encoding="utf-8")
        service = ProjectService(storage_root=root / "server")
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        conn = http.client.HTTPConnection(host, port, timeout=30)
        try:
            created = request_json(
                conn,
                "POST",
                "/projects",
                {
                    "objective": "Add workspace support",
                    "documents": [str(spec)],
                    "repository_path": str(repo),
                },
                expected=201,
            )
            project_id = str(created["project"]["project_id"])
            first_run = request_json(conn, "POST", f"/projects/{project_id}/runs", {}, expected=201)

            reopened = request_json(
                conn,
                "POST",
                f"/projects/{project_id}/feedback/reopen",
                {
                    "source_run_id": first_run["run_id"],
                    "feedback_files": [str(feedback)],
                    "run": {"auto_browser_verify": False},
                },
                expected=201,
            )

            self.assertEqual(reopened["run_id"], "run_002")
            self.assertEqual(reopened["feedback_reopen"]["source_run_id"], "run_001")
            self.assertEqual(reopened["recovery_comparison"]["current_run_id"], "run_002")
            delivery = request_json(conn, "GET", f"/projects/{project_id}/runs/run_002/delivery", expected=200)
            self.assertEqual(delivery["latest_run_id"], "run_002")
            self.assertEqual(delivery["delivery_evidence"]["recovery_comparison"]["current_run_id"], "run_002")
        finally:
            conn.close()
            server.shutdown()
            thread.join(timeout=10)
            server.server_close()

    def test_http_api_auto_iteration_preview_and_start(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        write_repo(repo)
        (repo / "index.html").write_text("<main>Playable artifact</main>\n", encoding="utf-8")
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        service = ProjectService(storage_root=root / "server")
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        conn = http.client.HTTPConnection(host, port, timeout=30)
        try:
            created = request_json(
                conn,
                "POST",
                "/projects",
                {
                    "objective": "Add workspace support",
                    "documents": [str(spec)],
                    "repository_path": str(repo),
                },
                expected=201,
            )
            project_id = str(created["project"]["project_id"])
            first_run = request_json(conn, "POST", f"/projects/{project_id}/runs", {}, expected=201)
            run_id = str(first_run["run_id"])
            run_dir = service.project_dir(project_id) / "runs" / run_id
            stored = service.get_run(project_id, run_id)
            stored["artifact_report"] = {"artifact_files": ["index.html"]}
            stored["runtime_state"]["repository"]["path"] = str(repo)
            stored["delivery_report"]["ready_for_review"] = False
            stored["delivery_report"]["status"] = "needs_iteration"
            stored["delivery_report"]["final_gate"]["score"] = 0.8
            stored["delivery_report"]["final_gate"]["dimension_scores"] = {"test_health": 0.6}
            service._write_json(run_dir / "run.json", stored)

            delivery_preview = request_json(conn, "GET", f"/projects/{project_id}/runs/{run_id}/delivery", expected=200)
            self.assertEqual(delivery_preview["central_review"]["decision"], "iterate")
            self.assertEqual(delivery_preview["auto_iteration"]["status"], "skipped")
            self.assertEqual(delivery_preview["repair_plan"]["status"], "ready")
            self.assertTrue(delivery_preview["repair_plan"]["auto_execution"]["allowed"])
            self.assertFalse((run_dir / "repair_plan.json").exists())

            preview = request_json(conn, "GET", f"/projects/{project_id}/runs/{run_id}/auto-iteration", expected=200)
            self.assertTrue(preview["auto_execution_available"])
            self.assertEqual(preview["repair_plan"]["status"], "ready")

            started = request_json(
                conn,
                "POST",
                f"/projects/{project_id}/runs/{run_id}/auto-iteration",
                {"async": True, "run": {"auto_browser_verify": False}},
                expected=201,
            )

            self.assertEqual(started["status"], "started")
            self.assertEqual(started["repair_run_id"], "run_002")
            self.assertEqual(started["job"]["status"], "queued")
            self.assertEqual(wait_for_http_job(conn, project_id, "run_002")["status"], "done")
            delivery = request_json(conn, "GET", f"/projects/{project_id}/runs/{run_id}/delivery", expected=200)
            self.assertEqual(delivery["auto_iteration"]["status"], "started")
        finally:
            conn.close()
            server.shutdown()
            thread.join(timeout=10)
            server.server_close()

    def test_project_service_github_inspect_without_prepare_returns_intake(self) -> None:
        root = temp_root()
        service = ProjectService(storage_root=root / "server")
        created = service.create_project(
            {
                "objective": "Add workspace support",
                "primary_input_mode": "document_driven",
                "repository": "https://github.com/example/saas-dashboard",
            }
        )
        project_id = str(created["project"]["project_id"])

        inspected = service.inspect_github(project_id, {"prepare": False})

        self.assertEqual(inspected["brief"]["repository"]["owner"], "example")
        self.assertEqual(created["project"]["repository_path"], "")
        self.assertEqual(inspected["project"]["repository_path"], "")
        self.assertEqual(inspected["brief"]["repository"]["local_path"], "")
        self.assertFalse((service.project_dir(project_id) / "repo").exists())

    def test_project_service_github_prepare_binds_managed_checkout_path(self) -> None:
        root = temp_root()
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        service = ProjectService(storage_root=root / "server")
        payload = {
            "objective": "Prepare public GitHub source",
            "documents": [str(spec)],
            "repository_url": "https://github.com/example/saas-dashboard",
            "source_mode": "github_public",
            "prepare_repository": True,
            "output_dir": str(root / "github-run"),
        }

        preflight = service.preflight_unified_request(payload)
        normalized = service._normalize_service_unified_payload(payload)
        created = service.create_project(normalized)
        project_id = str(created["project"]["project_id"])

        self.assertEqual(preflight["status"], "passed")
        self.assertEqual(
            Path(str(created["project"]["repository_path"])).resolve(),
            (root / "server" / "projects" / project_id / "repo").resolve(),
        )
        self.assertEqual(created["brief"]["repository"]["local_path"], created["project"]["repository_path"])

    def test_http_api_async_run_and_controls(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        write_repo(repo)
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        service = ProjectService(storage_root=root / "server")
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        conn = http.client.HTTPConnection(host, port, timeout=30)
        try:
            created = request_json(
                conn,
                "POST",
                "/projects",
                {
                    "objective": "Add workspace support",
                    "documents": [str(spec)],
                    "repository": "https://github.com/example/saas-dashboard",
                    "repository_path": str(repo),
                },
                expected=201,
            )
            project_id = str(created["project"]["project_id"])
            started = request_json(conn, "POST", f"/projects/{project_id}/runs", {"async": True}, expected=202)
            run_id = str(started["run_id"])
            request_json(conn, "POST", f"/projects/{project_id}/runs/{run_id}/pause", {}, expected=200)
            paused = wait_for_http_job_status(conn, project_id, run_id, {"paused", "done"})
            if paused["status"] == "paused":
                resumed = request_json(conn, "POST", f"/projects/{project_id}/runs/{run_id}/resume", {}, expected=200)
                self.assertIn("resumed_run_id", resumed)
                source_job = request_json(conn, "GET", f"/projects/{project_id}/runs/{run_id}/job", expected=200)
                self.assertEqual(source_job["status"], "resumed")
                resumed_job = wait_for_http_job(conn, project_id, str(resumed["resumed_run_id"]))
                self.assertIn(resumed_job["status"], {"done", "blocked"})
            else:
                job = wait_for_http_job(conn, project_id, run_id)
                self.assertEqual(job["status"], "done")
            events = request_json(conn, "GET", f"/projects/{project_id}/runs/{run_id}/events", expected=200)
            self.assertGreater(len(events["events"]), 0)
        finally:
            conn.close()
            server.shutdown()
            thread.join(timeout=10)
            server.server_close()

    def test_http_api_accepts_multipart_file_upload(self) -> None:
        root = temp_root()
        service = ProjectService(storage_root=root / "server")
        created = service.create_project(
            {
                "objective": "Add workspace support",
                "primary_input_mode": "document_driven",
            }
        )
        project_id = str(created["project"]["project_id"])
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        conn = http.client.HTTPConnection(host, port, timeout=30)
        try:
            boundary = "----alchemy-test-boundary"
            body = multipart_body(
                boundary,
                fields={"role": "primary_requirements", "required": "true"},
                files={
                    "file": (
                        "workspace_spec.md",
                        b"# Workspace Feature\n- Must add workspace support.\n",
                        "text/markdown",
                    )
                },
            )
            conn.request(
                "POST",
                f"/projects/{project_id}/files",
                body=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
            response = conn.getresponse()
            data = json.loads(response.read().decode("utf-8"))
            if response.status != 200:
                raise AssertionError(f"Expected 200, got {response.status}: {data}")

            self.assertEqual(data["project"]["status"], "intake_ready")
            uploaded = data["uploaded_files"][0]
            self.assertEqual(uploaded["name"], "workspace_spec.md")
            self.assertTrue(Path(uploaded["path"]).exists())
            self.assertEqual(data["brief"]["documents"][0]["name"], "workspace_spec.md")
        finally:
            conn.close()
            server.shutdown()
            thread.join(timeout=10)
            server.server_close()

    def test_project_service_updates_and_deletes_uploaded_files(self) -> None:
        root = temp_root()
        service = ProjectService(storage_root=root / "server")
        created = service.create_project(
            {
                "objective": "Add workspace support",
                "primary_input_mode": "document_driven",
            }
        )
        project_id = str(created["project"]["project_id"])
        uploaded = service.upload_files(
            project_id,
            [
                {
                    "filename": "workspace_spec.md",
                    "content_type": "text/markdown",
                    "content": b"# Workspace\n- Must add workspace support.\n",
                    "role": "primary_requirements",
                }
            ],
            {},
        )
        file_id = str(uploaded["brief"]["documents"][0]["id"])
        file_path = Path(str(uploaded["brief"]["documents"][0]["path"]))

        updated = service.update_file(
            project_id,
            file_id,
            {
                "content": "# Workspace\n- Must add workspace API support.\n",
                "role": "primary_requirements",
                "required": True,
            },
        )

        self.assertEqual(updated["project"]["status"], "intake_ready")
        self.assertIn("API support", file_path.read_text(encoding="utf-8"))
        updated_file_id = str(updated["brief"]["documents"][0]["id"])

        deleted = service.delete_file(project_id, updated_file_id)

        self.assertFalse(file_path.exists())
        self.assertEqual(deleted["project"]["documents"], [])
        self.assertEqual(deleted["project"]["status"], "intake_blocked")
        blocker_codes = {blocker["code"] for blocker in deleted["brief"]["blockers"]}
        self.assertIn("missing_primary_document", blocker_codes)

    def test_http_api_updates_files_and_streams_sse_events(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        write_repo(repo)
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        service = ProjectService(storage_root=root / "server")
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        conn = http.client.HTTPConnection(host, port, timeout=30)
        try:
            created = request_json(
                conn,
                "POST",
                "/projects",
                {
                    "objective": "Add workspace support",
                    "primary_input_mode": "document_driven",
                    "repository_path": str(repo),
                },
                expected=201,
            )
            project_id = str(created["project"]["project_id"])
            boundary = "----alchemy-test-boundary"
            body = multipart_body(
                boundary,
                fields={"role": "primary_requirements", "required": "true"},
                files={
                    "file": (
                        "workspace_spec.md",
                        b"# Workspace\n- Must add workspace support.\n",
                        "text/markdown",
                    )
                },
            )
            conn.request(
                "POST",
                f"/projects/{project_id}/files",
                body=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
            response = conn.getresponse()
            uploaded = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, 200)
            file_id = str(uploaded["brief"]["documents"][0]["id"])

            patched = request_json(
                conn,
                "PATCH",
                f"/projects/{project_id}/files/{file_id}",
                {
                    "content": "# Workspace\n- Must add workspace API support.\n",
                    "role": "primary_requirements",
                    "required": True,
                },
                expected=200,
            )
            self.assertEqual(patched["project"]["status"], "intake_ready")

            run = request_json(conn, "POST", f"/projects/{project_id}/runs", {"async": True}, expected=202)
            run_id = str(run["run_id"])
            job = wait_for_http_job(conn, project_id, run_id)
            self.assertEqual(job["status"], "done")
            sse = request_text(conn, "GET", f"/projects/{project_id}/runs/{run_id}/events-stream?timeout=0", expected=200)

            self.assertIn("event: queued", sse)
            self.assertIn("event: done", sse)
            self.assertIn("data: ", sse)

            latest_file_id = str(patched["brief"]["documents"][0]["id"])
            deleted = request_json(conn, "DELETE", f"/projects/{project_id}/files/{latest_file_id}", expected=200)
            self.assertEqual(deleted["project"]["status"], "intake_ready")
            self.assertEqual(deleted["project"]["documents"], [])
            self.assertEqual(deleted["project"]["repository_path"], str(repo))
        finally:
            conn.close()
            server.shutdown()
            thread.join(timeout=10)
            server.server_close()

    def test_http_api_serves_console_static_assets(self) -> None:
        root = temp_root()
        service = ProjectService(storage_root=root / "server")
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        conn = http.client.HTTPConnection(host, port, timeout=30)
        try:
            html = request_text(conn, "GET", "/", expected=200)
            css = request_text(conn, "GET", "/static/styles.css", expected=200)
            js = request_text(conn, "GET", "/static/app.js", expected=200)

            self.assertIn("Alchemy Dev Agent", html)
            self.assertIn("languageEn", html)
            self.assertIn("languageZh", html)
            self.assertIn("advancedToggle", html)
            self.assertIn("advancedConfigDetails", html)
            self.assertIn("advancedRunControls", html)
            self.assertIn("progressStopRun", html)
            self.assertIn("projectWorkspacePanel", html)
            self.assertIn("newProject", html)
            self.assertIn("refreshProjectHistory", html)
            self.assertIn("activeProjectSummary", html)
            self.assertIn("projectHistory", html)
            self.assertIn("scoreExplanation", html)
            self.assertIn("deliveryActionFeedback", html)
            self.assertIn("data-i18n", html)
            self.assertIn("data-lang=\"zh\"", html)
            self.assertIn("fileSelection", html)
            self.assertIn("filePicker", html)
            self.assertIn("grid-template-areas", css)
            self.assertIn("showAdvanced", css)
            self.assertIn("projectWorkspacePanel", css)
            self.assertIn("projectHistoryCard", css)
            self.assertIn("scoreExplanation", css)
            self.assertIn("deliveryActionFeedback", css)
            self.assertIn(".sourceCard textarea", css)
            self.assertIn("body.showAdvanced .sourceCard textarea", css)
            self.assertIn("startRun", js)
            self.assertIn("const I18N", js)
            self.assertIn("setLanguage", js)
            self.assertIn("applyLanguage", js)
            self.assertIn("toggleAdvancedVisibility", js)
            self.assertIn("progressStopRun", js)
            self.assertIn("renderFileSelection", js)
            self.assertIn("loadProjectHistory", js)
            self.assertIn("beginNewProject", js)
            self.assertIn("openProjectFromHistory", js)
            self.assertIn("deleteProjectFromHistory", js)
            self.assertIn("data-delete-project", js)
            self.assertIn("message.delete_project_confirm", js)
            self.assertIn("projectHistoryDelete", css)
            self.assertIn("allDeliveryActions", js)
            self.assertIn("renderScoreExplanation", js)
            self.assertIn("给不会写代码的人用的一键生成软件工具", js)
            self.assertIn("项目工作台", js)
            self.assertIn("未选择文件", js)
            self.assertIn("realCodex", html)
            self.assertIn("id=\"realCodex\" type=\"checkbox\" checked", html)
            self.assertIn("isolateRealRun", html)
            self.assertIn("githubCiWaitSeconds", html)
            self.assertIn("githubCollectCi", html)
            self.assertIn("deliverySummary", html)
            self.assertIn("runProgressPanel", html)
            self.assertIn("progressFill", html)
            self.assertIn("roadmapProgress", html)
            self.assertIn("centralReviewProgress", html)
            self.assertIn("deliveryActions", html)
            self.assertIn("centralReviewCard", html)
            self.assertIn("readinessBadge", html)
            self.assertIn("gateScore", html)
            self.assertIn("deliveryTabs", html)
            self.assertIn("evidenceCards", html)
            self.assertIn("evidenceDetails", html)
            self.assertIn("artifactPreviews", html)
            self.assertIn("graphViz", html)
            self.assertIn("coverageViz", html)
            self.assertIn("evidenceWorkbench", html)
            self.assertIn("evidenceRoot", html)
            self.assertIn("runEvidenceIndex", html)
            self.assertIn("runEvidencePackage", html)
            self.assertIn("runEvidenceReadiness", html)
            self.assertIn("readinessOutput", html)
            self.assertIn("data-i18n=\"gate.title\"", html)
            self.assertIn("configPanel", html)
            self.assertIn("environmentBadge", html)
            self.assertIn("environmentSummary", html)
            self.assertIn("modelProvider", html)
            self.assertIn("modelModeBadge", html)
            self.assertIn("modelSummary", html)
            self.assertIn("advancedModelSettings", html)
            self.assertIn("orchestratorModel", html)
            self.assertIn("documentExpansionModel", html)
            self.assertIn("reviewerModel", html)
            self.assertIn("modelApiKeyEnv", html)
            self.assertIn("modelBaseUrl", html)
            self.assertIn("sourceCards", html)
            self.assertIn("sourceRadio", html)
            self.assertIn("documentObjective", html)
            self.assertIn("githubObjective", html)
            self.assertIn("resetSourceChoice", html)
            self.assertIn("startUnifiedRun", html)
            self.assertIn("preflightUnifiedRun", html)
            self.assertIn("prepareRepository", html)
            self.assertIn("autoBrowserVerify", html)
            self.assertIn("generateStaticCi", html)
            self.assertIn("writeNativeUiTests", html)
            self.assertIn("autoMerge", html)
            self.assertIn("reopenFeedback", html)
            self.assertIn("real_codex", js)
            self.assertIn("isolate_real_run", js)
            self.assertIn("github_ci_wait_seconds", js)
            self.assertIn("github_collect_ci", js)
            self.assertIn("source_mode", js)
            self.assertIn("model_provider", js)
            self.assertIn("model_access", js)
            self.assertIn("/environment/defaults", js)
            self.assertIn("loadEnvironmentDefaults", js)
            self.assertIn("renderModelSummary", js)
            self.assertIn("environmentReady", js)
            self.assertIn("setSourceType", js)
            self.assertIn("projectPayloadForSource", js)
            self.assertIn("expand_one_line", js)
            self.assertIn("primary_input_mode: \"document_driven\"", js)
            self.assertIn("uploadSelectedFiles", js)
            self.assertIn("/runs", js)
            self.assertIn("/runs/preflight", js)
            self.assertIn("startUnifiedRun", js)
            self.assertIn("preflightUnifiedRun", js)
            self.assertIn("prepare_repository", js)
            self.assertIn("auto_browser_verify", js)
            self.assertIn("require_browser", js)
            self.assertIn("generate_static_ci", js)
            self.assertIn("write_native_ui_tests", js)
            self.assertIn("auto_merge", js)
            self.assertIn("renderDelivery", js)
            self.assertIn("renderDeliveryChrome", js)
            self.assertIn("renderRunStatus", js)
            self.assertIn("renderRoadmapProgress", js)
            self.assertIn("roadmap_progress", js)
            self.assertIn("full_roadmap", js)
            self.assertIn("renderCentralReview", js)
            self.assertIn("central.decision.handoff", js)
            self.assertIn("renderAutoIteration", js)
            self.assertIn("startAutoIteration", js)
            self.assertIn("/auto-iteration", js)
            self.assertIn("auto_iteration.action", js)
            self.assertIn("environmentChecking", js)
            self.assertIn("config.checking", js)
            self.assertIn("async: true", js)
            self.assertIn("renderDeliveryStatusFallback", js)
            self.assertIn("isRunStoppable", js)
            self.assertIn("refreshRunStatus", js)
            self.assertIn("handleDeliveryAction", js)
            self.assertIn("fallbackDeliveryActions", js)
            self.assertIn("bestDeliveryArtifact", js)
            self.assertIn("data-delivery-url", js)
            self.assertIn("artifactItemsForDisplay", js)
            self.assertIn("isRunnableArtifact", js)
            self.assertIn("artifact.hidden_sources", js)
            self.assertIn("delivery.folder_opening", js)
            self.assertIn("delivery.folder_failed", js)
            self.assertIn("max_worker_seconds: 0", js)
            self.assertIn("${state.runId}/status", js)
            self.assertIn("data-delivery-action", js)
            self.assertIn("method || \"GET\"", js)
            self.assertIn("renderEvidence", js)
            self.assertIn("renderEvidenceDetails", js)
            self.assertIn("renderArtifactPreviews", js)
            self.assertIn("renderGraphViz", js)
            self.assertIn("renderCoverageViz", js)
            self.assertIn("setDeliveryTab", js)
            self.assertIn("runEvidenceIndex", js)
            self.assertIn("runEvidencePackage", js)
            self.assertIn("runEvidenceReadiness", js)
            self.assertIn("renderReadinessReport", js)
            self.assertIn("statusText", js)
            self.assertIn("checkLabel", js)
            self.assertIn("/evidence/index", js)
            self.assertIn("/evidence/package", js)
            self.assertIn("/evidence/readiness", js)
            self.assertIn("EventSource", js)
            self.assertIn("events-stream", js)
            self.assertIn("loadFromUrl", js)
            self.assertIn("project_id", js)
            self.assertIn("run_id", js)
            self.assertIn("${state.runId}/delivery", js)
            self.assertIn("artifact_manifest", js)
            self.assertIn("reopenWithFeedback", js)
            self.assertIn("Repair Comparison", js)
            self.assertIn("recovery_comparison", js)
            self.assertIn("repair_suggestions", js)
            self.assertIn("deliverySummary", css)
            self.assertIn("runProgressPanel", css)
            self.assertIn("progressTrack", css)
            self.assertIn("roadmapProgress", css)
            self.assertIn("deliveryActionGrid", css)
            self.assertIn("deliveryAction", css)
            self.assertIn("centralReviewCard", css)
            self.assertIn("centralReviewProgress", css)
            self.assertIn("autoIterationPrompt", css)
            self.assertIn("languageSwitch", css)
            self.assertIn("languageOption", css)
            self.assertIn("filePicker", css)
            self.assertIn("fileSelection", css)
            self.assertIn("readinessBadge", css)
            self.assertIn("gateScoreCard", css)
            self.assertIn("deliveryTabs", css)
            self.assertIn("deliveryView", css)
            self.assertIn("evidenceCards", css)
            self.assertIn("evidenceDetails", css)
            self.assertIn("evidenceWorkbench", css)
            self.assertIn("readinessOutput", css)
            self.assertIn("readinessCheck", css)
            self.assertIn("artifactPreviews", css)
            self.assertIn("artifactHint", css)
            self.assertIn("graphViz", css)
            self.assertIn("coverageViz", css)
            self.assertIn("configPanel", css)
            self.assertIn("sourceCards", css)
            self.assertIn("sourceCard", css)
            self.assertIn("environmentSummary", css)
            self.assertIn("modelConfig", css)
            self.assertIn("modelSummary", css)
            self.assertIn("advancedModelSettings", css)
        finally:
            conn.close()
            server.shutdown()
            thread.join(timeout=10)
            server.server_close()

    def test_http_api_environment_check_accepts_codex_executable(self) -> None:
        root = temp_root()
        fake_codex = root / "codex.exe"
        fake_codex.write_text("", encoding="utf-8")
        service = ProjectService(storage_root=root / "server")
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        conn = http.client.HTTPConnection(host, port, timeout=30)
        try:
            report = request_json(
                conn,
                "POST",
                "/environment/check",
                {"codex_executable": str(fake_codex)},
                expected=200,
            )

            self.assertIn(report["status"], {"ready", "blocked"})
            checks = {check["name"]: check for check in report["checks"]}
            self.assertIn("codex", checks)
        finally:
            conn.close()
            server.shutdown()
            thread.join(timeout=10)
            server.server_close()

    def test_http_api_environment_defaults_returns_detected_recommendations(self) -> None:
        root = temp_root()
        service = ProjectService(storage_root=root / "server")
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        conn = http.client.HTTPConnection(host, port, timeout=30)
        try:
            defaults = request_json(conn, "GET", "/environment/defaults", expected=200)

            self.assertEqual(defaults["schema_version"], "2.56")
            self.assertEqual(defaults["model_provider"], "codex_cli")
            self.assertEqual(defaults["recommended_mode"], "codex_cli")
            self.assertIn("codex_executable", defaults)
            self.assertIn("github_cli", defaults)
        finally:
            conn.close()
            server.shutdown()
            thread.join(timeout=10)
            server.server_close()

    def test_http_api_lists_project_history(self) -> None:
        root = temp_root()
        spec = root / "workspace_feature_spec.md"
        write_spec(spec)
        service = ProjectService(storage_root=root / "server")
        created = service.create_project({"objective": "Add workspace support", "documents": [str(spec)]})
        project_id = str(created["project"]["project_id"])
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        conn = http.client.HTTPConnection(host, port, timeout=30)
        try:
            history = request_json(conn, "GET", "/projects", expected=200)

            self.assertEqual(len(history["projects"]), 1)
            self.assertEqual(history["projects"][0]["project_id"], project_id)
            self.assertEqual(history["projects"][0]["run_count"], 0)
            self.assertIn("workspace_path", history["projects"][0])
        finally:
            conn.close()
            server.shutdown()
            thread.join(timeout=10)
            server.server_close()

    def test_project_service_environment_check_requires_browser_when_auto_verify_is_requested(self) -> None:
        root = temp_root()
        service = ProjectService(storage_root=root / "server")
        captured: dict[str, object] = {}

        class FakeReport:
            def to_dict(self) -> dict[str, object]:
                return {"status": "ready", "checks": [], "blockers": []}

        def fake_run(self, **kwargs):
            captured.update(kwargs)
            return FakeReport()

        with mock.patch("server.project_service.RealEnvironmentCheck.run", fake_run):
            report = service.check_environment(
                {
                    "codex_executable": "custom-codex",
                    "auto_browser_verify": True,
                    "model_provider": "openai",
                    "model_api_key_env": "OPENAI_API_KEY",
                    "model_base_url": "https://api.openai.com/v1",
                }
            )

        self.assertEqual(report["status"], "ready")
        self.assertEqual(captured["codex_executable"], "custom-codex")
        self.assertEqual(captured["require_browser"], True)
        self.assertEqual(captured["model_provider"], "openai")
        self.assertEqual(captured["model_api_key_env"], "OPENAI_API_KEY")
        self.assertEqual(captured["model_base_url"], "https://api.openai.com/v1")


def request_json(
    conn: http.client.HTTPConnection,
    method: str,
    path: str,
    payload: dict[str, object] | None = None,
    *,
    expected: int,
) -> dict[str, object]:
    body = json.dumps(payload or {})
    headers = {"Content-Type": "application/json"}
    conn.request(method, path, body=body if method != "GET" else None, headers=headers)
    response = conn.getresponse()
    data = response.read().decode("utf-8")
    parsed = json.loads(data)
    if response.status != expected:
        raise AssertionError(f"Expected {expected}, got {response.status}: {parsed}")
    return parsed


def request_text(conn: http.client.HTTPConnection, method: str, path: str, *, expected: int) -> str:
    conn.request(method, path)
    response = conn.getresponse()
    data = response.read().decode("utf-8")
    if response.status != expected:
        raise AssertionError(f"Expected {expected}, got {response.status}: {data}")
    return data


def wait_for_job(service: ProjectService, project_id: str, run_id: str) -> dict[str, object]:
    deadline = time.time() + 10
    while time.time() < deadline:
        job = service.get_run_job(project_id, run_id)
        if job["status"] not in {"queued", "running", "paused"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for job {run_id}")


def wait_for_http_job(conn: http.client.HTTPConnection, project_id: str, run_id: str) -> dict[str, object]:
    deadline = time.time() + 10
    while time.time() < deadline:
        job = request_json(conn, "GET", f"/projects/{project_id}/runs/{run_id}/job", expected=200)
        if job["status"] not in {"queued", "running", "paused"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for HTTP job {run_id}")


def wait_for_http_job_status(
    conn: http.client.HTTPConnection,
    project_id: str,
    run_id: str,
    statuses: set[str],
) -> dict[str, object]:
    deadline = time.time() + 10
    while time.time() < deadline:
        job = request_json(conn, "GET", f"/projects/{project_id}/runs/{run_id}/job", expected=200)
        if job["status"] in statuses:
            return job
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for HTTP job {run_id} to reach {sorted(statuses)}")


def multipart_body(
    boundary: str,
    *,
    fields: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
) -> bytes:
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    for name, (filename, content, content_type) in files.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                content,
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks)


if __name__ == "__main__":
    unittest.main()
