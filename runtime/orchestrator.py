"""Top-level runtime orchestrator."""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from .agent_router import AgentRouter
from .artifact_verifier import StaticWebArtifactVerifier
from .control import ExecutionController, NoopExecutionController
from .codex_worker import CodexWorkerAdapter, CodexWorkerInput, CodexWorkerResult, CommandResult, _codex_usage_limit_message
from .evaluator import EvaluationResult, Evaluator
from .generated_ci import StaticWebCIGenerator
from .github_flow import GitHubFlow
from .models import RuntimeState, TaskGraph, TaskNode, utc_now_iso
from .state_manager import StateManager
from .task_graph_engine import TaskGraphEngine
from .worker_lifecycle import WorkerLifecycleRecorder
from .task_packet import TaskPacket, validate_task_packet


ENVIRONMENT_BLOCKER_PATTERNS = (
    "node_modules is missing",
    "node_modules/.bin",
    "vitest is not recognized",
    "test runner unavailable",
    "dependencies are not installed",
    "dependencies are absent",
    "frontend dependencies are absent",
    "cannot resolve vitest",
    "verification is blocked until frontend dependencies",
    "codex cli usage limit reached",
    "you've hit your usage limit",
    "purchase more credits",
    "local codex cli usage limit reached",
    "codex cli connectivity failed",
    "local codex cli connectivity failed",
    "stream disconnected",
    "idle timeout waiting for sse",
    "codex cli configuration failed",
    "local codex cli configuration is invalid",
    "error loading config.toml",
)
CODEX_USAGE_LIMIT_ENVIRONMENT_PATTERNS = (
    "codex cli usage limit reached",
    "you've hit your usage limit",
    "purchase more credits",
    "local codex cli usage limit reached",
)
NON_USAGE_ENVIRONMENT_BLOCKER_PATTERNS = tuple(
    pattern for pattern in ENVIRONMENT_BLOCKER_PATTERNS if pattern not in CODEX_USAGE_LIMIT_ENVIRONMENT_PATTERNS
)
STRUCTURED_PRODUCT_FAILURE_PATTERNS = (
    "final_audit_status=fail",
    "simulation_test_status=fail",
    "real_test_status=fail",
    "source-boundary",
    "allowed_files is empty",
    "build failed",
    "lint failed",
    "parsing error",
    "ts1005",
)

PACKAGE_LOCKFILE_COMPANIONS = (
    "pnpm-lock.yaml",
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "bun.lockb",
)
REPO_PATH_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_.:/\\-])((?:[A-Za-z0-9_.-]+[\\/])+[A-Za-z0-9_.-]+\.[A-Za-z0-9_.-]+)"
)


