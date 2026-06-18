"""Plan-to-execution handoff for document-driven runtime graphs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from context.models import ContextBundle
from intake.models import ProjectBrief

from .agent_router import AgentRouter
from .codex_worker import CodexWorkerInput
from .models import Dependency, RuntimeState, TaskGraph, TaskNode


@dataclass(slots=True)
class RuntimeHandoff:
    """Create runtime-ready state and worker packages from planning outputs."""

    router: AgentRouter = AgentRouter()

    def build_state(
        self,
        *,
        project_brief: ProjectBrief | dict[str, Any],
        context_bundle: ContextBundle | dict[str, Any],
        task_graph: TaskGraph,
        repository_path: str | Path | None = None,
    ) -> RuntimeState:
        brief_payload = project_brief.to_dict() if isinstance(project_brief, ProjectBrief) else dict(project_brief)
        context_payload = context_bundle.to_dict() if isinstance(context_bundle, ContextBundle) else dict(context_bundle)
        repository = brief_payload.get("repository") or {}
        resolved_repository_path = str(repository_path or repository.get("local_path") or ".")
        blockers = list(brief_payload.get("blockers", [])) + list(context_payload.get("blockers", []))
        executable_graph = ensure_release_task(task_graph)
        state = RuntimeState(
            objective=str(brief_payload.get("objective") or context_payload.get("objective") or ""),
            task_graph=executable_graph,
            blockers=blockers,
            repository={
                "provider": repository.get("provider", "local") if isinstance(repository, dict) else "local",
                "path": resolved_repository_path,
                "source": repository if isinstance(repository, dict) else {},
                "project_id": str(brief_payload.get("project_id", context_payload.get("project_id", ""))),
            },
            done_criteria=[
                "Required graph nodes are completed.",
                "Required tests or checks pass.",
                "Reviewer approval is recorded.",
                "Final gate score is at least 0.85.",
                "GitHub execution evidence is recorded.",
                "Document requirements are traced to completed task IDs.",
            ],
        )
        return state

    def build_worker_input(
        self,
        *,
        state: RuntimeState,
        task: TaskNode,
        repository_path: str | Path | None = None,
        constraints: list[str] | None = None,
    ) -> CodexWorkerInput:
        upstream = [dependency.source for dependency in state.task_graph.dependencies if dependency.target == task.id]
        return CodexWorkerInput(
            task_id=task.id,
            goal=self.router.build_worker_goal(task),
            objective=state.objective,
            task_description=task.description,
            acceptance_criteria=list(task.completion_criteria),
            repository_path=str(repository_path or state.repository.get("path") or "."),
            branch=task.branch or default_branch_for_task(task),
            agent_context={
                "assigned_agent": self.router.route(task),
                "task_type": task.type,
                "upstream_tasks": upstream,
                "source": "document_to_plan_handoff",
            },
            relevant_files=list(task.relevant_files),
            allowed_files=allowed_files_for_task(task),
            constraints=[*boundary_constraints_for_task(task), *list(constraints or [])],
            commands_to_run=list(task.commands_to_run),
        )

    def build_worker_inputs(
        self,
        *,
        state: RuntimeState,
        repository_path: str | Path | None = None,
        constraints: list[str] | None = None,
    ) -> list[CodexWorkerInput]:
        return [
            self.build_worker_input(
                state=state,
                task=task,
                repository_path=repository_path,
                constraints=constraints,
            )
            for task in state.task_graph.nodes
            if task.type != "release"
        ]


def default_branch_for_task(task: TaskNode) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in task.title).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return f"agent/{task.id.lower()}-{slug[:40]}"


def allowed_files_for_task(task: TaskNode) -> list[str]:
    if task.type in {"architecture", "review", "test"}:
        return []
    return list(task.relevant_files)


def boundary_constraints_for_task(task: TaskNode) -> list[str]:
    constraints = [
        "Do not edit files outside allowed_files.",
        "If allowed_files is empty, do not edit repository files.",
    ]
    if not allowed_files_for_task(task):
        constraints.append("Return partial or blocked if the task requires repository edits.")
    return constraints


def ensure_release_task(task_graph: TaskGraph) -> TaskGraph:
    if any(node.type == "release" for node in task_graph.nodes):
        return task_graph

    release_id = next_task_id(task_graph)
    upstream = [node.id for node in task_graph.nodes if node.type == "review"] or [task_graph.nodes[-1].id]
    release_task = TaskNode(
        id=release_id,
        title="Record delivery evidence",
        description="Record branch, commit, pull request, CI, or dry-run GitHub execution evidence for the completed document-driven graph.",
        type="release",
        assigned_agent="reviewer",
        dependencies=upstream,
        completion_criteria=["GitHub sync or dry-run delivery evidence is present in runtime state."],
        priority=60,
    )
    task_graph.nodes.append(release_task)
    task_graph.dependencies.extend(Dependency(source=task_id, target=release_id, type="requires_review") for task_id in upstream)
    return task_graph


def next_task_id(task_graph: TaskGraph) -> str:
    numeric_ids: list[int] = []
    for node in task_graph.nodes:
        if node.id.startswith("T") and node.id[1:].isdigit():
            numeric_ids.append(int(node.id[1:]))
    return f"T{(max(numeric_ids) if numeric_ids else len(task_graph.nodes)) + 1:03d}"
