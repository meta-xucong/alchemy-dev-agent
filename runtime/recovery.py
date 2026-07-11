"""Resume and retry helpers for persisted runtime states."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .models import RuntimeState, TaskNode, utc_now_iso


@dataclass(slots=True)
class RecoverySource:
    state: RuntimeState
    source_path: str
    source_run_id: str = ""
    project_id: str = ""
    project_brief: dict[str, Any] = field(default_factory=dict)
    context_bundle: dict[str, Any] = field(default_factory=dict)
    workspace: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RecoveryResult:
    state: RuntimeState
    checkpoint: dict[str, Any]
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint": dict(self.checkpoint),
            "blockers": list(self.blockers),
        }


class RuntimeRecovery:
    """Prepare a persisted runtime state for explicit resume/retry execution."""

    def load_source(self, resume_from: str | Path) -> RecoverySource:
        path = Path(resume_from)
        if path.is_dir():
            return self._load_from_directory(path)
        if path.name == "state.json":
            return RecoverySource(state=RuntimeState.from_dict(_read_json(path)), source_path=str(path))
        payload = _read_json(path)
        if "runtime_state" in payload:
            return self._source_from_report(payload, str(path))
        return RecoverySource(state=RuntimeState.from_dict(payload), source_path=str(path))

    def prepare(
        self,
        source: RecoverySource,
        *,
        task_ids: Sequence[str] = (),
        retry_blocked: bool = True,
        clear_operator_stop: bool = True,
    ) -> RecoveryResult:
        state = source.state
        selected = {str(task_id) for task_id in task_ids if str(task_id)}
        operator_stop = any(str(blocker.get("id", "")) == "B-RUN-STOPPED" for blocker in state.blockers)
        reset_task_ids: list[str] = []
        reconciled_task_ids: list[str] = []
        skipped_task_ids: list[str] = []
        blockers: list[str] = []

        terminal_records = self._terminal_lifecycle_by_task(state)

        for task in state.task_graph.nodes:
            if selected and task.id not in selected:
                continue
            terminal_record = terminal_records.get(task.id) or {}
            if (
                task.status == "active"
                and str(terminal_record.get("status", "")).lower() == "completed"
                and bool(terminal_record.get("recovered_from_worker_file", False))
            ):
                task.status = "completed"
                if task.id not in state.completed_tasks:
                    state.completed_tasks.append(task.id)
                reconciled_task_ids.append(task.id)
                continue
            if task.id in state.failed_tasks and task.status in {"pending", "ready"} and self._can_retry(task):
                task.status = "pending"
                reset_task_ids.append(task.id)
                continue
            if task.status == "active":
                task.status = "pending"
                reset_task_ids.append(task.id)
                continue
            if task.status == "failed":
                if self._can_retry(task):
                    task.status = "pending"
                    reset_task_ids.append(task.id)
                else:
                    skipped_task_ids.append(task.id)
                continue
            if task.status == "blocked" and retry_blocked:
                if self._can_retry(task):
                    task.retry_count += 1
                    task.status = "pending"
                    reset_task_ids.append(task.id)
                else:
                    skipped_task_ids.append(task.id)

        if selected:
            missing = sorted(selected - {task.id for task in state.task_graph.nodes})
            blockers.extend(f"Unknown resume task id: {task_id}" for task_id in missing)

        if not reset_task_ids and not reconciled_task_ids and not blockers and not operator_stop:
            blockers.append("No retryable failed, blocked, or active tasks were found to resume.")

        reset_set = set(reset_task_ids)
        reconciled_set = set(reconciled_task_ids)
        state.active_tasks = [task_id for task_id in state.active_tasks if task_id not in reset_set]
        state.active_tasks = [task_id for task_id in state.active_tasks if task_id not in reconciled_set]
        state.failed_tasks = [task_id for task_id in state.failed_tasks if task_id not in reset_set]
        state.failed_tasks = [task_id for task_id in state.failed_tasks if task_id not in reconciled_set]
        state.done = False
        cleared_blockers = self._clear_recoverable_blockers(
            state,
            reset_set=reset_set | reconciled_set,
            clear_operator_stop=clear_operator_stop,
        )

        checkpoint = {
            "recovery_id": f"recovery-{utc_now_iso()}",
            "source_path": source.source_path,
            "source_run_id": source.source_run_id,
            "project_id": source.project_id,
            "mode": "retry_failed_blocked_active",
            "reset_task_ids": reset_task_ids,
            "reconciled_completed_task_ids": reconciled_task_ids,
            "continued_task_ids": [
                task.id
                for task in state.task_graph.nodes
                if task.status in {"pending", "ready"} and (not selected or task.id in selected)
            ],
            "skipped_task_ids": skipped_task_ids,
            "cleared_blocker_ids": cleared_blockers,
            "worker_lifecycle": self._worker_lifecycle_recovery_evidence(state, reset_set),
            "workspace": dict(source.workspace),
            "created_at": utc_now_iso(),
        }
        state.recovery = checkpoint
        state.iteration_history.append(
            {
                "timestamp": utc_now_iso(),
                "type": "recovery_checkpoint",
                "summary": "Prepared runtime state for resumed execution.",
                "metadata": checkpoint,
            }
        )
        return RecoveryResult(state=state, checkpoint=checkpoint, blockers=blockers)

    def _load_from_directory(self, path: Path) -> RecoverySource:
        report_path = path / "document_run_report.json"
        run_path = path / "run.json"
        state_path = path / "state.json"
        if run_path.exists():
            return self._source_from_report(_read_json(run_path), str(run_path))
        if report_path.exists():
            return self._source_from_report(_read_json(report_path), str(report_path))
        if state_path.exists():
            state = RuntimeState.from_dict(_read_json(state_path))
            self._merge_worker_lifecycle_directory(state, path / "workers")
            return RecoverySource(state=state, source_path=str(state_path))
        raise FileNotFoundError(f"No resumable state found under {path}")

    def _source_from_report(self, payload: dict[str, Any], source_path: str) -> RecoverySource:
        runtime_state = payload.get("runtime_state", payload)
        if not isinstance(runtime_state, dict):
            raise ValueError(f"Report does not contain runtime_state: {source_path}")
        return RecoverySource(
            state=RuntimeState.from_dict(runtime_state),
            source_path=source_path,
            source_run_id=str(payload.get("run_id", "")),
            project_id=str(payload.get("project_id", "")),
            project_brief=dict(payload.get("project_brief", {})),
            context_bundle=dict(payload.get("context_bundle", {})),
            workspace=dict(payload.get("workspace", {})),
        )

    def _can_retry(self, task: TaskNode) -> bool:
        return task.retry_count < task.max_attempts

    def _worker_lifecycle_recovery_evidence(self, state: RuntimeState, reset_set: set[str]) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for record in state.worker_lifecycle:
            task_id = str(record.get("task_id", ""))
            if task_id not in reset_set:
                continue
            evidence.append(
                {
                    "task_id": task_id,
                    "previous_status": str(record.get("status", "")),
                    "worker_pid": record.get("worker_pid"),
                    "cleanup_required": bool(record.get("cleanup_required", False)),
                    "retry_instruction": (
                        "Clean up the recorded worker process before retrying."
                        if record.get("cleanup_required")
                        else "Worker lifecycle evidence allows retry."
                    ),
                }
            )
        return evidence

    def _merge_worker_lifecycle_directory(self, state: RuntimeState, workers_dir: Path) -> None:
        if not workers_dir.exists():
            return
        records_by_task = {str(record.get("task_id", "")): dict(record) for record in state.worker_lifecycle if isinstance(record, dict)}
        for path in sorted(workers_dir.glob("*.json")):
            try:
                payload = _read_json(path)
            except (OSError, json.JSONDecodeError):
                continue
            task_id = str(payload.get("task_id", "") or path.stem)
            if not task_id:
                continue
            payload["recovered_from_worker_file"] = True
            records_by_task[task_id] = payload
        state.worker_lifecycle = [records_by_task[task_id] for task_id in sorted(records_by_task)]

    def _terminal_lifecycle_by_task(self, state: RuntimeState) -> dict[str, dict[str, Any]]:
        terminal: dict[str, dict[str, Any]] = {}
        for record in state.worker_lifecycle:
            if not isinstance(record, dict):
                continue
            task_id = str(record.get("task_id", ""))
            status = str(record.get("status", "")).lower()
            if task_id and status in {"completed", "failed", "timed_out", "cancelled"}:
                terminal[task_id] = dict(record)
        return terminal

    def _clear_recoverable_blockers(
        self,
        state: RuntimeState,
        *,
        reset_set: set[str],
        clear_operator_stop: bool,
    ) -> list[str]:
        remaining: list[dict[str, Any]] = []
        cleared: list[str] = []
        for blocker in state.blockers:
            blocker_id = str(blocker.get("id", ""))
            task_ids = {str(task_id) for task_id in blocker.get("task_ids", [])}
            is_operator_stop = blocker_id == "B-RUN-STOPPED"
            if task_ids & reset_set or (clear_operator_stop and is_operator_stop):
                cleared.append(blocker_id)
                continue
            remaining.append(blocker)
        state.blockers = remaining
        return cleared


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
