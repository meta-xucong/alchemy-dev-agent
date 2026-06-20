from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

from autodev.benchmark_suite import BenchmarkSuite, benchmark_summary


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_RUN_ID = str(time.time_ns())
_TEMP_COUNTER = 0


def temp_root() -> Path:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    root = TEST_TMP_ROOT / f"benchmark-suite-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    root.mkdir(parents=True, exist_ok=False)
    return root


class BenchmarkSuiteTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_benchmark_suite_passes_with_fake_runner_outputs(self) -> None:
        root = temp_root()

        def fake_runner(args, *, cwd, capture_output, text, check):
            output = output_from_args(args)
            output.mkdir(parents=True, exist_ok=True)
            if "autodev.run" in args:
                write_json(output / "unified_run_report.json", {"status": "done", "source_mode": "local"})
                write_json(output / "document_run_report.json", {"status": "done"})
                (output / "index.html").write_text("<main>ok</main>", encoding="utf-8")
                (output / "generated_repository").mkdir(exist_ok=True)
                (output / "generated_repository" / "index.html").write_text("<main>ok</main>", encoding="utf-8")
            elif "autodev.real_unified_delivery" in args:
                write_json(
                    output / "real_unified_delivery_report.json",
                    {"status": "passed", "summary": {"failed_required_gates": []}},
                )
            elif "autodev.unified_acceptance" in args:
                write_json(output / "unified_acceptance_report.json", {"status": "passed"})
            elif "autodev.evidence_package" in args:
                write_json(output / "evidence_package_manifest.json", {"status": "passed"})
            return subprocess.CompletedProcess(args, 0, "{}", "")

        report = BenchmarkSuite(runner=fake_runner).run(output_dir=root / "out").to_dict()

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["summary"]["total"], 6)
        self.assertEqual(report["summary"]["failed"], 0)
        self.assertTrue((root / "out" / "benchmark_suite_report.json").exists())
        summary = benchmark_summary(report)
        self.assertEqual(summary["status"], "passed")

    def test_benchmark_suite_fails_when_required_check_missing(self) -> None:
        root = temp_root()

        def fake_runner(args, *, cwd, capture_output, text, check):
            output = output_from_args(args)
            output.mkdir(parents=True, exist_ok=True)
            return subprocess.CompletedProcess(args, 0, "{}", "")

        report = BenchmarkSuite(runner=fake_runner).run(
            output_dir=root / "out",
            include_unified_acceptance=False,
        ).to_dict()

        self.assertEqual(report["status"], "failed")
        self.assertGreater(report["summary"]["failed"], 0)

    def test_cli_summary_runs_lightweight_benchmark(self) -> None:
        root = temp_root()
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "autodev.benchmark_suite",
                "--output",
                str(root / "out"),
                "--skip-unified-acceptance",
                "--summary",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["summary"]["failed"], 0)
        self.assertTrue((root / "out" / "benchmark_suite_report.json").exists())


def output_from_args(args: list[str]) -> Path:
    index = args.index("--output")
    return Path(args[index + 1])


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
