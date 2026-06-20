from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

from autodev.evidence_package import EvidencePackageExporter, package_summary


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_RUN_ID = str(time.time_ns())
_TEMP_COUNTER = 0


def temp_root() -> Path:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    root = TEST_TMP_ROOT / f"evidence-package-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    root.mkdir(parents=True, exist_ok=False)
    return root


class EvidencePackageTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_exporter_copies_known_reports_and_writes_manifest(self) -> None:
        root = temp_root()
        evidence = root / "evidence"
        output = root / "package"
        write_json(
            evidence / "run" / "real_unified_delivery_report.json",
            {
                "schema_version": "2.47",
                "status": "passed",
                "request": {"route": "document_run", "execution_mode": "dry_run"},
                "summary": {"failed_required_gates": [], "blocker_count": 0},
                "blockers": [],
            },
        )
        write_json(evidence / "run" / "unknown.json", {"status": "ignored"})

        report = EvidencePackageExporter().export(roots=[evidence], output_dir=output).to_dict()

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["summary"]["file_count"], 1)
        self.assertEqual(report["summary"]["blocker_count"], 0)
        self.assertEqual(report["files"][0]["name"], "real_unified_delivery_report.json")
        self.assertTrue((output / "reports" / "run" / "real_unified_delivery_report.json").exists())
        self.assertFalse((output / "reports" / "run" / "unknown.json").exists())
        self.assertTrue((output / "evidence_package_manifest.json").exists())
        self.assertTrue((output / "summary.md").exists())
        self.assertIn("manifest", package_summary(report))

    def test_exporter_blocks_missing_root(self) -> None:
        root = temp_root()

        report = EvidencePackageExporter().export(roots=[root / "missing"], output_dir=root / "package").to_dict()

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["summary"]["file_count"], 0)
        self.assertEqual(report["blockers"][0]["id"], "B-EVIDENCE-PACKAGE-MISSING-ROOT")

    def test_exporter_can_include_unknown_json_when_requested(self) -> None:
        root = temp_root()
        evidence = root / "evidence"
        write_json(evidence / "custom.json", {"status": "passed"})

        report = EvidencePackageExporter().export(
            roots=[evidence],
            output_dir=root / "package",
            include_unknown_json=True,
        ).to_dict()

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["summary"]["file_count"], 1)
        self.assertEqual(report["files"][0]["name"], "custom.json")

    def test_cli_summary_outputs_package_paths(self) -> None:
        root = temp_root()
        evidence = root / "evidence"
        output = root / "package"
        write_json(evidence / "github_pr_lifecycle_report.json", {"schema_version": "2.48", "status": "passed", "blockers": []})

        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "autodev.evidence_package",
                "--root",
                str(evidence),
                "--output",
                str(output),
                "--summary",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["summary"]["file_count"], 1)
        self.assertTrue(str(payload["manifest"]).endswith("evidence_package_manifest.json"))


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
