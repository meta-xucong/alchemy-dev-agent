from __future__ import annotations

import http.client
import json
import shutil
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from server.api import make_handler
from server.jobs import JobExecutionController, JobStore
from server.project_service import ProjectService


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
        self.assertEqual(content.media_type, "text/plain; charset=utf-8")
        delivery = service.get_delivery(project_id)
        self.assertEqual(delivery["artifact_manifest"]["items"], manifest["items"])

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

    def test_http_api_serves_run_artifact_manifest_and_content(self) -> None:
        root = temp_root()
        repo = root / "repo"
        repo.mkdir()
        write_repo(repo)
        (repo / "index.html").write_text("<main>HTTP artifact</main>\n", encoding="utf-8")
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
            body = request_text(conn, "GET", f"/projects/{project_id}/runs/{run_id}/artifacts/{artifact_id}", expected=200)

            self.assertIn("HTTP artifact", body)
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
        self.assertNotIn("source", inspected)

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
            self.assertEqual(deleted["project"]["status"], "intake_blocked")
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
            self.assertIn("grid-template-areas", css)
            self.assertIn("startRun", js)
            self.assertIn("realCodex", html)
            self.assertIn("isolateRealRun", html)
            self.assertIn("githubCiWaitSeconds", html)
            self.assertIn("githubCollectCi", html)
            self.assertIn("deliverySummary", html)
            self.assertIn("evidenceCards", html)
            self.assertIn("evidenceDetails", html)
            self.assertIn("artifactPreviews", html)
            self.assertIn("graphViz", html)
            self.assertIn("coverageViz", html)
            self.assertIn("autoBrowserVerify", html)
            self.assertIn("generateStaticCi", html)
            self.assertIn("writeNativeUiTests", html)
            self.assertIn("autoMerge", html)
            self.assertIn("reopenFeedback", html)
            self.assertIn("real_codex", js)
            self.assertIn("isolate_real_run", js)
            self.assertIn("github_ci_wait_seconds", js)
            self.assertIn("github_collect_ci", js)
            self.assertIn("auto_browser_verify", js)
            self.assertIn("require_browser", js)
            self.assertIn("generate_static_ci", js)
            self.assertIn("write_native_ui_tests", js)
            self.assertIn("auto_merge", js)
            self.assertIn("renderDelivery", js)
            self.assertIn("renderEvidence", js)
            self.assertIn("renderEvidenceDetails", js)
            self.assertIn("renderArtifactPreviews", js)
            self.assertIn("renderGraphViz", js)
            self.assertIn("renderCoverageViz", js)
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
            self.assertIn("evidenceCards", css)
            self.assertIn("evidenceDetails", css)
            self.assertIn("artifactPreviews", css)
            self.assertIn("graphViz", css)
            self.assertIn("coverageViz", css)
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
                }
            )

        self.assertEqual(report["status"], "ready")
        self.assertEqual(captured["codex_executable"], "custom-codex")
        self.assertEqual(captured["require_browser"], True)


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
