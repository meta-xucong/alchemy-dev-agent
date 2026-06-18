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


if __name__ == "__main__":
    unittest.main()
