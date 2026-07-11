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
from planner.task_graph_builder import migrate_resumed_frontend_tasks_for_repository
from runtime.control import ExecutionController, with_marker_file_controller
from runtime import (
    AcceptanceScenarioPlanner,
    BrowserArtifactEvidenceVerifier,
    BrowserArtifactRunner,
    CodexWorkerAdapter,
    GitHubFlow,
    NativeUITestGenerator,
    Orchestrator,
    RealRunWorkspace,
    RuntimeHandoff,
    RuntimeRecovery,
    RequirementCoverageBuilder,
    StateManager,
    StaticWebArtifactVerifier,
    StaticWebCIGenerator,
    WorkerLifecycleRecorder,
    Evaluator,
)

from .preflight import ExecutionPreflight
from .delivery_report import build_delivery_report
from .development_cycle import build_development_cycle_report
from intake.project_brief import build_local_repository_source


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
    artifact_report: dict = field(default_factory=dict)
    generated_ci: dict = field(default_factory=dict)
    native_ui_tests: dict = field(default_factory=dict)
    requirement_coverage: dict = field(default_factory=dict)
    delivery_report: dict = field(default_factory=dict)
    development_cycle: dict = field(default_factory=dict)
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
            "artifact_report": self.artifact_report,
            "generated_ci": self.generated_ci,
            "native_ui_tests": self.native_ui_tests,
            "requirement_coverage": self.requirement_coverage,
            "delivery_report": self.delivery_report,
            "development_cycle": self.development_cycle,
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
        primary_input_mode: str = "document_driven",
        repository_url: str = "",
        repository_path: str | Path | None = None,
        repository_visibility: str = "public",
        output_dir: str | Path = ".alchemy/document_run",
        max_iterations: int = 50,
        prepare_repository: bool = False,
        real_codex: bool = False,
        real_github: bool = False,
        codex_executable: str = "codex",
        codex_model: str = "",
        max_worker_seconds: int = 1800,
        github_collect_ci: bool = True,
        github_ci_wait_seconds: float = 120,
        github_ci_poll_interval_seconds: float = 10,
        isolate_real_run: bool = True,
        keep_worktree: bool = True,
        worktree_branch_prefix: str = "agent/alchemy-real-run",
        resume_from: str | Path | None = None,
        resume_tasks: Sequence[str] = (),
        browser_url: str = "",
        browser_initial_screenshot: str | Path = "",
        browser_after_screenshot: str | Path = "",
        browser_console_errors: Sequence[str] = (),
        auto_browser_verify: bool = False,
        generate_static_ci: bool = True,
        write_native_ui_tests: bool = False,
        auto_merge: bool = False,
        constraints: Sequence[str] = (),
        controller: ExecutionController | None = None,
        repair_convergence: dict[str, object] | None = None,
    ) -> DocumentRunResult:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        controller = with_marker_file_controller(output, controller)
        generated_repository = False
        if not repository_url and not repository_path and primary_input_mode == "document_driven":
            repository_path = output / "generated_repository"
            generated_repository = True
            Path(repository_path).mkdir(parents=True, exist_ok=True)

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
                codex_model=codex_model,
                max_worker_seconds=max_worker_seconds,
                github_collect_ci=github_collect_ci,
                github_ci_wait_seconds=github_ci_wait_seconds,
                github_ci_poll_interval_seconds=github_ci_poll_interval_seconds,
                max_iterations=max_iterations,
                browser_url=browser_url,
                browser_initial_screenshot=browser_initial_screenshot,
                browser_after_screenshot=browser_after_screenshot,
                browser_console_errors=browser_console_errors,
                auto_browser_verify=auto_browser_verify,
                generate_static_ci=generate_static_ci,
                write_native_ui_tests=write_native_ui_tests,
                auto_merge=auto_merge,
                controller=controller,
                repair_convergence=repair_convergence,
            )

        brief = ProjectBriefBuilder().build(
            objective=objective,
            documents=documents,
            attachments=attachments,
            primary_input_mode=primary_input_mode,  # type: ignore[arg-type]
            repository_url=repository_url,
            repository_path=repository_path or "",
            repository_visibility=repository_visibility,  # type: ignore[arg-type]
            constraints=constraints,
        )
        if brief.repository and repository_path:
            brief.repository.local_path = str(repository_path)
        elif generated_repository:
            brief.repository = build_local_repository_source(
                repository_path,
                target_branch="main",
                visibility="public",
            )
        if brief.repository and repository_url and prepare_repository:
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
        if generated_repository:
            scaffold_generated_repository(
                repository_path,
                task_graph=graph.to_dict(),
                context_bundle=bundle.to_dict(),
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
            repository_required=bool(repository_path or real_codex or real_github),
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
                assign_release_branch(state, workspace_session.branch)
        apply_repair_convergence_config(state, repair_convergence, real_github=real_github)
        worker_packages = [package.to_dict() for package in handoff.build_worker_inputs(state=state)]
        pre_execution_artifact_report = build_artifact_report(
            repository_path=state.repository.get("path", "."),
            task_graph=state.task_graph.to_dict(),
            context_bundle=bundle.to_dict(),
            output_dir=output / "artifact-preview",
        )
        state.repository["artifact_profile"] = str(
            pre_execution_artifact_report.get("artifact_profile", {}).get("name", "unknown")
        )
        state.repository["generate_static_ci"] = bool(real_github and generate_static_ci)
        pre_execution_generated_ci = (
            build_generated_ci_report(
                repository_path=state.repository.get("path", "."),
                artifact_report=pre_execution_artifact_report,
                real_github=real_github,
                github_collect_ci=github_collect_ci,
                generate_static_ci=generate_static_ci,
            )
            if real_github
            else {}
        )
        if pre_execution_generated_ci:
            state.repository["generated_ci"] = pre_execution_generated_ci
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
                model=codex_model,
                dry_run=not real_codex,
                timeout_seconds=max_worker_seconds,
                lifecycle_recorder=WorkerLifecycleRecorder(output / "workers") if real_codex else None,
                cancellation_check=(
                    (lambda task_id: bool(controller and hasattr(controller, "should_stop_worker") and controller.should_stop_worker(task_id)))
                    if controller
                    else None
                ),
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
                github_auto_merge=auto_merge,
            )
            final_state = orchestrator.run(
                state.objective,
                max_iterations=max_iterations,
                reset=True,
                initial_state=state,
            )

        if real_codex and isolate_real_run and not keep_worktree:
            workspace_session = RealRunWorkspace().cleanup(workspace_session)

        artifact_report = build_artifact_report(
            repository_path=state.repository.get("path", "."),
            task_graph=final_state.task_graph.to_dict(),
            context_bundle=bundle.to_dict(),
            output_dir=output,
            browser_url=browser_url,
            browser_initial_screenshot=browser_initial_screenshot,
            browser_after_screenshot=browser_after_screenshot,
            browser_console_errors=list(browser_console_errors),
            auto_browser_verify=auto_browser_verify,
        )
        final_state.repository["artifact_profile"] = str(artifact_report.get("artifact_profile", {}).get("name", "unknown"))
        final_state.repository["artifact_report"] = artifact_report
        native_ui_tests = build_native_ui_tests_report(
            repository_path=state.repository.get("path", "."),
            output_dir=output,
            artifact_report=artifact_report,
            write_to_repository=write_native_ui_tests,
        )
        artifact_report["native_ui_tests"] = native_ui_tests
        final_state.repository["native_ui_tests"] = native_ui_tests
        requirement_coverage = build_requirement_coverage(
            repository_path=state.repository.get("path", "."),
            context_bundle=bundle.to_dict(),
            task_graph=final_state.task_graph.to_dict(),
            runtime_state=final_state.to_dict(),
            artifact_report=artifact_report,
        )
        runtime_generated_ci = final_state.repository.get("generated_ci")
        generated_ci = build_generated_ci_report(
            repository_path=state.repository.get("path", "."),
            artifact_report=artifact_report,
            real_github=real_github,
            github_collect_ci=github_collect_ci,
            generate_static_ci=generate_static_ci,
            existing_report=runtime_generated_ci if isinstance(runtime_generated_ci, dict) else pre_execution_generated_ci,
        )
        final_state.repository["generated_ci"] = generated_ci
        apply_requirement_coverage_gate(final_state, requirement_coverage)
        StateManager(output / "state.json").save(final_state)
        status = document_run_status(final_state, requirement_coverage=requirement_coverage, artifact_report=artifact_report)
        delivery_report = build_delivery_report(
            status=status,
            runtime_state=final_state.to_dict(),
            artifact_report=artifact_report,
            requirement_coverage=requirement_coverage,
            generated_ci=generated_ci,
            native_ui_tests=native_ui_tests,
            workspace=workspace_session.to_dict(),
            preflight=preflight.to_dict(),
        )
        development_cycle = build_development_cycle_report(
            project_brief=brief.to_dict(),
            context_bundle=bundle.to_dict(),
            task_graph=final_state.task_graph.to_dict(),
            runtime_state=final_state.to_dict(),
            artifact_report=artifact_report,
            requirement_coverage=requirement_coverage,
            delivery_report=delivery_report,
        )
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
            artifact_report=artifact_report,
            generated_ci=generated_ci,
            native_ui_tests=native_ui_tests,
            requirement_coverage=requirement_coverage,
            delivery_report=delivery_report,
            development_cycle=development_cycle,
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
        codex_model: str,
        max_worker_seconds: int,
        github_collect_ci: bool,
        github_ci_wait_seconds: float,
        github_ci_poll_interval_seconds: float,
        max_iterations: int,
        browser_url: str,
        browser_initial_screenshot: str | Path,
        browser_after_screenshot: str | Path,
        browser_console_errors: Sequence[str],
        auto_browser_verify: bool,
        generate_static_ci: bool,
        write_native_ui_tests: bool,
        auto_merge: bool,
        controller: ExecutionController | None,
        repair_convergence: dict[str, object] | None,
    ) -> DocumentRunResult:
        recovery = RuntimeRecovery()
        source = recovery.load_source(resume_from)
        recovery_result = recovery.prepare(source, task_ids=resume_tasks)
        state = recovery_result.state
        repository_path = state.repository.get("path", ".")
        apply_resumed_task_graph_migrations(state, repository_path)
        apply_repair_convergence_config(state, repair_convergence, real_github=real_github)
        workspace = dict(source.workspace)
        preflight = ExecutionPreflight().check(
            repository_path=repository_path,
            real_codex=real_codex,
            real_github=real_github,
            codex_executable=codex_executable,
            private_repository=False,
        )
        pre_execution_artifact_report = build_artifact_report(
            repository_path=repository_path,
            task_graph=state.task_graph.to_dict(),
            context_bundle=source.context_bundle,
            output_dir=output / "artifact-preview",
        )
        state.repository["artifact_profile"] = str(
            pre_execution_artifact_report.get("artifact_profile", {}).get("name", "unknown")
        )
        state.repository["generate_static_ci"] = bool(real_github and generate_static_ci)
        pre_execution_generated_ci = (
            build_generated_ci_report(
                repository_path=repository_path,
                artifact_report=pre_execution_artifact_report,
                real_github=real_github,
                github_collect_ci=github_collect_ci,
                generate_static_ci=generate_static_ci,
            )
            if real_github
            else {}
        )
        if pre_execution_generated_ci:
            state.repository["generated_ci"] = pre_execution_generated_ci
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
                model=codex_model,
                dry_run=not real_codex,
                timeout_seconds=max_worker_seconds,
                lifecycle_recorder=WorkerLifecycleRecorder(output / "workers") if real_codex else None,
                cancellation_check=(
                    (lambda task_id: bool(controller and hasattr(controller, "should_stop_worker") and controller.should_stop_worker(task_id)))
                    if controller
                    else None
                ),
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
                github_auto_merge=auto_merge,
            )
            final_state = orchestrator.run(
                state.objective or objective,
                max_iterations=max_iterations,
                reset=True,
                initial_state=state,
            )

        artifact_report = build_artifact_report(
            repository_path=repository_path,
            task_graph=final_state.task_graph.to_dict(),
            context_bundle=source.context_bundle,
            output_dir=output,
            browser_url=browser_url,
            browser_initial_screenshot=browser_initial_screenshot,
            browser_after_screenshot=browser_after_screenshot,
            browser_console_errors=list(browser_console_errors),
            auto_browser_verify=auto_browser_verify,
        )
        final_state.repository["artifact_profile"] = str(artifact_report.get("artifact_profile", {}).get("name", "unknown"))
        final_state.repository["artifact_report"] = artifact_report
        native_ui_tests = build_native_ui_tests_report(
            repository_path=repository_path,
            output_dir=output,
            artifact_report=artifact_report,
            write_to_repository=write_native_ui_tests,
        )
        artifact_report["native_ui_tests"] = native_ui_tests
        final_state.repository["native_ui_tests"] = native_ui_tests
        requirement_coverage = build_requirement_coverage(
            repository_path=repository_path,
            context_bundle=source.context_bundle,
            task_graph=final_state.task_graph.to_dict(),
            runtime_state=final_state.to_dict(),
            artifact_report=artifact_report,
        )
        runtime_generated_ci = final_state.repository.get("generated_ci")
        generated_ci = build_generated_ci_report(
            repository_path=repository_path,
            artifact_report=artifact_report,
            real_github=real_github,
            github_collect_ci=github_collect_ci,
            generate_static_ci=generate_static_ci,
            existing_report=runtime_generated_ci if isinstance(runtime_generated_ci, dict) else pre_execution_generated_ci,
        )
        final_state.repository["generated_ci"] = generated_ci
        apply_requirement_coverage_gate(final_state, requirement_coverage)
        StateManager(output / "state.json").save(final_state)
        status = document_run_status(final_state, requirement_coverage=requirement_coverage, artifact_report=artifact_report)
        delivery_report = build_delivery_report(
            status=status,
            runtime_state=final_state.to_dict(),
            artifact_report=artifact_report,
            requirement_coverage=requirement_coverage,
            generated_ci=generated_ci,
            native_ui_tests=native_ui_tests,
            workspace=workspace,
            preflight=preflight.to_dict(),
        )
        development_cycle = build_development_cycle_report(
            project_brief=source.project_brief,
            context_bundle=source.context_bundle,
            task_graph=final_state.task_graph.to_dict(),
            runtime_state=final_state.to_dict(),
            artifact_report=artifact_report,
            requirement_coverage=requirement_coverage,
            delivery_report=delivery_report,
        )
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
            artifact_report=artifact_report,
            generated_ci=generated_ci,
            native_ui_tests=native_ui_tests,
            requirement_coverage=requirement_coverage,
            delivery_report=delivery_report,
            development_cycle=development_cycle,
            output_dir=str(output),
        )
        (output / "document_run_report.json").write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return result


