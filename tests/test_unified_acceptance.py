from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

from autodev.unified_acceptance import UnifiedAcceptanceHarness
from server.project_service import ProjectService


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_RUN_ID = str(time.time_ns())
_TEMP_COUNTER = 0


def temp_root() -> Path:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    root = TEST_TMP_ROOT / f"unified-acceptance-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    root.mkdir(parents=True, exist_ok=False)
    return root


class UnifiedAcceptanceTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_harness_passes_all_unified_scenarios(self) -> None:
        root = temp_root()

        result = UnifiedAcceptanceHarness().run(output_dir=root)
        payload = result.to_dict()

        self.assertEqual(payload["status"], "passed")
        scenarios = {scenario["name"]: scenario for scenario in payload["scenarios"]}
        self.assertEqual(set(scenarios), {"one_line_fallback", "document_only_generated_repository", "local_repository_package", "github_url_dry_run_metadata"})
        self.assertTrue(all(scenario["status"] == "passed" for scenario in scenarios.values()))
        self.assertTrue((root / "unified_acceptance_report.json").exists())
        github_checks = {check["name"]: check for check in scenarios["github_url_dry_run_metadata"]["checks"]}
        self.assertTrue(github_checks["unprepared_github_warning"]["passed"])

    def test_cli_outputs_unified_acceptance_report(self) -> None:
        root = temp_root()

        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "autodev.unified_acceptance",
                "--output",
                str(root),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "passed")
        self.assertTrue((root / "unified_acceptance_report.json").exists())

    def test_service_one_line_unified_run_generates_artifact(self) -> None:
        root = temp_root()
        service = ProjectService(storage_root=root / "server")

        started = service.run_unified_request({"objective": "Build a small retro platform game", "async": False})
        project_id = str(started["project_id"])
        run_id = str(started["run_id"])
        run = service.get_run(project_id, run_id)
        manifest = service.get_run_artifacts(project_id, run_id)

        self.assertEqual(started["route"], "one_line_fallback")
        self.assertEqual(started["status"], "done")
        self.assertEqual(run["status"], "done")
        self.assertTrue(any(str(item["path"]).replace("\\", "/").endswith("index.html") for item in manifest["items"]))


if __name__ == "__main__":
    unittest.main()
