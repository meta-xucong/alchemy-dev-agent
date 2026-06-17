"""Shared runtime data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

TaskStatus = Literal["pending", "ready", "active", "blocked", "completed", "failed", "skipped"]
TaskType = Literal["architecture", "backend", "frontend", "test", "debug", "review", "documentation", "integration", "release"]
AgentName = Literal["architect", "backend", "frontend", "test", "debug", "reviewer"]


def utc_now_iso() -> str:
    """Return a stable UTC timestamp for persisted runtime events."""

    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class TaskNode:
    id: str
    title: str
    description: str
    type: TaskType
    assigned_agent: AgentName
    status: TaskStatus = "pending"
    dependencies: list[str] = field(default_factory=list)
    completion_criteria: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    retry_count: int = 0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TaskNode":
        return cls(
            id=str(payload["id"]),
            title=str(payload["title"]),
            description=str(payload["description"]),
            type=payload["type"],
            assigned_agent=payload["assigned_agent"],
            status=payload.get("status", "pending"),
            dependencies=list(payload.get("dependencies", [])),
            completion_criteria=list(payload.get("completion_criteria", [])),
            evidence=list(payload.get("evidence", [])),
            retry_count=int(payload.get("retry_count", 0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "type": self.type,
            "assigned_agent": self.assigned_agent,
            "status": self.status,
            "dependencies": list(self.dependencies),
            "completion_criteria": list(self.completion_criteria),
            "evidence": list(self.evidence),
            "retry_count": self.retry_count,
        }


@dataclass(slots=True)
class Dependency:
    source: str
    target: str
    type: str = "blocks"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Dependency":
        return cls(
            source=str(payload["from"]),
            target=str(payload["to"]),
            type=str(payload.get("type", "blocks")),
        )

    def to_dict(self) -> dict[str, str]:
        return {"from": self.source, "to": self.target, "type": self.type}


@dataclass(slots=True)
class TaskGraph:
    graph_id: str
    version: int
    nodes: list[TaskNode]
    dependencies: list[Dependency] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TaskGraph":
        return cls(
            graph_id=str(payload["graph_id"]),
            version=int(payload.get("version", 1)),
            nodes=[TaskNode.from_dict(node) for node in payload.get("nodes", [])],
            dependencies=[Dependency.from_dict(dep) for dep in payload.get("dependencies", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "version": self.version,
            "nodes": [node.to_dict() for node in self.nodes],
            "dependencies": [dep.to_dict() for dep in self.dependencies],
        }


@dataclass(slots=True)
class RuntimeState:
    objective: str
    task_graph: TaskGraph
    active_tasks: list[str] = field(default_factory=list)
    completed_tasks: list[str] = field(default_factory=list)
    failed_tasks: list[str] = field(default_factory=list)
    evaluation_result: dict[str, Any] = field(default_factory=dict)
    iteration_history: list[dict[str, Any]] = field(default_factory=list)
    done: bool = False
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeState":
        return cls(
            objective=str(payload["objective"]),
            task_graph=TaskGraph.from_dict(payload["task_graph"]),
            active_tasks=list(payload.get("active_tasks", [])),
            completed_tasks=list(payload.get("completed_tasks", [])),
            failed_tasks=list(payload.get("failed_tasks", [])),
            evaluation_result=dict(payload.get("evaluation_result", {})),
            iteration_history=list(payload.get("iteration_history", [])),
            done=bool(payload.get("done", False)),
            created_at=str(payload.get("created_at", utc_now_iso())),
            updated_at=str(payload.get("updated_at", utc_now_iso())),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "task_graph": self.task_graph.to_dict(),
            "active_tasks": list(self.active_tasks),
            "completed_tasks": list(self.completed_tasks),
            "failed_tasks": list(self.failed_tasks),
            "evaluation_result": dict(self.evaluation_result),
            "iteration_history": list(self.iteration_history),
            "done": self.done,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