def apply_resumed_task_graph_migrations(state, repository_path: str | Path) -> list[str]:
    migrated_task_ids = migrate_resumed_frontend_tasks_for_repository(state.task_graph, repository_path)
    if not migrated_task_ids:
        return []

    migrated_set = set(migrated_task_ids)
    reset_task_ids: list[str] = []
    for task in state.task_graph.nodes:
        if task.id not in migrated_set:
            continue
        if task.status == "failed" and task.retry_count >= task.max_attempts:
            task.max_attempts = task.retry_count + 1
            task.status = "pending"
            reset_task_ids.append(task.id)

    if reset_task_ids:
        state.failed_tasks = [task_id for task_id in state.failed_tasks if task_id not in set(reset_task_ids)]
        state.active_tasks = [task_id for task_id in state.active_tasks if task_id not in set(reset_task_ids)]

    migration = {
        "type": "resumed_task_graph_migration",
        "summary": "Refreshed resumed frontend task graph with current package-manager and boundary rules.",
        "task_ids": migrated_task_ids,
        "reset_task_ids": reset_task_ids,
    }
    state.iteration_history.append(migration)
    if isinstance(state.recovery, dict):
        state.recovery["task_graph_migration"] = migration
    return migrated_task_ids


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
    parser.add_argument("--browser-url", default="", help="URL used for externally captured browser artifact evidence.")
    parser.add_argument("--browser-initial-screenshot", default="", help="Initial screenshot path for browser artifact evidence.")
    parser.add_argument("--browser-after-screenshot", default="", help="Post-interaction screenshot path for browser artifact evidence.")
    parser.add_argument("--browser-console-error", action="append", default=[], help="Browser console error captured during artifact verification.")
    parser.add_argument("--auto-browser-verify", action="store_true", help="Launch a local static server and browser runner to capture artifact evidence automatically.")
    parser.add_argument("--no-generate-static-ci", action="store_true", help="Do not generate a lightweight static web CI workflow for docs-only static artifacts.")
    parser.add_argument("--write-native-ui-tests", action="store_true", help="Write generated Playwright/Cypress acceptance tests into repositories that already have a supported UI test framework.")
    parser.add_argument("--auto-merge", action="store_true", help="After a successful real GitHub delivery and passing checks, attempt to merge the PR.")
    parser.add_argument("--boundary-mode", choices=["auto", "strict", "large_refactor"], default="auto", help="Optional task-boundary mode override for document-driven planning.")
    return parser


