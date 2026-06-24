"""Asynchronous run job records for the local API runtime."""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

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

    def ensure_created(self, project_id: str, run_id: str) -> RunJob:
        try:
            return self.load(run_id)
        except FileNotFoundError:
            return self.create(project_id, run_id)

    def load(self, run_id: str) -> RunJob:
        path = self.job_path(run_id)
        last_error: json.JSONDecodeError | FileNotFoundError | PermissionError | None = None
        for _ in range(50):
            try:
                return RunJob.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except (FileNotFoundError, json.JSONDecodeError, PermissionError) as exc:
                last_error = exc
                time.sleep(0.02)
        if last_error:
            raise last_error
        raise FileNotFoundError(path)

    def save(self, job: RunJob) -> None:
        path = self.job_path(job.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        job = self._preserve_resumed_status(path, job)
        job.updated_at = utc_now_iso()
        temp_path = path.with_name(f"{path.name}.tmp-{threading.get_ident()}-{uuid.uuid4().hex}")
        try:
            for attempt in range(10):
                try:
                    job = self._preserve_resumed_status(path, job)
                    payload = json.dumps(job.to_dict(), indent=2, sort_keys=True) + "\n"
                    temp_path.write_text(payload, encoding="utf-8")
                    temp_path.replace(path)
                    return
                except PermissionError:
                    if attempt == 9:
                        raise
                    time.sleep(0.02)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def _preserve_resumed_status(self, path: Path, job: RunJob) -> RunJob:
        if not path.exists():
            return job
        try:
            current = RunJob.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            return job
        if current.status == "resumed" and job.status != "failed":
            job.status = "resumed"
            job.result_path = job.result_path or current.result_path
            job.error = job.error or current.error
        return job

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
        if status == "paused" and not job.controls.get("pause_requested") and job.status in {"paused", "resumed"}:
            job.status = "resumed"
        else:
            job.status = status
        self.save(job)
        self.append_event(job, job.status, "runtime", f"Run finished with status {job.status}.")
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

    def events_after(self, run_id: str, last_event_id: str = "") -> list[dict[str, object]]:
        events = self.events(run_id)
        if not last_event_id:
            return events
        for index, event in enumerate(events):
            if str(event.get("event_id", "")) == last_event_id:
                return events[index + 1 :]
        return events

    def stream_events(
        self,
        run_id: str,
        *,
        last_event_id: str = "",
        timeout_seconds: float = 30.0,
        poll_interval_seconds: float = 0.25,
    ) -> Iterable[dict[str, object]]:
        """Yield stored events that appear after ``last_event_id``.

        This is intentionally backed by the existing append-only JSONL store so
        the HTTP layer can provide SSE without introducing a separate broker.
        """

        deadline = time.time() + max(0.0, timeout_seconds)
        cursor = last_event_id
        terminal_types = {"done", "failed", "blocked", "paused", "needs_iteration"}
        while True:
            pending = self.events_after(run_id, cursor)
            for event in pending:
                cursor = str(event.get("event_id", cursor))
                yield event
                if str(event.get("type", "")) in terminal_types:
                    return
            if time.time() >= deadline:
                return
            time.sleep(max(0.01, poll_interval_seconds))

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
            if job.status == "resumed":
                self.store.append_event(job, "resume_boundary", "runtime", f"Run resume already handed off before {task_id}.", task_id=task_id)
                return ControlDecision("stop", f"Source run already resumed before task {task_id}.")
            job.status = "paused"
            self.store.save(job)
            self.store.append_event(job, "pause_boundary", "runtime", f"Run paused before dispatching {task_id}.", task_id=task_id)
            return ControlDecision("pause", f"Operator requested pause before task {task_id}.")
        return ControlDecision()

    def should_stop_worker(self, task_id: str) -> bool:
        try:
            job = self.store.load(self.run_id)
        except (FileNotFoundError, json.JSONDecodeError, PermissionError):
            return False
        if bool(job.controls.get("stop_requested")):
            self.store.append_event(job, "worker_stop_requested", "runtime", f"Stop requested while worker was executing {task_id}.", task_id=task_id)
            return True
        return False
