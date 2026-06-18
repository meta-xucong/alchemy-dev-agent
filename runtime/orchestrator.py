"""Top-level runtime orchestrator."""

from __future__ import annotations

from pathlib import Path

from .agent_router import AgentRouter
from .control import ExecutionController, NoopExecutionController
from .codex_worker import CodexWorkerAdapter, CodexWorkerInput, CodexWorkerResult, CommandResult
from .evaluator import EvaluationResult, Evaluator
from .github_flow import GitHubFlow
from .models import RuntimeState, TaskGraph, TaskNode, utc_now_iso
from .state_manager import StateManager
from .task_graph_engine import TaskGraphEngine


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
    ) -> None:
        self.state_manager = state_manager
        self.graph_engine = graph_engine or TaskGraphEngine()
        self.router = router or AgentRouter()
        self.worker = worker or CodexWorkerAdapter()
        self.evaluator = evaluator or Evaluator()
        self.github_flow = github_flow or GitHubFlow()
        self.controller = controller or NoopExecutionController()
        self.repository_path = Path(repository_path)

    @classmethod
    def for_project(
        cls,
        project_dir: str | Path,
        state_file: str = ".alchemy/state.json",
        *,
        real_codex: bool = False,
        real_github: bool = False,
        codex_executable: str = "codex",
        max_worker_seconds: int = 1800,
    ) -> "Orchestrator":
        project_path = Path(project_dir)
        return cls(
            StateManager(project_path / state_file),
            worker=CodexWorkerAdapter(
                executable=codex_executable,
                dry_run=not real_codex,
                timeout_seconds=max_worker_seconds,
            ),
            github_flow=GitHubFlow(dry_run=not real_github),
            repository_path=project_path,
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
            evaluation = self.evaluator.evaluate(state)
            self._record_evaluation(state, evaluation)
            if evaluation.done:
                state.done = True
                self.state_manager.save(state)
                return state

            ready_tasks = self.graph_engine.get_ready_tasks(state.task_graph)
            if not ready_tasks:
                if self._handle_retryable_failures(state):
                    self.state_manager.save(state)
                    continue
                self._record_history(state, "no_ready_tasks", "No ready tasks were available.")
                self.state_manager.save(state)
                return state

            for task in ready_tasks:
                decision = self.controller.before_task(task.id)
                if decision.action == "stop":
                    self._record_external_stop(state, decision.reason or "Run stopped before task dispatch.")
                    self.state_manager.save(state)
                    return state
                if decision.action == "pause":
                    self._record_history(state, "run_paused", decision.reason or "Run paused before task dispatch.", task.id)
                    self.state_manager.save(state)
                    return state
                self.execute_task(state, task, iteration)

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
            self._record_blocker(state, task, result.summary)
            self._record_history(state, "task_blocked", f"{task.id} blocked.", task.id)
            return

        self.graph_engine.mark_failed(state.task_graph, task.id, evidence)
        state.failed_tasks = self._add_unique(state.failed_tasks, task.id)
        self._record_history(state, "task_failed", f"{task.id} returned {result.status}.", task.id)
        self._handle_failed_task(state, task, result)

    def _can_execute_deterministically(self, task: TaskNode) -> bool:
        if task.type == "review":
            return True
        return task.type == "test" and task.commands_to_run == ["static document inspection"]

    def _execute_deterministic_task(self, state: RuntimeState, task: TaskNode, iteration: int) -> None:
        self.graph_engine.mark_active(state.task_graph, task.id)
        state.active_tasks = self._add_unique(state.active_tasks, task.id)
        self.state_manager.save(state)

        if task.type == "review":
            result = self._review_result(state, task)
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

        self.graph_engine.mark_failed(state.task_graph, task.id, evidence)
        state.failed_tasks = self._add_unique(state.failed_tasks, task.id)
        self._record_history(state, "task_failed", f"{task.id} deterministic check returned {result.status}.", task.id)
        self._handle_failed_task(state, task, result)

    def _static_document_result(self, task: TaskNode) -> CodexWorkerResult:
        paths = [Path(self.repository_path) / path for path in task.relevant_files]
        missing = [str(path.relative_to(self.repository_path)) for path in paths if not path.exists()]
        evidence: list[str] = []
        tests_failed: list[str] = []
        if missing:
            tests_failed.extend(f"Missing required file: {path}" for path in missing)
        for path in paths:
            if path.exists():
                relative = str(path.relative_to(self.repository_path))
                text = path.read_text(encoding="utf-8", errors="replace")
                evidence.append(f"Found required file: {relative}")
                for expected in self._expected_document_phrases(task.completion_criteria):
                    if expected.lower() in text.lower():
                        evidence.append(f"Found expected phrase in {relative}: {expected}")
                    else:
                        tests_failed.append(f"Missing expected phrase in {relative}: {expected}")
        if not paths:
            evidence.append("No task-specific document files were required.")
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
            constraints=self._constraints_for_task(task),
            commands_to_run=list(task.commands_to_run),
            retry_context=retry_context,
        )

    def _allowed_files_for_task(self, task: TaskNode) -> list[str]:
        if task.type in {"architecture", "review", "test"}:
            return []
        return list(task.relevant_files)

    def _constraints_for_task(self, task: TaskNode) -> list[str]:
        constraints = [
            "Do not edit files outside allowed_files.",
            "If allowed_files is empty, do not edit repository files.",
        ]
        if not self._allowed_files_for_task(task):
            constraints.append("Return partial or blocked if the task requires repository edits.")
        return constraints

    def _worker_evidence(self, task: TaskNode, result: CodexWorkerResult, iteration: int) -> dict:
        return {
            "type": "worker_result",
            "summary": result.summary,
            "result": result.to_dict(),
            "agent": self.router.route(task),
            "created_at": utc_now_iso(),
            "iteration": iteration,
        }

    def _handle_failed_task(self, state: RuntimeState, task: TaskNode, result: CodexWorkerResult) -> None:
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

    def _execute_release_task(self, state: RuntimeState, task: TaskNode, iteration: int) -> None:
        self.graph_engine.mark_active(state.task_graph, task.id)
        state.active_tasks = self._add_unique(state.active_tasks, task.id)
        self.state_manager.save(state)

        result = self.github_flow.record_execution(
            repository_path=self.repository_path,
            branch=task.branch or "agent/alchemy-runtime",
            task_ids=list(state.completed_tasks),
            title=f"{task.id}: {task.title}",
            body=self._build_release_body(state),
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
        if result.status in {"recorded", "pushed"}:
            self.graph_engine.mark_completed(state.task_graph, task.id, evidence)
            state.completed_tasks = self._add_unique(state.completed_tasks, task.id)
            self._record_history(state, "github_evidence_recorded", result.summary, task.id)
            return

        self.graph_engine.mark_failed(state.task_graph, task.id, evidence)
        state.failed_tasks = self._add_unique(state.failed_tasks, task.id)
        self._record_history(state, "github_flow_failed", result.summary, task.id)

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
