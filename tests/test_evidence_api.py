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


def write_benchmark_report(path: Path, scenarios: dict[str, str]) -> None:
    write_json(
        path,
        {
            "schema_version": "2.50",
            "status": "passed" if all(status == "passed" for status in scenarios.values()) else "failed",
            "scenarios": [{"name": name, "status": status} for name, status in scenarios.items()],
            "summary": {
                "total": len(scenarios),
                "passed": sum(1 for status in scenarios.values() if status == "passed"),
                "failed": sum(1 for status in scenarios.values() if status != "passed"),
                "failed_scenarios": [name for name, status in scenarios.items() if status != "passed"],
            },
        },
    )


def write_ready_evidence_reports(root: Path) -> dict[str, Path]:
    index = root / "real_probe_index.json"
    package = root / "evidence_package_manifest.json"
    regression = root / "benchmark_regression_report.json"
    write_json(
        index,
        {
            "status": "passed",
            "summary": {"total": 2, "passed": 2, "blocked_or_failed": 0},
            "entries": [{"type": "benchmark_suite", "status": "passed"}],
            "blockers": [],
        },
    )
    write_json(
        package,
        {
            "status": "passed",
            "summary": {"file_count": 2, "blocker_count": 0},
            "files": [{"name": "benchmark_suite_report.json"}],
            "blockers": [],
        },
    )
    write_json(regression, {"status": "passed", "summary": {}, "blockers": []})
    return {"index": index, "package": package, "regression": regression}


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

    def test_project_service_compares_benchmark_regression(self) -> None:
        root = temp_root()
        baseline = root / "baseline.json"
        current = root / "current.json"
        write_benchmark_report(baseline, {"one_line_cli": "passed"})
        write_benchmark_report(current, {"one_line_cli": "passed", "document_only_cli": "passed"})
        service = ProjectService(storage_root=root / "server", evidence_root=root / "evidence")

        report = service.compare_benchmark_regression({"baseline": str(baseline), "current": str(current)})

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["summary"]["added_scenarios"], ["document_only_cli"])
        self.assertTrue((root / "server" / "benchmark_regression" / "benchmark_regression_report.json").exists())

    def test_http_route_returns_blocked_benchmark_regression_report(self) -> None:
        root = temp_root()
        current = root / "current.json"
        write_benchmark_report(current, {"one_line_cli": "passed"})
        service = ProjectService(storage_root=root / "server", evidence_root=root / "evidence")

        report, status = route_request(
            service,
            "POST",
            "/evidence/benchmark-regression",
            {"baseline": str(root / "missing.json"), "current": str(current), "output": str(root / "regression")},
        )

        self.assertEqual(status, 200)
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["blockers"][0]["id"], "B-BENCHMARK-BASELINE-MISSING")
        self.assertTrue((root / "regression" / "benchmark_regression_report.json").exists())

    def test_project_service_evaluates_evidence_readiness(self) -> None:
        root = temp_root()
        reports = write_ready_evidence_reports(root)
        service = ProjectService(storage_root=root / "server", evidence_root=root / "evidence")

        report = service.evaluate_evidence_readiness(
            {
                "evidence_index": str(reports["index"]),
                "evidence_package": str(reports["package"]),
                "benchmark_regression": str(reports["regression"]),
            }
        )

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["summary"]["blocker_count"], 0)
        self.assertTrue((root / "server" / "evidence_readiness" / "evidence_readiness_report.json").exists())

    def test_http_route_returns_blocked_evidence_readiness_report(self) -> None:
        root = temp_root()
        reports = write_ready_evidence_reports(root)
        service = ProjectService(storage_root=root / "server", evidence_root=root / "evidence")

        report, status = route_request(
            service,
            "POST",
            "/evidence/readiness",
            {
                "evidence_index": str(root / "missing.json"),
                "evidence_package": str(reports["package"]),
                "output": str(root / "readiness"),
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(report["status"], "blocked")
        self.assertTrue(any(item["id"] == "B-EVIDENCE-READINESS-MISSING-INPUT" for item in report["blockers"]))
        self.assertTrue((root / "readiness" / "evidence_readiness_report.json").exists())

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
