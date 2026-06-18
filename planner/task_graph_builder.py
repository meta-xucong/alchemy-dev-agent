"""Build runtime task graphs from ContextBundle objects."""

from __future__ import annotations

from context.models import ContextBundle, Requirement
from runtime.models import Dependency, TaskGraph, TaskNode


class TaskGraphBuilder:
    """Create deterministic task graphs from context bundles."""

    def build(self, context_bundle: ContextBundle) -> TaskGraph:
        if self._is_generated_artifact_context(context_bundle):
            return self._build_generated_artifact_graph(context_bundle)
        return self._build_document_driven_graph(context_bundle)

    def _build_document_driven_graph(self, context_bundle: ContextBundle) -> TaskGraph:
        requirements = context_bundle.requirements
        test_commands = context_bundle.test_commands or ["static artifact inspection"]
        nodes: list[TaskNode] = [
            TaskNode(
                id="T001",
                title="Plan implementation from requirements",
                description="Map requirements, repository evidence, risks, and verification commands into an implementation plan.",
                type="architecture",
                assigned_agent="architect",
                completion_criteria=[
                    "All requirements are assigned to implementation tasks.",
                    "Known blockers and risks are reflected in task scope.",
                ],
                relevant_files=self._top_level_context_files(context_bundle),
                commands_to_run=[],
                priority=95,
            )
        ]

        implementation_nodes, requirement_task_ids = self._implementation_nodes(requirements, test_commands)
        nodes.extend(implementation_nodes)
        implementation_ids = [node.id for node in implementation_nodes]
        verification_commands = (
            ["static document inspection"]
            if implementation_nodes and all(node.type == "documentation" for node in implementation_nodes)
            else test_commands + context_bundle.build_commands + context_bundle.lint_commands
        )

        verify_id = f"T{len(nodes) + 1:03d}"
        nodes.append(
            TaskNode(
                id=verify_id,
                title="Verify implementation against project checks",
                description="Run detected tests, builds, lints, and requirement-specific verification.",
                type="test",
                assigned_agent="test",
                dependencies=implementation_ids or ["T001"],
                completion_criteria=[
                    "Detected verification commands pass or produce documented blockers.",
                    "Every must requirement has implementation evidence.",
                ],
                commands_to_run=verification_commands,
                relevant_files=self._test_relevant_files(context_bundle),
                priority=85,
            )
        )

        review_id = f"T{len(nodes) + 1:03d}"
        nodes.append(
            TaskNode(
                id=review_id,
                title="Review delivery readiness",
                description="Check requirement traceability, risks, test evidence, and final gate readiness.",
                type="review",
                assigned_agent="reviewer",
                dependencies=[verify_id],
                completion_criteria=[
                    "All must requirements are traced to completed tasks.",
                    "Reviewer approval is recorded.",
                    "Final gate score is at least 0.85.",
                ],
                relevant_files=self._top_level_context_files(context_bundle),
                priority=80,
            )
        )

        for requirement in requirements:
            if requirement.id in requirement_task_ids:
                requirement.planned_task_ids = [requirement_task_ids[requirement.id], verify_id, review_id]

        dependencies = [Dependency(source="T001", target=node.id, type="blocks") for node in implementation_nodes]
        dependencies.extend(Dependency(source=node.id, target=verify_id, type="requires_test_pass") for node in implementation_nodes)
        dependencies.append(Dependency(source=verify_id, target=review_id, type="requires_review"))
        return TaskGraph(graph_id=f"{context_bundle.project_id}-document-plan", version=1, nodes=nodes, dependencies=dependencies)

    def _implementation_nodes(self, requirements: list[Requirement], test_commands: list[str]) -> tuple[list[TaskNode], dict[str, str]]:
        nodes: list[TaskNode] = []
        requirement_task_ids: dict[str, str] = {}
        if not requirements:
            return nodes, requirement_task_ids
        for index, grouped_requirements in enumerate(group_implementation_requirements(requirements), start=2):
            requirement = grouped_requirements[0]
            task_type, agent = classify_requirement_task(requirement)
            task_id = f"T{index:03d}"
            title = task_title(requirement, task_type) if len(grouped_requirements) == 1 else grouped_task_title(grouped_requirements, task_type)
            description = (
                f"Implement requirement {requirement.id}: {requirement.text}"
                if len(grouped_requirements) == 1
                else "Implement requirements "
                + ", ".join(item.id for item in grouped_requirements)
                + ": "
                + " ".join(item.text for item in grouped_requirements)
            )
            nodes.append(
                TaskNode(
                    id=task_id,
                    title=title,
                    description=description,
                    type=task_type,
                    assigned_agent=agent,
                    dependencies=["T001"],
                    completion_criteria=dedupe([criterion for item in grouped_requirements for criterion in item.acceptance_criteria]),
                    relevant_files=dedupe([file for item in grouped_requirements for file in item.related_files]),
                    commands_to_run=commands_for_task_type(task_type, test_commands),
                    priority=max(priority_for_requirement(item) for item in grouped_requirements),
                )
            )
            for item in grouped_requirements:
                requirement_task_ids[item.id] = task_id
        return nodes, requirement_task_ids

    def _build_generated_artifact_graph(self, context_bundle: ContextBundle) -> TaskGraph:
        requirements = context_bundle.requirements
        criteria = requirements[0].acceptance_criteria if requirements else ["Generated artifact exists."]
        nodes = [
            TaskNode(
                id="T001",
                title="Architect generated application",
                description="Convert the context bundle into an implementation plan.",
                type="architecture",
                assigned_agent="architect",
                completion_criteria=["Implementation plan maps requirements to generated files."],
                commands_to_run=["static artifact inspection"],
            ),
            TaskNode(
                id="T002",
                title="Implement generated application",
                description="Generate the local application artifact.",
                type="frontend",
                assigned_agent="frontend",
                dependencies=["T001"],
                completion_criteria=criteria,
                relevant_files=["index.html"],
                commands_to_run=["static artifact inspection"],
            ),
            TaskNode(
                id="T003",
                title="Verify generated application",
                description="Inspect generated artifact for required controls, canvas, and safety constraints.",
                type="test",
                assigned_agent="test",
                dependencies=["T002"],
                completion_criteria=["Generated artifact passes static verification."],
                relevant_files=["index.html"],
                commands_to_run=["static artifact inspection"],
            ),
            TaskNode(
                id="T004",
                title="Review generated delivery",
                description="Review requirements, risks, and delivery evidence.",
                type="review",
                assigned_agent="reviewer",
                dependencies=["T003"],
                completion_criteria=["Reviewer approves delivery or records blockers."],
                relevant_files=["index.html"],
            ),
        ]
        dependencies = [
            Dependency(source="T001", target="T002", type="blocks"),
            Dependency(source="T002", target="T003", type="requires_test_pass"),
            Dependency(source="T003", target="T004", type="requires_review"),
        ]
        return TaskGraph(graph_id=f"{context_bundle.project_id}-generated-app", version=1, nodes=nodes, dependencies=dependencies)

    def _is_generated_artifact_context(self, context_bundle: ContextBundle) -> bool:
        return bool(context_bundle.requirements and context_bundle.requirements[0].source_document_id == "generated_one_line")

    def _top_level_context_files(self, context_bundle: ContextBundle) -> list[str]:
        files = [document.path for document in context_bundle.documents]
        files.extend(context_bundle.package_files)
        return dedupe(files)

    def _test_relevant_files(self, context_bundle: ContextBundle) -> list[str]:
        test_files = [file.path for file in context_bundle.repository_files if file.kind in {"test", "ci"}]
        return dedupe(test_files + context_bundle.ci_files)


