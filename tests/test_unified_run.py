from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import unittest
import unittest.mock
from contextlib import contextmanager
from http import HTTPStatus
from pathlib import Path
from typing import Iterator

from autodev.unified_preflight import UnifiedRunPreflight
from autodev.unified_request import AutoDevRunRequest
from server.project_service import ApiError
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
        self.assertEqual(request.max_worker_seconds, 0)
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

    def test_request_run_payload_preserves_full_roadmap_contract(self) -> None:
        request = AutoDevRunRequest.from_mapping(
            {
                "objective": "Build every phase",
                "full_roadmap": True,
                "max_phases": 12,
                "boundary_mode": "large_refactor",
                "constraints": ["The target system must not retain token relay behavior."],
            }
        )

        payload = request.to_run_payload()

        self.assertTrue(payload["full_roadmap"])
        self.assertEqual(payload["max_phases"], 12)
        self.assertIn("The target system must not retain token relay behavior.", payload["constraints"])
        self.assertIn("Scope boundary mode: large_refactor", payload["constraints"])

    def test_request_preserves_large_refactor_boundary_mode(self) -> None:
        request = AutoDevRunRequest.from_mapping(
            {
                "objective": "Convert product into standalone billing core",
                "documents": ["spec.md"],
                "boundary_mode": "large_refactor",
            }
        )

        self.assertEqual(request.boundary_mode, "large_refactor")
        self.assertEqual(request.to_run_payload()["boundary_mode"], "large_refactor")
        self.assertIn("Scope boundary mode: large_refactor", request.to_document_run_kwargs()["constraints"])

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
            self.assertTrue((output / "generated_repository" / "src" / "main.js").exists())
            self.assertTrue((output / "generated_repository" / "src" / "styles.css").exists())
            self.assertTrue((output / "generated_repository" / "src" / "api" / "workspaces.ts").exists())
            self.assertTrue((output / "generated_repository" / "src" / "pages" / "dashboard.tsx").exists())
            html = (output / "generated_repository" / "index.html").read_text(encoding="utf-8")
            script = (output / "generated_repository" / "src" / "main.js").read_text(encoding="utf-8")
            self.assertIn("src/main.js", html)
            self.assertIn("src/styles.css", html)
            self.assertIn("window.alchemyGeneratedApp", script)
            self.assertNotIn("export const", script)

    def test_unified_cli_full_roadmap_executes_multiple_phases(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            repo = write_repo(root)
            roadmap = root / "roadmap.md"
            roadmap.write_text(
                "\n".join(
                    [
                        "# Roadmap",
                        "## V1.0 Foundation",
                        "### Requirements",
                        "- Must add foundation evidence to the app.",
                        "## V1.1 Product Feature",
                        "### Requirements",
                        "- Must add product feature evidence to the app.",
                    ]
                ),
                encoding="utf-8",
            )
            output = root / "out"

            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "autodev.run",
                    "--objective",
                    "Execute every phase in this roadmap",
                    "--document",
                    str(roadmap),
                    "--repository-path",
                    str(repo),
                    "--full-roadmap",
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
            report = json.loads((output / "unified_run_report.json").read_text(encoding="utf-8"))
            roadmap_report = json.loads((output / "full_roadmap_report.json").read_text(encoding="utf-8"))
            project_analysis = json.loads((output / "project_analysis_report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["request"]["full_roadmap"])
            self.assertGreaterEqual(len(roadmap_report["phase_records"]), 2)
            self.assertTrue(all(record["status"] == "done" for record in roadmap_report["phase_records"][:2]))
            self.assertEqual(project_analysis["start_decision"], "start")
            self.assertTrue(project_analysis["ready_to_start"])

    def test_unified_cli_preflight_only_writes_report_without_execution(self) -> None:
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
                    "Build from this development document",
                    "--document",
                    str(spec),
                    "--output",
                    str(output),
                    "--preflight-only",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            summary = json.loads(completed.stdout)
            self.assertEqual(summary["status"], "passed")
            self.assertTrue(summary["can_start"])
            report = json.loads((output / "unified_preflight_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["planned_repository_path"], str(output / "generated_repository"))
            self.assertFalse((output / "unified_run_report.json").exists())
            self.assertFalse((output / "document_run_report.json").exists())

    def test_unified_cli_preflight_blocks_bad_real_codex_executable(self) -> None:
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
                    "--real-codex",
                    "--codex-executable",
                    "alchemy-definitely-missing-codex",
                    "--output",
                    str(output),
                    "--preflight-only",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            summary = json.loads(completed.stdout)
            self.assertEqual(summary["status"], "blocked")
            report = json.loads((output / "unified_preflight_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "blocked")
            self.assertTrue(any(blocker["code"] == "preflight_codex" for blocker in report["blockers"]))

    def test_unified_preflight_blocks_one_line_real_execution(self) -> None:
        request = AutoDevRunRequest.from_mapping({"objective": "Build an app", "real_codex": True})

        report = UnifiedRunPreflight().run(request).to_dict()

        self.assertEqual(report["status"], "blocked")
        self.assertTrue(any(blocker["code"] == "one_line_real_execution_unsupported" for blocker in report["blockers"]))

    def test_unified_preflight_blocks_unprepared_github_real_execution(self) -> None:
        request = AutoDevRunRequest.from_mapping(
            {
                "objective": "Implement docs",
                "documents": [__file__],
                "repository_url": "https://github.com/example/project",
                "real_codex": True,
                "codex_executable": "alchemy-definitely-missing-codex",
            }
        )

        report = UnifiedRunPreflight().run(request).to_dict()

        self.assertEqual(report["status"], "blocked")
        self.assertTrue(any(blocker["code"] == "github_source_unprepared_for_real_execution" for blocker in report["blockers"]))

    def test_unified_preflight_prepare_github_plans_intake_checkout_path(self) -> None:
        request = AutoDevRunRequest.from_mapping(
            {
                "objective": "Implement docs",
                "documents": [__file__],
                "repository_url": "https://github.com/example/project",
                "prepare_repository": True,
            }
        )

        report = UnifiedRunPreflight().run(request).to_dict()

        self.assertEqual(report["status"], "passed")
        self.assertIn(".alchemy/projects/proj_", str(report["planned_repository_path"]))
        self.assertTrue(str(report["planned_repository_path"]).endswith("/repo") or str(report["planned_repository_path"]).endswith("\\repo"))
        self.assertTrue(any(check["name"] == "git" and check["required"] for check in report["checks"]))

    def test_unified_preflight_prepare_github_allows_future_checkout_path(self) -> None:
        request = AutoDevRunRequest.from_mapping(
            {
                "objective": "Implement docs",
                "repository_url": "https://github.com/example/project",
                "repository_path": "future/checkout/repo",
                "prepare_repository": True,
            }
        )

        report = UnifiedRunPreflight().run(request).to_dict()

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["planned_repository_path"], "future/checkout/repo")
        self.assertFalse(any(blocker["code"] == "invalid_input_path" for blocker in report["blockers"]))

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
            self.assertEqual(result["preflight"]["status"], "passed")

    def test_project_service_expands_ui_one_line_to_document_run(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            service = ProjectService(storage_root=root / "server")

            preflight = service.preflight_unified_request(
                {
                    "objective": "Build a small playable platform game",
                    "expand_one_line": True,
                    "async": False,
                }
            )
            self.assertEqual(preflight["status"], "passed")
            self.assertEqual(preflight["route"], "document_run")
            self.assertEqual(preflight["request"]["route"], "document_run")
            generated_documents = preflight["request"]["documents"]
            self.assertEqual(len(generated_documents), 1)
            self.assertTrue(Path(generated_documents[0]).exists())

            result = service.run_unified_request(
                {
                    "objective": "Build a small playable platform game",
                    "expand_one_line": True,
                    "async": False,
                }
            )

            self.assertFalse(result["async"])
            self.assertEqual(result["route"], "document_run")
            self.assertEqual(result["source_mode"], "none")
            self.assertEqual(result["project"]["primary_input_mode"], "document_driven")
            self.assertEqual(result["run"]["status"], "done")
            self.assertNotEqual(result["run"]["project_brief"]["primary_input_mode"], "one_line_fallback")
            self.assertEqual(result["preflight"]["request"]["documents"], result["project"]["documents"])

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
            self.assertEqual(result["preflight"]["status"], "passed")

    def test_http_api_exposes_unified_preflight_without_project_creation(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            repo = write_repo(root)
            spec = write_spec(root)
            service = ProjectService(storage_root=root / "server")

            result, status = route_request(
                service,
                "POST",
                "/runs/preflight",
                {
                    "objective": "Add workspace support",
                    "documents": [str(spec)],
                    "repository_path": str(repo),
                    "async": False,
                },
            )

            self.assertEqual(status, HTTPStatus.OK)
            self.assertEqual(result["status"], "passed")
            self.assertEqual(list((root / "server" / "projects").glob("*")), [])

    def test_project_service_github_preflight_uses_service_storage_root(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            service = ProjectService(storage_root=root / "server")

            result = service.preflight_unified_request(
                {
                    "objective": "Build from GitHub",
                    "repository": "https://github.com/example/repo",
                    "repository_url": "https://github.com/example/repo",
                    "source_mode": "github_public",
                    "prepare_repository": True,
                    "async": False,
                }
            )

            self.assertEqual(result["status"], "passed")
            self.assertIn(str(root / "server"), result["planned_repository_path"])
            self.assertTrue(str(result["planned_repository_path"]).endswith("repo"))

    def test_project_service_blocks_failed_unified_preflight_before_project_creation(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            repo = write_repo(root)
            spec = write_spec(root)
            service = ProjectService(storage_root=root / "server")

            with self.assertRaises(ApiError) as caught:
                service.run_unified_request(
                    {
                        "objective": "Add workspace support",
                        "documents": [str(spec)],
                        "repository_path": str(repo),
                        "real_codex": True,
                        "codex_executable": "alchemy-definitely-missing-codex",
                        "async": False,
                    }
                )

            self.assertEqual(caught.exception.code, "unified_preflight_blocked")
            self.assertEqual(list((root / "server" / "projects").glob("*")), [])

    def test_project_service_disables_real_run_isolation_for_generated_repository(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            service = ProjectService(storage_root=root / "server")
            captured: dict[str, object] = {}

            class FakeRunResult:
                def to_dict(self) -> dict[str, object]:
                    return {
                        "status": "done",
                        "project_brief": {"primary_input_mode": "document_driven"},
                        "runtime_state": {"done": True, "evaluation": {"done": True}},
                    }

            class FakePipeline:
                def run(self, **kwargs) -> FakeRunResult:
                    captured.update(kwargs)
                    return FakeRunResult()

            with unittest.mock.patch("server.project_service.DocumentRunPipeline", return_value=FakePipeline()):
                result = service.run_unified_request(
                    {
                        "objective": "Build a small playable platform game",
                        "expand_one_line": True,
                        "real_codex": True,
                        "isolate_real_run": True,
                        "async": False,
                    }
                )

            self.assertEqual(result["execution_mode"], "real_codex")
            self.assertEqual(result["route"], "document_run")
            self.assertEqual(captured["real_codex"], True)
            self.assertEqual(captured["isolate_real_run"], False)
            self.assertEqual(captured["repository_path"], None)

    def test_project_service_passes_large_refactor_boundary_mode_to_document_run(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            repo = write_repo(root)
            spec = write_spec(root)
            service = ProjectService(storage_root=root / "server")
            captured: dict[str, object] = {}

            class FakeRunResult:
                def to_dict(self) -> dict[str, object]:
                    return {
                        "status": "done",
                        "project_brief": {"primary_input_mode": "document_driven"},
                        "runtime_state": {"done": True, "evaluation": {"done": True}},
                    }

            class FakePipeline:
                def run(self, **kwargs) -> FakeRunResult:
                    captured.update(kwargs)
                    return FakeRunResult()

            with unittest.mock.patch("server.project_service.DocumentRunPipeline", return_value=FakePipeline()):
                service.run_unified_request(
                    {
                        "objective": "Refactor into standalone billing core",
                        "documents": [str(spec)],
                        "repository_path": str(repo),
                        "boundary_mode": "large_refactor",
                        "async": False,
                    }
                )

            self.assertIn("Scope boundary mode: large_refactor", captured["constraints"])

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
