"""End-to-end local autonomous development demo pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from context import ContextBundleBuilder
from intake import ProjectBriefBuilder
from intake.schema_validation import validate_context_bundle_contract, validate_project_brief_contract

from .agents import AgentEvent, LocalAgentCluster


@dataclass(slots=True)
class AutoDevResult:
    status: str
    output_dir: str
    project_brief: dict[str, object]
    context_bundle: dict[str, object]
    task_graph: dict[str, object]
    agent_events: list[AgentEvent]
    artifacts: list[str]
    validation_errors: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "output_dir": self.output_dir,
            "project_brief": self.project_brief,
            "context_bundle": self.context_bundle,
            "task_graph": self.task_graph,
            "agent_events": [event.to_dict() for event in self.agent_events],
            "artifacts": list(self.artifacts),
            "validation_errors": list(self.validation_errors),
        }


class AutoDevPipeline:
    """Run one-line fallback through intake, context, planning, agents, and delivery."""

    def __init__(self, agent_cluster: LocalAgentCluster | None = None) -> None:
        self.agent_cluster = agent_cluster or LocalAgentCluster()

    def run(self, objective: str, output_dir: str | Path) -> AutoDevResult:
        brief = ProjectBriefBuilder().build(
            objective=objective,
            primary_input_mode="one_line_fallback",
        )
        brief_payload = brief.to_dict()
        context_bundle = ContextBundleBuilder().build(brief)
        context_payload = context_bundle.to_dict()
        scope_controls = context_payload.get("scope_controls")
        if not isinstance(scope_controls, dict):
            scope_controls = {}
        context_payload["scope_controls"] = {
            "allowed_prefixes": list(scope_controls.get("allowed_prefixes", []) or []),
            "protected_prefixes": list(scope_controls.get("protected_prefixes", []) or []),
            "target_files": list(scope_controls.get("target_files", []) or []),
            "boundary_mode": str(scope_controls.get("boundary_mode", "strict") or "strict"),
        }

        validation_errors = []
        validation_errors.extend(validate_project_brief_contract(brief_payload))
        validation_errors.extend(validate_context_bundle_contract(context_payload))

        task_graph, events = self.agent_cluster.run(context_bundle, output_dir)
        artifact_paths = sorted({artifact for event in events for artifact in event.artifacts})
        all_tasks_completed = all(node.status == "completed" for node in task_graph.nodes)
        status = "done" if all_tasks_completed and not validation_errors else "failed"

        report = AutoDevResult(
            status=status,
            output_dir=str(output_dir),
            project_brief=brief_payload,
            context_bundle=context_payload,
            task_graph=task_graph.to_dict(),
            agent_events=events,
            artifacts=artifact_paths,
            validation_errors=validation_errors,
        )
        write_delivery_report(output_dir, report)
        return report


def write_delivery_report(output_dir: str | Path, result: AutoDevResult) -> Path:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    report_path = target / "autodev_report.json"
    report_path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report_path
