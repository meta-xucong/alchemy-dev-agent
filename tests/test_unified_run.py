from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import unittest
from contextlib import contextmanager
from http import HTTPStatus
from pathlib import Path
from typing import Iterator

from autodev.unified_request import AutoDevRunRequest
from server.api import route_request
from server.project_service import ProjectService


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_COUNTER = 0
_TEMP_RUN_ID = str(time.time_ns())


class UnifiedRunTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_request_routes_one_line_to_fallback(self) -> None:
        request = AutoDevRunRequest.from_mapping({"objective": "Build a tiny arcade game"})

        self.assertEqual(request.route, "one_line_fallback")
        self.assertEqual(request.source_mode, "none")
        self.assertEqual(request.execution_mode, "dry_run")
        self.assertEqual(request.delivery_mode, "report_only")
        self.assertEqual(request.primary_input_mode, "one_line_fallback")
        self.assertEqual(request.validate_paths(), [])

    def test_request_routes_local_document_to_document_run(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            repo = write_repo(root)
            spec = write_spec(root)

            request = AutoDevRunRequest.from_mapping(
                {
                    "objective": "Add a scoring HUD",
                    "documents": [str(spec)],
                    "repository_path": str(repo),
                    "execution": {"mode": "dry_run"},
                    "delivery": {"mode": "local"},
                }
            )

            self.assertEqual(request.route, "document_run")
            self.assertEqual(request.source_mode, "local")
            self.assertEqual(request.delivery_mode, "local")
            self.assertEqual(request.to_project_payload()["primary_input_mode"], "document_driven")
            self.assertFalse(request.to_run_payload()["real_codex"])
            self.assertEqual(request.validate_paths(), [])

    def test_unified_cli_one_line_writes_report(self) -> None:
        with workspace_tempdir() as temp:
            output = Path(temp) / "out"

            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "autodev.run",
                    "--objective",
                    "Build a small retro platform game",
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            summary = json.loads(completed.stdout)
            self.assertEqual(summary["status"], "done")
            self.assertEqual(summary["route"], "one_line_fallback")
            report = json.loads((output / "unified_run_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["source_mode"], "none")
            self.assertTrue((output / "autodev_report.json").exists())
            self.assertTrue((output / "index.html").exists())

    def test_unified_cli_document_local_repo_writes_report(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            repo = write_repo(root)
            spec = write_spec(root)
            output = root / "out"

            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "autodev.run",
                    "--objective",
                    "Add workspace support",
                    "--document",
                    str(spec),
                    "--repository-path",
                    str(repo),
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            summary = json.loads(completed.stdout)
            self.assertEqual(summary["status"], "done")
            self.assertEqual(summary["route"], "document_run")
            self.assertEqual(summary["source_mode"], "local")
            self.assertTrue((output / "unified_run_report.json").exists())
            self.assertTrue((output / "document_run_report.json").exists())
            self.assertTrue((output / "project_brief.json").exists())
            self.assertTrue((output / "context_bundle.json").exists())
            self.assertTrue((output / "task_graph.json").exists())

    def test_unified_cli_document_only_uses_generated_repository(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            spec = write_spec(root)
            output = root / "out"

            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "autodev.run",
                    "--objective",
                    "Build the app from this development document",
                    "--document",
                    str(spec),
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            summary = json.loads(completed.stdout)
            self.assertEqual(summary["status"], "done")
            self.assertEqual(summary["route"], "document_run")
            self.assertEqual(summary["source_mode"], "none")
            self.assertEqual(summary["selected_project_profile"], "static_web_app")
            self.assertTrue((output / "generated_repository" / "index.html").exists())
            self.assertTrue((output / "generated_repository" / "src" / "api" / "workspaces.ts").exists())
            self.assertTrue((output / "generated_repository" / "src" / "pages" / "dashboard.tsx").exists())

    def test_project_service_unified_request_runs_sync(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            repo = write_repo(root)
            spec = write_spec(root)
            service = ProjectService(storage_root=root / "server")

            result = service.run_unified_request(
                {
                    "objective": "Add workspace support",
                    "documents": [str(spec)],
                    "repository_path": str(repo),
                    "async": False,
                }
            )

            self.assertFalse(result["async"])
            self.assertEqual(result["route"], "document_run")
            self.assertEqual(result["source_mode"], "local")
            self.assertEqual(result["run"]["status"], "done")
            self.assertEqual(result["status"], "done")
            self.assertIn("/events", result["events_url"])
            self.assertIn("/events-stream", result["events_stream_url"])
            self.assertIn("/delivery", result["delivery_url"])
            self.assertIn("/artifacts", result["artifact_manifest_url"])
            self.assertIn("/delivery", result["urls"]["delivery"])

    def test_http_api_exposes_unified_run_endpoint(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            repo = write_repo(root)
            spec = write_spec(root)
            service = ProjectService(storage_root=root / "server")

            result, status = route_request(
                service,
                "POST",
                "/runs",
                {
                    "objective": "Add workspace support",
                    "documents": [str(spec)],
                    "repository_path": str(repo),
                    "async": False,
                },
            )

            self.assertEqual(status, HTTPStatus.CREATED)
            self.assertEqual(result["route"], "document_run")
            self.assertEqual(result["source_mode"], "local")
            self.assertEqual(result["run"]["status"], "done")
            self.assertEqual(result["status"], "done")
            self.assertIn("/events", result["events_url"])
            self.assertIn("/events-stream", result["events_stream_url"])
            self.assertIn("/delivery", result["delivery_url"])
            self.assertIn("/artifacts", result["artifact_manifest_url"])

    def test_project_service_unified_request_starts_async_run_with_events(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            repo = write_repo(root)
            spec = write_spec(root)
            service = ProjectService(storage_root=root / "server")

            started = service.run_unified_request(
                {
                    "objective": "Add workspace support",
                    "documents": [str(spec)],
                    "repository_path": str(repo),
                    "async": True,
                }
            )
            job = wait_for_job(service, str(started["project_id"]), str(started["run_id"]), {"done"})
            events = service.get_run_events(str(started["project_id"]), str(started["run_id"]))

            self.assertTrue(started["async"])
            self.assertEqual(started["status"], "queued")
            self.assertEqual(job["status"], "done")
            self.assertTrue(any(event["type"] == "queued" for event in events["events"]))
            self.assertTrue(any(event["type"] == "done" for event in events["events"]))

    def test_project_service_unified_request_reopens_with_feedback(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            repo = write_repo(root)
            spec = write_spec(root)
            feedback = root / "feedback.md"
            feedback.write_text("- Bug: workspace switch button should update visible status.\n", encoding="utf-8")
            service = ProjectService(storage_root=root / "server")
            first = service.run_unified_request(
                {
                    "objective": "Add workspace support",
                    "documents": [str(spec)],
                    "repository_path": str(repo),
                    "async": False,
                }
            )

            reopened = service.run_unified_request(
                {
                    "project_id": first["project_id"],
                    "source_run_id": first["run_id"],
                    "feedback_files": [str(feedback)],
                    "async": False,
                }
            )

            self.assertEqual(reopened["route"], "feedback_reopen")
            self.assertEqual(reopened["run"]["feedback_reopen"]["source_run_id"], "run_001")
            self.assertEqual(reopened["run"]["feedback_reopen"]["feedback_files"], [str(feedback)])
            self.assertEqual(reopened["run"]["recovery_comparison"]["source_run_id"], "run_001")
            nodes = reopened["run"]["feedback_reopen"]["task_graph"]["nodes"]
            self.assertTrue(any(node["assigned_agent"] == "debug" for node in nodes))


def write_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    (repo / "src" / "api").mkdir(parents=True)
    (repo / "src" / "pages").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src" / "api" / "workspaces.ts").write_text("export const api = true;\n", encoding="utf-8")
    (repo / "src" / "pages" / "dashboard.tsx").write_text("export const ui = true;\n", encoding="utf-8")
    (repo / "tests" / "workspaces.test.ts").write_text("test('workspace', () => {});\n", encoding="utf-8")
    (repo / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
    return repo


def wait_for_job(service: ProjectService, project_id: str, run_id: str, expected: set[str]) -> dict[str, object]:
    deadline = time.time() + 30
    last: dict[str, object] = {}
    while time.time() < deadline:
        last = service.get_run_job(project_id, run_id)
        if str(last.get("status", "")) in expected:
            return last
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for {expected}; last job={last}")


@contextmanager
def workspace_tempdir() -> Iterator[Path]:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    path = TEST_TMP_ROOT / f"unified-run-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def write_spec(root: Path) -> Path:
    spec = root / "spec.md"
    spec.write_text(
        "\n".join(
            [
                "# Development Spec",
                "",
                "## Objective",
                "Add workspace support.",
                "",
                "## Requirements",
                "- Must add workspace API support in src/api/workspaces.ts.",
                "- Must add dashboard workspace switching in src/pages/dashboard.tsx.",
                "",
                "## Acceptance",
                "- Users can create a workspace.",
                "- Users can switch active workspace.",
            ]
        ),
        encoding="utf-8",
    )
    return spec


if __name__ == "__main__":
    unittest.main()
