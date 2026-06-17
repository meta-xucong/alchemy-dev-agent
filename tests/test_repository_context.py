from __future__ import annotations

import json
import shutil
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from context import ContextBundleBuilder, RepositoryIndexer
from intake import ProjectBriefBuilder
from intake.schema_validation import validate_context_bundle_contract


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_COUNTER = 0
_TEMP_RUN_ID = str(time.time_ns())


@contextmanager
def temp_repo_dir() -> Iterator[Path]:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    path = TEST_TMP_ROOT / f"repo-context-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def write_sample_repo(root: Path) -> None:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "src" / "app.ts").write_text("export const answer = 42;\n", encoding="utf-8")
    (root / "tests" / "app.test.ts").write_text("test('answer', () => expect(42).toBe(42));\n", encoding="utf-8")
    (root / "README.md").write_text("# Sample Repo\n", encoding="utf-8")
    (root / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")
    (root / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "test": "vitest run",
                    "build": "vite build",
                    "lint": "eslint .",
                }
            }
        ),
        encoding="utf-8",
    )


class RepositoryIndexerTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_indexes_repository_files_and_test_profile(self) -> None:
        with temp_repo_dir() as repo:
            write_sample_repo(repo)
            index = RepositoryIndexer().index(repo)

        paths = {file.path: file for file in index.files}
        self.assertIn("src/app.ts", paths)
        self.assertIn("tests/app.test.ts", paths)
        self.assertIn(".github/workflows/ci.yml", paths)
        self.assertEqual(paths["src/app.ts"].kind, "source")
        self.assertEqual(paths["tests/app.test.ts"].kind, "test")
        self.assertEqual(paths[".github/workflows/ci.yml"].kind, "ci")
        self.assertEqual(index.package_files, ["package.json"])
        self.assertEqual(index.ci_files, [".github/workflows/ci.yml"])
        self.assertEqual(index.package_managers, ["npm"])
        self.assertEqual(index.test_commands, ["npm test"])
        self.assertEqual(index.build_commands, ["npm run build"])
        self.assertEqual(index.lint_commands, ["npm run lint"])
        self.assertFalse(index.coverage_unknown)
        self.assertEqual(index.blockers, [])

    def test_missing_repository_path_records_blocker(self) -> None:
        index = RepositoryIndexer().index("missing/path/for/alchemy")

        self.assertEqual(index.files, [])
        self.assertEqual(index.blockers[0].code, "repository_path_missing")

    def test_context_bundle_includes_repository_index(self) -> None:
        with temp_repo_dir() as repo:
            write_sample_repo(repo)
            spec = repo / "feature.md"
            spec.write_text("# Feature\nAdd dashboard workspace support.\n", encoding="utf-8")
            brief = ProjectBriefBuilder().build(
                objective="Add workspace support",
                documents=[spec],
                repository_url="https://github.com/example/repo",
                created_at="2026-06-18T00:00:00+00:00",
            )
            brief.repository.local_path = str(repo)
            bundle = ContextBundleBuilder().build(brief)
            payload = bundle.to_dict()

        self.assertEqual(validate_context_bundle_contract(payload), [])
        repo_map = payload["repository_map"]
        test_profile = payload["test_profile"]
        files_by_path = {file["path"]: file for file in repo_map["files"]}
        self.assertEqual(files_by_path["src/app.ts"]["kind"], "source")
        self.assertEqual(files_by_path["src/app.ts"]["language"], "typescript")
        self.assertGreater(files_by_path["src/app.ts"]["size_bytes"], 0)
        self.assertEqual(repo_map["package_files"], ["package.json"])
        self.assertEqual(repo_map["ci_files"], [".github/workflows/ci.yml"])
        self.assertEqual(test_profile["package_managers"], ["npm"])
        self.assertEqual(test_profile["test_commands"], ["npm test"])
        self.assertEqual(test_profile["build_commands"], ["npm run build"])
        self.assertEqual(test_profile["lint_commands"], ["npm run lint"])
        self.assertFalse(test_profile["coverage_unknown"])


if __name__ == "__main__":
    unittest.main()
