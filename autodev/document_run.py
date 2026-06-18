"""Document-driven end-to-end dry-run pipeline."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from context import ContextBundleBuilder
from intake import Blocker, GitHubSourceRuntime, PrivateGitHubSourceRuntime, ProjectBriefBuilder
from planner import TaskGraphBuilder
from runtime.control import ExecutionController
from runtime import CodexWorkerAdapter, GitHubFlow, Orchestrator, RealRunWorkspace, RuntimeHandoff, RuntimeRecovery, StateManager

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
    workspace: dict = field(default_factory=dict)
    recovery: dict = field(default_factory=dict)
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
            "workspace": self.workspace,
            "recovery": self.recovery,
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
        repository_visibility: str = "public",
        output_dir: str | Path = ".alchemy/document_run",
        max_iterations: int = 50,
        prepare_repository: bool = False,
        real_codex: bool = False,
        real_github: bool = False,
        codex_executable: str = "codex",
        max_worker_seconds: int = 1800,
        github_collect_ci: bool = True,
        github_ci_wait_seconds: float = 120,
        github_ci_poll_interval_seconds: float = 10,
        isolate_real_run: bool = True,
        keep_worktree: bool = True,
        worktree_branch_prefix: str = "agent/alchemy-real-run",
        resume_from: str | Path | None = None,
        resume_tasks: Sequence[str] = (),
        controller: ExecutionController | None = None,
    ) -> DocumentRunResult:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)

        recovery_payload: dict = {}
        if resume_from:
            return self._run_resumed(
                resume_from=resume_from,
                resume_tasks=resume_tasks,
                output=output,
                objective=objective,
                real_codex=real_codex,
                real_github=real_github,
                codex_executable=codex_executable,
                max_worker_seconds=max_worker_seconds,
                github_collect_ci=github_collect_ci,
                github_ci_wait_seconds=github_ci_wait_seconds,
                github_ci_poll_interval_seconds=github_ci_poll_interval_seconds,
                max_iterations=max_iterations,
                controller=controller,
            )

        brief = ProjectBriefBuilder().build(
            objective=objective,
            documents=documents,
            attachments=attachments,
            repository_url=repository_url,
            repository_visibility=repository_visibility,  # type: ignore[arg-type]
        )
        if brief.repository and repository_path:
            brief.repository.local_path = str(repository_path)
        if brief.repository and prepare_repository and not repository_path:
            source_runtime = (
                PrivateGitHubSourceRuntime()
                if brief.repository.visibility == "private" or brief.repository.gh_auth_required
                else GitHubSourceRuntime()
            )
            source_result = source_runtime.prepare(brief.repository)
            if source_result.blockers:
                brief.blockers.extend(source_result.blockers)
            repository_path = brief.repository.local_path

        source_repository_path = repository_path or (brief.repository.local_path if brief.repository else ".")
        workspace_session = RealRunWorkspace().prepare(
            source_path=source_repository_path,
            output_dir=output / "workspaces",
            enabled=False,
        )

        bundle = ContextBundleBuilder().build(brief)
        graph = TaskGraphBuilder().build(bundle)
        handoff = RuntimeHandoff()
        state = handoff.build_state(
            project_brief=brief,
            context_bundle=bundle,
            task_graph=graph,
            repository_path=repository_path or (brief.repository.local_path if brief.repository else "."),
        )
        preflight = ExecutionPreflight().check(
            repository_path=state.repository.get("path", "."),
            real_codex=real_codex,
            real_github=real_github,
            codex_executable=codex_executable,
            private_repository=bool(brief.repository and (brief.repository.visibility == "private" or brief.repository.gh_auth_required)),
        )
        if preflight.status != "blocked" and real_codex and isolate_real_run:
            workspace_session = RealRunWorkspace().prepare(
                source_path=source_repository_path,
                output_dir=output / "workspaces",
                enabled=True,
                keep=keep_worktree,
                branch_prefix=worktree_branch_prefix,
            )
            if workspace_session.blockers:
                brief.blockers.extend(
                    [
                        Blocker(code="WORKTREE_PREPARE_FAILED", message=blocker, severity="hard")
                        for blocker in workspace_session.blockers
                    ]
                )
            if workspace_session.status == "ready":
                repository_path = workspace_session.execution_path
                if brief.repository:
                    brief.repository.local_path = workspace_session.execution_path
                bundle = ContextBundleBuilder().build(brief)
                graph = TaskGraphBuilder().build(bundle)
                state = handoff.build_state(
                    project_brief=brief,
                    context_bundle=bundle,
                    task_graph=graph,
                    repository_path=repository_path,
                )
                state.repository["path"] = workspace_session.execution_path
        worker_packages = [package.to_dict() for package in handoff.build_worker_inputs(state=state)]
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
        elif workspace_session.blockers:
            state.blockers.append(
                {
                    "id": "B-WORKTREE",
                    "type": "environment",
                    "description": "Real-run worktree preparation failed.",
                    "required_resolution": "Inspect worktree blockers and retry after repository or git state is corrected.",
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
                controller=controller,
                github_collect_ci=github_collect_ci,
                github_ci_wait_seconds=github_ci_wait_seconds if real_github else 0,
                github_ci_poll_interval_seconds=github_ci_poll_interval_seconds,
            )
            final_state = orchestrator.run(
                state.objective,
                max_iterations=max_iterations,
                reset=True,
                initial_state=state,
            )

        if real_codex and isolate_real_run and not keep_worktree:
            workspace_session = RealRunWorkspace().cleanup(workspace_session)

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
            workspace=workspace_session.to_dict(),
            recovery=recovery_payload,
            output_dir=str(output),
        )
        (output / "document_run_report.json").write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return result

    def _run_resumed(
        self,
        *,
        resume_from: str | Path,
        resume_tasks: Sequence[str],
        output: Path,
        objective: str,
        real_codex: bool,
        real_github: bool,
        codex_executable: str,
        max_worker_seconds: int,
        github_collect_ci: bool,
        github_ci_wait_seconds: float,
        github_ci_poll_interval_seconds: float,
        max_iterations: int,
        controller: ExecutionController | None,
    ) -> DocumentRunResult:
        recovery = RuntimeRecovery()
        source = recovery.load_source(resume_from)
        recovery_result = recovery.prepare(source, task_ids=resume_tasks)
        state = recovery_result.state
        repository_path = state.repository.get("path", ".")
        workspace = dict(source.workspace)
        preflight = ExecutionPreflight().check(
            repository_path=repository_path,
            real_codex=real_codex,
            real_github=real_github,
            codex_executable=codex_executable,
            private_repository=False,
        )
        if recovery_result.blockers:
            state.blockers.append(
                {
                    "id": "B-RECOVERY",
                    "type": "technical_limit",
                    "description": "; ".join(recovery_result.blockers),
                    "required_resolution": "Select retryable failed, blocked, or active tasks from the source run.",
                    "task_ids": [],
                    "can_continue_partially": False,
                }
            )
            final_state = state
        elif preflight.status == "blocked":
            state.blockers.append(
                {
                    "id": "B-PREFLIGHT",
                    "type": "environment",
                    "description": "Execution preflight failed during resumed run.",
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
            orchestrator = Orchestrator(
                StateManager(output / "state.json"),
                repository_path=repository_path,
                worker=worker,
                github_flow=GitHubFlow(dry_run=not real_github),
                controller=controller,
                github_collect_ci=github_collect_ci,
                github_ci_wait_seconds=github_ci_wait_seconds if real_github else 0,
                github_ci_poll_interval_seconds=github_ci_poll_interval_seconds,
            )
            final_state = orchestrator.run(
                state.objective or objective,
                max_iterations=max_iterations,
                reset=True,
                initial_state=state,
            )

        StateManager(output / "state.json").save(final_state)
        status = "done" if final_state.done else "blocked" if final_state.blockers else "in_progress"
        result = DocumentRunResult(
            status=status,
            project_brief=source.project_brief,
            context_bundle=source.context_bundle,
            task_graph=final_state.task_graph.to_dict(),
            worker_packages=[],
            runtime_state=final_state.to_dict(),
            preflight=preflight.to_dict(),
            workspace=workspace,
            recovery=recovery_result.to_dict(),
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
    parser.add_argument("--repository-visibility", choices=["public", "private", "unknown"], default="public")
    parser.add_argument("--output", default=".alchemy/document_run", help="Output directory for state and report.")
    parser.add_argument("--max-iterations", type=int, default=50)
    parser.add_argument("--prepare-repository", action="store_true", help="Clone/fetch the public GitHub repository before context indexing when no local path is provided.")
    parser.add_argument("--real-codex", action="store_true", help="Invoke the real Codex CLI instead of dry-run worker mode.")
    parser.add_argument("--real-github", action="store_true", help="Run real git/gh delivery evidence instead of dry-run GitHub mode.")
    parser.add_argument("--codex-executable", default="codex")
    parser.add_argument("--max-worker-seconds", type=int, default=1800)
    parser.add_argument("--no-github-ci", action="store_true", help="Skip PR check collection in real GitHub mode.")
    parser.add_argument("--github-ci-wait-seconds", type=float, default=120)
    parser.add_argument("--github-ci-poll-interval-seconds", type=float, default=10)
    parser.add_argument("--no-isolated-worktree", action="store_true", help="Run real Codex directly in the repository path instead of an isolated git worktree.")
    parser.add_argument("--cleanup-worktree", action="store_true", help="Remove the isolated real-run worktree and branch after the run.")
    parser.add_argument("--worktree-branch-prefix", default="agent/alchemy-real-run")
    parser.add_argument("--resume-from", default="", help="Path to a prior run directory, run.json, document_run_report.json, or state.json.")
    parser.add_argument("--resume-task", action="append", default=[], help="Specific task ID to reset and retry from the prior run.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = DocumentRunPipeline().run(
        objective=args.objective,
        documents=args.document,
        attachments=args.attachment,
        repository_url=args.repository,
        repository_path=args.repository_path or None,
        repository_visibility=args.repository_visibility,
        output_dir=args.output,
        max_iterations=args.max_iterations,
        prepare_repository=args.prepare_repository,
        real_codex=args.real_codex,
        real_github=args.real_github,
        codex_executable=args.codex_executable,
        max_worker_seconds=args.max_worker_seconds,
        github_collect_ci=not args.no_github_ci,
        github_ci_wait_seconds=args.github_ci_wait_seconds,
        github_ci_poll_interval_seconds=args.github_ci_poll_interval_seconds,
        isolate_real_run=not args.no_isolated_worktree,
        keep_worktree=not args.cleanup_worktree,
        worktree_branch_prefix=args.worktree_branch_prefix,
        resume_from=args.resume_from or None,
        resume_tasks=args.resume_task,
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.status == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
