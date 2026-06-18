from __future__ import annotations

import http.client
import json
import shutil
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from server.api import make_handler
from server.jobs import JobExecutionController
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
        events = service.get_run_events(project_id, "run_001")
        self.assertEqual(events["run_id"], "run_001")
        self.assertGreater(len(events["events"]), 0)

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
            request_json(conn, "POST", f"/projects/{project_id}/runs/{run_id}/resume", {}, expected=200)
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
                "primary_input_mode": "one_line_fallback",
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
        finally:
            conn.close()
            server.shutdown()
            thread.join(timeout=10)
            server.server_close()


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
