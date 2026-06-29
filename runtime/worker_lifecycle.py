"""Managed worker process lifecycle evidence and cleanup."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from .models import utc_now_iso
from .subprocess_utils import hidden_subprocess_startup_kwargs


Terminator = Callable[[int], dict[str, Any]]
CancellationCheck = Callable[[], bool]
ProgressProbe = Callable[[int], dict[str, Any]]

PROGRESS_PROCESS_NAMES = {
    "go.exe",
    "go",
    "link.exe",
    "link",
    "node.exe",
    "node",
    "npm.exe",
    "npm",
    "pnpm.exe",
    "pnpm",
    "yarn.exe",
    "yarn",
    "bun.exe",
    "bun",
    "vite.exe",
    "vite",
    "vitest.exe",
    "vitest",
    "tsc.exe",
    "tsc",
    "esbuild.exe",
    "esbuild",
    "rollup.exe",
    "rollup",
    "webpack.exe",
    "webpack",
    "cargo.exe",
    "cargo",
    "rustc.exe",
    "rustc",
    "gcc.exe",
    "gcc",
    "g++.exe",
    "g++",
    "clang.exe",
    "clang",
    "clang++.exe",
    "clang++",
    "dotnet.exe",
    "dotnet",
    "msbuild.exe",
    "msbuild",
}


@dataclass(slots=True)
class WorkerLifecycleRecord:
    task_id: str
    timeout_seconds: int | None
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
    timeout_grace_seconds: float = 0.0
    timeout_grace_count: int = 0
    timeout_grace_deadline_at: str = ""
    timeout_grace_snapshots: list[dict[str, Any]] = field(default_factory=list)

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
            "timeout_grace_seconds": self.timeout_grace_seconds,
            "timeout_grace_count": self.timeout_grace_count,
            "timeout_grace_deadline_at": self.timeout_grace_deadline_at,
            "timeout_grace_snapshots": list(self.timeout_grace_snapshots),
        }


class WorkerLifecycleRecorder:
    """Persist lifecycle evidence for real worker subprocesses."""

    def __init__(self, output_dir: str | Path | None = None, terminator: Terminator | None = None) -> None:
        self.output_dir = Path(output_dir) if output_dir else None
        self.terminator = terminator or terminate_process_tree
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)

    def start(self, task_id: str, timeout_seconds: int | None) -> WorkerLifecycleRecord:
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

    def record_timeout_grace(
        self,
        record: WorkerLifecycleRecord,
        *,
        grace_seconds: float,
        snapshot: dict[str, Any],
    ) -> None:
        deadline_at = (datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=float(grace_seconds))).isoformat()
        record.timeout_grace_seconds += float(grace_seconds)
        record.timeout_grace_count += 1
        record.timeout_grace_deadline_at = deadline_at
        record.timeout_grace_snapshots.append(
            {
                "granted_at": utc_now_iso(),
                "grace_seconds": float(grace_seconds),
                "deadline_at": deadline_at,
                "snapshot": snapshot,
            }
        )
        record.error = (
            f"Timeout boundary extended by {float(grace_seconds):g}s until {deadline_at} "
            "because worker progress was detected."
        )
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
        self.output_dir.mkdir(parents=True, exist_ok=True)
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
        pipe_drain_grace_seconds: float = 2.0,
        timeout_progress_grace_seconds: float = 0.0,
        max_timeout_grace_extensions: int = 1,
        progress_probe: ProgressProbe | None = None,
    ) -> None:
        self.recorder = recorder
        self.record = record
        self.cancellation_check = cancellation_check
        self.poll_interval_seconds = poll_interval_seconds
        self.pipe_drain_grace_seconds = pipe_drain_grace_seconds
        self.timeout_progress_grace_seconds = max(0.0, float(timeout_progress_grace_seconds))
        self.max_timeout_grace_extensions = max(0, int(max_timeout_grace_extensions))
        self.progress_probe = progress_probe or detect_worker_progress

    def __call__(
        self,
        args: list[str],
        *,
        cwd: str | Path,
        input: str | bytes,
        capture_output: bool,
        text: bool,
        timeout: int | None,
        check: bool,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[Any]:
        stdout_pipe = subprocess.PIPE if capture_output else None
        stderr_pipe = subprocess.PIPE if capture_output else None
        creation_kwargs = _managed_process_startup_kwargs()

        process = subprocess.Popen(
            args,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=stdout_pipe,
            stderr=stderr_pipe,
            text=text,
            env=env,
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
        timeout: int | float | None,
        args: list[str],
    ) -> tuple[Any, Any]:
        deadline = time.monotonic() + float(timeout) if timeout and float(timeout) > 0 else None
        if self.cancellation_check is None and deadline is None:
            return process.communicate(input=input, timeout=None)
        sent_input = False
        last_timeout: subprocess.TimeoutExpired | None = None
        grace_extensions = 0
        while True:
            if self.cancellation_check and self.cancellation_check():
                raise WorkerCancelled(f"Worker cancellation requested for {self.record.task_id}.")
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                if self._can_extend_timeout_for_progress(process, grace_extensions):
                    snapshot = self.progress_probe(process.pid)
                    if bool(snapshot.get("active")):
                        grace_extensions += 1
                        deadline = time.monotonic() + self.timeout_progress_grace_seconds
                        self.recorder.record_timeout_grace(
                            self.record,
                            grace_seconds=self.timeout_progress_grace_seconds,
                            snapshot=snapshot,
                        )
                        continue
                raise _timeout_with_partial_output(args, timeout, last_timeout)
            try:
                return process.communicate(
                    input=input if not sent_input else None,
                    timeout=self.poll_interval_seconds if remaining is None else min(self.poll_interval_seconds, remaining),
                )
            except subprocess.TimeoutExpired as exc:
                sent_input = True
                last_timeout = exc
                if process.poll() is not None:
                    return self._finish_exited_process_with_open_pipes(process, args, exc)

    def _can_extend_timeout_for_progress(self, process: subprocess.Popen[Any], grace_extensions: int) -> bool:
        if process.poll() is not None:
            return False
        if self.timeout_progress_grace_seconds <= 0:
            return False
        if grace_extensions >= self.max_timeout_grace_extensions:
            return False
        return True

    def _finish_exited_process_with_open_pipes(
        self,
        process: subprocess.Popen[Any],
        args: list[str],
        first_timeout: subprocess.TimeoutExpired,
    ) -> tuple[Any, Any]:
        """Recover when a finished child leaves captured pipes open via descendants."""

        try:
            return process.communicate(input=None, timeout=self.pipe_drain_grace_seconds)
        except subprocess.TimeoutExpired as exc:
            self.record.error = "Process exited before captured pipes closed; salvaged available output."
            self.recorder.persist(self.record)
            self._close_process_pipes(process)
            stdout = exc.output if exc.output is not None else first_timeout.output
            stderr = exc.stderr if exc.stderr is not None else first_timeout.stderr
            return stdout, stderr

    def _close_process_pipes(self, process: subprocess.Popen[Any]) -> None:
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is None:
                continue
            try:
                stream.close()
            except OSError:
                continue


class WorkerCancelled(Exception):
    """Raised when operator stop is requested while the worker is running."""


def _timeout_with_partial_output(
    args: list[str],
    timeout: int | float | None,
    last_timeout: subprocess.TimeoutExpired | None,
) -> subprocess.TimeoutExpired:
    if last_timeout is None:
        return subprocess.TimeoutExpired(args, timeout)
    return subprocess.TimeoutExpired(args, timeout, output=last_timeout.output, stderr=last_timeout.stderr)


def _managed_process_startup_kwargs() -> dict[str, Any]:
    if os.name != "nt":
        return {"preexec_fn": os.setsid}
    return hidden_subprocess_startup_kwargs(new_process_group=True)


def detect_worker_progress(pid: int) -> dict[str, Any]:
    """Return a small process-tree snapshot when a timed-out worker is still doing verification work."""

    if pid <= 0:
        return {"active": False, "reason": "invalid worker pid"}
    if os.name == "nt":
        return _detect_windows_worker_progress(pid)
    return {"active": False, "reason": "progress probe is only implemented for Windows workers"}


def _detect_windows_worker_progress(pid: int) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name | ConvertTo-Json -Compress -Depth 3",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            **hidden_subprocess_startup_kwargs(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"active": False, "reason": f"process snapshot failed: {exc}"}
    if result.returncode != 0:
        return {"active": False, "reason": "process snapshot command failed", "stderr": result.stderr[:400]}
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        return {"active": False, "reason": f"process snapshot parse failed: {exc}"}
    rows = payload if isinstance(payload, list) else [payload]
    descendants = _worker_descendants(pid, rows)
    active = [
        row
        for row in descendants
        if str(row.get("Name", "")).strip().lower() in PROGRESS_PROCESS_NAMES
    ]
    return {
        "active": bool(active),
        "reason": "verification child process detected" if active else "no verification child process detected",
        "worker_pid": pid,
        "descendant_count": len(descendants),
        "active_descendants": [
            {
                "pid": int_or_zero(row.get("ProcessId")),
                "parent_pid": int_or_zero(row.get("ParentProcessId")),
                "name": str(row.get("Name", "")),
            }
            for row in active[:12]
        ],
    }


def _worker_descendants(pid: int, rows: list[Any]) -> list[dict[str, Any]]:
    children_by_parent: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        parent_id = int_or_zero(row.get("ParentProcessId"))
        if parent_id <= 0:
            continue
        children_by_parent.setdefault(parent_id, []).append(row)
    descendants: list[dict[str, Any]] = []
    queue = [pid]
    seen: set[int] = set()
    while queue:
        parent_id = queue.pop(0)
        if parent_id in seen:
            continue
        seen.add(parent_id)
        for child in children_by_parent.get(parent_id, []):
            descendants.append(child)
            child_pid = int_or_zero(child.get("ProcessId"))
            if child_pid > 0:
                queue.append(child_pid)
    return descendants


def int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def terminate_process_tree(pid: int) -> dict[str, Any]:
    if os.name == "nt":
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            **hidden_subprocess_startup_kwargs(),
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


def process_exists(pid: int | None) -> bool:
    """Return whether a recorded worker PID still exists."""

    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                **hidden_subprocess_startup_kwargs(),
            )
        except (OSError, subprocess.SubprocessError):
            return False
        output = result.stdout.strip()
        return result.returncode == 0 and output and "no tasks" not in output.lower() and f'"{pid}"' in output
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _safe_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "worker"
    if len(safe) <= 96:
        return safe
    return safe[:80].rstrip("-_.") + "-" + str(abs(hash(safe)))[-12:]
