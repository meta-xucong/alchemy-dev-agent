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

from intake import ProjectBriefBuilder, parse_github_source, validate_project_brief_contract


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"
_TEMP_COUNTER = 0
_TEMP_RUN_ID = str(time.time_ns())


@contextmanager
def temp_intake_dir() -> Iterator[Path]:
    global _TEMP_COUNTER
    _TEMP_COUNTER += 1
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    path = TEST_TMP_ROOT / f"intake-{_TEMP_RUN_ID}-{_TEMP_COUNTER}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class ProjectBriefBuilderTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        if TEST_TMP_ROOT.exists():
            shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)

    def test_document_driven_project_brief_matches_schema_contract(self) -> None:
        with temp_intake_dir() as tmp_dir:
            primary = tmp_dir / "workspace_feature_spec.md"
            primary.write_text("# Workspace Feature\nUsers can create workspaces.\n", encoding="utf-8")
            api_spec = tmp_dir / "api_contract.yaml"
            api_spec.write_text("openapi: 3.0.0\ninfo:\n  title: Workspace API\n", encoding="utf-8")

            brief = ProjectBriefBuilder().build(
                objective="Add workspace support",
                documents=[primary],
                attachments=[api_spec],
                repository_url="https://github.com/example/saas-dashboard.git",
                target_branch="main",
                constraints=["Keep existing single-user accounts working."],
                acceptance_criteria=["Users can create a workspace."],
                created_at="2026-06-18T00:00:00+00:00",
            )
            payload = brief.to_dict()

        self.assertEqual(payload["schema_version"], "2.0")
        self.assertEqual(payload["primary_input_mode"], "document_driven")
        self.assertEqual(payload["documents"][0]["role"], "primary_requirements")
        self.assertEqual(payload["documents"][0]["parse_status"], "parsed")
        self.assertEqual(payload["attachments"][0]["role"], "api_spec")
        self.assertEqual(payload["repository"]["url"], "https://github.com/example/saas-dashboard")
        self.assertFalse(payload["repository"]["gh_auth_required"])
        self.assertEqual(payload["repository"]["visibility"], "public")
        self.assertEqual(payload["repository"]["access_status"], "unchecked")
        self.assertEqual(payload["blockers"], [])
        self.assertEqual(validate_project_brief_contract(payload), [])

    def test_feedback_files_are_first_class_intake_role(self) -> None:
        with temp_intake_dir() as tmp_dir:
            primary = tmp_dir / "spec.md"
            primary.write_text("# Spec\nBuild the app.\n", encoding="utf-8")
            feedback = tmp_dir / "playtest_notes.md"
            feedback.write_text("- Bug: submit button does not update the todo list.\n", encoding="utf-8")

            brief = ProjectBriefBuilder().build(
                objective="Fix todo app feedback",
                documents=[primary],
                attachments=[feedback],
                created_at="2026-06-18T00:00:00+00:00",
            )
            payload = brief.to_dict()

        self.assertEqual(payload["attachments"][0]["role"], "feedback")
        self.assertEqual(validate_project_brief_contract(payload), [])

    def test_private_repository_metadata_is_explicit_optional_path(self) -> None:
        brief = ProjectBriefBuilder().build(
            objective="Add workspace support",
            primary_input_mode="one_line_fallback",
            repository_url="git@github.com:example/private-saas-dashboard.git",
            repository_visibility="private",
            created_at="2026-06-18T00:00:00+00:00",
        )
        payload = brief.to_dict()

        self.assertEqual(payload["repository"]["url"], "https://github.com/example/private-saas-dashboard")
        self.assertEqual(payload["repository"]["visibility"], "private")
        self.assertTrue(payload["repository"]["gh_auth_required"])
        self.assertEqual(validate_project_brief_contract(payload), [])

    def test_document_driven_mode_requires_primary_document(self) -> None:
        brief = ProjectBriefBuilder().build(
            objective="Build billing dashboard",
            primary_input_mode="document_driven",
            created_at="2026-06-18T00:00:00+00:00",
        )
        payload = brief.to_dict()

        self.assertEqual(payload["source_confidence"], "low")
        self.assertEqual(payload["blockers"][0]["code"], "missing_primary_document")
        self.assertEqual(validate_project_brief_contract(payload), [])

    def test_required_unsupported_file_creates_hard_blocker(self) -> None:
        with temp_intake_dir() as tmp_dir:
            primary = tmp_dir / "spec.md"
            primary.write_text("# Spec\n", encoding="utf-8")
            design = tmp_dir / "mockup.png"
            design.write_bytes(b"\x89PNG\r\n")

            brief = ProjectBriefBuilder().build(
                objective="Build dashboard",
                documents=[primary],
                attachments=[design],
                required_attachments=[design],
                created_at="2026-06-18T00:00:00+00:00",
            )
            payload = brief.to_dict()

        blockers = payload["blockers"]
        self.assertEqual(blockers[0]["code"], "unsupported_required_file")
        self.assertEqual(blockers[0]["severity"], "hard")
        self.assertEqual(payload["attachments"][0]["parse_status"], "unsupported")
        self.assertEqual(validate_project_brief_contract(payload), [])

    def test_one_line_fallback_is_marked_low_confidence(self) -> None:
        brief = ProjectBriefBuilder().build(
            objective="Build a todo app",
            primary_input_mode="one_line_fallback",
            created_at="2026-06-18T00:00:00+00:00",
        )
        payload = brief.to_dict()

        self.assertTrue(payload["generated_from_one_liner"])
        self.assertEqual(payload["source_confidence"], "low")
        self.assertEqual(payload["blockers"], [])
        self.assertEqual(validate_project_brief_contract(payload), [])

    def test_invalid_repository_url_is_a_blocker(self) -> None:
        brief = ProjectBriefBuilder().build(
            objective="Build integration",
            primary_input_mode="one_line_fallback",
            repository_url="https://gitlab.com/example/repo",
            created_at="2026-06-18T00:00:00+00:00",
        )
        payload = brief.to_dict()

        self.assertIsNone(payload["repository"])
        self.assertEqual(payload["blockers"][0]["code"], "invalid_github_url")
        self.assertEqual(validate_project_brief_contract(payload), [])

    def test_cli_outputs_valid_project_brief_json(self) -> None:
        with temp_intake_dir() as tmp_dir:
            primary = tmp_dir / "feature.md"
            primary.write_text("# Feature\nAcceptance: done.\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "intake.project_brief",
                    "--objective",
                    "Build feature",
                    "--document",
                    str(primary),
                    "--repository",
                    "https://github.com/example/repo",
                    "--validate",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["objective"], "Build feature")
        self.assertEqual(payload["repository"]["owner"], "example")
        self.assertEqual(payload["repository"]["visibility"], "public")
        self.assertFalse(payload["repository"]["gh_auth_required"])
        self.assertEqual(validate_project_brief_contract(payload), [])


class GitHubSourceTests(unittest.TestCase):
    def test_parse_github_source_accepts_https_and_ssh_urls(self) -> None:
        https_source = parse_github_source("https://github.com/example/repo.git", project_id="proj_test")
        ssh_source = parse_github_source("git@github.com:example/repo.git", project_id="proj_test")
        ssh_url_source = parse_github_source("ssh://git@github.com/example/repo.git", project_id="proj_test")

        self.assertIsNotNone(https_source)
        self.assertIsNotNone(ssh_source)
        self.assertIsNotNone(ssh_url_source)
        self.assertEqual(https_source.url, "https://github.com/example/repo")
        self.assertEqual(ssh_source.url, "https://github.com/example/repo")
        self.assertEqual(ssh_url_source.url, "https://github.com/example/repo")


if __name__ == "__main__":
    unittest.main()
