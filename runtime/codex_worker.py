"""Codex worker adapter.

The runtime supports two execution modes:

- ``dry_run=True`` returns deterministic structured evidence for local tests and
  demos without mutating a repository.
- ``dry_run=False`` invokes a real Codex CLI subprocess with a bounded worker
  package and parses the required ``codex_worker_result_v1`` JSON contract.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from .models import WorkerStatus


@dataclass(slots=True)
class CommandResult:
    command: str
    exit_code: int
    summary: str = ""
    stdout: str = ""
    stderr: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CommandResult":
        return cls(
            command=str(payload.get("command", "")),
            exit_code=int(payload.get("exit_code", 0)),
            summary=str(payload.get("summary", "")),
            stdout=str(payload.get("stdout", "")),
            stderr=str(payload.get("stderr", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "exit_code": self.exit_code,
            "summary": self.summary,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


@dataclass(slots=True)
class CodexWorkerInput:
    task_id: str
    goal: str
    objective: str = ""
    task_description: str = ""
    acceptance_criteria: list[str] = field(default_factory=list)
    repository_path: str = "."
    branch: str = ""
    agent_context: dict[str, Any] = field(default_factory=dict)
    relevant_files: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    commands_to_run: list[str] = field(default_factory=list)
    expected_output_format: str = "codex_worker_result_v1"
    retry_context: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "objective": self.objective or self.goal,
            "goal": self.goal,
            "task_description": self.task_description or self.goal,
            "acceptance_criteria": list(self.acceptance_criteria),
            "repository_path": self.repository_path,
            "branch": self.branch,
            "agent_context": dict(self.agent_context),
            "relevant_files": list(self.relevant_files),
            "constraints": list(self.constraints),
            "commands_to_run": list(self.commands_to_run),
            "expected_output_format": self.expected_output_format,
            "retry_context": self.retry_context,
        }


@dataclass(slots=True)
class CodexWorkerResult:
    task_id: str
    status: WorkerStatus
    summary: str
    files_changed: list[str] = field(default_factory=list)
    commands_run: list[CommandResult] = field(default_factory=list)
    tests_passed: list[str] = field(default_factory=list)
    tests_failed: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    known_issues: list[str] = field(default_factory=list)
    follow_up_tasks: list[str] = field(default_factory=list)
    confidence: float = 0.0
    raw_output: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CodexWorkerResult":
        status = _normalize_status(str(payload.get("status", "failed")))
        commands = [
            item if isinstance(item, CommandResult) else CommandResult.from_dict(dict(item))
            for item in payload.get("commands_run", [])
        ]
        return cls(
            task_id=str(payload.get("task_id", "")),
            status=status,
            summary=str(payload.get("summary", "")),
            files_changed=[str(item) for item in payload.get("files_changed", [])],
            commands_run=commands,
            tests_passed=[str(item) for item in payload.get("tests_passed", [])],
            tests_failed=[str(item) for item in payload.get("tests_failed", [])],
            evidence=[str(item) for item in payload.get("evidence", [])],
            known_issues=[str(item) for item in payload.get("known_issues", [])],
            follow_up_tasks=[str(item) for item in payload.get("follow_up_tasks", [])],
            confidence=float(payload.get("confidence", 0.0)),
            raw_output=str(payload.get("raw_output", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "summary": self.summary,
            "files_changed": list(self.files_changed),
            "commands_run": [command.to_dict() for command in self.commands_run],
            "tests_passed": list(self.tests_passed),
            "tests_failed": list(self.tests_failed),
            "evidence": list(self.evidence),
            "known_issues": list(self.known_issues),
            "follow_up_tasks": list(self.follow_up_tasks),
            "confidence": self.confidence,
            "raw_output": self.raw_output,
        }


class SubprocessRunner(Protocol):
    def __call__(
        self,
        args: list[str],
        *,
        cwd: str | Path,
        input: str,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        ...


class CodexWorkerAdapter:
    """Invoke Codex CLI or produce deterministic dry-run worker results."""

    def __init__(
        self,
        *,
        executable: str = "codex",
        dry_run: bool = True,
        timeout_seconds: int = 1800,
        runner: SubprocessRunner = subprocess.run,
    ) -> None:
        self.executable = executable
        self.dry_run = dry_run
        self.timeout_seconds = timeout_seconds
        self.runner = runner

    def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
        if self.dry_run:
            return self._execute_dry_run(worker_input)
        return self._execute_codex(worker_input)

    def build_prompt(self, worker_input: CodexWorkerInput) -> str:
        package_json = json.dumps(worker_input.to_dict(), indent=2, sort_keys=True)
        return (
            "You are a Codex execution worker inside the Alchemy Dev Agent System.\n"
            "Complete only the bounded task package below. Inspect files, edit within scope, "
            "run requested verification commands, fix task-local failures, and return only "
            "valid JSON matching codex_worker_result_v1.\n\n"
            "Required JSON fields: task_id, status, summary, files_changed, commands_run, "
            "tests_passed, tests_failed, evidence, known_issues, follow_up_tasks, confidence.\n"
            "Allowed status values: completed, partial, failed, blocked.\n\n"
            f"TASK_PACKAGE:\n{package_json}\n"
        )

    def _execute_codex(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
        prompt = self.build_prompt(worker_input)
        args = [self.executable, "exec", "--json"]
        try:
            completed = self.runner(
                args,
                cwd=worker_input.repository_path,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            return self._blocked(worker_input, f"Codex executable not found: {exc}")
        except PermissionError as exc:
            return self._blocked(worker_input, f"Codex executable is not launchable: {exc}")
        except subprocess.TimeoutExpired as exc:
            return CodexWorkerResult(
                task_id=worker_input.task_id,
                status="failed",
                summary=f"Codex worker timed out after {self.timeout_seconds} seconds.",
                known_issues=[str(exc)],
                confidence=0.0,
                raw_output=str(exc),
            )

        raw_output = "\n".join(part for part in [completed.stdout, completed.stderr] if part)
        parsed = self._parse_worker_json(completed.stdout) or self._parse_worker_json(raw_output)
        if parsed is None:
            status: WorkerStatus = "failed" if completed.returncode else "partial"
            return CodexWorkerResult(
                task_id=worker_input.task_id,
                status=status,
                summary="Codex worker did not return parseable codex_worker_result_v1 JSON.",
                commands_run=[
                    CommandResult(
                        command=" ".join(args),
                        exit_code=completed.returncode,
                        summary="Codex subprocess completed without a parseable structured result.",
                        stdout=completed.stdout,
                        stderr=completed.stderr,
                    )
                ],
                known_issues=["Missing structured worker JSON."],
                confidence=0.0,
                raw_output=raw_output,
            )

        result = CodexWorkerResult.from_dict(parsed)
        if not result.task_id:
            result.task_id = worker_input.task_id
        result.raw_output = raw_output
        if completed.returncode != 0 and result.status == "completed":
            result.status = "partial"
            result.known_issues.append(f"Codex subprocess exited {completed.returncode}.")
        return result

    def _execute_dry_run(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
        goal = worker_input.goal.lower()
        constraints = " ".join(worker_input.constraints).lower()

        if "block" in constraints or "blocked" in goal:
            return CodexWorkerResult(
                task_id=worker_input.task_id,
                status="blocked",
                summary=f"{worker_input.task_id}: blocked by deterministic constraint.",
                known_issues=["Dry-run blocker requested by constraints."],
                confidence=0.0,
            )

        if "fail" in constraints:
            return CodexWorkerResult(
                task_id=worker_input.task_id,
                status="failed",
                summary=f"{worker_input.task_id}: failed by deterministic constraint.",
                tests_failed=["dry-run failure constraint"],
                confidence=0.0,
            )

        command_results = [
            CommandResult(command=command, exit_code=0, summary="Dry-run command treated as passing.")
            for command in worker_input.commands_to_run
        ]
        tests_passed = worker_input.commands_to_run or ["dry-run verification"]
        files_changed = list(worker_input.relevant_files)
        if not files_changed and worker_input.task_id:
            files_changed = [f"dry-run/{worker_input.task_id}"]

        return CodexWorkerResult(
            task_id=worker_input.task_id,
            status="completed",
            summary=f"{worker_input.task_id}: dry-run completed for {worker_input.goal}",
            files_changed=files_changed,
            commands_run=command_results,
            tests_passed=tests_passed,
            evidence=[
                "Bounded task package accepted.",
                "Dry-run execution preserves worker result contract.",
            ],
            confidence=0.9,
        )

    def _parse_worker_json(self, output: str) -> dict[str, Any] | None:
        if not output.strip():
            return None
        matches: list[dict[str, Any]] = []
        for candidate in self._json_candidates(output):
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            match = self._find_worker_result(payload)
            if match is not None:
                matches.append(match)
        return matches[-1] if matches else None

    def _json_candidates(self, output: str) -> list[str]:
        stripped = output.strip()
        candidates = [stripped]
        candidates.extend(line.strip() for line in stripped.splitlines() if line.strip())
        candidates.extend(self._fenced_json_candidates(stripped))
        start = stripped.find("{")
        end = stripped.rfind("}")
        if 0 <= start < end:
            candidates.append(stripped[start : end + 1])
        return candidates

    def _fenced_json_candidates(self, output: str) -> list[str]:
        candidates: list[str] = []
        fence = "```"
        start = 0
        while True:
            open_index = output.find(fence, start)
            if open_index < 0:
                break
            content_start = output.find("\n", open_index + len(fence))
            if content_start < 0:
                break
            close_index = output.find(fence, content_start + 1)
            if close_index < 0:
                break
            candidates.append(output[content_start + 1 : close_index].strip())
            start = close_index + len(fence)
        return candidates

    def _find_worker_result(self, payload: Any) -> dict[str, Any] | None:
        if isinstance(payload, dict):
            if "status" in payload:
                return payload
            for value in payload.values():
                match = self._find_worker_result(value)
                if match is not None:
                    return match
        if isinstance(payload, list):
            for value in payload:
                match = self._find_worker_result(value)
                if match is not None:
                    return match
        if isinstance(payload, str):
            return self._parse_worker_json(payload)
        return None

    def _blocked(self, worker_input: CodexWorkerInput, summary: str) -> CodexWorkerResult:
        return CodexWorkerResult(
            task_id=worker_input.task_id,
            status="blocked",
            summary=summary,
            known_issues=[summary],
            confidence=0.0,
        )


def _normalize_status(status: str) -> WorkerStatus:
    if status in {"completed", "partial", "failed", "blocked"}:
        return status  # type: ignore[return-value]
    legacy_map: dict[str, WorkerStatus] = {
        "passed": "completed",
        "success": "completed",
        "error": "failed",
    }
    return legacy_map.get(status, "failed")
