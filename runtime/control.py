"""Task-boundary execution controls for the runtime loop."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence


@dataclass(slots=True)
class ControlDecision:
    action: str = "continue"
    reason: str = ""


class ExecutionController(Protocol):
    def before_task(self, task_id: str) -> ControlDecision:
        ...

    def should_stop_worker(self, task_id: str) -> bool:
        ...


class NoopExecutionController:
    def before_task(self, task_id: str) -> ControlDecision:
        return ControlDecision()

    def should_stop_worker(self, task_id: str) -> bool:
        return False


class MarkerFileExecutionController:
    """Stop a live run when a supervisor/operator marker appears on disk."""

    def __init__(
        self,
        run_dir: str | Path,
        marker_names: Sequence[str] = ("supervisor_stop.json", "operator_stop.json"),
    ) -> None:
        self.run_dir = Path(run_dir)
        self.marker_names = tuple(marker_names)

    def before_task(self, task_id: str) -> ControlDecision:
        return self._decision()

    def should_stop_worker(self, task_id: str) -> bool:
        return self._decision().action == "stop"

    def _decision(self) -> ControlDecision:
        for name in self.marker_names:
            marker = self.run_dir / name
            if marker.exists():
                return ControlDecision("stop", _marker_reason(marker))
        return ControlDecision()


class CompositeExecutionController:
    """Compose multiple execution controllers with stop/pause precedence."""

    def __init__(self, controllers: Sequence[ExecutionController]) -> None:
        self.controllers = tuple(controllers)

    def before_task(self, task_id: str) -> ControlDecision:
        for controller in self.controllers:
            decision = controller.before_task(task_id)
            if decision.action in {"stop", "pause"}:
                return decision
        return ControlDecision()

    def should_stop_worker(self, task_id: str) -> bool:
        return any(controller.should_stop_worker(task_id) for controller in self.controllers)


def with_marker_file_controller(
    run_dir: str | Path,
    controller: ExecutionController | None = None,
) -> ExecutionController:
    marker_controller = MarkerFileExecutionController(run_dir)
    if controller is None:
        return marker_controller
    return CompositeExecutionController([marker_controller, controller])


def _marker_reason(marker: Path) -> str:
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return f"Run stopped by marker file: {marker.name}"
    if isinstance(payload, dict):
        reason = str(payload.get("reason", "")).strip()
        if reason:
            return reason
    return f"Run stopped by marker file: {marker.name}"
