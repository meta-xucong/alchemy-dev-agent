"""Managed worker process lifecycle evidence and cleanup."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .models import utc_now_iso


Terminator = Callable[[int], dict[str, Any]]
CancellationCheck = Callable[[], bool]


@dataclass(slots=True)
class WorkerLifecycleRecord:
    task_id: str
    timeout_seconds: int
    process_group: str
    status: str = "running"
    worker_pid: int | None = None
    started_at: str = field(default_factory=utc_now_iso)
    completed_at: str = ""
    timed_out_at: str = ""
    terminated_at: str = ""
    returncode: int | None = None
    cleanup_required: bool = False
    termination: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "worker_pid": self.worker_pid,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "timed_out_at": self.timed_out_at,
            "terminated_at": self.terminated_at,
            "timeout_seconds": self.timeout_seconds,
            "status": self.status,
            "returncode": self.returncode,
            "process_group": self.process_group,
            "cleanup_required": self.cleanup_required,
            "termination": dict(self.termination),
            "error": self.error,
        }


class WorkerLifecycleRecorder:
    """Persist lifecycle evidence for real worker subprocesses."""

    def __init__(self, output_dir: str | Path | None = None, terminator: Terminator | None = None) -> None:
        self.output_dir = Path(output_dir) if output_dir else None
        self.terminator = terminator or terminate_process_tree
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)

    def start(self, task_id: str, timeout_seconds: int) -> WorkerLifecycleRecord:
        process_group = f"alchemy-run-{_safe_id(task_id)}-{int(time.time() * 1000)}"
        record = WorkerLifecycleRecord(task_id=task_id, timeout_seconds=timeout_seconds, process_group=process_group)
        self.persist(record)
        return record

    def attach_pid(self, record: WorkerLifecycleRecord, pid: int) -> None:
        record.worker_pid = pid
        self.persist(record)

    def complete(self, record: WorkerLifecycleRecord, returncode: int) -> None:
        record.status = "completed"
        record.returncode = returncode
        record.completed_at = utc_now_iso()
        record.cleanup_required = False
        self.persist(record)

    def mark_timed_out(self, record: WorkerLifecycleRecord, error: str) -> None:
        record.status = "timed_out"
        record.timed_out_at = utc_now_iso()
        record.cleanup_required = bool(record.worker_pid)
        record.error = error
        self.persist(record)

    def cancel(self, record: WorkerLifecycleRecord, reason: str) -> None:
        record.status = "cancelled"
        record.terminated_at = utc_now_iso()
        record.cleanup_required = bool(record.worker_pid)
        record.error = reason
        self.persist(record)

    def terminate(self, record: WorkerLifecycleRecord) -> None:
        if not record.worker_pid:
            record.cleanup_required = False
            self.persist(record)
            return
        record.termination = self.terminator(record.worker_pid)
        record.terminated_at = utc_now_iso()
        record.cleanup_required = not bool(record.termination.get("terminated"))
        self.persist(record)

    def fail(self, record: WorkerLifecycleRecord, error: str) -> None:
        record.status = "failed"
        record.completed_at = utc_now_iso()
        record.error = error
        record.cleanup_required = False
        self.persist(record)

    def persist(self, record: WorkerLifecycleRecord) -> None:
        if not self.output_dir:
            return
        path = self.output_dir / f"{_safe_id(record.task_id)}.json"
        path.write_text(json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


class ManagedSubprocessRunner:
    """Run a subprocess with PID evidence and timeout process-tree cleanup."""

    def __init__(
        self,
        recorder: WorkerLifecycleRecorder,
        record: WorkerLifecycleRecord,
        *,
        cancellation_check: CancellationCheck | None = None,
        poll_interval_seconds: float = 0.1,
    ) -> None:
        self.recorder = recorder
        self.record = record
        self.cancellation_check = cancellation_check
        self.poll_interval_seconds = poll_interval_seconds

    def __call__(
        self,
        args: list[str],
        *,
        cwd: str | Path,
        input: str | bytes,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
    ) -> subprocess.CompletedProcess[Any]:
        stdout_pipe = subprocess.PIPE if capture_output else None
        stderr_pipe = subprocess.PIPE if capture_output else None
        creation_kwargs: dict[str, Any] = {}
        if os.name == "nt":
            creation_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            creation_kwargs["preexec_fn"] = os.setsid

        process = subprocess.Popen(
            args,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=stdout_pipe,
            stderr=stderr_pipe,
            text=text,
            **creation_kwargs,
        )
        self.recorder.attach_pid(self.record, process.pid)
        try:
            stdout, stderr = self._communicate_with_control(process, input=input, timeout=timeout, args=args)
        except subprocess.TimeoutExpired as exc:
            self.recorder.mark_timed_out(self.record, str(exc))
            self.recorder.terminate(self.record)
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
            raise subprocess.TimeoutExpired(args, timeout, output=stdout or exc.output, stderr=stderr or exc.stderr)
        except WorkerCancelled as exc:
            self.recorder.cancel(self.record, str(exc))
            self.recorder.terminate(self.record)
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
            return subprocess.CompletedProcess(args, 130, stdout, stderr)

        self.recorder.complete(self.record, process.returncode)
        if check and process.returncode:
            raise subprocess.CalledProcessError(process.returncode, args, output=stdout, stderr=stderr)
        return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)

    def _communicate_with_control(
        self,
        process: subprocess.Popen[Any],
        *,
        input: str | bytes,
        timeout: int | float,
        args: list[str],
    ) -> tuple[Any, Any]:
        if self.cancellation_check is None:
            return process.communicate(input=input, timeout=timeout)
        deadline = time.monotonic() + float(timeout)
        sent_input = False
        while True:
            if self.cancellation_check():
                raise WorkerCancelled(f"Worker cancellation requested for {self.record.task_id}.")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(args, timeout)
            try:
                return process.communicate(
                    input=input if not sent_input else None,
                    timeout=min(self.poll_interval_seconds, remaining),
                )
            except subprocess.TimeoutExpired:
                sent_input = True


class WorkerCancelled(Exception):
    """Raised when operator stop is requested while the worker is running."""


def terminate_process_tree(pid: int) -> dict[str, Any]:
    if os.name == "nt":
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return {
            "terminated": result.returncode == 0 or "not found" in (result.stderr + result.stdout).lower(),
            "method": "taskkill",
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    try:
        os.killpg(pid, signal.SIGTERM)
        time.sleep(0.2)
        os.killpg(pid, signal.SIGKILL)
        return {"terminated": True, "method": "killpg"}
    except ProcessLookupError:
        return {"terminated": True, "method": "killpg", "stdout": "process group not found"}
    except OSError as exc:
        return {"terminated": False, "method": "killpg", "stderr": str(exc)}


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "worker"
