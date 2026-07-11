from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from server.api import route_request
from server.project_service import ApiError, ProjectService
from server.remote_codex import RemoteCodexBridge


class FakeWorkerWeb:
    def __init__(self) -> None:
        self.posts: list[tuple[str, dict[str, object]]] = []

    def get_json(self, path: str) -> dict[str, object]:
        if path == "/ui/config":
            return {"logged_in": True, "display_name": "Studio Commander", "binding": {"state": "bound"}}
        if path == "/ui/tasks/task_123":
            return {
                "task": {"task_id": "task_123", "state": "running"},
                "messages": [{"role": "user", "text": "Build it"}, {"role": "assistant", "text": "Working on the first screen."}],
                "progress": [{"label": "Codex is working", "state": "active"}],
                "is_terminal": False,
            }
        raise AssertionError(path)

    def post_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        self.posts.append((path, payload))
        return {"task_id": "task_123", "state": "queued"}


class RemoteCodexBridgeTests(unittest.TestCase):
    def test_configuration_submission_and_detail_use_worker_web_contract(self) -> None:
        fake = FakeWorkerWeb()
        with tempfile.TemporaryDirectory() as directory:
            bridge = RemoteCodexBridge(Path(directory), transport_factory=lambda _url: fake)
            configured = bridge.configure({"base_url": "http://127.0.0.1:8765/"})
            self.assertTrue(configured["connected"])
            self.assertEqual(configured["base_url"], "http://127.0.0.1:8765")

            submitted = bridge.submit_conversation({"project_id": "project_1", "message": "Build it"})
            self.assertEqual(submitted["task"]["task_id"], "task_123")
            self.assertEqual(fake.posts, [("/ui/tasks", {"message": "Build it"})])

            detail = bridge.task_detail("task_123")
            self.assertEqual(detail["progress"][0]["label"], "Codex is working")

    def test_submission_stops_before_posting_when_remote_login_is_missing(self) -> None:
        class NotLoggedInWorkerWeb(FakeWorkerWeb):
            def get_json(self, path: str) -> dict[str, object]:
                if path == "/ui/config":
                    return {"logged_in": False, "binding": {"state": "not_logged_in"}}
                return super().get_json(path)

        with tempfile.TemporaryDirectory() as directory:
            fake = NotLoggedInWorkerWeb()
            bridge = RemoteCodexBridge(Path(directory), transport_factory=lambda _url: fake)
            bridge.configure({"base_url": "http://127.0.0.1:8765"})
            with self.assertRaises(ApiError) as raised:
                bridge.submit_conversation({"project_id": "project_1", "message": "Build it"})
            self.assertEqual(raised.exception.code, "remote_codex_authentication_required")
            self.assertEqual(fake.posts, [])

    def test_api_routes_keep_remote_conversations_scoped_to_a_project(self) -> None:
        class FakeBridge:
            def configuration(self):
                return {"configured": True, "connected": True, "base_url": "http://remote.test"}

            def configure(self, payload):
                return {"configured": True, "connected": True, "base_url": payload["base_url"]}

            def submit_conversation(self, payload):
                return {"project_id": payload["project_id"], "task": {"task_id": "task_123", "state": "queued"}}

            def task_detail(self, task_id):
                return {"task": {"task_id": task_id}, "messages": [], "progress": []}

        with tempfile.TemporaryDirectory() as directory:
            service = ProjectService(Path(directory) / "server")
            created = service.create_project({"objective": "A small project"})
            project_id = created["project"]["project_id"]
            service.remote_codex = FakeBridge()

            configured, _ = route_request(service, "GET", "/integrations/remote-codex", {})
            self.assertTrue(configured["connected"])
            started, status = route_request(service, "POST", f"/projects/{project_id}/remote-codex/tasks", {"message": "Build it"})
            self.assertEqual(status, 201)
            self.assertEqual(started["task"]["task_id"], "task_123")
            detail, _ = route_request(service, "GET", f"/projects/{project_id}/remote-codex/tasks/task_123", {})
            self.assertEqual(detail["task"]["task_id"], "task_123")

            service.runtime_status_probe = type("Status", (), {"local_status": lambda self: {"codex_cli": {"connected": True}}})()
            status, _ = route_request(service, "GET", "/runtime/status", {})
            self.assertTrue(status["local"]["codex_cli"]["connected"])
