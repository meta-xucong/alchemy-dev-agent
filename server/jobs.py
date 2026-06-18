"""Asynchronous run job records for the local API runtime."""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from intake.models import utc_now_iso
from runtime.control import ControlDecision


@dataclass(slots=True)
class RunJob:
    project_id: str
    run_id: str
    status: str
    created_at: str
    updated_at: str
    controls: dict[str, bool] = field(default_factory=lambda: {
        "pause_requested": False,
        "stop_requested": False,
    })
    result_path: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "run_id": self.run_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "controls": dict(self.controls),
            "result_path": self.result_path,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RunJob":
        return cls(
            project_id=str(payload["project_id"]),
            run_id=str(payload["run_id"]),
            status=str(payload["status"]),
            created_at=str(payload["created_at"]),
            updated_at=str(payload["updated_at"]),
            controls={str(key): bool(value) for key, value in payload.get("controls", {}).items()},
            result_path=str(payload.get("result_path", "")),
            error=str(payload.get("error", "")),
        )


class JobStore:
    """Persist run job state and append-only event records."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir

    def run_dir(self, run_id: str) -> Path:
        return self.project_dir / "runs" / run_id

    def job_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "job.json"

    def events_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "events.jsonl"

    def create(self, project_id: str, run_id: str) -> RunJob:
        now = utc_now_iso()
        job = RunJob(
            project_id=project_id,
            run_id=run_id,
            status="queued",
            created_at=now,
            updated_at=now,
        )
        self.save(job)
        self.append_event(job, "queued", "api", "Run queued.")
        return job

    def load(self, run_id: str) -> RunJob:
        path = self.job_path(run_id)
        last_error: json.JSONDecodeError | FileNotFoundError | PermissionError | None = None
        for _ in range(10):
            try:
                return RunJob.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except (FileNotFoundError, json.JSONDecodeError, PermissionError) as exc:
                last_error = exc
                time.sleep(0.01)
        if last_error:
            raise last_error
        raise FileNotFoundError(path)

    def save(self, job: RunJob) -> None:
        path = self.job_path(job.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        job.updated_at = utc_now_iso()
        payload = json.dumps(job.to_dict(), indent=2, sort_keys=True) + "\n"
        temp_path = path.with_name(f"{path.name}.tmp-{threading.get_ident()}-{uuid.uuid4().hex}")
        temp_path.write_text(payload, encoding="utf-8")
        try:
            for attempt in range(10):
                try:
                    temp_path.replace(path)
                    return
                except PermissionError:
                    if attempt == 9:
                        raise
                    time.sleep(0.02)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def transition(self, run_id: str, status: str, message: str, *, source: str = "runtime", error: str = "") -> RunJob:
        job = self.load(run_id)
        job.status = status
        if error:
            job.error = error
        self.save(job)
        self.append_event(job, status, source, message, level="error" if status == "failed" else "info")
        return job

    def update_control(self, run_id: str, key: str, value: bool, message: str) -> RunJob:
        job = self.load(run_id)
        job.controls[key] = value
        self.save(job)
        self.append_event(job, key, "api", message)
        return job

    def set_result(self, run_id: str, result_path: Path, status: str) -> RunJob:
        job = self.load(run_id)
        job.result_path = str(result_path)
        job.status = status
        self.save(job)
        self.append_event(job, status, "runtime", f"Run finished with status {status}.")
        return job

    def append_event(
        self,
        job: RunJob,
        event_type: str,
        source: str,
        message: str,
        *,
        level: str = "info",
        task_id: str = "",
        agent: str = "",
    ) -> None:
        events_path = self.events_path(job.run_id)
        events_path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "event_id": f"{job.run_id}-event-{self._next_event_index(job.run_id):03d}",
            "run_id": job.run_id,
            "timestamp": utc_now_iso(),
            "level": level,
            "source": source,
            "type": event_type,
            "message": message,
            "task_id": task_id,
            "agent": agent,
        }
        with events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    def events(self, run_id: str) -> list[dict[str, object]]:
        path = self.events_path(run_id)
        if not path.exists():
            return []
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
        return events

    def _next_event_index(self, run_id: str) -> int:
        return len(self.events(run_id)) + 1


def start_background_job(target: Callable[[], None]) -> threading.Thread:
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread


class JobExecutionController:
    """Translate persisted job controls into runtime task-boundary decisions."""

    def __init__(self, store: JobStore, run_id: str) -> None:
        self.store = store
        self.run_id = run_id

    def before_task(self, task_id: str) -> ControlDecision:
        job = self.store.load(self.run_id)
        if job.controls.get("stop_requested"):
            self.store.append_event(job, "stop_boundary", "runtime", f"Run stopped before dispatching {task_id}.", task_id=task_id)
            return ControlDecision("stop", f"Operator requested stop before task {task_id}.")
        if job.controls.get("pause_requested"):
            job.status = "paused"
            self.store.save(job)
            self.store.append_event(job, "pause_boundary", "runtime", f"Run paused before dispatching {task_id}.", task_id=task_id)
            return ControlDecision("pause", f"Operator requested pause before task {task_id}.")
        return ControlDecision()
