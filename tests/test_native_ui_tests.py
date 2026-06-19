from __future__ import annotations

import json
import shutil
import time
import unittest
from pathlib import Path

from runtime.native_ui_tests import NativeUITestGenerator, detect_ui_test_framework


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_COUNTER = 0
_TEMP_RUN_ID = str(time.time_ns())


def temp_dir() -> Path:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    path = TEST_TMP_ROOT / f"native-ui-tests-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def scenario_payload() -> dict[str, object]:
    return {
        "status": "generated",
        "scenarios": [
            {
                "id": "SCN-001",
                "title": "CRUD create acceptance scenario",
                "kind": "crud",
                "required_behaviors": ["create"],
            }
        ],
    }


class NativeUITestGeneratorTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_report_only_static_web_generates_playwright_draft(self) -> None:
        root = temp_dir()
        repo = root / "repo"
        output = root / "run"
        repo.mkdir()
        (repo / "index.html").write_text("<!doctype html><main><input><button>Add</button><ul><li>Seed</li></ul></main>", encoding="utf-8")

        result = NativeUITestGenerator().generate(
            repository_path=repo,
            output_dir=output,
            acceptance_scenarios=scenario_payload(),
            artifact_profile="static_web_app",
        )

        target = output / "generated_tests" / "playwright" / "alchemy_acceptance.spec.ts"
        self.assertEqual(result.status, "generated")
        self.assertEqual(result.framework, "playwright")
        self.assertEqual(result.write_mode, "report_only")
        self.assertTrue(target.exists())
        text = target.read_text(encoding="utf-8")
        self.assertIn("type Page", text)
        self.assertIn("const scenarios: AlchemyScenario[]", text)
        self.assertIn("SCN-001", text)

    def test_static_web_write_request_stays_report_only_without_framework_dependency(self) -> None:
        root = temp_dir()
        repo = root / "repo"
        output = root / "run"
        repo.mkdir()
        (repo / "index.html").write_text("<!doctype html><main><input><button>Add</button><ul><li>Seed</li></ul></main>", encoding="utf-8")

        result = NativeUITestGenerator().generate(
            repository_path=repo,
            output_dir=output,
            acceptance_scenarios=scenario_payload(),
            artifact_profile="static_web_app",
            write_to_repository=True,
        )

        self.assertEqual(result.status, "generated")
        self.assertEqual(result.framework, "playwright")
        self.assertEqual(result.write_mode, "report_only")
        self.assertTrue((output / "generated_tests" / "playwright" / "alchemy_acceptance.spec.ts").exists())
        self.assertFalse((repo / "tests" / "alchemy_acceptance.spec.ts").exists())
        self.assertIn("Repository write skipped", " ".join(result.evidence))

    def test_detects_playwright_and_can_write_repository_file(self) -> None:
        root = temp_dir()
        repo = root / "repo"
        output = root / "run"
        repo.mkdir()
        (repo / "package.json").write_text(
            json.dumps({"devDependencies": {"@playwright/test": "^1.0.0"}}),
            encoding="utf-8",
        )

        framework, evidence = detect_ui_test_framework(repo)
        result = NativeUITestGenerator().generate(
            repository_path=repo,
            output_dir=output,
            acceptance_scenarios=scenario_payload(),
            write_to_repository=True,
        )

        target = repo / "tests" / "alchemy_acceptance.spec.ts"
        self.assertEqual(framework, "playwright")
        self.assertTrue(evidence)
        self.assertEqual(result.write_mode, "repository")
        self.assertEqual(result.target_path, "tests/alchemy_acceptance.spec.ts")
        self.assertTrue(target.exists())

    def test_detects_playwright_from_script_value(self) -> None:
        root = temp_dir()
        repo = root / "repo"
        repo.mkdir()
        (repo / "package.json").write_text(
            json.dumps({"scripts": {"e2e": "playwright test"}}),
            encoding="utf-8",
        )

        framework, evidence = detect_ui_test_framework(repo)

        self.assertEqual(framework, "playwright")
        self.assertTrue(evidence)

    def test_detects_cypress_and_can_write_repository_file(self) -> None:
        root = temp_dir()
        repo = root / "repo"
        output = root / "run"
        repo.mkdir()
        (repo / "cypress.config.js").write_text("module.exports = {}\n", encoding="utf-8")

        framework, evidence = detect_ui_test_framework(repo)
        result = NativeUITestGenerator().generate(
            repository_path=repo,
            output_dir=output,
            acceptance_scenarios=scenario_payload(),
            write_to_repository=True,
        )

        target = repo / "cypress" / "e2e" / "alchemy_acceptance.cy.js"
        self.assertEqual(framework, "cypress")
        self.assertTrue(evidence)
        self.assertEqual(result.write_mode, "repository")
        self.assertEqual(result.target_path, "cypress/e2e/alchemy_acceptance.cy.js")
        self.assertTrue(target.exists())
        self.assertIn("cy.visit('/')", target.read_text(encoding="utf-8"))

    def test_skips_without_scenarios(self) -> None:
        root = temp_dir()
        repo = root / "repo"
        output = root / "run"
        repo.mkdir()

        result = NativeUITestGenerator().generate(
            repository_path=repo,
            output_dir=output,
            acceptance_scenarios={"status": "skipped"},
            artifact_profile="static_web_app",
        )

        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.framework, "none")
        self.assertFalse((output / "generated_tests").exists())


if __name__ == "__main__":
    unittest.main()