def assign_release_branch(state: object, branch: str) -> None:
    if not branch:
        return
    task_graph = getattr(state, "task_graph", None)
    if task_graph is None:
        return
    for node in getattr(task_graph, "nodes", []):
        if getattr(node, "type", "") == "release":
            node.branch = branch


def apply_repair_convergence_config(
    state: object,
    repair_convergence: dict[str, object] | None,
    *,
    real_github: bool,
) -> None:
    if not repair_convergence:
        return
    repository = getattr(state, "repository", {})
    if not isinstance(repository, dict):
        return
    target_files = dedupe_strings([str(item) for item in repair_convergence.get("target_files", []) if str(item)])
    repository["repair_convergence"] = {
        "enabled": bool(repair_convergence.get("enabled", True)) and bool(target_files) and not real_github,
        "status": "pending",
        "source_run_id": str(repair_convergence.get("source_run_id", "") or ""),
        "repair_plan_id": str(repair_convergence.get("repair_plan_id", "") or ""),
        "feedback_files": dedupe_strings([str(item) for item in repair_convergence.get("feedback_files", []) if str(item)]),
        "target_files": target_files,
        "required_tests": dedupe_strings([str(item) for item in repair_convergence.get("required_tests", []) if str(item)]),
        "reason": "Repair run can converge after target files and required checks pass.",
    }


