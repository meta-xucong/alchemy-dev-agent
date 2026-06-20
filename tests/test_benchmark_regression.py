from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

from autodev.benchmark_regression import BenchmarkRegressionGate, regression_summary


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_RUN_ID = str(time.time_ns())
_TEMP_COUNTER = 0


def temp_root() -> Path:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    root = TEST_TMP_ROOT / f"benchmark-regression-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    root.mkdir(parents=True, exist_ok=False)
    return root


class BenchmarkRegressionTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_regression_gate_passes_when_current_preserves_baseline(self) -> None:
        root = temp_root()
        baseline = root / "baseline.json"
        current = root / "current.json"
        write_report(baseline, scenarios={"one_line_cli": "passed", "local_repository_cli": "failed"}, status="failed")
        write_report(
            current,
            scenarios={"one_line_cli": "passed", "local_repository_cli": "passed", "new_api": "passed"},
            status="passed",
        )

        report = BenchmarkRegressionGate().compare(
            baseline=baseline,
            current=current,
            output_dir=root / "out",
        ).to_dict()

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["summary"]["resolved_failures"], ["local_repository_cli"])
        self.assertEqual(report["summary"]["added_scenarios"], ["new_api"])
        self.assertEqual(report["blockers"], [])
        self.assertTrue((root / "out" / "benchmark_regression_report.json").exists())

    def test_regression_gate_blocks_scenario_regression_and_missing_baseline_pass(self) -> None:
        root = temp_root()
        baseline = root / "baseline.json"
        current = root / "current.json"
        write_report(baseline, scenarios={"one_line_cli": "passed", "document_only_cli": "passed"}, status="passed")
        write_report(current, scenarios={"one_line_cli": "failed"}, status="failed")

        report = BenchmarkRegressionGate().compare(
            baseline=baseline,
            current=current,
            output_dir=root / "out",
        ).to_dict()

        self.assertEqual(report["status"], "blocked")
        blocker_ids = {item["id"] for item in report["blockers"]}
        self.assertIn("B-BENCHMARK-CURRENT-FAILED", blocker_ids)
        self.assertIn("B-BENCHMARK-SCENARIO-REGRESSED", blocker_ids)
        self.assertIn("B-BENCHMARK-SCENARIO-MISSING", blocker_ids)
        self.assertIn("B-BENCHMARK-FAILED-COUNT-INCREASED", blocker_ids)
        self.assertEqual(report["summary"]["new_failures"], ["one_line_cli"])
        self.assertEqual(report["summary"]["missing_baseline_passes"], ["document_only_cli"])

    def test_regression_gate_blocks_missing_baseline_report(self) -> None:
        root = temp_root()
        current = root / "current.json"
        write_report(current, scenarios={"one_line_cli": "passed"}, status="passed")

        report = BenchmarkRegressionGate().compare(
            baseline=root / "missing.json",
            current=current,
            output_dir=root / "out",
        ).to_dict()

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["blockers"][0]["id"], "B-BENCHMARK-BASELINE-MISSING")

    def test_cli_summary_outputs_compact_report(self) -> None:
        root = temp_root()
        baseline = root / "baseline.json"
        current = root / "current.json"
        write_report(baseline, scenarios={"one_line_cli": "passed"}, status="passed")
        write_report(current, scenarios={"one_line_cli": "passed"}, status="passed")

        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "autodev.benchmark_regression",
                "--baseline",
                str(baseline),
                "--current",
                str(current),
                "--output",
                str(root / "out"),
                "--summary",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["blocker_count"], 0)
        self.assertEqual(regression_summary(payload)["status"], "passed")


def write_report(path: Path, *, scenarios: dict[str, str], status: str) -> None:
    payload = {
        "schema_version": "2.50",
        "status": status,
        "scenarios": [{"name": name, "status": scenario_status} for name, scenario_status in scenarios.items()],
        "summary": {
            "total": len(scenarios),
            "passed": sum(1 for scenario_status in scenarios.values() if scenario_status == "passed"),
            "failed": sum(1 for scenario_status in scenarios.values() if scenario_status != "passed"),
            "failed_scenarios": [name for name, scenario_status in scenarios.items() if scenario_status != "passed"],
        },
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
