"""Runtime state persistence."""

from __future__ import annotations

import json
from pathlib import Path

from .models import RuntimeState, utc_now_iso
from .task_graph_engine import TaskGraphEngine


class StateManager:
    """Load and save runtime state as deterministic JSON."""

    def __init__(self, state_path: str | Path) -> None:
        self.state_path = Path(state_path)

    def initialize(self, objective: str, graph_engine: TaskGraphEngine | None = None) -> RuntimeState:
        engine = graph_engine or TaskGraphEngine()
        state = RuntimeState(objective=objective, task_graph=engine.create_default_graph(objective))
        self.save(state)
        return state

    def load(self) -> RuntimeState:
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        return RuntimeState.from_dict(payload)

    def save(self, state: RuntimeState) -> None:
        state.updated_at = utc_now_iso()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def load_or_initialize(self, objective: str, graph_engine: TaskGraphEngine | None = None) -> RuntimeState:
        if self.state_path.exists():
            return self.load()
        return self.initialize(objective, graph_engine)
