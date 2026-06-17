"""Top-level runtime orchestrator."""

from __future__ import annotations

from pathlib import Path

from .agent_router import AgentRouter
from .codex_worker import CodexWorkerAdapter, CodexWorkerInput
from .evaluator import EvaluationResult, Evaluator
from .models import RuntimeState, TaskNode, utc_now_iso
from .state_manager import StateManager
from .task_graph_engine import TaskGraphEngine


class Orchestrator:
    """Coordinate graph selection, worker execution, state updates, and evaluation."""

    def __init__(
        self,
        state_manager: StateManager,
        graph_engine: TaskGraphEngine | None = None,
        router: AgentRouter | None = None,
        worker: CodexWorkerAdapter | None = None,
        evaluator: Evaluator | None = None,
    ) -> None:
        self.state_manager = state_manager
        self.graph_engine = graph_engine or TaskGraphEngine()
        self.router = router or AgentRouter()
        self.worker = worker or CodexWorkerAdapter()
        self.evaluator = evaluator or Evaluator()

    @classmethod
    def for_project(cls, project_dir: str | Path, state_file: str = ".alchemy/state.json") -> "Orchestrator":
        return cls(StateManager(Path(project_dir) / state_file))

    def initialize(self, objective: str, reset: bool = False) -> RuntimeState:
        if reset and self.state_manager.state_path.exists():
            self.state_manager.state_path.unlink()
        return self.state_manager.load_or_initialize(objective, self.graph_engine)

    def run(self, objective: str, max_iterations: int = 20, reset: bool = False) -> RuntimeState:
        state = self.initialize(objective, reset=reset)
        for iteration in range(1, max_iterations + 1):
            evaluation = self.evaluator.evaluate(state)
            self._record_evaluation(state, evaluation)
            if evaluation.done:
                state.done = True
                self.state_manager.save(state)
                return state

            ready_tasks = self.graph_engine.get_ready_tasks(state.task_graph)
            if not ready_tasks:
                self._record_history(state, "no_ready_tasks", "No ready tasks were available.")
                self.state_manager.save(state)
                return state

            for task in ready_tasks:
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
        self.graph_engine.mark_active(state.task_graph, task.id)
        state.active_tasks = self._add_unique(state.active_tasks, task.id)
        self.state_manager.save(state)

        worker_input = CodexWorkerInput(
            task_id=task.id,
            goal=self.router.build_worker_goal(task),
            context_files=[],
            constraints=[],
        )
        result = self.worker.execute(worker_input)
        evidence = {
            "type": "worker_result",
            "summary": result.logs,
            "result": result.to_dict(),
            "agent": self.router.route(task),
            "created_at": utc_now_iso(),
            "iteration": iteration,
        }

        state.active_tasks = [task_id for task_id in state.active_tasks if task_id != task.id]
        if result.status == "passed":
            self.graph_engine.mark_completed(state.task_graph, task.id, evidence)
            state.completed_tasks = self._add_unique(state.completed_tasks, task.id)
            state.failed_tasks = [task_id for task_id in state.failed_tasks if task_id != task.id]
            self._record_history(state, "task_completed", f"{task.id} completed.")
            return

        self.graph_engine.mark_failed(state.task_graph, task.id, evidence)
        state.failed_tasks = self._add_unique(state.failed_tasks, task.id)
        self._record_history(state, "task_failed", f"{task.id} returned {result.status}.")

    def _record_evaluation(self, state: RuntimeState, evaluation: EvaluationResult) -> None:
        state.evaluation_result = evaluation.to_dict()
        self._record_history(state, "evaluation", evaluation.reason)

    def _record_history(self, state: RuntimeState, event_type: str, summary: str) -> None:
        state.iteration_history.append(
            {
                "timestamp": utc_now_iso(),
                "type": event_type,
                "summary": summary,
            }
        )

    def _add_unique(self, values: list[str], value: str) -> list[str]:
        if value not in values:
            values.append(value)
        return values
