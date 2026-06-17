"""Task-to-agent routing."""

from __future__ import annotations

from .models import AgentName, TaskNode


class AgentRouter:
    """Resolve the responsible agent for a task."""

    DEFAULT_ROUTES: dict[str, AgentName] = {
        "architecture": "architect",
        "backend": "backend",
        "frontend": "frontend",
        "test": "test",
        "debug": "debug",
        "review": "reviewer",
        "documentation": "architect",
        "integration": "backend",
        "release": "reviewer",
    }

    def route(self, task: TaskNode) -> AgentName:
        if task.assigned_agent:
            return task.assigned_agent
        try:
            return self.DEFAULT_ROUTES[task.type]
        except KeyError as exc:
            raise ValueError(f"No agent route for task type {task.type!r}") from exc

    def build_worker_goal(self, task: TaskNode) -> str:
        agent = self.route(task)
        return f"[{agent}] {task.title}: {task.description}"
