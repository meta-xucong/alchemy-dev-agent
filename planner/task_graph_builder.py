"""Build runtime task graphs from ContextBundle objects."""

from __future__ import annotations

from context.models import ContextBundle
from runtime.models import Dependency, TaskGraph, TaskNode


class TaskGraphBuilder:
    """Create a deterministic task graph for local autonomous generation demos."""

    def build(self, context_bundle: ContextBundle) -> TaskGraph:
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