class Orchestrator:
    """Coordinate scheduling, worker execution, retries, state, and evaluation."""

    def __init__(
        self,
        state_manager: StateManager,
        graph_engine: TaskGraphEngine | None = None,
        router: AgentRouter | None = None,
        worker: CodexWorkerAdapter | None = None,
        evaluator: Evaluator | None = None,
        github_flow: GitHubFlow | None = None,
        controller: ExecutionController | None = None,
        repository_path: str | Path = ".",
        github_collect_ci: bool = True,
        github_ci_wait_seconds: float = 0,
        github_ci_poll_interval_seconds: float = 5,
        github_auto_merge: bool = False,
        artifact_verifier: StaticWebArtifactVerifier | None = None,
    ) -> None:
        self.state_manager = state_manager
        self.graph_engine = graph_engine or TaskGraphEngine()
        self.router = router or AgentRouter()
        self.worker = worker or CodexWorkerAdapter()
        self.evaluator = evaluator or Evaluator()
        self.github_flow = github_flow or GitHubFlow()
        self.controller = controller or NoopExecutionController()
        self.repository_path = Path(repository_path)
        self.github_collect_ci = github_collect_ci
        self.github_ci_wait_seconds = github_ci_wait_seconds
        self.github_ci_poll_interval_seconds = github_ci_poll_interval_seconds
        self.github_auto_merge = github_auto_merge
        self.artifact_verifier = artifact_verifier or StaticWebArtifactVerifier()

    @classmethod
    def for_project(
        cls,
        project_dir: str | Path,
        state_file: str = ".alchemy/state.json",
        *,
        real_codex: bool = False,
        real_github: bool = False,
        codex_executable: str = "codex",
        codex_model: str = "",
        max_worker_seconds: int = 1800,
        github_collect_ci: bool = True,
        github_ci_wait_seconds: float = 0,
        github_ci_poll_interval_seconds: float = 5,
        github_auto_merge: bool = False,
    ) -> "Orchestrator":
        project_path = Path(project_dir)
        return cls(
            StateManager(project_path / state_file),
            worker=CodexWorkerAdapter(
                executable=codex_executable,
                model=codex_model,
                dry_run=not real_codex,
                timeout_seconds=max_worker_seconds,
                lifecycle_recorder=WorkerLifecycleRecorder(project_path / ".alchemy" / "workers") if real_codex else None,
            ),
            github_flow=GitHubFlow(dry_run=not real_github),
            repository_path=project_path,
            github_collect_ci=github_collect_ci,
            github_ci_wait_seconds=github_ci_wait_seconds,
            github_ci_poll_interval_seconds=github_ci_poll_interval_seconds,
            github_auto_merge=github_auto_merge,
        )

    def initialize(
        self,
        objective: str,
        reset: bool = False,
        *,
        initial_state: RuntimeState | None = None,
        task_graph: TaskGraph | None = None,
    ) -> RuntimeState:
        if reset and self.state_manager.state_path.exists():
            self.state_manager.state_path.unlink()
        if initial_state is not None:
            state = initial_state
            if not state.repository:
                state.repository = {"provider": "local", "path": str(self.repository_path)}
            self.state_manager.save(state)
            return state
        if task_graph is not None and not self.state_manager.state_path.exists():
            state = RuntimeState(objective=objective, task_graph=task_graph)
            state.repository = {"provider": "local", "path": str(self.repository_path)}
            self.state_manager.save(state)
            return state
        state = self.state_manager.load_or_initialize(objective, self.graph_engine)
        if not state.repository:
            state.repository = {"provider": "local", "path": str(self.repository_path)}
        self.state_manager.save(state)
        return state

    def run(
        self,
        objective: str,
        max_iterations: int = 20,
        reset: bool = False,
        *,
        initial_state: RuntimeState | None = None,
        task_graph: TaskGraph | None = None,
    ) -> RuntimeState:
        state = self.initialize(objective, reset=reset, initial_state=initial_state, task_graph=task_graph)
        for iteration in range(1, max_iterations + 1):
            if self._converge_unproductive_debug_chains(state):
                self.state_manager.save(state)
            if self._prune_obsolete_debug_tasks(state):
                self.state_manager.save(state)
            evaluation = self.evaluator.evaluate(state)
            self._record_evaluation(state, evaluation)
            if evaluation.done:
                state.done = True
                self.state_manager.save(state)
                return state
            existing_blocker_ids = self._non_partial_blocker_ids(state)
            if existing_blocker_ids:
                if self._promote_completed_debug_repairs(state):
                    self.state_manager.save(state)
                    continue
                blocker_list = ", ".join(sorted(existing_blocker_ids))
                self._record_history(
                    state,
                    "run_blocked",
                    f"Stopping because non-partial blocker(s) are present: {blocker_list}.",
                )
                self.state_manager.save(state)
                return state

            ready_tasks = self.graph_engine.get_ready_tasks(state.task_graph)
            if not ready_tasks:
                if self._promote_completed_debug_repairs(state):
                    self.state_manager.save(state)
                    continue
                if self._handle_retryable_failures(state):
                    self.state_manager.save(state)
                    continue
                self._record_history(state, "no_ready_tasks", "No ready tasks were available.")
                self.state_manager.save(state)
                return state

            for task in ready_tasks:
                if self._prune_obsolete_debug_tasks(state):
                    self.state_manager.save(state)
                if task.status == "skipped":
                    continue
                decision = self.controller.before_task(task.id)
                if decision.action == "stop":
                    self._record_external_stop(state, decision.reason or "Run stopped before task dispatch.")
                    self.state_manager.save(state)
                    return state
                if decision.action == "pause":
                    self._record_history(state, "run_paused", decision.reason or "Run paused before task dispatch.", task.id)
                    self.state_manager.save(state)
                    return state
                blocker_ids_before = self._non_partial_blocker_ids(state)
                self.execute_task(state, task, iteration)
                if self._prune_obsolete_debug_tasks(state):
                    self.state_manager.save(state)
                new_blocker_ids = self._non_partial_blocker_ids(state) - blocker_ids_before
                if new_blocker_ids:
                    blocker_list = ", ".join(sorted(new_blocker_ids))
                    self._record_history(
                        state,
                        "run_blocked",
                        f"Stopping after non-partial blocker(s) were recorded: {blocker_list}.",
                        task.id,
                    )
                    self.state_manager.save(state)
                    return state
                if self._maybe_apply_repair_convergence(state, task):
                    self.state_manager.save(state)
                    return state
                if self._has_pending_debug_work(state):
                    self.state_manager.save(state)
                    break

            evaluation = self.evaluator.evaluate(state)
            self._record_evaluation(state, evaluation)
            state.done = evaluation.done
            self.state_manager.save(state)
            if state.done:
                return state

        self._record_history(state, "iteration_limit", f"Stopped after {max_iterations} iterations.")
        self.state_manager.save(state)
        return state

    def execute_task(self, state: RuntimeState, task: TaskNode, iteration: int) -> None:
        if task.type == "release":
            self._execute_release_task(state, task, iteration)
            return
        if self._can_execute_deterministically(task):
            self._execute_deterministic_task(state, task, iteration)
            return

        self.graph_engine.mark_active(state.task_graph, task.id)
        state.active_tasks = self._add_unique(state.active_tasks, task.id)
        self.state_manager.save(state)

        worker_input = self._build_worker_input(state, task)
        result = self.worker.execute(worker_input)
        self._record_worker_lifecycle(state, result)
        evidence = self._worker_evidence(task, result, iteration)

        state.active_tasks = [task_id for task_id in state.active_tasks if task_id != task.id]
        if result.status == "completed":
            self.graph_engine.mark_completed(state.task_graph, task.id, evidence)
            state.completed_tasks = self._add_unique(state.completed_tasks, task.id)
            state.failed_tasks = [task_id for task_id in state.failed_tasks if task_id != task.id]
            self._record_history(state, "task_completed", f"{task.id} completed.", task.id)
            return

        if result.status == "blocked":
            self.graph_engine.mark_blocked(state.task_graph, task.id, evidence)
            state.failed_tasks = self._add_unique(state.failed_tasks, task.id)
            environment_summary = _worker_result_environment_blocker_summary(result)
            self._record_blocker(
                state,
                task,
                environment_summary or result.summary,
                blocker_type="environment" if environment_summary else "technical_limit",
            )
            self._record_history(state, "task_blocked", f"{task.id} blocked.", task.id)
            return

        if result.status == "partial":
            downstream_handoff_tasks = self._partial_downstream_handoff_tasks(state, task, result)
            if downstream_handoff_tasks:
                handoff_evidence = self._partial_downstream_handoff_evidence(
                    evidence,
                    result,
                    downstream_handoff_tasks,
                )
                self.graph_engine.mark_completed(state.task_graph, task.id, handoff_evidence)
                state.completed_tasks = self._add_unique(state.completed_tasks, task.id)
                state.failed_tasks = [task_id for task_id in state.failed_tasks if task_id != task.id]
                downstream_ids = ", ".join(node.id for node in downstream_handoff_tasks)
                self._record_history(
                    state,
                    "task_partial_handed_off",
                    f"{task.id} completed its scoped work; deferred out-of-scope partial evidence to downstream task(s): {downstream_ids}.",
                    task.id,
                )
                return

        self.graph_engine.mark_failed(state.task_graph, task.id, evidence)
        state.failed_tasks = self._add_unique(state.failed_tasks, task.id)
        self._record_history(state, "task_failed", f"{task.id} returned {result.status}.", task.id)
        self._handle_failed_task(state, task, result)

    def _can_execute_deterministically(self, task: TaskNode) -> bool:
        if task.type == "review":
            return True
        if task.commands_to_run == ["static document inspection"]:
            return task.type in {"documentation", "test"}
        if task.commands_to_run == ["static artifact inspection"]:
            return task.type == "test"
        return False

    def _execute_deterministic_task(self, state: RuntimeState, task: TaskNode, iteration: int) -> None:
        self.graph_engine.mark_active(state.task_graph, task.id)
        state.active_tasks = self._add_unique(state.active_tasks, task.id)
        self.state_manager.save(state)

        if task.type == "review":
            result = self._review_result(state, task)
        elif task.commands_to_run == ["static artifact inspection"]:
            result = self._static_artifact_result(task)
        else:
            result = self._static_document_result(task)
        evidence = self._worker_evidence(task, result, iteration)

        state.active_tasks = [task_id for task_id in state.active_tasks if task_id != task.id]
        if result.status == "completed":
            self.graph_engine.mark_completed(state.task_graph, task.id, evidence)
            state.completed_tasks = self._add_unique(state.completed_tasks, task.id)
            state.failed_tasks = [task_id for task_id in state.failed_tasks if task_id != task.id]
            self._record_history(state, "task_completed", f"{task.id} completed deterministically.", task.id)
            return
        if result.status == "skipped":
            self.graph_engine.mark_skipped(state.task_graph, task.id, evidence)
            state.completed_tasks = self._add_unique(state.completed_tasks, task.id)
            state.failed_tasks = [task_id for task_id in state.failed_tasks if task_id != task.id]
            self._record_history(state, "task_skipped", f"{task.id} skipped deterministic check: {result.summary}", task.id)
            return

        self.graph_engine.mark_failed(state.task_graph, task.id, evidence)
        state.failed_tasks = self._add_unique(state.failed_tasks, task.id)
        self._record_history(state, "task_failed", f"{task.id} deterministic check returned {result.status}.", task.id)
        self._handle_failed_task(state, task, result)

    def _static_document_result(self, task: TaskNode) -> CodexWorkerResult:
        repository_path = Path(self.repository_path).resolve()
        paths, missing = self._static_document_paths(task.relevant_files, repository_path)
        evidence: list[str] = []
        tests_failed: list[str] = []
        if not paths:
            tests_failed.append("No task-specific document files were provided for static document inspection.")
        if missing:
            tests_failed.extend(f"Missing required file: {path}" for path in missing)
        for path in paths:
            if path.exists():
                relative = str(path.relative_to(repository_path))
                text = path.read_text(encoding="utf-8", errors="replace")
                evidence.append(f"Found required file: {relative}")
                for expected in self._expected_document_phrases(task.completion_criteria):
                    if expected.lower() in text.lower():
                        evidence.append(f"Found expected phrase in {relative}: {expected}")
                    else:
                        tests_failed.append(f"Missing expected phrase in {relative}: {expected}")
        status = "failed" if tests_failed else "completed"
        summary = "Static document inspection passed." if status == "completed" else "Static document inspection failed."
        return CodexWorkerResult(
            task_id=task.id,
            status=status,
            summary=summary,
            commands_run=[
                CommandResult(
                    command="static document inspection",
                    exit_code=0 if status == "completed" else 1,
                    summary=summary,
                )
            ],
            tests_passed=["static document inspection"] if status == "completed" else [],
            tests_failed=tests_failed,
            evidence=evidence,
            confidence=1.0 if status == "completed" else 0.0,
        )

    def _static_document_paths(self, relevant_files: list[str], repository_path: Path) -> tuple[list[Path], list[str]]:
        paths: list[Path] = []
        missing: list[str] = []
        for raw_path in relevant_files:
            clean = str(raw_path).replace("\\", "/").strip().strip("`")
            if not clean:
                continue
            if clean.endswith("/**"):
                base = repository_path / clean[:-3].rstrip("/")
                if base.is_dir():
                    paths.extend(
                        item
                        for item in base.rglob("*")
                        if item.is_file() and item.suffix.lower() in {".md", ".txt", ".rst"}
                    )
                else:
                    missing.append(clean)
                continue
            if any(marker in clean for marker in ("*", "?", "[")):
                matches = [
                    path
                    for path in repository_path.glob(clean)
                    if path.is_file() and path.suffix.lower() in {".md", ".txt", ".rst"}
                ]
                if matches:
                    paths.extend(matches)
                else:
                    missing.append(clean)
                continue
            path = repository_path / clean
            if path.is_dir():
                matches = [
                    item
                    for item in path.rglob("*")
                    if item.is_file() and item.suffix.lower() in {".md", ".txt", ".rst"}
                ]
                if matches:
                    paths.extend(matches)
                else:
                    missing.append(clean)
                continue
            if path.suffix.lower() not in {".md", ".txt", ".rst"}:
                continue
            if path.exists():
                paths.append(path)
            else:
                missing.append(clean)
        return _dedupe_path_objects(paths), missing

    def _static_artifact_result(self, task: TaskNode) -> CodexWorkerResult:
        verification = self.artifact_verifier.verify(self.repository_path, task.relevant_files)
        return CodexWorkerResult(
            task_id=task.id,
            status=verification.status,  # type: ignore[arg-type]
            summary=verification.summary,
            commands_run=[
                CommandResult(
                    command="static artifact inspection",
                    exit_code=0 if verification.status == "completed" else 1,
                    summary=verification.summary,
                )
            ],
            tests_passed=verification.tests_passed,
            tests_failed=verification.tests_failed,
            evidence=verification.evidence,
            confidence=1.0 if verification.status == "completed" else 0.0,
        )

    def _expected_document_phrases(self, criteria: list[str]) -> list[str]:
        phrases: list[str] = []
        for criterion in criteria:
            phrases.extend(_backtick_phrases(criterion))
            lowered = criterion.lower()
            if "isolated git worktree" in lowered:
                phrases.append("isolated git worktree")
            if "source checkout" in lowered:
                phrases.append("source checkout")
            if "v2.19 representative delivery probe" in lowered:
                phrases.append("V2.19 representative delivery probe")
        return _dedupe_strings([phrase for phrase in phrases if not phrase.endswith((".md", ".txt", ".rst"))])

    def _review_result(self, state: RuntimeState, task: TaskNode) -> CodexWorkerResult:
        failed = [node.id for node in state.task_graph.nodes if node.id != task.id and node.status in {"failed", "blocked"}]
        unfinished = [
            node.id
            for node in state.task_graph.nodes
            if node.id != task.id and node.type != "release" and node.status not in {"completed", "skipped"}
        ]
        issues = [f"Failed or blocked tasks: {', '.join(failed)}"] if failed else []
        issues.extend([f"Unfinished tasks: {', '.join(unfinished)}"] if unfinished else [])
        status = "completed" if not issues else "failed"
        summary = "Reviewer approved completed task evidence." if status == "completed" else "Reviewer found unresolved task issues."
        return CodexWorkerResult(
            task_id=task.id,
            status=status,
            summary=summary,
            tests_passed=["review evidence"] if status == "completed" else [],
            tests_failed=issues,
            evidence=[
                f"Completed task IDs before review: {', '.join(state.completed_tasks) or 'none'}",
                "No failed or blocked tasks were present." if not failed else issues[0],
            ],
            known_issues=issues,
            confidence=1.0 if status == "completed" else 0.0,
        )

    def _build_worker_input(self, state: RuntimeState, task: TaskNode) -> CodexWorkerInput:
        upstream = [
            dependency.source
            for dependency in self.graph_engine.dependency_edges_for(state.task_graph, [task.id])
            if dependency.target == task.id
        ]
        retry_context = ""
        if task.retry_count:
            retry_context = f"Retry attempt {task.retry_count + 1}; use prior evidence to avoid repeating failures."
        task_packet = self._goal_locked_task_packet(state, task)
        constraints = self._constraints_for_task(task)
        if task_packet:
            validation_errors = validate_task_packet(task_packet)
            constraints.extend(
                [
                    "This is a goal-locked task. Preserve requirement IDs, transformation IDs, and expected final state in all evidence.",
                    "For a required strategy, emit DECISION_RECORD: before reporting edits; for reference use, emit REFERENCE_FILES: with consulted paths.",
                    *[f"Task packet validation error: {error}" for error in validation_errors],
                ]
            )
        return CodexWorkerInput(
            task_id=task.id,
            goal=self.router.build_worker_goal(task),
            objective=state.objective,
            task_description=task.description,
            acceptance_criteria=list(task.completion_criteria),
            repository_path=str(self.repository_path),
            branch=task.branch or self._default_branch_for_task(task),
            agent_context={
                "assigned_agent": self.router.route(task),
                "task_type": task.type,
                "upstream_tasks": upstream,
            },
            relevant_files=list(task.relevant_files),
            allowed_files=self._allowed_files_for_task(task),
            constraints=constraints,
            commands_to_run=list(task.commands_to_run),
            retry_context=retry_context,
            boundary_mode=task.boundary_mode,
            task_packet=task_packet.to_dict() if task_packet else {},
        )

    def _goal_locked_task_packet(self, state: RuntimeState, task: TaskNode) -> TaskPacket | None:
        contract = next(
            (
                item
                for item in task.evidence
                if isinstance(item, dict) and item.get("type") == "task_contract"
            ),
            None,
        )
        if not contract:
            return None
        return TaskPacket(
            task_id=task.id,
            target_root=str(self.repository_path.resolve()),
            allowed_write_paths=[str(item) for item in contract.get("allowed_write_paths", [])],
            reference_roots=[str(item) for item in contract.get("reference_roots", [])],
            requirement_ids=[str(item) for item in contract.get("requirement_ids", [])],
            transformation_ids=[str(item) for item in contract.get("transformation_ids", [])],
            objective_slice=[{"objective": state.objective, "expected_final_state": contract.get("expected_final_state", {})}],
            required_strategy_decision=str(contract.get("required_strategy_decision", "")),
            repository_fingerprint=str(state.repository.get("repository_fingerprint", "")),
        )

    def _allowed_files_for_task(self, task: TaskNode) -> list[str]:
        task_contract = next(
            (
                item
                for item in task.evidence
                if isinstance(item, dict) and item.get("type") == "task_contract"
            ),
            None,
        )
        if task_contract:
            if bool(task_contract.get("read_only")):
                return []
            return _expand_package_lockfile_boundaries(
                _clean_paths([str(item) for item in task_contract.get("allowed_write_paths", [])])
            )
        if task.type in {"architecture", "review", "test"}:
            return []
        if self._is_read_only_inventory_task(task):
            return []
        return _expand_package_lockfile_boundaries(_clean_paths(task.relevant_files))

    def _constraints_for_task(self, task: TaskNode) -> list[str]:
        constraints = [
            "Do not edit files outside allowed_files.",
            "If allowed_files is empty, do not edit repository files.",
        ]
        read_only_inventory = self._is_read_only_inventory_task(task)
        if read_only_inventory:
            constraints.append(
                "This is a read-only inventory/checkpoint task: inspect relevant_files, do not edit repository files, "
                "do not run heavy build or test commands unless commands_to_run explicitly lists them, and return "
                "concise evidence plus follow-up implementation targets."
            )
        if task.boundary_mode == "large_refactor" and not read_only_inventory:
            constraints.append(
                "This is a large_refactor integration task: implement cross-module changes within allowed_files as one coherent product migration."
            )
        if not self._allowed_files_for_task(task):
            constraints.append("Return partial or blocked if the task requires repository edits.")
        return constraints

    def _is_read_only_inventory_task(self, task: TaskNode) -> bool:
        if task.commands_to_run:
            return False
        text = f"{task.title} {task.description}".lower()
        return "inventory" in text or "checkpoint" in text

    def _worker_evidence(self, task: TaskNode, result: CodexWorkerResult, iteration: int) -> dict:
        return {
            "type": "worker_result",
            "summary": result.summary,
            "result": result.to_dict(),
            "agent": self.router.route(task),
            "created_at": utc_now_iso(),
            "iteration": iteration,
        }

    def _partial_downstream_handoff_tasks(
        self,
        state: RuntimeState,
        task: TaskNode,
        result: CodexWorkerResult,
    ) -> list[TaskNode]:
        if task.type == "debug" or result.status != "partial":
            return []
        if _worker_result_final_gate_failure_summary(result):
            return []
        if _worker_result_environment_blocker_summary(result) or _worker_result_timed_out(result):
            return []
        result_payload = result.to_dict()
        made_scoped_progress = bool(
            result.files_changed
            or result.tests_passed
            or self._worker_result_has_passing_checks(result_payload)
        )
        if not made_scoped_progress:
            return []

        deferred_paths = _deferred_repo_paths_from_result(result)
        if not deferred_paths:
            return []

        downstream_tasks = [
            node
            for node in state.task_graph.nodes
            if task.id in node.dependencies and node.status in {"pending", "ready"} and node.type != "debug"
        ]
        handoff_tasks: list[TaskNode] = []
        for downstream in downstream_tasks:
            downstream_scope = self._allowed_files_for_task(downstream)
            if not downstream_scope:
                downstream_scope = _clean_paths(downstream.relevant_files)
            if downstream_scope and _any_path_matches_scope(deferred_paths, downstream_scope):
                handoff_tasks.append(downstream)
        return handoff_tasks

    def _partial_downstream_handoff_evidence(
        self,
        evidence: dict,
        result: CodexWorkerResult,
        downstream_tasks: list[TaskNode],
    ) -> dict:
        downstream_ids = [node.id for node in downstream_tasks]
        original_result = result.to_dict()
        handoff_result = dict(original_result)
        if original_result.get("tests_failed"):
            handoff_result["tests_deferred_to_downstream"] = list(original_result.get("tests_failed", []))
        if original_result.get("known_issues"):
            handoff_result["known_issues_deferred_to_downstream"] = list(original_result.get("known_issues", []))
        handoff_result["status"] = "completed"
        handoff_result["original_status"] = original_result.get("status", result.status)
        handoff_result["partial_handoff"] = True
        handoff_result["partial_handoff_to"] = downstream_ids
        handoff_result["handoff_original_result"] = original_result
        handoff_result["tests_failed"] = []
        handoff_result["known_issues"] = []
        handoff_result["summary"] = (
            f"{result.summary} Remaining out-of-scope partial evidence was handed off to downstream task(s): "
            f"{', '.join(downstream_ids)}."
        )

        handoff_evidence = dict(evidence)
        handoff_evidence["summary"] = handoff_result["summary"]
        handoff_evidence["partial_handoff"] = True
        handoff_evidence["partial_handoff_to"] = downstream_ids
        handoff_evidence["result"] = handoff_result
        return handoff_evidence

    def _handle_failed_task(self, state: RuntimeState, task: TaskNode, result: CodexWorkerResult) -> None:
        if task.type == "debug":
            self._converge_debug_task_to_parent_retry(
                state,
                task,
                f"{task.id} returned {result.status}: {result.summary}",
            )
            return

        environment_summary = _worker_result_environment_blocker_summary(result)
        if environment_summary:
            task.status = "blocked"
            self._record_blocker(state, task, environment_summary, blocker_type="environment")
            self._record_history(
                state,
                "worker_environment_blocker",
                f"{task.id} blocked by worker environment or local Codex CLI availability.",
                task.id,
            )
            return

        if _worker_result_timed_out(result):
            self._record_timeout_blocker(
                state,
                task,
                f"{task.id} exceeded the Codex worker timeout. Stop instead of launching a same-scope debug task.",
            )
            return

        if _worker_result_boundary_violation(result):
            self._record_blocker(
                state,
                task,
                (
                    f"{task.id} modified files outside allowed_files. Stop instead of launching a same-scope "
                    "debug task; split the task or expand the task boundary before retrying."
                ),
                blocker_type="technical_limit",
            )
            self._record_history(
                state,
                "worker_boundary_blocker",
                f"{task.id} blocked after an out-of-scope file boundary violation.",
                task.id,
            )
            return

        final_gate_failure_summary = _worker_result_final_gate_failure_summary(result)
        if final_gate_failure_summary:
            self._record_blocker(
                state,
                task,
                final_gate_failure_summary,
                blocker_type="technical_limit",
            )
            self._record_history(
                state,
                "final_gate_blocker",
                f"{task.id} stopped after final gate failure.",
                task.id,
            )
            return

        if not self.graph_engine.can_retry(task):
            self._record_blocker(
                state,
                task,
                f"Retry policy exhausted after {task.retry_count} attempt(s): {result.summary}",
                blocker_type="technical_limit",
            )
            return

        debug_task = self.graph_engine.create_debug_task(state.task_graph, task, result.summary)
        self._record_history(
            state,
            "debug_task_created",
            f"Created {debug_task.id} to diagnose {task.id}.",
            debug_task.id,
        )
        self.graph_engine.reset_for_retry(task)

    def _converge_unproductive_debug_chains(self, state: RuntimeState) -> bool:
        changed = False
        for task in list(state.task_graph.nodes):
            if task.type != "debug" or task.status in {"completed", "skipped"}:
                continue
            debug_depth = task.id.count("-DEBUG-")
            if (
                debug_depth <= 1
                and task.status not in {"failed", "blocked"}
                and task.id not in state.failed_tasks
                and not self._debug_task_has_unproductive_evidence(task)
            ):
                continue
            if self._converge_debug_task_to_parent_retry(
                state,
                task,
                f"{task.id} is an unproductive debug branch with status {task.status}.",
            ):
                changed = True
        return changed

    def _converge_debug_task_to_parent_retry(self, state: RuntimeState, task: TaskNode, reason: str) -> bool:
        if task.type != "debug" or task.status in {"completed", "skipped"}:
            return False

        root = self._root_task_for_debug(state, task)
        latest_result = self._latest_worker_result(task)
        task.status = "skipped"
        task.evidence.append(
            {
                "type": "debug_convergence",
                "summary": reason,
                "created_at": utc_now_iso(),
            }
        )
        state.active_tasks = [task_id for task_id in state.active_tasks if task_id != task.id]
        state.failed_tasks = [task_id for task_id in state.failed_tasks if task_id != task.id]
        self._record_history(
            state,
            "debug_chain_converged",
            f"{task.id} skipped so the original task can retry instead of creating nested debug work.",
            task.id,
        )

        if root is None or root.type == "debug":
            self._record_blocker(
                state,
                task,
                f"Debug task could not be mapped back to a non-debug parent: {reason}",
                blocker_type="technical_limit",
            )
            return True

        if root.status in {"completed", "skipped"}:
            return True

        if _worker_result_timed_out(latest_result):
            root.status = "blocked"
            root.evidence.append(
                {
                    "type": "debug_timeout_blocker",
                    "summary": f"{task.id} also exceeded the Codex worker timeout.",
                    "source_task_id": task.id,
                    "created_at": utc_now_iso(),
                }
            )
            state.active_tasks = [task_id for task_id in state.active_tasks if task_id != root.id]
            state.failed_tasks = self._add_unique(state.failed_tasks, root.id)
            self._record_timeout_blocker(
                state,
                root,
                f"{task.id} timed out while diagnosing {root.id}. Stop instead of replaying the original task.",
            )
            return True

        environment_blocker = self._debug_environment_blocker_summary(task)
        if environment_blocker:
            root.status = "blocked"
            root.evidence.append(
                {
                    "type": "debug_environment_blocker",
                    "summary": environment_blocker,
                    "source_task_id": task.id,
                    "created_at": utc_now_iso(),
                }
            )
            state.active_tasks = [task_id for task_id in state.active_tasks if task_id != root.id]
            state.failed_tasks = self._add_unique(state.failed_tasks, root.id)
            self._record_blocker(state, root, environment_blocker, blocker_type="environment")
            self._record_history(
                state,
                "debug_environment_blocker",
                f"{root.id} blocked because {task.id} identified a verification environment setup gap.",
                root.id,
            )
            return True

        if self.graph_engine.can_retry(root):
            root.status = "pending"
            state.active_tasks = [task_id for task_id in state.active_tasks if task_id != root.id]
            state.failed_tasks = [task_id for task_id in state.failed_tasks if task_id != root.id]
            self._record_history(
                state,
                "debug_chain_parent_retry",
                f"{root.id} reset for retry after {task.id} did not produce completed repair evidence.",
                root.id,
            )
            return True

        self._record_blocker(
            state,
            root,
            f"Debug task {task.id} did not produce completed repair evidence and {root.id} has no retry attempts left: {reason}",
            blocker_type="technical_limit",
        )
        return True

    def _record_timeout_blocker(self, state: RuntimeState, task: TaskNode, description: str) -> None:
        self._record_blocker(state, task, description, blocker_type="technical_limit")
        self._record_history(
            state,
            "worker_timeout_blocker",
            f"{task.id} blocked after a worker timeout; split the task or adjust the worker budget before retrying.",
            task.id,
        )

    def _debug_task_has_unproductive_evidence(self, task: TaskNode) -> bool:
        if task.retry_count > 0:
            return True
        result = self._latest_worker_result(task)
        if not result:
            return False
        return result.get("status") in {"partial", "failed", "blocked"}

    def _debug_environment_blocker_summary(self, task: TaskNode) -> str:
        text = "\n".join(_debug_evidence_text(task)).lower()
        if not any(pattern in text for pattern in ENVIRONMENT_BLOCKER_PATTERNS):
            return ""
        return (
            f"{task.id} reported a verification environment blocker, so the parent task should not be retried "
            "until dependency setup succeeds. Evidence mentions missing dependencies or unavailable test runner."
        )

    def _root_task_for_debug(self, state: RuntimeState, task: TaskNode) -> TaskNode | None:
        root_id = task.id.split("-DEBUG-", 1)[0]
        for node in state.task_graph.nodes:
            if node.id == root_id:
                return node
        return None

    def _handle_retryable_failures(self, state: RuntimeState) -> bool:
        changed = False
        for task in self.graph_engine.failed_required_tasks(state.task_graph):
            if task.status == "failed" and self.graph_engine.can_retry(task):
                self._handle_failed_task(
                    state,
                    task,
                    CodexWorkerResult(task_id=task.id, status="failed", summary="Retryable failure found."),
                )
                changed = True
        return changed

    def _has_pending_debug_work(self, state: RuntimeState) -> bool:
        return any(
            node.type == "debug" and node.status in {"pending", "ready", "active", "failed", "blocked"}
            for node in state.task_graph.nodes
        )

    def _promote_completed_debug_repairs(self, state: RuntimeState) -> bool:
        changed = False
        completed_debug_nodes = [
            node
            for node in state.task_graph.nodes
            if node.type == "debug" and node.status == "completed"
        ]
        if not completed_debug_nodes:
            return False

        for task in state.task_graph.nodes:
            if task.type == "debug" or task.status not in {"failed", "blocked"}:
                continue
            repair = self._best_debug_repair_for(task, completed_debug_nodes)
            if repair is None:
                continue
            repair_node, result = repair
            evidence = self._debug_repair_promotion_evidence(task, repair_node, result)
            task.status = "completed"
            task.evidence.append(evidence)
            state.completed_tasks = self._add_unique(state.completed_tasks, task.id)
            state.failed_tasks = [task_id for task_id in state.failed_tasks if task_id != task.id]
            state.active_tasks = [task_id for task_id in state.active_tasks if task_id != task.id]
            state.blockers = [
                blocker
                for blocker in state.blockers
                if task.id not in [str(item) for item in blocker.get("task_ids", [])]
            ]
            self._record_history(
                state,
                "debug_repair_promoted",
                f"{task.id} completed from successful debug evidence in {repair_node.id}.",
                task.id,
            )
            changed = True
        return changed

    def _prune_obsolete_debug_tasks(self, state: RuntimeState) -> bool:
        completed_roots = {
            node.id
            for node in state.task_graph.nodes
            if node.type != "debug" and node.status == "completed"
        }
        if not completed_roots:
            return False
        changed = False
        for node in state.task_graph.nodes:
            if node.type != "debug" or node.status in {"completed", "skipped"}:
                continue
            root_id = node.id.split("-DEBUG-", 1)[0]
            if root_id not in completed_roots:
                continue
            node.status = "skipped"
            node.evidence.append(
                {
                    "type": "obsolete_debug_pruned",
                    "summary": f"{node.id} skipped because {root_id} is already completed.",
                    "created_at": utc_now_iso(),
                }
            )
            state.active_tasks = [task_id for task_id in state.active_tasks if task_id != node.id]
            state.failed_tasks = [task_id for task_id in state.failed_tasks if task_id != node.id]
            self._record_history(
                state,
                "obsolete_debug_pruned",
                f"{node.id} skipped because {root_id} is already completed.",
                node.id,
            )
            changed = True
        return changed

    def _best_debug_repair_for(
        self,
        task: TaskNode,
        debug_nodes: list[TaskNode],
    ) -> tuple[TaskNode, dict] | None:
        prefix = f"{task.id}-DEBUG-"
        for debug_node in reversed(debug_nodes):
            if not debug_node.id.startswith(prefix):
                continue
            result = self._latest_worker_result(debug_node)
            if self._debug_result_can_promote_failed_task(result):
                return debug_node, result or {}
        return None

    def _debug_result_can_promote_failed_task(self, result: dict | None) -> bool:
        if not result or result.get("status") != "completed":
            return False
        if result.get("tests_failed"):
            return False
        if result.get("follow_up_tasks"):
            return False
        if self._debug_result_reports_unfinished_repair(result):
            return False
        confidence = _float_or_default(result.get("confidence"), 0.0)
        if confidence < 0.75:
            return False
        if result.get("tests_passed"):
            return True
        commands = result.get("commands_run", [])
        if not isinstance(commands, list) or not commands:
            return False
        return all(
            isinstance(command, dict) and _int_or_default(command.get("exit_code", 1), 1) == 0
            for command in commands
        )

    def _debug_result_reports_unfinished_repair(self, result: dict) -> bool:
        values: list[str] = []
        for key in ("summary", "known_issues", "evidence"):
            value = result.get(key)
            if isinstance(value, str):
                values.append(value)
            elif isinstance(value, list):
                values.extend(str(item) for item in value)
        text = "\n".join(values).lower()
        unfinished_markers = (
            "remains incomplete",
            "still needs",
            "next implementation attempt",
            "implementation retry",
            "repair instructions",
            "retry repair",
            "not yet complete",
            "not complete",
            "not completed",
            "unable to verify",
            "cannot verify",
        )
        return any(marker in text for marker in unfinished_markers)

    def _debug_repair_promotion_evidence(
        self,
        task: TaskNode,
        repair_node: TaskNode,
        result: dict,
    ) -> dict:
        return {
            "type": "worker_result",
            "source": "debug_repair_promotion",
            "summary": f"{task.id} accepted as repaired by successful debug task {repair_node.id}.",
            "result": {
                "task_id": task.id,
                "status": "completed",
                "summary": "Central debug repair gate promoted the failed task after passing verification evidence.",
                "files_changed": list(result.get("files_changed", [])),
                "commands_run": list(result.get("commands_run", [])),
                "tests_passed": list(result.get("tests_passed", [])),
                "tests_failed": [],
                "evidence": [
                    f"Debug task {repair_node.id} completed with confidence {result.get('confidence', 0)}.",
                    str(result.get("summary", "")),
                ],
                "known_issues": list(result.get("known_issues", [])),
                "follow_up_tasks": list(result.get("follow_up_tasks", [])),
                "confidence": _float_or_default(result.get("confidence"), 0.0),
                "raw_output": "",
                "worker_lifecycle": {},
            },
            "agent": self.router.route(task),
            "created_at": utc_now_iso(),
            "trigger_task_id": repair_node.id,
        }

    def _execute_release_task(self, state: RuntimeState, task: TaskNode, iteration: int) -> None:
        self.graph_engine.mark_active(state.task_graph, task.id)
        state.active_tasks = self._add_unique(state.active_tasks, task.id)
        self.state_manager.save(state)

        self._generate_static_ci_before_release(state)

        result = self.github_flow.record_execution(
            repository_path=self.repository_path,
            branch=task.branch or "agent/alchemy-runtime",
            task_ids=list(state.completed_tasks),
            title=f"{task.id}: {task.title}",
            body=self._build_release_body(state),
            collect_ci=self.github_collect_ci,
            ci_wait_seconds=self.github_ci_wait_seconds,
            ci_poll_interval_seconds=self.github_ci_poll_interval_seconds,
            auto_merge=self.github_auto_merge,
        )
        state.github = result.to_dict()
        state.active_tasks = [task_id for task_id in state.active_tasks if task_id != task.id]

        evidence = {
            "type": "ci_result" if result.ci_status != "unknown" else "artifact",
            "summary": result.summary,
            "result": result.to_dict(),
            "agent": self.router.route(task),
            "created_at": utc_now_iso(),
            "iteration": iteration,
        }
        unhealthy_ci_status = result.ci_status in {"failed", "pending"} or (
            self.github_collect_ci and result.ci_status == "unknown"
        )
        if result.status in {"recorded", "pushed"} and not unhealthy_ci_status:
            self.graph_engine.mark_completed(state.task_graph, task.id, evidence)
            state.completed_tasks = self._add_unique(state.completed_tasks, task.id)
            self._record_history(state, "github_evidence_recorded", result.summary, task.id)
            return

        if result.status in {"recorded", "pushed"} and unhealthy_ci_status:
            self.graph_engine.mark_blocked(state.task_graph, task.id, evidence)
            state.failed_tasks = self._add_unique(state.failed_tasks, task.id)
            self._record_blocker(
                state,
                task,
                f"GitHub CI status {result.ci_status} prevented release completion.",
                blocker_type="quality_gate",
            )
            self._record_history(state, "github_flow_blocked", result.summary, task.id)
            return

        self.graph_engine.mark_failed(state.task_graph, task.id, evidence)
        state.failed_tasks = self._add_unique(state.failed_tasks, task.id)
        self._record_history(state, "github_flow_failed", result.summary, task.id)

    def _generate_static_ci_before_release(self, state: RuntimeState) -> None:
        if not state.repository.get("generate_static_ci"):
            return
        existing_report = state.repository.get("generated_ci")
        if isinstance(existing_report, dict) and existing_report.get("status") == "generated":
            workflow_path = str(existing_report.get("workflow_path", ""))
            if workflow_path and (self.repository_path / workflow_path).is_file():
                return
        profile = str(state.repository.get("artifact_profile", "unknown") or "unknown")
        result = StaticWebCIGenerator().generate_if_needed(
            self.repository_path,
            artifact_profile=profile,
            collect_ci=self.github_collect_ci,
            explicit_no_ci=not self.github_collect_ci,
        )
        state.repository["generated_ci"] = result.to_dict()
        if result.status == "generated":
            self._record_history(state, "generated_static_ci", result.summary)

    def _build_release_body(self, state: RuntimeState) -> str:
        completed = ", ".join(state.completed_tasks) or "none"
        return (
            f"Objective: {state.objective}\n\n"
            f"Completed task IDs: {completed}\n\n"
            f"Latest evaluation: {state.evaluation_result.get('reason', 'not evaluated')}"
        )

    def _record_evaluation(self, state: RuntimeState, evaluation: EvaluationResult) -> None:
        state.evaluation_result = evaluation.to_dict()
        self._record_history(state, "evaluation", evaluation.reason)

    def _maybe_apply_repair_convergence(self, state: RuntimeState, task: TaskNode) -> bool:
        config = state.repository.get("repair_convergence", {})
        if not isinstance(config, dict) or not config.get("enabled"):
            return False
        if config.get("status") == "completed":
            return False

        result = self._latest_worker_result(task)
        if not result or result.get("status") != "completed":
            return False
        if result.get("tests_failed") or result.get("known_issues"):
            return False

        target_files = _clean_paths([str(item) for item in config.get("target_files", []) if str(item)])
        if not self._task_matches_repair_targets(task, result, target_files):
            return False
        if not self._worker_result_has_passing_checks(result):
            return False

        for node in state.task_graph.nodes:
            if node.status in {"completed", "skipped"}:
                continue
            evidence = self._repair_convergence_evidence(node, task, result, target_files)
            node.status = "completed"
            node.evidence.append(dict(evidence))
            state.completed_tasks = self._add_unique(state.completed_tasks, node.id)
            state.failed_tasks = [task_id for task_id in state.failed_tasks if task_id != node.id]
        state.active_tasks = []
        state.repository["repair_convergence"] = {
            **config,
            "status": "completed",
            "trigger_task_id": task.id,
            "completed_at": utc_now_iso(),
            "target_files": target_files,
            "tests_passed": [str(item) for item in result.get("tests_passed", [])],
        }
        if not state.github.get("commit") and not state.github.get("pull_request_url"):
            state.github = self._repair_convergence_github_evidence(task, target_files)
        self._record_history(
            state,
            "repair_convergence_gate",
            f"Repair convergence gate completed remaining tasks after {task.id}.",
            task.id,
        )
        evaluation = self.evaluator.evaluate(state)
        self._record_evaluation(state, evaluation)
        state.done = evaluation.done
        return True

    def _latest_worker_result(self, task: TaskNode) -> dict | None:
        for item in reversed(task.evidence):
            result = item.get("result", {}) if isinstance(item, dict) else {}
            if isinstance(result, dict) and result:
                return result
        return None

    def _task_matches_repair_targets(self, task: TaskNode, result: dict, target_files: list[str]) -> bool:
        if not target_files:
            return task.type in {"backend", "frontend", "debug", "test", "integration"}
        target_set = set(_normalized_paths(target_files))
        scoped_files = _normalized_paths(
            [
                *[str(item) for item in result.get("files_changed", []) if str(item)],
                *task.relevant_files,
            ]
        )
        return bool(target_set and target_set.issubset(set(scoped_files)))

    def _worker_result_has_passing_checks(self, result: dict) -> bool:
        if result.get("tests_passed"):
            return True
        commands = result.get("commands_run", [])
        if not isinstance(commands, list) or not commands:
            return False
        for command in commands:
            if not isinstance(command, dict) or _int_or_default(command.get("exit_code", 1), 1) != 0:
                return False
        return True

    def _repair_convergence_evidence(
        self,
        node: TaskNode,
        trigger_task: TaskNode,
        result: dict,
        target_files: list[str],
    ) -> dict:
        tests_passed = [str(item) for item in result.get("tests_passed", [])]
        return {
            "type": "worker_result",
            "source": "repair_convergence_gate",
            "summary": f"Covered by repair convergence after {trigger_task.id}: target files matched and checks passed.",
            "result": {
                "task_id": node.id,
                "status": "completed",
                "summary": "Repair convergence gate completed this remaining task without another worker dispatch.",
                "files_changed": target_files,
                "commands_run": list(result.get("commands_run", [])),
                "tests_passed": tests_passed or ["repair convergence check"],
                "tests_failed": [],
                "evidence": [
                    f"Trigger task {trigger_task.id} completed.",
                    "Target files and required checks converged.",
                ],
                "known_issues": [],
                "follow_up_tasks": [],
                "confidence": 0.9,
                "raw_output": "",
                "worker_lifecycle": {},
            },
            "agent": self.router.route(node),
            "created_at": utc_now_iso(),
            "trigger_task_id": trigger_task.id,
            "target_files": list(target_files),
        }

    def _repair_convergence_github_evidence(self, task: TaskNode, target_files: list[str]) -> dict:
        branch = task.branch or self._default_branch_for_task(task)
        return {
            "status": "recorded",
            "branch": branch,
            "commit": f"dry-run:repair-convergence:{task.id}",
            "pull_request_url": f"dry-run://repair-convergence/{branch}",
            "ci_status": "passed",
            "ci_details": [
                {
                    "name": "repair-convergence",
                    "status": "passed",
                    "summary": f"Target files converged: {', '.join(target_files) or 'unspecified repair scope'}.",
                }
            ],
            "merge": {"status": "skipped", "summary": "Repair convergence used local dry-run delivery evidence."},
            "commands_run": [],
            "summary": "Repair convergence gate recorded dry-run delivery evidence.",
        }

    def _record_worker_lifecycle(self, state: RuntimeState, result: CodexWorkerResult) -> None:
        if not result.worker_lifecycle:
            return
        task_id = str(result.worker_lifecycle.get("task_id", result.task_id))
        state.worker_lifecycle = [
            record for record in state.worker_lifecycle if str(record.get("task_id", "")) != task_id
        ]
        state.worker_lifecycle.append(dict(result.worker_lifecycle))

    def _record_history(self, state: RuntimeState, event_type: str, summary: str, task_id: str = "") -> None:
        payload = {
            "timestamp": utc_now_iso(),
            "type": event_type,
            "summary": summary,
        }
        if task_id:
            payload["task_id"] = task_id
        state.iteration_history.append(payload)

    def _record_blocker(
        self,
        state: RuntimeState,
        task: TaskNode,
        description: str,
        blocker_type: str = "technical_limit",
    ) -> None:
        blocker_id = f"B-{task.id}-{task.retry_count}"
        if any(blocker.get("id") == blocker_id for blocker in state.blockers):
            return
        state.blockers.append(
            {
                "id": blocker_id,
                "type": blocker_type,
                "description": description,
                "required_resolution": "Inspect task evidence and provide a fix, dependency, or revised requirement.",
                "task_ids": [task.id],
                "can_continue_partially": False,
                "created_at": utc_now_iso(),
            }
        )

    def _record_external_stop(self, state: RuntimeState, reason: str) -> None:
        blocker_id = "B-RUN-STOPPED"
        if not any(blocker.get("id") == blocker_id for blocker in state.blockers):
            state.blockers.append(
                {
                    "id": blocker_id,
                    "type": "operator_control",
                    "description": reason,
                    "required_resolution": "Resume or start a new run when the operator is ready.",
                    "task_ids": [],
                    "can_continue_partially": True,
                    "created_at": utc_now_iso(),
                }
            )
        self._record_history(state, "run_stopped", reason)

    def _non_partial_blocker_ids(self, state: RuntimeState) -> set[str]:
        blocker_ids: set[str] = set()
        for blocker in state.blockers:
            if blocker.get("can_continue_partially", False):
                continue
            blocker_id = str(blocker.get("id", "")).strip()
            if blocker_id:
                blocker_ids.add(blocker_id)
        return blocker_ids

    def _default_branch_for_task(self, task: TaskNode) -> str:
        slug = "".join(char.lower() if char.isalnum() else "-" for char in task.title).strip("-")
        while "--" in slug:
            slug = slug.replace("--", "-")
        return f"agent/{task.id.lower()}-{slug[:40]}"

    def _add_unique(self, values: list[str], value: str) -> list[str]:
        if value not in values:
            values.append(value)
        return values


