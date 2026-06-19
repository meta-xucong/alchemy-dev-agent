"""Task-boundary execution controls for the runtime loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


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
