from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

from autodev.evidence_readiness import EvidenceReadinessGate, readiness_summary


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_RUN_ID = str(time.time_ns())
_TEMP_COUNTER = 0


def temp_root() -> Path:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    root = TEST_TMP_ROOT / f"evidence-readiness-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    root.mkdir(parents=True, exist_ok=False)
    return root


class EvidenceReadinessTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_readiness_gate_reports_ready_for_complete_evidence(self) -> None:
        root = temp_root()
        reports = write_ready_reports(root)

        report = EvidenceReadinessGate().evaluate(
            evidence_index=reports["index"],
            evidence_package=reports["package"],
            benchmark_regression=reports["regression"],
            output_dir=root / "out",
        ).to_dict()

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["summary"]["blocker_count"], 0)
        self.assertEqual(report["summary"]["failed_checks"], [])
        self.assertTrue((root / "out" / "evidence_readiness_report.json").exists())

    def test_readiness_gate_blocks_failed_index_and_package_blockers(self) -> None:
        root = temp_root()
        index = root / "real_probe_index.json"
        package = root / "evidence_package_manifest.json"
        write_json(index, {"status": "blocked", "summary": {"total": 1, "blocked_or_failed": 1}, "blockers": []})
        write_json(package, {"status": "blocked", "summary": {"file_count": 0, "blocker_count": 1}, "blockers": [{"id": "B"}]})

        report = EvidenceReadinessGate().evaluate(
            evidence_index=index,
            evidence_package=package,
            output_dir=root / "out",
        ).to_dict()

        self.assertEqual(report["status"], "blocked")
        blocker_ids = {item["id"] for item in report["blockers"]}
        self.assertIn("B-EVIDENCE-READINESS-CHECK", blocker_ids)
        self.assertIn("B-EVIDENCE-READINESS-INPUT-BLOCKER", blocker_ids)

    def test_readiness_gate_blocks_missing_input(self) -> None:
        root = temp_root()
        package = root / "evidence_package_manifest.json"
        write_json(package, {"status": "passed", "summary": {"file_count": 1, "blocker_count": 0}, "blockers": []})

        report = EvidenceReadinessGate().evaluate(
            evidence_index=root / "missing.json",
            evidence_package=package,
            output_dir=root / "out",
        ).to_dict()

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["blockers"][0]["id"], "B-EVIDENCE-READINESS-CHECK")
        self.assertTrue(any(item["id"] == "B-EVIDENCE-READINESS-MISSING-INPUT" for item in report["blockers"]))

    def test_cli_summary_outputs_ready_report(self) -> None:
        root = temp_root()
        reports = write_ready_reports(root)

        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "autodev.evidence_readiness",
                "--evidence-index",
                str(reports["index"]),
                "--evidence-package",
                str(reports["package"]),
                "--benchmark-regression",
                str(reports["regression"]),
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
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(readiness_summary(payload)["status"], "ready")


def write_ready_reports(root: Path) -> dict[str, Path]:
    index = root / "real_probe_index.json"
    package = root / "evidence_package_manifest.json"
    regression = root / "benchmark_regression_report.json"
    write_json(
        index,
        {
            "status": "passed",
            "summary": {"total": 3, "passed": 3, "blocked_or_failed": 0},
            "entries": [{"type": "benchmark_suite", "status": "passed"}],
            "blockers": [],
        },
    )
    write_json(
        package,
        {
            "status": "passed",
            "summary": {"file_count": 2, "blocker_count": 0, "failed_required_gates": []},
            "files": [{"name": "benchmark_suite_report.json"}],
            "blockers": [],
        },
    )
    write_json(
        regression,
        {
            "status": "passed",
            "summary": {"new_failures": [], "missing_baseline_passes": []},
            "blockers": [],
        },
    )
    return {"index": index, "package": package, "regression": regression}


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
