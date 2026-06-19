"""Local repository import and feedback-reopen acceptance harness."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from server import ProjectService


@dataclass(slots=True)
class LocalRepositoryAcceptanceResult:
    status: str
    checks: list[dict[str, object]] = field(default_factory=list)
    project: dict[str, object] = field(default_factory=dict)
    initial_run: dict[str, object] = field(default_factory=dict)
    reopened_run: dict[str, object] = field(default_factory=dict)
    delivery: dict[str, object] = field(default_factory=dict)
    output_dir: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "checks": list(self.checks),
            "project": dict(self.project),
            "initial_run": dict(self.initial_run),
            "reopened_run": dict(self.reopened_run),
            "delivery": dict(self.delivery),
            "output_dir": self.output_dir,
        }


class LocalRepositoryAcceptanceHarness:
    """Exercise local repository import, delivery, and feedback repair without GitHub."""

    def run(
        self,
        *,
        output_dir: str | Path = ".alchemy/local_repository_acceptance",
        keep: bool = False,
        auto_browser_verify: bool = False,
    ) -> LocalRepositoryAcceptanceResult:
        output = Path(output_dir)
        if output.exists() and not keep:
            shutil.rmtree(output)
        output.mkdir(parents=True, exist_ok=True)
        repo = output / "local-todo-repo"
        spec = output / "todo_spec.md"
        feedback = output / "todo_feedback.md"
        write_local_todo_repo(repo)
        write_todo_spec(spec)
        write_feedback(feedback)

        service = ProjectService(storage_root=output / "server")
        created = service.create_project(
            {
                "objective": "Deliver the local todo app from the provided development document.",
                "documents": [str(spec)],
                "repository_path": str(repo),
            }
        )
        project_id = str(created["project"]["project_id"])
        initial_run = service.run_project(
            project_id,
            {
                "auto_browser_verify": auto_browser_verify,
                "real_codex": False,
                "real_github": False,
            },
        )
        reopened_run = service.reopen_with_feedback(
            project_id,
            {
                "source_run_id": initial_run["run_id"],
                "feedback_files": [str(feedback)],
                "run": {
                    "auto_browser_verify": auto_browser_verify,
                    "real_codex": False,
                    "real_github": False,
                },
            },
        )
        project = service.get_project(project_id)
        delivery = service.get_delivery(project_id)
        checks = build_checks(
            created=created,
            project=project,
            initial_run=initial_run,
            reopened_run=reopened_run,
            delivery=delivery,
            repo=repo,
            feedback=feedback,
        )
        status = "passed" if all(item["passed"] for item in checks) else "failed"
        result = LocalRepositoryAcceptanceResult(
            status=status,
            checks=checks,
            project=project,
            initial_run=initial_run,
            reopened_run=reopened_run,
            delivery=delivery,
            output_dir=str(output),
        )
        (output / "local_repository_acceptance_report.json").write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return result


def build_checks(
    *,
    created: dict[str, object],
    project: dict[str, object],
    initial_run: dict[str, object],
    reopened_run: dict[str, object],
    delivery: dict[str, object],
    repo: Path,
    feedback: Path,
) -> list[dict[str, object]]:
    created_project = created["project"] if isinstance(created.get("project"), dict) else {}
    brief = created["brief"] if isinstance(created.get("brief"), dict) else {}
    repository = brief.get("repository") if isinstance(brief, dict) else {}
    context = reopened_run.get("context_bundle", {}) if isinstance(reopened_run.get("context_bundle"), dict) else {}
    task_graph = reopened_run.get("task_graph", {}) if isinstance(reopened_run.get("task_graph"), dict) else {}
    requirements = context.get("requirement_map", {}).get("requirements", []) if isinstance(context, dict) else []
    nodes = task_graph.get("nodes", []) if isinstance(task_graph, dict) else []
    feedback_requirements = [
        requirement
        for requirement in requirements
        if isinstance(requirement, dict) and requirement.get("source_role") == "feedback"
    ]
    debug_nodes = [node for node in nodes if isinstance(node, dict) and node.get("type") == "debug"]
    reopen = reopened_run.get("feedback_reopen", {}) if isinstance(reopened_run.get("feedback_reopen"), dict) else {}
    comparison = delivery.get("recovery_comparison", {}) if isinstance(delivery.get("recovery_comparison"), dict) else {}
    return [
        check("local_repository_source", repository.get("provider") == "local", repository),
        check("repository_path_preserved", Path(str(created_project.get("repository_path", ""))) == repo, created_project.get("repository_path", "")),
        check("context_indexed_local_files", repository_file_exists(context, "index.html"), context.get("repository_map", {})),
        check("initial_run_done", initial_run.get("status") == "done", initial_run.get("status", "")),
        check("reopened_run_id_incremented", reopened_run.get("run_id") == "run_002", reopened_run.get("run_id", "")),
        check("feedback_role_preserved", bool(feedback_requirements), feedback_requirements),
        check("debug_task_created", bool(debug_nodes), debug_nodes),
        check("feedback_reopen_metadata", reopen.get("source_run_id") == "run_001", reopen),
        check("recovery_comparison_recorded", comparison.get("source_run_id") == "run_001", comparison),
        check("feedback_file_attached", str(feedback) in project.get("attachments", []), project.get("attachments", [])),
        check("dry_run_github_only", dry_run_github_evidence(reopened_run), reopened_run.get("runtime_state", {}).get("github", {})),
        check("delivery_done", delivery.get("status") == "done", delivery.get("status", "")),
        check("delivery_ready_for_review", bool(delivery.get("delivery_report", {}).get("ready_for_review")), delivery.get("delivery_report", {})),
    ]


def repository_file_exists(context: dict[str, object], expected: str) -> bool:
    repository_map = context.get("repository_map", {}) if isinstance(context, dict) else {}
    files = repository_map.get("files", []) if isinstance(repository_map, dict) else []
    return any(isinstance(item, dict) and item.get("path") == expected for item in files)


def dry_run_github_evidence(run: dict[str, object]) -> bool:
    runtime_state = run.get("runtime_state", {})
    github = runtime_state.get("github", {}) if isinstance(runtime_state, dict) else {}
    return (
        isinstance(github, dict)
        and github.get("status") == "recorded"
        and str(github.get("pull_request_url", "")).startswith("dry-run://")
        and not github.get("commands_run")
    )


def check(name: str, passed: bool, detail: object) -> dict[str, object]:
    return {
        "name": name,
        "passed": passed,
        "detail": detail,
    }


def write_local_todo_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.html").write_text(
        "\n".join(
            [
                "<!doctype html>",
                "<html lang=\"en\">",
                "  <head>",
                "    <meta charset=\"utf-8\">",
                "    <title>Alchemy Local Todo</title>",
                "  </head>",
                "  <body>",
                "    <main id=\"app\">",
                "      <h1>Todo Board</h1>",
                "      <form id=\"todoForm\">",
                "        <label>Todo <input id=\"todoInput\" name=\"todo\" type=\"text\"></label>",
                "        <button type=\"submit\">Add Todo</button>",
                "      </form>",
                "      <ul id=\"todoList\"><li>Read development document</li></ul>",
                "    </main>",
                "    <script>",
                "      const form = document.getElementById('todoForm');",
                "      const input = document.getElementById('todoInput');",
                "      const list = document.getElementById('todoList');",
                "      form.addEventListener('submit', (event) => {",
                "        event.preventDefault();",
                "        const value = input.value.trim();",
                "        if (!value) return;",
                "        const item = document.createElement('li');",
                "        item.textContent = value;",
                "        list.appendChild(item);",
                "        input.value = '';",
                "      });",
                "    </script>",
                "  </body>",
                "</html>",
            ]
        ),
        encoding="utf-8",
    )


def write_todo_spec(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# Local Todo App",
                "",
                "## Requirements",
                "- Must deliver a static todo app in index.html.",
                "- Must allow users to create visible todo items.",
                "- Should keep the app runnable from the local repository without a GitHub URL.",
                "",
                "## Acceptance Criteria",
                "- CRUD create updates the visible todo list.",
                "- The app can be opened locally from index.html.",
            ]
        ),
        encoding="utf-8",
    )


def write_feedback(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# Todo Playtest Feedback",
                "",
                "## Feedback",
                "- Bug: empty todo submission should remain blocked in index.html.",
                "- Issue: the Add Todo flow needs explicit feedback repair evidence.",
            ]
        ),
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run local repository import and feedback-reopen acceptance checks.")
    parser.add_argument("--output", default=".alchemy/local_repository_acceptance")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--auto-browser-verify", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = LocalRepositoryAcceptanceHarness().run(
        output_dir=args.output,
        keep=args.keep,
        auto_browser_verify=args.auto_browser_verify,
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
