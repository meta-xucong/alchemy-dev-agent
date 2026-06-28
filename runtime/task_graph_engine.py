"""Dependency-aware task graph operations."""

from __future__ import annotations

from collections.abc import Iterable

from .models import Dependency, TaskGraph, TaskNode


class TaskGraphEngine:
    """Create and evaluate a deterministic task graph."""

    def create_default_graph(self, objective: str) -> TaskGraph:
        """Create a minimal graph that exercises all runtime roles."""

        normalized = " ".join(objective.strip().split()) or "autonomous development objective"
        nodes = [
            TaskNode(
                id="T001",
                title="Architect task graph",
                description=f"Turn the objective into an executable task plan: {normalized}",
                type="architecture",
                assigned_agent="architect",
                completion_criteria=["Task graph and runtime plan are defined."],
                commands_to_run=["python -m unittest discover -s tests"],
            ),
            TaskNode(
                id="T002",
                title="Execute implementation task",
                description=f"Perform the smallest implementation step for: {normalized}",
                type="backend",
                assigned_agent="backend",
                dependencies=["T001"],
                completion_criteria=["Worker returns a passed result with execution evidence."],
                relevant_files=["runtime", "tests"],
                commands_to_run=["python -m unittest discover -s tests"],
            ),
            TaskNode(
                id="T003",
                title="Verify implementation",
                description="Run deterministic verification over the completed implementation task.",
                type="test",
                assigned_agent="test",
                dependencies=["T002"],
                completion_criteria=["Verification task passes and records evidence."],
                commands_to_run=["python -m unittest discover -s tests"],
            ),
            TaskNode(
                id="T004",
                title="Review final result",
                description="Review task evidence and decide whether the run can finish.",
                type="review",
                assigned_agent="reviewer",
                dependencies=["T003"],
                completion_criteria=["Reviewer score supports final evaluation gate."],
                commands_to_run=["python -m unittest discover -s tests"],
            ),
            TaskNode(
                id="T005",
                title="Record GitHub execution evidence",
                description="Record branch, commit, pull request, or dry-run GitHub execution evidence.",
                type="release",
                assigned_agent="reviewer",
                dependencies=["T004"],
                completion_criteria=["GitHub sync evidence is present in runtime state."],
            ),
        ]
        dependencies = [
            Dependency(source="T001", target="T002", type="blocks"),
            Dependency(source="T002", target="T003", type="requires_test_pass"),
            Dependency(source="T003", target="T004", type="requires_review"),
            Dependency(source="T004", target="T005", type="requires_review"),
        ]
        return TaskGraph(graph_id="runtime-v0.1-default", version=1, nodes=nodes, dependencies=dependencies)

    def get_ready_tasks(self, graph: TaskGraph) -> list[TaskNode]:
        ready: list[TaskNode] = []
        completed_ids = {node.id for node in graph.nodes if node.status in {"completed", "skipped"}}
        for node in graph.nodes:
            if node.status not in {"pending", "ready"}:
                continue
            if all(dep_id in completed_ids for dep_id in node.dependencies):
                node.status = "ready"
                ready.append(node)
        return sorted(ready, key=lambda task: (-task.priority, task.id))

    def get_node(self, graph: TaskGraph, task_id: str) -> TaskNode:
        for node in graph.nodes:
            if node.id == task_id:
                return node
        raise KeyError(f"Unknown task id: {task_id}")

    def mark_active(self, graph: TaskGraph, task_id: str) -> TaskNode:
        node = self.get_node(graph, task_id)
        node.status = "active"
        return node

    def mark_completed(self, graph: TaskGraph, task_id: str, evidence: dict) -> TaskNode:
        node = self.get_node(graph, task_id)
        node.status = "completed"
        node.evidence.append(evidence)
        return node

    def mark_skipped(self, graph: TaskGraph, task_id: str, evidence: dict) -> TaskNode:
        node = self.get_node(graph, task_id)
        node.status = "skipped"
        node.evidence.append(evidence)
        return node

    def mark_failed(self, graph: TaskGraph, task_id: str, evidence: dict) -> TaskNode:
        node = self.get_node(graph, task_id)
        node.status = "failed"
        node.retry_count += 1
        node.evidence.append(evidence)
        return node

    def mark_blocked(self, graph: TaskGraph, task_id: str, evidence: dict) -> TaskNode:
        node = self.get_node(graph, task_id)
        node.status = "blocked"
        node.evidence.append(evidence)
        return node

    def can_retry(self, task: TaskNode) -> bool:
        return task.retry_count < task.max_attempts

    def reset_for_retry(self, task: TaskNode) -> None:
        task.status = "pending"

    def create_debug_task(self, graph: TaskGraph, failed_task: TaskNode, reason: str) -> TaskNode:
        debug_id = f"{failed_task.id}-DEBUG-{failed_task.retry_count}"
        for node in graph.nodes:
            if node.id == debug_id:
                return node

        debug_task = TaskNode(
            id=debug_id,
            title=f"Debug {failed_task.id}",
            description=f"Diagnose and repair failure for {failed_task.title}. Failure summary: {reason}",
            type="debug",
            assigned_agent="debug",
            dependencies=[],
            completion_criteria=[
                "Failure diagnosis is recorded.",
                "A retry attempt has new repair instructions.",
            ],
            priority=max(100, failed_task.priority + 10),
            relevant_files=debug_task_relevant_files(failed_task),
            commands_to_run=list(failed_task.commands_to_run),
            boundary_mode=failed_task.boundary_mode,
        )
        graph.nodes.append(debug_task)
        return debug_task

    def all_required_complete(self, graph: TaskGraph) -> bool:
        return all(node.status in {"completed", "skipped"} for node in graph.nodes)

    def failed_required_tasks(self, graph: TaskGraph) -> list[TaskNode]:
        return [node for node in graph.nodes if node.status in {"failed", "blocked"}]

    def dependency_edges_for(self, graph: TaskGraph, task_ids: Iterable[str]) -> list[Dependency]:
        selected = set(task_ids)
        return [dep for dep in graph.dependencies if dep.source in selected or dep.target in selected]


def debug_task_relevant_files(failed_task: TaskNode) -> list[str]:
    if failed_task.type in {"architecture", "review", "test"}:
        return []
    return list(failed_task.relevant_files)
