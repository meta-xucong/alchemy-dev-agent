"""Deterministic local agents for end-to-end demo generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from context.models import ContextBundle
from planner import TaskGraphBuilder
from runtime.models import TaskGraph

from .game_generator import RetroPlatformerGenerator


@dataclass(slots=True)
class AgentEvent:
    agent: str
    task_id: str
    status: str
    summary: str
    artifacts: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "agent": self.agent,
            "task_id": self.task_id,
            "status": self.status,
            "summary": self.summary,
            "artifacts": list(self.artifacts),
        }


class LocalAgentCluster:
    """Run a small deterministic agent chain against a generated task graph."""

    def __init__(self, game_generator: RetroPlatformerGenerator | None = None) -> None:
        self.game_generator = game_generator or RetroPlatformerGenerator()

    def run(self, context_bundle: ContextBundle, output_dir: str | Path) -> tuple[TaskGraph, list[AgentEvent]]:
        task_graph = TaskGraphBuilder().build(context_bundle)
        output = Path(output_dir)
        events: list[AgentEvent] = []

        events.append(
            AgentEvent(
                agent="architect",
                task_id="T001",
                status="completed",
                summary="Mapped context requirements to a local generated game artifact.",
                artifacts=[],
            )
        )
        task_graph.nodes[0].status = "completed"
        task_graph.nodes[0].evidence.append(events[-1].to_dict())

        index_path = self.game_generator.generate(output, title="Original Retro Platformer")
        events.append(
            AgentEvent(
                agent="frontend",
                task_id="T002",
                status="completed",
                summary="Generated self-contained HTML canvas platform game.",
                artifacts=[str(index_path)],
            )
        )
        task_graph.nodes[1].status = "completed"
        task_graph.nodes[1].evidence.append(events[-1].to_dict())

        test_summary = inspect_generated_game(index_path)
        events.append(
            AgentEvent(
                agent="test",
                task_id="T003",
                status="completed" if test_summary["passed"] else "failed",
                summary=str(test_summary["summary"]),
                artifacts=[str(index_path)],
            )
        )
        task_graph.nodes[2].status = "completed" if test_summary["passed"] else "failed"
        task_graph.nodes[2].evidence.append({**events[-1].to_dict(), "checks": test_summary["checks"]})

        review_status = "completed" if test_summary["passed"] else "failed"
        review_summary = "Approved original generated game delivery." if test_summary["passed"] else "Review failed because static checks failed."
        events.append(
            AgentEvent(
                agent="reviewer",
                task_id="T004",
                status=review_status,
                summary=review_summary,
                artifacts=[str(index_path)],
            )
        )
        task_graph.nodes[3].status = review_status
        task_graph.nodes[3].evidence.append(events[-1].to_dict())

        return task_graph, events


def inspect_generated_game(index_path: str | Path) -> dict[str, object]:
    path = Path(index_path)
    html = path.read_text(encoding="utf-8") if path.exists() else ""
    lowered = html.lower()
    forbidden_terms = ["super mario", "mario", "goomba", "koopa", "mushroom kingdom", "nintendo"]
    checks = {
        "index_exists": path.exists(),
        "has_canvas": "<canvas" in lowered,
        "has_player_controls": "arrow" in lowered and "jump" in lowered,
        "has_platform_logic": "collideaxis" in lowered and "level.platforms" in lowered,
        "has_collectibles": "coins" in lowered,
        "has_finish_condition": "stage clear" in lowered and "finish" in lowered,
        "has_no_protected_terms": not any(term in lowered for term in forbidden_terms),
    }
    passed = all(checks.values())
    failed = [name for name, ok in checks.items() if not ok]
    return {
        "passed": passed,
        "checks": checks,
        "summary": "Generated game passed static checks." if passed else f"Generated game failed checks: {', '.join(failed)}",
    }
