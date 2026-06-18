from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from autodev import DocumentRunPipeline


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_COUNTER = 0
_TEMP_RUN_ID = str(time.time_ns())


@contextmanager
def temp_document_run_dir() -> Iterator[Path]:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    path = TEST_TMP_ROOT / f"document-run-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def write_repo(root: Path) -> None:
    (root / "src" / "api").mkdir(parents=True)
    (root / "src" / "pages").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "api" / "workspaces.ts").write_text("export const api = true;\n", encoding="utf-8")
    (root / "src" / "pages" / "dashboard.tsx").write_text("export const ui = true;\n", encoding="utf-8")
    (root / "tests" / "workspaces.test.ts").write_text("test('workspace', () => {});\n", encoding="utf-8")
    (root / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")


def write_spec(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# Workspace Feature",
                "## Requirements",
                "- Must add workspace API support in src/api/workspaces.ts.",
                "- Must add dashboard workspace switching in src/pages/dashboard.tsx.",
                "## Acceptance Criteria",
                "- Users can create a workspace.",
                "- Users can switch active workspace.",
            ]
        ),
        encoding="utf-8",
    )


class DocumentRunPipelineTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_pipeline_generates_done_report(self) -> None:
        with temp_document_run_dir() as root:
            repo = root / "repo"
            repo.mkdir()
            write_repo(repo)
            spec = root / "workspace_feature_spec.md"
            write_spec(spec)
            output = root / "run"

            result = DocumentRunPipeline().run(
                objective="Add workspace support",
                documents=[spec],
                repository_url="https://github.com/example/saas-dashboard",
                repository_path=repo,
                output_dir=output,
            )
            payload = result.to_dict()
            self.assertEqual(payload["status"], "done")
            self.assertEqual(payload["runtime_state"]["evaluation"]["reason"], "DONE condition met.")
            self.assertTrue((output / "document_run_report.json").exists())
            self.assertTrue((output / "state.json").exists())
            self.assertGreaterEqual(len(payload["worker_packages"]), 5)
            self.assertEqual(payload["project_brief"]["repository"]["visibility"], "public")
            self.assertEqual(payload["context_bundle"]["requirement_map"]["requirements"][0]["planned_task_ids"][0], "T002")
        self.assertIn("pull_request_url", payload["runtime_state"]["github"])
        self.assertEqual(payload["preflight"]["status"], "passed")

    def test_cli_outputs_done_report(self) -> None:
        with temp_document_run_dir() as root:
            repo = root / "repo"
            repo.mkdir()
            write_repo(repo)
            spec = root / "workspace_feature_spec.md"
            write_spec(spec)
            output = root / "run"

            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "autodev.document_run",
                    "--objective",
                    "Add workspace support",
                    "--document",
                    str(spec),
                    "--repository",
                    "https://github.com/example/saas-dashboard",
                    "--repository-path",
                    str(repo),
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "done")
            self.assertTrue((output / "document_run_report.json").exists())
            self.assertEqual(payload["runtime_state"]["done"], True)
            self.assertEqual(payload["preflight"]["status"], "passed")

    def test_real_codex_missing_executable_blocks_before_execution(self) -> None:
        with temp_document_run_dir() as root:
            repo = root / "repo"
            repo.mkdir()
            write_repo(repo)
            spec = root / "workspace_feature_spec.md"
            write_spec(spec)
            output = root / "run"

            result = DocumentRunPipeline().run(
                objective="Add workspace support",
                documents=[spec],
                repository_url="https://github.com/example/saas-dashboard",
                repository_path=repo,
                output_dir=output,
                real_codex=True,
                codex_executable="definitely-missing-codex-for-test",
            )
            payload = result.to_dict()

            self.assertEqual(payload["status"], "blocked")
            self.assertEqual(payload["preflight"]["status"], "blocked")
            self.assertFalse(payload["runtime_state"]["done"])
            self.assertEqual(payload["runtime_state"]["blockers"][0]["id"], "B-PREFLIGHT")
            self.assertTrue((output / "state.json").exists())


if __name__ == "__main__":
    unittest.main()