def classify_requirement_task(requirement: Requirement) -> tuple[str, str]:
    text = requirement.text.lower()
    files = " ".join(requirement.related_files).lower()
    combined = f"{text} {files}"
    if any(file.endswith((".md", ".txt", ".rst")) for file in requirement.related_files):
        return "documentation", "architect"
    if any(marker in combined for marker in ("test", "tests/", ".test.", ".spec.", "qa", "verification", "coverage", "ci")):
        return "test", "test"
    if any(marker in combined for marker in ("api", "backend", "database", "schema", "migration", "auth", "server", "service")):
        return "backend", "backend"
    if any(marker in combined for marker in ("ui", "frontend", "dashboard", "page", "screen", "component", ".tsx", ".jsx", ".css", ".html")):
        return "frontend", "frontend"
    if any(marker in combined for marker in ("readme", "docs", "documentation", ".md")):
        return "documentation", "architect"
    if len(requirement.related_files) > 1:
        return "integration", "backend"
    return "backend", "backend"


def task_title(requirement: Requirement, task_type: str) -> str:
    label = {
        "backend": "Implement backend requirement",
        "frontend": "Implement frontend requirement",
        "test": "Implement verification requirement",
        "documentation": "Update documentation requirement",
        "integration": "Implement integration requirement",
    }.get(task_type, "Implement requirement")
    return f"{label}: {shorten(requirement.text)}"


def grouped_task_title(requirements: list[Requirement], task_type: str) -> str:
    label = {
        "backend": "Implement grouped backend requirements",
        "frontend": "Implement grouped frontend requirements",
        "test": "Implement grouped verification requirements",
        "documentation": "Update grouped documentation requirements",
        "integration": "Implement grouped integration requirements",
    }.get(task_type, "Implement grouped requirements")
    files = dedupe([file for requirement in requirements for file in requirement.related_files])
    if files:
        return f"{label}: {', '.join(files)}"
    return f"{label}: {shorten(requirements[0].text)}"


def group_implementation_requirements(requirements: list[Requirement]) -> list[list[Requirement]]:
    groups: list[list[Requirement]] = []
    group_index: dict[tuple[str, tuple[str, ...]], int] = {}
    for requirement in requirements:
        task_type, _agent = classify_requirement_task(requirement)
        key = (task_type, tuple(requirement.related_files))
        if requirement.related_files and key in group_index:
            groups[group_index[key]].append(requirement)
            continue
        group_index[key] = len(groups)
        groups.append([requirement])
    return groups


def priority_for_requirement(requirement: Requirement) -> int:
    return {"must": 90, "should": 70, "could": 50}.get(requirement.priority, 70)


def commands_for_task_type(task_type: str, test_commands: list[str]) -> list[str]:
    if task_type == "documentation":
        return ["static document inspection"]
    return list(test_commands)


def shorten(text: str, limit: int = 72) -> str:
    clean = " ".join(text.split())
    return clean if len(clean) <= limit else clean[: limit - 3].rstrip() + "..."


def dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value)
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result
