"""Codex worker adapter.

The v0.1 runtime ships with a deterministic local worker stub. It models the
Codex CLI contract without invoking external tools, making tests and smoke runs
repeatable. A production adapter can replace `execute` with a real Codex CLI
subprocess while preserving the input and output shapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(slots=True)
class CodexWorkerInput:
    task_id: str
    goal: str
    context_files: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "context_files": list(self.context_files),
            "constraints": list(self.constraints),
        }


@dataclass(slots=True)
class CodexWorkerResult:
    status: Literal["passed", "failed", "blocked"]
    diff: list[str] = field(default_factory=list)
    logs: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "diff": list(self.diff),
            "logs": self.logs,
        }


class CodexWorkerAdapter:
    """Deterministic implementation of the Codex worker contract."""

    def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
        goal = worker_input.goal.lower()
        constraints = " ".join(worker_input.constraints).lower()

        if "block" in constraints or "blocked" in goal:
            return CodexWorkerResult(
                status="blocked",
                diff=[],
                logs=f"{worker_input.task_id}: blocked by deterministic constraint.",
            )

        if "fail" in constraints:
            return CodexWorkerResult(
                status="failed",
                diff=[],
                logs=f"{worker_input.task_id}: failed by deterministic constraint.",
            )

        diff_marker = f"{worker_input.task_id}: simulated execution for {worker_input.goal}"
        return CodexWorkerResult(
            status="passed",
            diff=[diff_marker],
            logs=f"{worker_input.task_id}: completed successfully.",
        )