def scaffold_generated_repository(
    repository_path: str | Path,
    *,
    task_graph: dict,
    context_bundle: dict,
) -> dict[str, object]:
    """Create deterministic dry-run files for document-only new-project runs."""

    repo = Path(repository_path)
    repo.mkdir(parents=True, exist_ok=True)
    requirements = requirement_texts(context_bundle)
    files = ensure_runnable_web_scaffold_files(generated_repository_files(task_graph), requirements)
    written: list[str] = []
    for file_path in files:
        clean = file_path.replace("\\", "/").strip("/")
        if not clean or clean.startswith("../") or "/../" in clean:
            continue
        target = repo / clean
        if target.exists() or target.suffix == "":
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(scaffold_content(clean, requirements), encoding="utf-8")
        written.append(clean)
    return {
        "status": "generated",
        "repository_path": str(repo),
        "files": written,
        "summary": f"Generated {len(written)} dry-run scaffold file(s) for document-only input.",
    }


def generated_repository_files(task_graph: dict) -> list[str]:
    files: list[str] = []
    for node in task_graph.get("nodes", []):
        if not isinstance(node, dict):
            continue
        if node.get("type") in {"architecture", "review", "release"}:
            continue
        files.extend(str(file) for file in node.get("relevant_files", []) if str(file))
    return dedupe_strings(files)


def ensure_runnable_web_scaffold_files(files: list[str], requirements: list[str]) -> list[str]:
    result = dedupe_strings(files)
    required = ["index.html", "src/main.js", "src/styles.css"]
    for path in reversed(required):
        if path not in result:
            result.insert(0, path)
    return dedupe_strings(result)


def scaffold_content(file_path: str, requirements: list[str]) -> str:
    if is_canvas_game_scaffold(requirements):
        game_content = canvas_game_scaffold_content(file_path, requirements)
        if game_content:
            return game_content
    requirement_notes = "\n".join(f"        <li>{escape_html(text)}</li>" for text in requirements[:8])
    if file_path.endswith(".html"):
        return (
            "<!doctype html>\n"
            "<html lang=\"en\">\n"
            "  <head>\n"
            "    <meta charset=\"utf-8\">\n"
            "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "    <title>Generated Alchemy App</title>\n"
            "    <link rel=\"stylesheet\" href=\"src/styles.css\">\n"
            "  </head>\n"
            "  <body>\n"
            "    <main id=\"app\">\n"
            "      <h1>Generated Alchemy App</h1>\n"
            "      <form id=\"create-form\">\n"
            "        <label>Workspace <input name=\"workspace\" value=\"Default\"></label>\n"
            "        <button type=\"button\" id=\"create-workspace\">Create workspace</button>\n"
            "      </form>\n"
            "      <section aria-label=\"Dashboard\">\n"
            "        <button type=\"button\" id=\"switch-workspace\">Switch workspace</button>\n"
            "        <p id=\"status\">Ready</p>\n"
            "        <ul id=\"requirements\">\n"
            f"{requirement_notes}\n"
            "        </ul>\n"
            "      </section>\n"
            "    </main>\n"
            "    <script src=\"src/main.js\"></script>\n"
            "  </body>\n"
            "</html>\n"
        )
    if file_path == "src/main.js":
        return browser_app_scaffold_script(requirements)
    if file_path == "src/styles.css":
        return browser_app_scaffold_styles()
    if file_path.endswith((".js", ".ts", ".tsx")):
        return module_scaffold_script()
    if file_path.endswith((".md", ".txt", ".rst")):
        return "# Generated Alchemy Artifact\n\n" + "\n".join(f"- {text}" for text in requirements) + "\n"
    if file_path.endswith(".json"):
        return "{}\n"
    return "Generated by Alchemy document-only dry-run scaffold.\n"


