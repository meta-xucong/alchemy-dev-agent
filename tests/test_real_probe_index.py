from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

from autodev.real_probe_index import RealProbeIndexer, index_summary


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_RUN_ID = str(time.time_ns())
_TEMP_COUNTER = 0


def temp_root() -> Path:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    root = TEST_TMP_ROOT / f"real-probe-index-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    root.mkdir(parents=True, exist_ok=False)
    return root


class RealProbeIndexTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_indexer_collects_known_probe_reports(self) -> None:
        root = temp_root()
        write_json(
            root / "ready" / "real_readiness_report.json",
            {
                "schema_version": "2.42",
                "status": "ready",
                "environment": {"status": "ready"},
                "request_preflights": [{"name": "local_real_pr", "status": "passed", "blockers": []}],
                "blockers": [],
            },
        )
        write_json(
            root / "worker" / "real_worker_smoke_report.json",
            {
                "schema_version": "2.43",
                "status": "passed",
                "preflight": {"status": "passed"},
                "worker_result": {"status": "completed", "files_changed": ["app.py"]},
                "verification": {"status": "passed"},
                "blockers": [],
            },
        )
        write_json(
            root / "document" / "real_document_run_smoke_report.json",
            {
                "schema_version": "2.44",
                "status": "passed",
                "preflight": {"status": "passed"},
                "document_run": {"status": "done", "worker_lifecycle_count": 3, "delivery_ready_for_review": True},
                "verification": {"status": "passed"},
                "blockers": [],
            },
        )
        write_json(
            root / "github" / "real_delivery_validation_report.json",
            {
                "status": "passed",
                "branch": "agent/alchemy-v2-46-pr-probe",
                "base_branch": "master",
                "github": {
                    "status": "pushed",
                    "branch": "agent/alchemy-v2-46-pr-probe",
                    "commit": "abc123",
                    "pull_request_url": "https://github.example/pull/7",
                    "ci_status": "passed",
                    "merge": {"status": "skipped"},
                },
                "workspace": {"status": "ready"},
                "blockers": [],
            },
        )
        write_json(
            root / "unified" / "real_unified_delivery_report.json",
            {
                "schema_version": "2.47",
                "status": "passed",
                "request": {
                    "route": "document_run",
                    "execution_mode": "dry_run",
                    "delivery_mode": "report_only",
                },
                "gates": [
                    {"name": "preflight_passed", "status": "passed", "required": True},
                    {"name": "real_github_pr_evidence", "status": "skipped", "required": False},
                ],
                "summary": {
                    "required_gates": 1,
                    "passed_required_gates": 1,
                    "failed_required_gates": [],
                },
                "blockers": [],
            },
        )
        write_json(
            root / "lifecycle" / "github_pr_lifecycle_report.json",
            {
                "schema_version": "2.48",
                "status": "passed",
                "action": "inspect",
                "selector": "3",
                "pull_request": {
                    "number": 3,
                    "url": "https://github.example/pull/3",
                    "state": "OPEN",
                    "isDraft": True,
                    "headRefName": "agent/probe",
                    "baseRefName": "master",
                },
                "checks": [{"name": "tests"}],
                "warnings": [],
                "blockers": [],
            },
        )
        write_json(
            root / "package" / "evidence_package_manifest.json",
            {
                "schema_version": "2.49",
                "status": "passed",
                "output_dir": "package",
                "source_roots": ["evidence"],
                "summary": {"file_count": 3, "blocker_count": 0, "failed_required_gates": []},
                "blockers": [],
            },
        )
        write_json(
            root / "benchmark" / "benchmark_suite_report.json",
            {
                "schema_version": "2.50",
                "status": "passed",
                "output_dir": "benchmark",
                "summary": {
                    "total": 6,
                    "passed": 6,
                    "failed": 0,
                    "failed_scenarios": [],
                },
                "blockers": [],
            },
        )
        write_json(root / "other" / "unknown.json", {"status": "ignored"})

        index = RealProbeIndexer().build(roots=[root], output_path=root / "index.json").to_dict()

        self.assertEqual(index["status"], "passed")
        self.assertEqual(index["schema_version"], "2.47")
        self.assertEqual(index["summary"]["total"], 8)
        entries = {entry["type"]: entry for entry in index["entries"]}
        self.assertEqual(entries["real_readiness"]["environment_status"], "ready")
        self.assertEqual(entries["real_worker_smoke"]["worker_status"], "completed")
        self.assertEqual(entries["real_document_run_smoke"]["worker_lifecycle_count"], 3)
        self.assertEqual(entries["real_github_pr_probe"]["github_status"], "pushed")
        self.assertEqual(entries["real_github_pr_probe"]["pull_request_url"], "https://github.example/pull/7")
        self.assertEqual(entries["real_github_pr_probe"]["ci_status"], "passed")
        self.assertEqual(entries["real_unified_delivery"]["route"], "document_run")
        self.assertEqual(entries["real_unified_delivery"]["required_gates"], 1)
        self.assertEqual(entries["real_unified_delivery"]["failed_required_gates"], [])
        self.assertEqual(entries["github_pr_lifecycle"]["action"], "inspect")
        self.assertEqual(entries["github_pr_lifecycle"]["number"], 3)
        self.assertEqual(entries["github_pr_lifecycle"]["check_count"], 1)
        self.assertEqual(entries["evidence_package"]["file_count"], 3)
        self.assertEqual(entries["evidence_package"]["package_blocker_count"], 0)
        self.assertEqual(entries["benchmark_suite"]["scenario_total"], 6)
        self.assertEqual(entries["benchmark_suite"]["scenario_failed"], 0)
        self.assertTrue((root / "index.json").exists())

    def test_indexer_reports_blocked_when_any_probe_failed(self) -> None:
        root = temp_root()
        write_json(
            root / "worker" / "real_worker_smoke_report.json",
            {
                "schema_version": "2.43",
                "status": "failed",
                "blockers": [{"id": "B"}],
            },
        )

        index = RealProbeIndexer().build(roots=[root], output_path=root / "index.json").to_dict()

        self.assertEqual(index["status"], "blocked")
        self.assertEqual(index["summary"]["blocked_or_failed"], 1)

    def test_cli_summary_outputs_compact_index(self) -> None:
        root = temp_root()
        write_json(root / "ready" / "real_readiness_report.json", {"schema_version": "2.42", "status": "ready", "blockers": []})

        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "autodev.real_probe_index",
                "--root",
                str(root),
                "--output",
                str(root / "index.json"),
                "--summary",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(len(payload["entries"]), 1)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
