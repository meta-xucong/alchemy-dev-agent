"""Document-driven end-to-end dry-run pipeline."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from context import ContextBundleBuilder
from intake import GitHubSourceRuntime, ProjectBriefBuilder
from planner import TaskGraphBuilder
from runtime import CodexWorkerAdapter, GitHubFlow, Orchestrator, RuntimeHandoff, StateManager

from .preflight import ExecutionPreflight


@dataclass(slots=True)
class DocumentRunResult:
    status: str
    project_brief: dict
    context_bundle: dict
    task_graph: dict
    worker_packages: list[dict] = field(default_factory=list)
    runtime_state: dict = field(default_factory=dict)
    preflight: dict = field(default_factory=dict)
    output_dir: str = ""
    validation_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "project_brief": self.project_brief,
            "context_bundle": self.context_bundle,
            "task_graph": self.task_graph,
            "worker_packages": list(self.worker_packages),
            "runtime_state": self.runtime_state,
            "preflight": self.preflight,
            "output_dir": self.output_dir,
            "validation_errors": list(self.validation_errors),
        }


class DocumentRunPipeline:
    """Run the document-driven contracts through dry-run execution."""

    def run(
        self,
        *,
        objective: str,
        documents: Sequence[str | Path],
        attachments: Sequence[str | Path] = (),
        repository_url: str = "",
        repository_path: str | Path | None = None,
        output_dir: str | Path = ".alchemy/document_run",
        max_iterations: int = 50,
        prepare_repository: bool = False,
        real_codex: bool = False,
        real_github: bool = False,
        codex_executable: str = "codex",
        max_worker_seconds: int = 1800,
    ) -> DocumentRunResult:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)

        brief = ProjectBriefBuilder().build(
            objective=objective,
            documents=documents,
            attachments=attachments,
            repository_url=repository_url,
        )
        if brief.repository and repository_path:
            brief.repository.local_path = str(repository_path)
        if brief.repository and prepare_repository and not repository_path:
            source_result = GitHubSourceRuntime().prepare(brief.repository)
            if source_result.blockers:
                brief.blockers.extend(source_result.blockers)
            repository_path = brief.repository.local_path

        bundle = ContextBundleBuilder().build(brief)
        graph = TaskGraphBuilder().build(bundle)
        handoff = RuntimeHandoff()
        state = handoff.build_state(
            project_brief=brief,
            context_bundle=bundle,
            task_graph=graph,
            repository_path=repository_path or (brief.repository.local_path if brief.repository else "."),
        )
        worker_packages = [package.to_dict() for package in handoff.build_worker_inputs(state=state)]
        preflight = ExecutionPreflight().check(
            repository_path=state.repository.get("path", "."),
            real_codex=real_codex,
            real_github=real_github,
            codex_executable=codex_executable,
        )
        if preflight.status == "blocked":
            state.blockers.append(
                {
                    "id": "B-PREFLIGHT",
                    "type": "environment",
                    "description": "Execution preflight failed.",
                    "required_resolution": "Install or configure required local tools or use dry-run mode.",
                    "task_ids": [],
                    "can_continue_partially": False,
                }
            )
            final_state = state
        else:
            worker = CodexWorkerAdapter(
                executable=codex_executable,
                dry_run=not real_codex,
                timeout_seconds=max_worker_seconds,
            )
            github_flow = GitHubFlow(dry_run=not real_github)
            orchestrator = Orchestrator(
                StateManager(output / "state.json"),
                repository_path=state.repository.get("path", "."),
                worker=worker,
                github_flow=github_flow,
            )
            final_state = orchestrator.run(
                state.objective,
                max_iterations=max_iterations,
                reset=True,
                initial_state=state,
            )

        StateManager(output / "state.json").save(final_state)
        status = "done" if final_state.done else "blocked" if final_state.blockers else "in_progress"
        result = DocumentRunResult(
            status=status,
            project_brief=brief.to_dict(),
            context_bundle=bundle.to_dict(),
            task_graph=final_state.task_graph.to_dict(),
            worker_packages=worker_packages,
            runtime_state=final_state.to_dict(),
            preflight=preflight.to_dict(),
            output_dir=str(output),
        )
        (output / "document_run_report.json").write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the document-driven autonomous development dry-run pipeline.")
    parser.add_argument("--objective", required=True)
    parser.add_argument("--document", action="append", required=True, help="Primary or additional development document path.")
    parser.add_argument("--attachment", action="append", default=[], help="Supporting file path.")
    parser.add_argument("--repository", default="", help="GitHub repository URL.")
    parser.add_argument("--repository-path", default="", help="Local repository checkout path to index and execute against.")
    parser.add_argument("--output", default=".alchemy/document_run", help="Output directory for state and report.")
    parser.add_argument("--max-iterations", type=int, default=50)
    parser.add_argument("--prepare-repository", action="store_true", help="Clone/fetch the public GitHub repository before context indexing when no local path is provided.")
    parser.add_argument("--real-codex", action="store_true", help="Invoke the real Codex CLI instead of dry-run worker mode.")
    parser.add_argument("--real-github", action="store_true", help="Run real git/gh delivery evidence instead of dry-run GitHub mode.")
    parser.add_argument("--codex-executable", default="codex")
    parser.add_argument("--max-worker-seconds", type=int, default=1800)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = DocumentRunPipeline().run(
        objective=args.objective,
        documents=args.document,
        attachments=args.attachment,
        repository_url=args.repository,
        repository_path=args.repository_path or None,
        output_dir=args.output,
        max_iterations=args.max_iterations,
        prepare_repository=args.prepare_repository,
        real_codex=args.real_codex,
        real_github=args.real_github,
        codex_executable=args.codex_executable,
        max_worker_seconds=args.max_worker_seconds,
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.status == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