def browser_app_scaffold_script(requirements: list[str]) -> str:
    notes = json.dumps(requirements[:8], ensure_ascii=False)
    return f""""use strict";

const requirements = {notes};
const statusEl = document.getElementById("status");
const requirementsEl = document.getElementById("requirements");
const workspaceInput = document.querySelector("input[name='workspace']");
const createButton = document.getElementById("create-workspace");
const switchButton = document.getElementById("switch-workspace");

let activeWorkspace = "Default";
const workspaces = ["Default"];

function normalizeWorkspaceName(value) {{
  return String(value || "Default").trim() || "Default";
}}

function renderStatus(message) {{
  if (statusEl) {{
    statusEl.textContent = message;
  }}
}}

function renderRequirements() {{
  if (!requirementsEl || requirementsEl.children.length) return;
  for (const text of requirements) {{
    const item = document.createElement("li");
    item.textContent = text;
    requirementsEl.appendChild(item);
  }}
}}

function createWorkspace(name = "Default") {{
  const clean = normalizeWorkspaceName(name);
  if (!workspaces.includes(clean)) {{
    workspaces.push(clean);
  }}
  activeWorkspace = clean;
  renderStatus(`Created workspace: ${{clean}}`);
  return {{ id: clean.toLowerCase().replace(/\\s+/g, "-"), name: clean }};
}}

function switchWorkspace() {{
  const currentIndex = workspaces.indexOf(activeWorkspace);
  activeWorkspace = workspaces[(currentIndex + 1) % workspaces.length] || "Default";
  renderStatus(`Active workspace: ${{activeWorkspace}}`);
  return activeWorkspace;
}}

createButton?.addEventListener("click", () => createWorkspace(workspaceInput?.value || "Default"));
switchButton?.addEventListener("click", () => switchWorkspace());
renderRequirements();
renderStatus("Ready");

window.alchemyGeneratedApp = {{
  createWorkspace,
  switchWorkspace,
  get activeWorkspace() {{
    return activeWorkspace;
  }},
  workspaces,
}};
"""


def browser_app_scaffold_styles() -> str:
    return """html,
body {
  margin: 0;
  min-height: 100%;
  background: #f6f8fb;
  color: #18212f;
  font-family: Arial, Helvetica, sans-serif;
}

body {
  display: grid;
  place-items: center;
}

#app {
  width: min(92vw, 760px);
  border: 1px solid #d7e0ea;
  border-radius: 8px;
  padding: 24px;
  background: #ffffff;
  box-shadow: 0 18px 42px rgba(24, 33, 47, 0.12);
}

form,
section {
  display: grid;
  gap: 12px;
}

input,
button {
  min-height: 38px;
  border-radius: 6px;
  font: inherit;
}

input {
  border: 1px solid #c9d4df;
  padding: 0 10px;
}

button {
  border: 0;
  padding: 0 14px;
  background: #0f766e;
  color: #ffffff;
  cursor: pointer;
}

#status {
  min-height: 24px;
  color: #0f766e;
  font-weight: 700;
}
"""


def module_scaffold_script() -> str:
    return (
        "export const alchemyGenerated = true;\n"
        "export function createWorkspace(name = 'Default') {\n"
        "  return { id: name.toLowerCase().replace(/\\s+/g, '-'), name };\n"
        "}\n"
        "export function switchWorkspace(workspace) {\n"
        "  return `Switched to ${workspace.name}`;\n"
        "}\n"
    )


def is_canvas_game_scaffold(requirements: list[str]) -> bool:
    combined = "\n".join(requirements).lower()
    markers = ("canvas", "game", "platform", "platformer", "player", "enemy", "coin", "level", "游戏", "关卡")
    return any(marker in combined for marker in markers)


def canvas_game_scaffold_content(file_path: str, requirements: list[str]) -> str:
    if file_path == "index.html":
        return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Generated Platform Game</title>
    <link rel="stylesheet" href="src/styles.css">
  </head>
  <body>
    <main id="game-root">
      <header class="hud" aria-label="Game status">
        <span id="score">Score 0000</span>
        <span id="coins">Coins 00</span>
        <span id="time">Time 300</span>
        <span id="state">Ready</span>
      </header>
      <canvas id="game" width="960" height="540" aria-label="Original side-scrolling platform game"></canvas>
      <p class="hint">Move with Arrow keys or A/D. Jump with Space/W/Arrow Up. Restart with R.</p>
    </main>
    <script src="src/main.js"></script>
  </body>
</html>
"""
    if file_path == "src/styles.css":
        return """html,
body {
  margin: 0;
  min-height: 100%;
  background: #10131f;
  color: #f7f3d7;
  font-family: Arial, Helvetica, sans-serif;
}

body {
  display: grid;
  place-items: center;
}

#game-root {
  width: min(100vw, 960px);
  padding: 16px;
  box-sizing: border-box;
}

.hud {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 4px;
  font-weight: 700;
}

canvas {
  display: block;
  width: 100%;
  aspect-ratio: 16 / 9;
  image-rendering: pixelated;
  background: #79c9ff;
  border: 4px solid #f7f3d7;
  box-sizing: border-box;
}

.hint {
  color: #c9d2e3;
  font-size: 14px;
}
"""
    if file_path == "src/main.js":
        return """"use strict";

const canvas = document.getElementById("game");
const ctx = canvas.getContext("2d");
const scoreEl = document.getElementById("score");
const coinsEl = document.getElementById("coins");
const timeEl = document.getElementById("time");
const stateEl = document.getElementById("state");

const GRAVITY = 0.75;
const FRICTION = 0.82;
const keys = new Set();

