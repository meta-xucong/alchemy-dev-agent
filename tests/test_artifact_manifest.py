from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from autodev.artifact_manifest import build_artifact_manifest, resolve_artifact_content


class ArtifactManifestTests(unittest.TestCase):
    def test_manifest_collects_only_reported_delivery_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            project_dir = root / "server" / "projects" / "proj_demo"
            run_dir = project_dir / "runs" / "run_001"
            repo = root / "repo"
            generated_tests = run_dir / "generated_tests" / "playwright"
            (repo / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
            generated_tests.mkdir(parents=True, exist_ok=True)
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "browser_initial.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            (generated_tests / "alchemy_acceptance.spec.ts").write_text("test('acceptance', async () => {});\n", encoding="utf-8")
            (repo / "index.html").write_text("<main>Demo</main>\n", encoding="utf-8")
            (repo / ".github" / "workflows" / "alchemy-static-checks.yml").write_text("name: checks\n", encoding="utf-8")

            run = {
                "artifact_report": {
                    "browser_verification": {"screenshots": {"initial": str(run_dir / "browser_initial.png")}},
                    "native_ui_tests": {"files": [str(generated_tests / "alchemy_acceptance.spec.ts")]},
                    "artifact_files": ["index.html"],
                },
                "generated_ci": {
                    "status": "generated",
                    "workflow_path": ".github/workflows/alchemy-static-checks.yml",
                },
                "runtime_state": {"repository": {"path": str(repo)}},
            }

            manifest = build_artifact_manifest(
                project_id="proj_demo",
                run_id="run_001",
                run=run,
                project_dir=project_dir,
                repository_path=repo,
            )

            items = manifest["items"]
            self.assertEqual(len(items), 4)
            self.assertEqual({item["kind"] for item in items}, {"screenshot", "native_ui_test", "artifact_file", "generated_ci"})
            self.assertTrue(all("_absolute_path" not in item for item in items))
            self.assertTrue(all(str(item["url"]).startswith("/projects/proj_demo/runs/run_001/artifacts/") for item in items))
            self.assertIn("image/png", [item["media_type"] for item in items])
            self.assertIn("text/plain; charset=utf-8", [item["media_type"] for item in items])

            artifact_id = next(item["artifact_id"] for item in items if item["kind"] == "artifact_file")
            content = resolve_artifact_content(
                project_id="proj_demo",
                run_id="run_001",
                artifact_id=str(artifact_id),
                run=run,
                project_dir=project_dir,
                repository_path=repo,
            )
            self.assertIsNotNone(content)
            self.assertEqual(content.data.decode("utf-8").strip(), "<main>Demo</main>")

    def test_manifest_rejects_reported_files_outside_allowed_roots(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            project_dir = root / "server" / "projects" / "proj_demo"
            run_dir = project_dir / "runs" / "run_001"
            outside = root / "outside.txt"
            run_dir.mkdir(parents=True, exist_ok=True)
            outside.parent.mkdir(parents=True, exist_ok=True)
            outside.write_text("secret\n", encoding="utf-8")
            run = {
                "artifact_report": {
                    "browser_verification": {"screenshots": {"outside": str(outside)}},
                }
            }

            manifest = build_artifact_manifest(
                project_id="proj_demo",
                run_id="run_001",
                run=run,
                project_dir=project_dir,
            )

            self.assertEqual(manifest["items"], [])


if __name__ == "__main__":
    unittest.main()
