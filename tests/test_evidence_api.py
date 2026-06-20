from __future__ import annotations

import http.client
import json
import shutil
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from server.api import make_handler, route_request
from server.project_service import ProjectService


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_RUN_ID = str(time.time_ns())
_TEMP_COUNTER = 0


def temp_root() -> Path:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    root = TEST_TMP_ROOT / f"evidence-api-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def request_json(
    conn: http.client.HTTPConnection,
    method: str,
    path: str,
    payload: dict[str, object] | None = None,
    *,
    expected: int,
) -> dict[str, object]:
    body = json.dumps(payload or {})
    conn.request(method, path, body=body if method != "GET" else None, headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    data = response.read().decode("utf-8")
    parsed = json.loads(data)
    if response.status != expected:
        raise AssertionError(f"Expected {expected}, got {response.status}: {parsed}")
    return parsed


class EvidenceApiTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_project_service_indexes_configured_evidence_root(self) -> None:
        root = temp_root()
        evidence_root = root / "evidence"
        write_json(
            evidence_root / "run" / "real_unified_delivery_report.json",
            {
                "schema_version": "2.47",
                "status": "passed",
                "request": {"route": "document_run", "execution_mode": "dry_run", "delivery_mode": "local"},
                "summary": {"required_gates": 2, "passed_required_gates": 2, "failed_required_gates": []},
                "gates": [
                    {"name": "preflight_passed", "status": "passed", "required": True},
                    {"name": "delivery_ready_for_review", "status": "passed", "required": True},
                ],
                "blockers": [],
            },
        )
        service = ProjectService(storage_root=root / "server", evidence_root=evidence_root)

        index = service.get_evidence_index()

        self.assertEqual(index["status"], "passed")
        self.assertEqual(index["summary"]["total"], 1)
        self.assertEqual(index["entries"][0]["type"], "real_unified_delivery")
        self.assertTrue((root / "server" / "evidence" / "real_probe_index.json").exists())

    def test_http_routes_expose_evidence_index_and_package(self) -> None:
        root = temp_root()
        evidence_root = root / "evidence"
        write_json(
            evidence_root / "github" / "github_pr_lifecycle_report.json",
            {
                "schema_version": "2.48",
                "status": "passed",
                "action": "inspect",
                "selector": "3",
                "pull_request": {"number": 3, "url": "https://github.com/example/repo/pull/3", "state": "OPEN"},
                "checks": [],
                "warnings": [],
                "blockers": [],
            },
        )
        service = ProjectService(storage_root=root / "server", evidence_root=evidence_root)

        index, index_status = route_request(service, "GET", "/evidence/index", {})
        custom_index, custom_index_status = route_request(
            service,
            "POST",
            "/evidence/index",
            {"roots": [str(evidence_root)], "output": str(root / "custom-index.json")},
        )
        package, package_status = route_request(
            service,
            "POST",
            "/evidence/package",
            {"roots": [str(evidence_root)], "output": str(root / "package")},
        )

        self.assertEqual(index_status, 200)
        self.assertEqual(index["status"], "passed")
        self.assertEqual(index["entries"][0]["type"], "github_pr_lifecycle")
        self.assertEqual(custom_index_status, 200)
        self.assertEqual(custom_index["summary"]["total"], 1)
        self.assertTrue((root / "custom-index.json").exists())
        self.assertEqual(package_status, 201)
        self.assertEqual(package["status"], "passed")
        self.assertEqual(package["summary"]["file_count"], 1)
        self.assertTrue((root / "package" / "evidence_package_manifest.json").exists())
        self.assertTrue((root / "package" / "summary.md").exists())

    def test_missing_evidence_package_root_returns_blocked_manifest(self) -> None:
        root = temp_root()
        service = ProjectService(storage_root=root / "server", evidence_root=root / "missing")

        package = service.export_evidence_package()

        self.assertEqual(package["status"], "blocked")
        self.assertEqual(package["summary"]["file_count"], 0)
        self.assertEqual(package["blockers"][0]["id"], "B-EVIDENCE-PACKAGE-MISSING-ROOT")
        self.assertTrue((root / "server" / "evidence_package" / "evidence_package_manifest.json").exists())

    def test_http_server_serves_evidence_api(self) -> None:
        root = temp_root()
        evidence_root = root / "evidence"
        write_json(
            evidence_root / "benchmark" / "benchmark_suite_report.json",
            {
                "schema_version": "2.50",
                "status": "passed",
                "summary": {"total": 1, "passed": 1, "failed": 0, "failed_scenarios": []},
                "scenarios": [{"name": "one_line_cli", "status": "passed"}],
                "blockers": [],
            },
        )
        service = ProjectService(storage_root=root / "server", evidence_root=evidence_root)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        try:
            index = request_json(conn, "GET", "/evidence/index", expected=200)
            package = request_json(
                conn,
                "POST",
                "/evidence/package",
                {"output": str(root / "http-package")},
                expected=201,
            )
            self.assertEqual(index["entries"][0]["type"], "benchmark_suite")
            self.assertEqual(package["summary"]["file_count"], 1)
        finally:
            conn.close()
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()


if __name__ == "__main__":
    unittest.main()