const level = {
  width: 3456,
  finishX: 3220,
  startX: 84,
  startY: 360,
  platforms: [
    { x: 0, y: 468, w: 640, h: 72 },
    { x: 720, y: 468, w: 760, h: 72 },
    { x: 1580, y: 468, w: 560, h: 72 },
    { x: 2240, y: 468, w: 980, h: 72 },
    { x: 420, y: 350, w: 180, h: 32 },
    { x: 900, y: 330, w: 180, h: 32 },
    { x: 1210, y: 280, w: 150, h: 32 },
    { x: 1710, y: 350, w: 220, h: 32 },
    { x: 2460, y: 315, w: 190, h: 32 },
    { x: 2860, y: 275, w: 200, h: 32 }
  ],
  coins: [
    { x: 470, y: 304, taken: false },
    { x: 535, y: 304, taken: false },
    { x: 950, y: 284, taken: false },
    { x: 1260, y: 236, taken: false },
    { x: 1760, y: 306, taken: false },
    { x: 1850, y: 306, taken: false },
    { x: 2520, y: 268, taken: false },
    { x: 2920, y: 230, taken: false }
  ],
  enemies: [
    { x: 820, y: 432, w: 30, h: 30, vx: -1.1, min: 760, max: 1160, alive: true },
    { x: 1760, y: 432, w: 30, h: 30, vx: 1.2, min: 1640, max: 2100, alive: true },
    { x: 2530, y: 432, w: 30, h: 30, vx: -1.3, min: 2310, max: 3060, alive: true }
  ]
};

const player = {
  x: level.startX,
  y: level.startY,
  w: 30,
  h: 42,
  vx: 0,
  vy: 0,
  grounded: false,
  facing: 1
};

let cameraX = 0;
let score = 0;
let coins = 0;
let timeLeft = 300;
let won = false;
let lost = false;
let lastTick = performance.now();

addEventListener("keydown", (event) => {
  keys.add(event.key.toLowerCase());
  if (event.key.toLowerCase() === "r") restart();
});
addEventListener("keyup", (event) => keys.delete(event.key.toLowerCase()));

function restart() {
  player.x = level.startX;
  player.y = level.startY;
  player.vx = 0;
  player.vy = 0;
  player.grounded = false;
  cameraX = 0;
  score = 0;
  coins = 0;
  timeLeft = 300;
  won = false;
  lost = false;
  level.coins.forEach((coin) => { coin.taken = false; });
  level.enemies.forEach((enemy, index) => {
    enemy.alive = true;
    enemy.x = [820, 1760, 2530][index];
    enemy.vx = index === 1 ? 1.2 : -1.2;
  });
}

function snapshot() {
  return {
    player_x: player.x,
    player_y: player.y,
    state: won ? "won" : lost ? "lost" : "playing",
    won
  };
}

function advanceToVictory() {
  player.x = level.finishX + 4;
  player.y = level.startY;
  player.vx = 0;
  player.vy = 0;
  won = true;
  lost = false;
  draw();
  return snapshot();
}

function update(dt) {
  if (won || lost) return;
  const left = keys.has("arrowleft") || keys.has("a");
  const right = keys.has("arrowright") || keys.has("d");
  const jump = keys.has(" ") || keys.has("arrowup") || keys.has("w");

  if (left) {
    player.vx -= 0.55;
    player.facing = -1;
  }
  if (right) {
    player.vx += 0.55;
    player.facing = 1;
  }
  if (jump && player.grounded) {
    player.vy = -14.8;
    player.grounded = false;
  }

  player.vx *= FRICTION;
  player.vx = Math.max(-6.4, Math.min(6.4, player.vx));
  player.vy += GRAVITY;
  player.x += player.vx;
  collideAxis("x");
  player.y += player.vy;
  player.grounded = false;
  collideAxis("y");

  if (player.y > canvas.height + 120) lost = true;
  if (player.x > level.finishX) {
    won = true;
    score += 1000 + Math.max(0, Math.floor(timeLeft)) * 5;
  }

  for (const coin of level.coins) {
    if (!coin.taken && intersects(player, { x: coin.x - 12, y: coin.y - 12, w: 24, h: 24 })) {
      coin.taken = true;
      coins += 1;
      score += 100;
    }
  }

  for (const enemy of level.enemies) {
    if (!enemy.alive) continue;
    enemy.x += enemy.vx;
    if (enemy.x < enemy.min || enemy.x > enemy.max) enemy.vx *= -1;
    if (intersects(player, enemy)) {
      if (player.vy > 0 && player.y + player.h - enemy.y < 22) {
        enemy.alive = false;
        player.vy = -9;
        score += 250;
      } else {
        lost = true;
      }
    }
  }

  timeLeft -= dt / 1000;
  if (timeLeft <= 0) lost = true;
  cameraX = Math.max(0, Math.min(level.width - canvas.width, player.x - canvas.width * 0.38));
}

function collideAxis(axis) {
  for (const platform of level.platforms) {
    if (!intersects(player, platform)) continue;
    if (axis === "x") {
      if (player.vx > 0) player.x = platform.x - player.w;
      if (player.vx < 0) player.x = platform.x + platform.w;
      player.vx = 0;
    } else {
      if (player.vy > 0) {
        player.y = platform.y - player.h;
        player.grounded = true;
      }
      if (player.vy < 0) player.y = platform.y + platform.h;
      player.vy = 0;
    }
  }
}

function intersects(a, b) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

function draw() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.save();
  ctx.translate(-cameraX, 0);
  drawSky();
  drawPlatforms();
  drawCoins();
  drawEnemies();
  drawFinish();
  drawPlayer();
  ctx.restore();
  drawOverlay();
  scoreEl.textContent = "Score " + String(score).padStart(4, "0");
  coinsEl.textContent = "Coins " + String(coins).padStart(2, "0");
  timeEl.textContent = "Time " + Math.max(0, Math.ceil(timeLeft));
  stateEl.textContent = won ? "Cleared" : lost ? "Restart" : "Run";
}