def _backtick_phrases(text: str) -> list[str]:
    phrases: list[str] = []
    parts = text.split("`")
    for index in range(1, len(parts), 2):
        phrase = parts[index].strip()
        if phrase:
            phrases.append(phrase)
    return phrases


def _debug_evidence_text(task: TaskNode) -> list[str]:
    fragments: list[str] = []
    for item in task.evidence:
        if not isinstance(item, dict):
            continue
        for key in ("summary", "reason", "message"):
            value = item.get(key)
            if isinstance(value, str):
                fragments.append(value)
        result = item.get("result")
        if isinstance(result, dict):
            fragments.extend(_result_text_fragments(result))
    return fragments


def _result_text_fragments(payload: dict) -> list[str]:
    fragments: list[str] = []
    for key in ("summary", "known_issues", "follow_up_tasks", "tests_failed", "evidence"):
        value = payload.get(key)
        fragments.extend(_value_text_fragments(value))
    return fragments


def _value_text_fragments(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        fragments: list[str] = []
        for nested in value.values():
            fragments.extend(_value_text_fragments(nested))
        return fragments
    if isinstance(value, list):
        fragments: list[str] = []
        for item in value:
            fragments.extend(_value_text_fragments(item))
        return fragments
    return []


def _deferred_repo_paths_from_result(result: CodexWorkerResult) -> list[str]:
    fragments: list[str] = [
        result.summary,
        *result.known_issues,
        *result.follow_up_tasks,
        *result.tests_failed,
        *result.evidence,
        result.raw_output,
    ]
    for command in result.commands_run:
        fragments.extend([command.command, command.summary, command.stdout, command.stderr])
    text = "\n".join(fragment for fragment in fragments if fragment)
    paths = [match.group(1) for match in REPO_PATH_TOKEN_RE.finditer(text)]
    return _clean_paths(paths)


def _any_path_matches_scope(paths: list[str], scope_patterns: list[str]) -> bool:
    clean_scope = _clean_paths(scope_patterns)
    for path in paths:
        for variant in _repo_path_variants(path):
            if any(_repo_path_matches_pattern(variant, pattern) for pattern in clean_scope):
                return True
    return False


def _repo_path_variants(path: str) -> list[str]:
    clean_paths = _clean_paths([path])
    if not clean_paths:
        return []
    normalized = clean_paths[0]
    variants = {normalized}
    if normalized.startswith("internal/") or normalized.startswith("cmd/") or normalized.startswith("ent/"):
        variants.add(f"backend/{normalized}")
    if normalized.startswith("src/"):
        variants.add(f"frontend/{normalized}")
    return sorted(variants)


def _repo_path_matches_pattern(path: str, pattern: str) -> bool:
    normalized = path.lower()
    clean = pattern.lower()
    if clean.endswith("/**") and not _repo_pattern_has_glob_meta(clean[:-3]):
        prefix = clean[:-3].rstrip("/")
        return normalized == prefix or normalized.startswith(prefix + "/")
    if clean.endswith("/*") and not _repo_pattern_has_glob_meta(clean[:-2]):
        prefix = clean[:-2].rstrip("/")
        if not normalized.startswith(prefix + "/"):
            return False
        return "/" not in normalized[len(prefix) + 1 :]
    if clean.endswith("/") and not _repo_pattern_has_glob_meta(clean):
        return normalized.startswith(clean)
    if any(char in clean for char in "*?["):
        return _repo_segment_glob_matches(normalized, clean)
    return normalized == clean


def _repo_pattern_has_glob_meta(pattern: str) -> bool:
    return any(char in pattern for char in "*?[")


def _repo_segment_glob_matches(path: str, pattern: str) -> bool:
    path_parts = [part for part in path.replace("\\", "/").strip("/").split("/") if part]
    pattern_parts = [part for part in pattern.replace("\\", "/").strip("/").split("/") if part]
    return _repo_match_path_segments(path_parts, pattern_parts)


def _repo_match_path_segments(path_parts: list[str], pattern_parts: list[str]) -> bool:
    if not pattern_parts:
        return not path_parts
    head, *tail = pattern_parts
    if head == "**":
        if _repo_match_path_segments(path_parts, tail):
            return True
        return bool(path_parts) and _repo_match_path_segments(path_parts[1:], pattern_parts)
    if not path_parts:
        return False
    if not fnmatch.fnmatchcase(path_parts[0], head):
        return False
    return _repo_match_path_segments(path_parts[1:], tail)


def _worker_result_timed_out(result: CodexWorkerResult | dict | None) -> bool:
    if result is None:
        return False

    if isinstance(result, CodexWorkerResult):
        lifecycle = result.worker_lifecycle
        text_values: list[object] = [result.summary]
    elif isinstance(result, dict):
        raw_lifecycle = result.get("worker_lifecycle", {})
        lifecycle = raw_lifecycle if isinstance(raw_lifecycle, dict) else {}
        text_values = [result.get("summary", "")]
    else:
        return False

    if str(lifecycle.get("status", "")).lower() == "timed_out":
        return True
    if lifecycle.get("timed_out_at"):
        return True
    status = getattr(result, "status", "") if isinstance(result, CodexWorkerResult) else result.get("status", "")
    if str(status).lower() == "timed_out":
        return True

    text = "\n".join(fragment.lower() for value in text_values for fragment in _value_text_fragments(value))
    timeout_markers = (
        "codex worker timed out",
        "worker timed out",
        "timed out after",
    )
    return any(marker in text for marker in timeout_markers)


def _worker_result_boundary_violation(result: CodexWorkerResult | dict | None) -> bool:
    if result is None:
        return False

    if isinstance(result, CodexWorkerResult):
        if not result.files_changed:
            return False
        text_values: list[object] = [result.summary, *result.known_issues]
    elif isinstance(result, dict):
        if not _list(result.get("files_changed")):
            return False
        text_values = [result.get("summary", ""), result.get("known_issues", [])]
    else:
        return False

    text = "\n".join(fragment.lower() for value in text_values for fragment in _value_text_fragments(value))
    return (
        "outside the task boundary" in text
        or "out-of-scope files changed" in text
        or "outside allowed_files" in text
    )


def _worker_result_final_gate_failure_summary(result: CodexWorkerResult | dict | None) -> str:
    if result is None:
        return ""

    if isinstance(result, CodexWorkerResult):
        summary = result.summary
        text_values: list[object] = [
            result.summary,
            result.tests_failed,
            result.known_issues,
            result.evidence,
            result.follow_up_tasks,
            result.raw_output,
        ]
        for command in result.commands_run:
            text_values.extend([command.summary, command.stdout, command.stderr])
    elif isinstance(result, dict):
        summary = str(result.get("summary", "") or "")
        text_values = [
            summary,
            result.get("tests_failed", []),
            result.get("known_issues", []),
            result.get("evidence", []),
            result.get("follow_up_tasks", []),
            result.get("raw_output", ""),
        ]
        for command in _list(result.get("commands_run", [])):
            if isinstance(command, dict):
                text_values.extend(
                    [
                        str(command.get("summary", "") or ""),
                        str(command.get("stdout", "") or ""),
                        str(command.get("stderr", "") or ""),
                    ]
                )
    else:
        return ""

    text = "\n".join(fragment.lower() for value in text_values for fragment in _value_text_fragments(value))
    markers = (
        "final_audit_status=fail",
        "final_audit_status: fail",
        "final_audit_status is failed",
        "simulation_test_status=fail",
        "simulation_test_status: fail",
        "simulation_test_status is failed",
        "real_test_status=fail",
        "real_test_status: fail",
        "real_test_status is failed",
    )
    if not any(marker in text for marker in markers):
        return ""
    return summary or "Final verification gate reported FAIL."


def _worker_result_environment_blocker_summary(result: CodexWorkerResult | dict | None) -> str:
    if result is None:
        return ""
    raw_text_parts: list[str] = []
    status = ""
    if isinstance(result, CodexWorkerResult):
        status = str(result.status or "").lower()
        commands = result.commands_run
        text_parts = [
            result.summary,
            *result.known_issues,
            *result.tests_failed,
        ]
        raw_text_parts.append(result.raw_output)
        for command in commands:
            text_parts.extend([command.summary, command.stderr])
            raw_text_parts.append(command.stdout)
    else:
        status = str(result.get("status", "") or "").lower()
        commands = _list(result.get("commands_run", []))
        text_parts = [
            str(result.get("summary", "") or ""),
            *[str(item) for item in _list(result.get("known_issues", []))],
            *[str(item) for item in _list(result.get("tests_failed", []))],
        ]
        raw_text_parts.append(str(result.get("raw_output", "") or ""))
        for command in commands:
            if isinstance(command, dict):
                text_parts.extend(
                    [
                        str(command.get("summary", "") or ""),
                        str(command.get("stderr", "") or ""),
                    ]
                )
                raw_text_parts.append(str(command.get("stdout", "") or ""))
            else:
                text_parts.append(str(command))
    text = "\n".join(part for part in text_parts if part).lower()
    raw_text = "\n".join(part for part in raw_text_parts if part).lower()
    raw_environment_patterns_are_authoritative = status == "blocked"
    usage_limit_in_structured_error = raw_environment_patterns_are_authoritative and any(
        _codex_usage_limit_message(part) for part in raw_text_parts if part
    )
    has_environment_pattern = any(pattern in text for pattern in ENVIRONMENT_BLOCKER_PATTERNS)
    structured_product_failure = any(pattern in text for pattern in STRUCTURED_PRODUCT_FAILURE_PATTERNS)
    if raw_environment_patterns_are_authoritative:
        raw_has_environment_pattern = any(pattern in raw_text for pattern in NON_USAGE_ENVIRONMENT_BLOCKER_PATTERNS)
        if raw_has_environment_pattern and not structured_product_failure:
            has_environment_pattern = True
    if not has_environment_pattern and not usage_limit_in_structured_error:
        return ""
    return (
        "Worker environment or local Codex CLI availability blocked execution. "
        "Evidence indicates missing dependencies, unavailable verification tooling, local Codex usage limits, "
        "or local Codex connectivity failures."
    )


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(value)
    return result


def _dedupe_path_objects(values: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value.resolve()).lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(value)
    return result


def _normalized_paths(values: list[str]) -> list[str]:
    return [value.lower() for value in _clean_paths(values)]


def _clean_paths(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.replace("\\", "/").strip().strip("/")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _expand_package_lockfile_boundaries(paths: list[str]) -> list[str]:
    result = list(paths)
    seen = {path.lower() for path in result}
    for path in paths:
        if path == "package.json":
            prefix = ""
        elif path.endswith("/package.json"):
            prefix = path.rsplit("/", 1)[0]
        else:
            continue

        for companion in PACKAGE_LOCKFILE_COMPANIONS:
            candidate = f"{prefix}/{companion}" if prefix else companion
            normalized = candidate.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            result.append(candidate)
    return result


def _int_or_default(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _float_or_default(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