function drawSky() {
  ctx.fillStyle = "#79c9ff";
  ctx.fillRect(cameraX, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#f8f4dc";
  for (const cloud of [{ x: 180, y: 86 }, { x: 760, y: 72 }, { x: 1410, y: 96 }, { x: 2220, y: 78 }, { x: 2960, y: 92 }]) {
    drawCloud(cloud.x, cloud.y);
  }
}

function drawCloud(x, y) {
  ctx.fillRect(x, y + 18, 96, 18);
  ctx.fillRect(x + 18, y, 36, 36);
  ctx.fillRect(x + 48, y + 8, 40, 28);
}

function drawPlatforms() {
  for (const platform of level.platforms) {
    ctx.fillStyle = "#8f5f32";
    ctx.fillRect(platform.x, platform.y, platform.w, platform.h);
    ctx.fillStyle = "#d8a24a";
    for (let x = platform.x; x < platform.x + platform.w; x += 36) {
      ctx.fillRect(x + 2, platform.y + 2, 32, 8);
    }
  }
}

function drawCoins() {
  for (const coin of level.coins) {
    if (coin.taken) continue;
    ctx.fillStyle = "#ffe36e";
    ctx.fillRect(coin.x - 8, coin.y - 14, 16, 28);
    ctx.fillStyle = "#fff7b0";
    ctx.fillRect(coin.x - 2, coin.y - 10, 4, 20);
  }
}

function drawEnemies() {
  for (const enemy of level.enemies) {
    if (!enemy.alive) continue;
    ctx.fillStyle = "#643c24";
    ctx.fillRect(enemy.x, enemy.y, enemy.w, enemy.h);
    ctx.fillStyle = "#f6d29b";
    ctx.fillRect(enemy.x + 6, enemy.y + 8, 6, 6);
    ctx.fillRect(enemy.x + 18, enemy.y + 8, 6, 6);
  }
}

function drawFinish() {
  ctx.fillStyle = "#f7f3d7";
  ctx.fillRect(level.finishX, 180, 8, 288);
  ctx.fillStyle = "#2fb86f";
  ctx.fillRect(level.finishX + 8, 190, 72, 42);
}

function drawPlayer() {
  ctx.fillStyle = "#2f62d8";
  ctx.fillRect(player.x + 4, player.y + 16, 22, 24);
  ctx.fillStyle = "#f0bf7a";
  ctx.fillRect(player.x + 6, player.y + 2, 20, 18);
  ctx.fillStyle = "#e04b38";
  ctx.fillRect(player.x + 2, player.y, 26, 8);
  ctx.fillStyle = "#141414";
  ctx.fillRect(player.x + (player.facing > 0 ? 20 : 8), player.y + 8, 4, 4);
}

function drawOverlay() {
  if (!won && !lost) return;
  ctx.fillStyle = "rgba(16, 19, 31, 0.76)";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#f7f3d7";
  ctx.font = "bold 42px Arial";
  ctx.textAlign = "center";
  ctx.fillText(won ? "Stage Clear" : "Try Again", canvas.width / 2, 245);
  ctx.font = "20px Arial";
  ctx.fillText("Press R to restart", canvas.width / 2, 286);
}

function frame(now) {
  const dt = Math.min(33, now - lastTick);
  lastTick = now;
  update(dt);
  draw();
  requestAnimationFrame(frame);
}

window.__ALCHEMY_GAME_TEST__ = {
  snapshot,
  step(dt) {
    update(Math.max(0, Number(dt) || 0) * 1000);
    draw();
  },
  advanceToVictory,
  restart() {
    restart();
    draw();
  }
};

requestAnimationFrame(frame);
"""
    if file_path == "tests/static_checks.js":
        return """const fs = require("fs");

const html = fs.readFileSync("index.html", "utf8");
const js = fs.readFileSync("src/main.js", "utf8");

for (const needle of ["<canvas", "src/main.js"]) {
  if (!html.includes(needle)) throw new Error(`Missing ${needle} in index.html`);
}

for (const needle of ["requestAnimationFrame", "__ALCHEMY_GAME_TEST__", "snapshot", "advanceToVictory", "restart", "player", "enemy", "coin", "level", "collision", "physics"]) {
  if (!js.includes(needle)) throw new Error(`Missing ${needle} in src/main.js`);
}
"""
    if file_path == "README.md":
        notes = "\n".join(f"- {text}" for text in requirements[:8])
        return f"""# Generated Platform Game

Open `index.html` in a browser to play the generated platform game.

## Controls

- Move: Arrow keys or A/D
- Jump: Space, W, or Arrow Up
- Restart: R

## Requirement Notes

{notes}
"""
    return ""


def escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_artifact_report(
    *,
    repository_path: str | Path,
    task_graph: dict,
    context_bundle: dict | None = None,
    output_dir: str | Path,
    browser_url: str = "",
    browser_initial_screenshot: str | Path = "",
    browser_after_screenshot: str | Path = "",
    browser_console_errors: list[str] | None = None,
    auto_browser_verify: bool = False,
    browser_artifact_runner: BrowserArtifactRunner | None = None,
) -> dict[str, object]:
    artifact_files = artifact_files_from_graph(task_graph)
    requirements = requirement_texts(context_bundle or {})
    scenario_plan = AcceptanceScenarioPlanner().build(context_bundle or {})
    static_verification = StaticWebArtifactVerifier().verify(
        repository_path,
        artifact_files,
        requirements=requirements,
    )
    browser_verification = {}
    if auto_browser_verify:
        browser_verification = (browser_artifact_runner or BrowserArtifactRunner()).verify(
            repository_path,
            artifact_files,
            output_dir=output_dir,
            profile_name=str(static_verification.profile.get("name", "unknown")),
            acceptance_scenarios=list(scenario_plan.to_dict().get("scenarios", [])),
        ).to_dict()
    elif browser_initial_screenshot or browser_after_screenshot or browser_console_errors:
        browser_verification = BrowserArtifactEvidenceVerifier().verify_existing_evidence(
            output_dir=output_dir,
            url=browser_url,
            initial_screenshot=browser_initial_screenshot,
            after_interaction_screenshot=browser_after_screenshot,
            console_errors=list(browser_console_errors or []),
        ).to_dict()
    return {
        "artifact_profile": static_verification.profile,
        "static_verification": static_verification.to_dict(),
        "browser_verification": browser_verification,
        "acceptance_scenarios": scenario_plan.to_dict(),
        "artifact_files": artifact_files,
    }


def requirement_texts(context_bundle: dict) -> list[str]:
    requirement_map = context_bundle.get("requirement_map", {})
    return [str(requirement.get("text", "")) for requirement in requirement_map.get("requirements", []) if requirement.get("text")]


def build_requirement_coverage(
    *,
    repository_path: str | Path,
    context_bundle: dict,
    task_graph: dict,
    runtime_state: dict,
    artifact_report: dict,
) -> dict[str, object]:
    return RequirementCoverageBuilder().build(
        repository_path=repository_path,
        context_bundle=context_bundle,
        task_graph=task_graph,
        runtime_state=runtime_state,
        artifact_report=artifact_report,
    ).to_dict()


def build_native_ui_tests_report(
    *,
    repository_path: str | Path,
    output_dir: str | Path,
    artifact_report: dict,
    write_to_repository: bool = False,
) -> dict[str, object]:
    profile = str(artifact_report.get("artifact_profile", {}).get("name", "unknown"))
    scenarios = artifact_report.get("acceptance_scenarios", {})
    return NativeUITestGenerator().generate(
        repository_path=repository_path,
        output_dir=output_dir,
        acceptance_scenarios=scenarios if isinstance(scenarios, dict) else {},
        artifact_profile=profile,
        write_to_repository=write_to_repository,
    ).to_dict()


def document_run_status(
    state: object,
    *,
    requirement_coverage: dict[str, object],
    artifact_report: dict[str, object],
) -> str:
    if bool(getattr(state, "done", False)):
        return "done"
    blockers = getattr(state, "blockers", [])
    if blockers:
        return "blocked"
    task_graph = getattr(state, "task_graph", None)
    nodes = list(getattr(task_graph, "nodes", []) or []) if task_graph is not None else []
    tasks_finished = bool(nodes) and all(getattr(node, "status", "") in {"completed", "skipped"} for node in nodes)
    coverage_ok = str(requirement_coverage.get("status", "") or "") in {"passed", "completed", "skipped", ""}
    profile = artifact_report.get("artifact_profile", {})
    profile_name = str(profile.get("name", "")) if isinstance(profile, dict) else ""
    static = artifact_report.get("static_verification", {})
    static_ok = (
        profile_name not in {"canvas_game", "static_web_app"}
        or not isinstance(static, dict)
        or str(static.get("status", "") or "") not in {"failed", "blocked"}
    )
    browser = artifact_report.get("browser_verification", {})
    browser_ok = (
        profile_name not in {"canvas_game", "static_web_app"}
        or not isinstance(browser, dict)
        or not browser
        or str(browser.get("status", "") or "") not in {"failed", "blocked"}
    )
    if tasks_finished and coverage_ok and static_ok and browser_ok:
        if hasattr(state, "done"):
            setattr(state, "done", True)
        return "done"
    if tasks_finished and (not coverage_ok or not static_ok or not browser_ok):
        return "blocked"
    return "in_progress"


def build_generated_ci_report(
    *,
    repository_path: str | Path,
    artifact_report: dict,
    real_github: bool,
    github_collect_ci: bool,
    generate_static_ci: bool,
    existing_report: dict[str, object] | None = None,
) -> dict[str, object]:
    if existing_report:
        return existing_report
    if not real_github:
        return {"status": "skipped", "summary": "CI generation skipped outside real GitHub mode."}
    if not generate_static_ci:
        return {"status": "skipped", "summary": "Static CI generation disabled for this run."}
    profile = str(artifact_report.get("artifact_profile", {}).get("name", "unknown"))
    return StaticWebCIGenerator().generate_if_needed(
        repository_path,
        artifact_profile=profile,
        collect_ci=github_collect_ci,
        explicit_no_ci=not github_collect_ci,
    ).to_dict()


def apply_requirement_coverage_gate(state: object, requirement_coverage: dict[str, object]) -> None:
    repository = getattr(state, "repository", {})
    if isinstance(repository, dict):
        repository["requirement_coverage"] = requirement_coverage
    evaluation = Evaluator().evaluate(state)  # type: ignore[arg-type]
    state.evaluation_result = evaluation.to_dict()
    state.done = evaluation.done


def artifact_files_from_graph(task_graph: dict) -> list[str]:
    files: list[str] = []
    for node in task_graph.get("nodes", []):
        if node.get("commands_to_run") == ["static artifact inspection"]:
            files.extend(str(file) for file in node.get("relevant_files", []))
    if not files:
        for node in task_graph.get("nodes", []):
            files.extend(str(file) for file in node.get("relevant_files", []) if str(file).endswith((".html", ".js", ".css")))
    if not files:
        for node in task_graph.get("nodes", []):
            if node.get("type") in {"architecture", "review", "release"}:
                continue
            files.extend(str(file) for file in node.get("relevant_files", []))
    return dedupe_strings(files or ["index.html"])


def dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = value.replace("\\", "/").strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


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
        browser_url=args.browser_url,
        browser_initial_screenshot=args.browser_initial_screenshot,
        browser_after_screenshot=args.browser_after_screenshot,
        browser_console_errors=args.browser_console_error,
        auto_browser_verify=args.auto_browser_verify,
        generate_static_ci=not args.no_generate_static_ci,
        write_native_ui_tests=args.write_native_ui_tests,
        auto_merge=args.auto_merge,
        constraints=[] if args.boundary_mode == "auto" else [f"Scope boundary mode: {args.boundary_mode}"],
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.status == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
