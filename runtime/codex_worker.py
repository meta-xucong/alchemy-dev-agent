"""Codex worker adapter.

The runtime supports two execution modes:

- ``dry_run=True`` returns deterministic structured evidence for local tests and
  demos without mutating a repository.
- ``dry_run=False`` invokes a real Codex CLI subprocess with a bounded worker
  package and parses the required ``codex_worker_result_v1`` JSON contract.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import subprocess
import tempfile
from hashlib import sha1
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Protocol

from .models import WorkerStatus
from .subprocess_utils import clean_git_env, run_hidden
from .tool_discovery import codex_executable_candidates, is_codex_command, resolve_codex_executable
from .worker_lifecycle import ManagedSubprocessRunner, WorkerLifecycleRecorder


RAW_OUTPUT_LIMIT = 20_000
WORKER_TEXT_FIELD_LIMIT = 4_000
COMMAND_OUTPUT_FIELD_LIMIT = 1_000
CODEX_USAGE_LIMIT_MARKERS = (
    "you've hit your usage limit",
    "you have hit your usage limit",
    "usage limit reached",
    "purchase more credits",
)
CODEX_CONFIG_FAILURE_MARKERS = (
    "error loading config.toml",
    "unknown variant",
    "in `service_tier`",
)


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
            command=_truncate_text(str(payload.get("command", "")), limit=WORKER_TEXT_FIELD_LIMIT),
            exit_code=_coerce_exit_code(payload.get("exit_code")),
            summary=_truncate_text(str(payload.get("summary", "")), limit=WORKER_TEXT_FIELD_LIMIT),
            stdout=_truncate_text(str(payload.get("stdout", "")), limit=COMMAND_OUTPUT_FIELD_LIMIT),
            stderr=_truncate_text(str(payload.get("stderr", "")), limit=COMMAND_OUTPUT_FIELD_LIMIT),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "exit_code": self.exit_code,
            "summary": self.summary,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


@dataclass(frozen=True, slots=True)
class FileSnapshot:
    exists: bool
    content: bytes = b""


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
    allowed_files: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    commands_to_run: list[str] = field(default_factory=list)
    expected_output_format: str = "codex_worker_result_v1"
    retry_context: str = ""
    boundary_mode: str = "strict"
    task_packet: dict[str, Any] = field(default_factory=dict)

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
            "allowed_files": list(self.allowed_files),
            "constraints": list(self.constraints),
            "commands_to_run": list(self.commands_to_run),
            "expected_output_format": self.expected_output_format,
            "retry_context": self.retry_context,
            "boundary_mode": self.boundary_mode,
            "task_packet": dict(self.task_packet),
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
    worker_lifecycle: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CodexWorkerResult":
        status = _normalize_status(str(payload.get("status", "failed")))
        commands = [_coerce_command_result(item) for item in _coerce_list(payload.get("commands_run", []))]
        return cls(
            task_id=str(payload.get("task_id", "")),
            status=status,
            summary=_truncate_text(str(payload.get("summary", "")), limit=WORKER_TEXT_FIELD_LIMIT),
            files_changed=[str(item) for item in _coerce_list(payload.get("files_changed", []))],
            commands_run=commands,
            tests_passed=_coerce_text_list(payload.get("tests_passed", [])),
            tests_failed=_coerce_text_list(payload.get("tests_failed", [])),
            evidence=_coerce_text_list(payload.get("evidence", [])),
            known_issues=_coerce_text_list(payload.get("known_issues", [])),
            follow_up_tasks=_coerce_text_list(payload.get("follow_up_tasks", [])),
            confidence=_coerce_float(payload.get("confidence", 0.0)),
            raw_output=_truncate_raw_output(str(payload.get("raw_output", ""))),
            worker_lifecycle=dict(payload.get("worker_lifecycle", {})) if isinstance(payload.get("worker_lifecycle", {}), dict) else {},
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
            "worker_lifecycle": dict(self.worker_lifecycle),
        }


class SubprocessRunner(Protocol):
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
        ...


class CodexWorkerAdapter:
    """Invoke Codex CLI or produce deterministic dry-run worker results."""

    def __init__(
        self,
        *,
        executable: str = "codex",
        model: str = "",
        dry_run: bool = True,
        sandbox: Literal["read-only", "workspace-write", "danger-full-access"] = "workspace-write",
        timeout_seconds: int | None = 1800,
        runner: SubprocessRunner = subprocess.run,
        lifecycle_recorder: WorkerLifecycleRecorder | None = None,
        cancellation_check: Callable[[str], bool] | None = None,
    ) -> None:
        self.executable = executable
        self.model = model.strip() or os.environ.get("ALCHEMY_CODEX_MODEL", "").strip()
        self.dry_run = dry_run
        self.sandbox = sandbox
        self.timeout_seconds = timeout_seconds if timeout_seconds and timeout_seconds > 0 else None
        self.runner = runner
        self.lifecycle_recorder = lifecycle_recorder
        self.cancellation_check = cancellation_check

    def execute(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
        if self.dry_run:
            return self._execute_dry_run(worker_input)
        return self._execute_codex(worker_input)

    def build_prompt(self, worker_input: CodexWorkerInput) -> str:
        package_json = json.dumps(worker_input.to_dict(), indent=2, sort_keys=True)
        return (
            "You are a Codex execution worker inside the Alchemy Dev Agent System.\n"
            "Complete only the bounded task package below. Inspect files, edit only files listed "
            "in allowed_files, run requested verification commands, fix task-local failures, and return only "
            "valid JSON matching codex_worker_result_v1.\n\n"
            "If allowed_files is empty, do not edit repository files. Return blocked or partial if the task "
            "cannot be completed without edits.\n\n"
            "Before opening, patching, or testing a file whose path is uncertain, confirm the exact repository "
            "path from repository evidence such as `rg --files` or `rg -n` instead of guessing.\n\n"
            "Keep command output small. Prefer path-scoped searches, `rg -l`, `rg --count`, or searches piped to "
            "`Select-Object -First 80` before printing matching lines. Do not run broad `rg -n` searches for common "
            "terms across large directories unless the command limits output. Do not print full `git diff`, full "
            "`git status --short` for a very dirty tree, generated files, dependency directories, build artifacts, "
            "or long test logs; use path filters, summaries, counts, or targeted line ranges instead. In the final "
            "JSON, keep `commands_run.stdout`, `commands_run.stderr`, `raw_output`, and each evidence string brief; "
            "summarize large outputs instead of pasting them.\n\n"
            "You may run package-manager install commands when they are needed for verification and existing "
            "dependency manifests or lockfiles define the dependency set. Keep install output limited to ignored "
            "dependency/cache directories such as node_modules; do not modify manifests or lockfiles unless those "
            "files are explicitly listed in allowed_files.\n\n"
            "When the host shell is Windows PowerShell, use PowerShell-safe command forms: do not pass wildcard "
            "paths as literal file arguments to `rg` or `Get-Content`; prefer searching directories or using "
            "`rg --glob`. When reading line ranges, load the file into `$lines = Get-Content ...` and slice "
            "`$lines[start..end]` instead of `Select-Object -Index start..end`. Avoid inline shell commands whose "
            "regex or filter text contains unescaped `|` when a simpler split command would work. Quote Windows "
            "paths that contain spaces before passing them to scripts or flags such as `--project`, and prefer "
            "setting the working directory instead of embedding long absolute paths when a command supports that. "
            "Treat shell globbing, quoting, or path-syntax errors as command formulation issues to fix before "
            "drawing repository conclusions.\n\n"
            "When verification uses Go, confirm the active module root from repository evidence before running "
            "`go test` or `go build`. If the relevant `go.mod` lives under a subdirectory such as `backend`, run "
            "Go commands from that module directory, for example `cd backend && go test ./...`, instead of "
            "assuming the repository root is a Go module.\n\n"
            "For single-file final frontend repair tasks, especially task titles containing `final frontend` and "
            "`view file`, `leaf file`, or `component file`, keep verification file-local. Do not run broad frontend "
            "commands such as `pnpm typecheck`, `pnpm build`, `pnpm test`, or `vitest run` unless the task package "
            "explicitly requests one of those commands. Prefer reading the named file, making the smallest scoped edit, "
            "checking nearby imports/types by inspection or path-scoped search, and leaving broad verification to the "
            "later final real repository checks.\n\n"
            "When the host shell is Windows PowerShell and Go verification needs `-run`, do not send regex "
            "alternation such as `|` through inline PowerShell commands. Prefer separate `go test -run ^TestName$` "
            "commands or another shell-safe formulation so the shell does not interpret the pattern.\n\n"
            "On Windows, treat Go cache setup as a stability concern. Prefer a known-writable, already populated "
            "`GOMODCACHE` when one exists. Do not launch multiple parallel `go test` processes against a fresh "
            "shared module cache, because concurrent module-download temp-file renames can fail with access denied. "
            "If a cold cache is unavoidable, warm it or use it sequentially before parallelizing verification.\n\n"
            "When a task references a protected commercial game or franchise, preserve only broad genre mechanics. "
            "Do not write protected names, character names, artwork names, exact layout names, or brand names into "
            "generated repository files, even in safety notes. Use original names and neutral descriptions instead.\n\n"
            "For generated canvas games, expose a deterministic browser-test hook at window.__ALCHEMY_GAME_TEST__. "
            "It must provide snapshot(), step(dt), advanceToVictory(), and restart(). snapshot() should return numeric "
            "player_x, numeric player_y, state, and won fields. These hooks are for automated acceptance and must not "
            "require external assets or network calls.\n\n"
            "For generated static web apps, use semantic HTML controls where possible: forms, labels, inputs, buttons, "
            "main/app roots, accessible names, and visible state updates after user actions. Automated acceptance may "
            "fill inputs, click safe controls, and compare visible DOM state. When acceptance criteria mention CRUD, "
            "login/auth, file upload, dashboards, metrics, filters, tables, or search, expose matching visible controls "
            "and labels so domain-specific browser scenarios can verify them.\n\n"
            "Required JSON fields: task_id, status, summary, files_changed, commands_run, "
            "tests_passed, tests_failed, evidence, known_issues, follow_up_tasks, confidence.\n"
            "Allowed status values: completed, partial, failed, blocked.\n\n"
            f"TASK_PACKAGE:\n{package_json}\n"
        )

    def _execute_codex(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
        prompt = self.build_prompt(worker_input)
        repository_path = str(Path(worker_input.repository_path).resolve())
        def _build_args(executable: str) -> list[str]:
            if not _is_codex_cli_executable(executable):
                return [executable, "exec", "--json", "--sandbox", self.sandbox]
            model_args = ["-m", self.model] if self.model else []
            if _should_bypass_codex_cli_sandbox(self.sandbox):
                return [
                    executable,
                    "--disable",
                    "plugins",
                    *model_args,
                    "--dangerously-bypass-approvals-and-sandbox",
                    "exec",
                    "--json",
                    "--cd",
                    repository_path,
                ]
            return [
                executable,
                "--disable",
                "plugins",
                *model_args,
                "-c",
                'approval_policy="never"',
                "-c",
                f'sandbox_mode="{self.sandbox}"',
                "--ask-for-approval",
                "never",
                "--sandbox",
                self.sandbox,
                "exec",
                "--json",
                "--cd",
                repository_path,
            ]

        selected_executable = self.executable
        if self.runner is subprocess.run and _is_codex_cli_executable(self.executable):
            selected_executable = resolve_codex_executable(self.executable) or self.executable
        args = _build_args(selected_executable)
        codex_env = _build_codex_subprocess_env(worker_input.repository_path) if self.runner is subprocess.run else None
        _cleanup_codex_windows_scratch_files(worker_input.repository_path)
        before_snapshot = self._capture_worktree_snapshot(worker_input.repository_path)
        lifecycle_record = None
        runner = self.runner
        if self.lifecycle_recorder is not None and self.runner is subprocess.run:
            lifecycle_record = self.lifecycle_recorder.start(worker_input.task_id, self.timeout_seconds)
            runner = ManagedSubprocessRunner(
                self.lifecycle_recorder,
                lifecycle_record,
                cancellation_check=(
                    (lambda: bool(self.cancellation_check and self.cancellation_check(worker_input.task_id)))
                    if self.cancellation_check
                    else None
                ),
                timeout_progress_grace_seconds=_timeout_progress_grace_seconds(self.timeout_seconds),
            )
        try:
            kwargs: dict[str, Any] = {
                "cwd": worker_input.repository_path,
                "input": prompt.encode("utf-8"),
                "capture_output": True,
                "text": False,
                "timeout": self.timeout_seconds,
                "check": False,
            }
            if codex_env is not None:
                kwargs["env"] = codex_env
            completed = runner(args, **kwargs)
        except (FileNotFoundError, PermissionError) as exc:
            fallback_executable = _fallback_codex_executable(selected_executable)
            if not fallback_executable:
                if lifecycle_record is not None:
                    self.lifecycle_recorder.fail(lifecycle_record, str(exc))
                failure = "not found" if isinstance(exc, FileNotFoundError) else "not launchable"
                return self._blocked(worker_input, f"Codex executable is {failure}: {exc}", lifecycle_record)
            try:
                args = _build_args(fallback_executable)
                completed = runner(args, **kwargs)
            except (FileNotFoundError, PermissionError) as retry_exc:
                if lifecycle_record is not None:
                    self.lifecycle_recorder.fail(lifecycle_record, str(retry_exc))
                return self._blocked(worker_input, f"Codex executable is not launchable: {retry_exc}", lifecycle_record)
        except subprocess.TimeoutExpired as exc:
            self._rollback_task_changes(worker_input.repository_path, before_snapshot)
            lifecycle_payload = lifecycle_record.to_dict() if lifecycle_record is not None else {}
            timeout_summary = f"Codex worker timed out after {self.timeout_seconds} seconds."
            grace_seconds = float(lifecycle_payload.get("timeout_grace_seconds") or 0.0)
            if grace_seconds > 0:
                timeout_summary = (
                    f"Codex worker timed out after {self.timeout_seconds} seconds plus "
                    f"{grace_seconds:g} seconds of progress grace."
                )
            if lifecycle_payload.get("status") == "cancelled":
                return CodexWorkerResult(
                    task_id=worker_input.task_id,
                    status="blocked",
                    summary="Codex worker was cancelled by operator stop request.",
                    known_issues=["Worker subprocess was terminated after stop was requested."],
                    confidence=0.0,
                    raw_output=_truncate_raw_output(str(exc)),
                    worker_lifecycle=lifecycle_payload,
                )
            return CodexWorkerResult(
                task_id=worker_input.task_id,
                status="failed",
                summary=timeout_summary,
                known_issues=[
                    str(exc),
                    "Task-local repository changes were rolled back to the pre-task snapshot; pre-existing dirty files may remain.",
                ],
                confidence=0.0,
                raw_output=_truncate_raw_output(str(exc)),
                worker_lifecycle=lifecycle_payload,
            )

        stdout = _decode_subprocess_output(completed.stdout)
        stderr = _decode_subprocess_output(completed.stderr)
        raw_output = "\n".join(part for part in [stdout, stderr] if part)
        if lifecycle_record is not None and lifecycle_record.status == "cancelled":
            self._rollback_task_changes(worker_input.repository_path, before_snapshot)
            return CodexWorkerResult(
                task_id=worker_input.task_id,
                status="blocked",
                summary="Codex worker was cancelled by operator stop request.",
                commands_run=[
                    CommandResult(
                        command=" ".join(args),
                        exit_code=completed.returncode,
                        summary="Codex subprocess was terminated after stop was requested.",
                        stdout=stdout,
                        stderr=stderr,
                    )
                ],
                known_issues=["Worker subprocess was terminated after stop was requested."],
                confidence=0.0,
                raw_output=_truncate_raw_output(raw_output),
                worker_lifecycle=lifecycle_record.to_dict(),
            )
        changed_files = self._task_changed_files(worker_input.repository_path, before_snapshot)
        boundary_violation = self._audit_file_boundaries(worker_input, changed_files)
        if boundary_violation:
            self._rollback_files(worker_input.repository_path, boundary_violation, before_snapshot)
            return CodexWorkerResult(
                task_id=worker_input.task_id,
                status="failed",
                summary="Codex worker modified files outside the task boundary; offending changes were rolled back.",
                files_changed=changed_files,
                known_issues=[
                    "Out-of-scope files changed: " + ", ".join(boundary_violation),
                    "Allowed files: " + (", ".join(worker_input.allowed_files) if worker_input.allowed_files else "(none)"),
                ],
                confidence=0.0,
                raw_output=_truncate_raw_output(raw_output),
                worker_lifecycle=lifecycle_record.to_dict() if lifecycle_record is not None else {},
            )
        usage_limit_message = _codex_usage_limit_message(raw_output)
        if usage_limit_message:
            return CodexWorkerResult(
                task_id=worker_input.task_id,
                status="blocked",
                summary=f"Codex CLI usage limit reached: {usage_limit_message}",
                files_changed=changed_files,
                commands_run=[
                    CommandResult(
                        command=" ".join(args),
                        exit_code=completed.returncode,
                        summary="Codex subprocess stopped before returning structured worker output because local usage is limited.",
                        stdout=stdout,
                        stderr=stderr,
                    )
                ],
                known_issues=[
                    "Local Codex CLI usage limit reached; wait for the reset time or configure an approved provider before retrying.",
                ],
                confidence=0.0,
                raw_output=_truncate_raw_output(raw_output),
                worker_lifecycle=lifecycle_record.to_dict() if lifecycle_record is not None else {},
            )
        parsed = self._parse_worker_json(stdout) or self._parse_worker_json(raw_output)
        if parsed is None:
            config_failure_message = _codex_config_failure_message(raw_output)
            if config_failure_message:
                return CodexWorkerResult(
                    task_id=worker_input.task_id,
                    status="blocked",
                    summary=f"Codex CLI configuration failed before structured worker output: {config_failure_message}",
                    commands_run=[
                        CommandResult(
                            command=" ".join(args),
                            exit_code=completed.returncode,
                            summary="Codex subprocess stopped before returning structured worker output because local CLI configuration is invalid.",
                            stdout=stdout,
                            stderr=stderr,
                        )
                    ],
                    known_issues=[
                        "Local Codex CLI configuration is invalid; fix the user config.toml before retrying workers.",
                    ],
                    confidence=0.0,
                    raw_output=_truncate_raw_output(raw_output),
                    worker_lifecycle=lifecycle_record.to_dict() if lifecycle_record is not None else {},
                )
            connectivity_message = _codex_connectivity_failure_message(raw_output)
            if connectivity_message:
                return CodexWorkerResult(
                    task_id=worker_input.task_id,
                    status="blocked",
                    summary=f"Codex CLI connectivity failed before structured worker output: {connectivity_message}",
                    commands_run=[
                        CommandResult(
                            command=" ".join(args),
                            exit_code=completed.returncode,
                            summary="Codex subprocess stopped before returning structured worker output because the local Codex connection failed.",
                            stdout=stdout,
                            stderr=stderr,
                        )
                    ],
                    known_issues=[
                        "Local Codex CLI connectivity failed before a parseable worker result was returned; retry only after a smoke check or connectivity recovery.",
                    ],
                    confidence=0.0,
                    raw_output=_truncate_raw_output(raw_output),
                    worker_lifecycle=lifecycle_record.to_dict() if lifecycle_record is not None else {},
                )
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
                        stdout=stdout,
                        stderr=stderr,
                    )
                ],
                known_issues=["Missing structured worker JSON."],
                confidence=0.0,
                raw_output=_truncate_raw_output(raw_output),
                worker_lifecycle=lifecycle_record.to_dict() if lifecycle_record is not None else {},
            )

        result = CodexWorkerResult.from_dict(parsed)
        if not result.task_id:
            result.task_id = worker_input.task_id
        result.files_changed = changed_files or result.files_changed
        result.raw_output = _truncate_raw_output(raw_output)
        if lifecycle_record is not None:
            result.worker_lifecycle = lifecycle_record.to_dict()
        if completed.returncode != 0 and result.status == "completed":
            result.status = "partial"
            result.known_issues.append(f"Codex subprocess exited {completed.returncode}.")
        return result

    def _execute_dry_run(self, worker_input: CodexWorkerInput) -> CodexWorkerResult:
        goal = worker_input.goal.lower()
        constraint_values = {constraint.strip().lower() for constraint in worker_input.constraints}

        if {"block", "blocked", "dry-run:block", "dry-run:blocked"} & constraint_values:
            return CodexWorkerResult(
                task_id=worker_input.task_id,
                status="blocked",
                summary=f"{worker_input.task_id}: blocked by deterministic constraint.",
                known_issues=["Dry-run blocker requested by constraints."],
                confidence=0.0,
            )

        if {"fail", "dry-run:fail", "dry-run:failed"} & constraint_values:
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

    def _git_changed_files(self, repository_path: str | Path) -> set[str]:
        path = Path(repository_path)
        if not (path / ".git").exists():
            return set()
        try:
            kwargs = {
                "cwd": path,
                "input": "",
                "capture_output": True,
                "text": True,
                "timeout": 30,
                "check": False,
            }
            if self.runner is subprocess.run:
                kwargs["env"] = clean_git_env(path)
            result = run_hidden(self.runner, ["git", "status", "--porcelain"], **kwargs)
        except (OSError, subprocess.SubprocessError):
            return set()
        if result.returncode != 0:
            return set()
        return set(self._parse_porcelain_paths(result.stdout))

    def _new_or_modified_files(self, repository_path: str | Path, before: set[str]) -> list[str]:
        after = self._git_changed_files(repository_path)
        changed: list[str] = []
        for path in after - before:
            changed.extend(self._expand_changed_path(repository_path, path))
        return sorted(path for path in set(changed) if not _is_ignorable_generated_file(path))

    def _capture_worktree_snapshot(self, repository_path: str | Path) -> dict[str, FileSnapshot]:
        snapshots: dict[str, FileSnapshot] = {}
        for changed_path in self._git_changed_files(repository_path):
            for file_path in self._expand_changed_path(repository_path, changed_path):
                if not _is_ignorable_generated_file(file_path):
                    snapshots[file_path] = self._snapshot_file(repository_path, file_path)
        return snapshots

    def _task_changed_files(self, repository_path: str | Path, before: dict[str, FileSnapshot]) -> list[str]:
        after_paths: set[str] = set()
        for changed_path in self._git_changed_files(repository_path):
            after_paths.update(self._expand_changed_path(repository_path, changed_path))
        candidates = after_paths | set(before)
        changed: list[str] = []
        for file_path in candidates:
            if _is_ignorable_generated_file(file_path):
                continue
            previous = before.get(file_path)
            current = self._snapshot_file(repository_path, file_path)
            if previous is None:
                if file_path in after_paths or current.exists:
                    changed.append(file_path)
                continue
            if current != previous:
                changed.append(file_path)
        return sorted(set(changed))

    def _snapshot_file(self, repository_path: str | Path, file_path: str) -> FileSnapshot:
        repo = Path(repository_path)
        repo_root = repo.resolve()
        target = (repo / file_path).resolve()
        try:
            target.relative_to(repo_root)
        except ValueError:
            return FileSnapshot(False)
        if target.is_file():
            return FileSnapshot(True, target.read_bytes())
        return FileSnapshot(False)

    def _expand_changed_path(self, repository_path: str | Path, changed_path: str) -> list[str]:
        normalized = _normalize_repo_path(changed_path)
        if not normalized:
            return []
        target = Path(repository_path) / normalized
        if not target.is_dir():
            return [normalized]
        expanded: list[str] = []
        for child in target.rglob("*"):
            if child.is_file():
                try:
                    expanded.append(_normalize_repo_path(str(child.relative_to(repository_path))))
                except ValueError:
                    continue
        return expanded or [normalized]

    def _parse_porcelain_paths(self, output: str) -> list[str]:
        paths: list[str] = []
        for line in output.splitlines():
            if not line:
                continue
            raw_path = line[3:].strip()
            if " -> " in raw_path:
                raw_path = raw_path.split(" -> ", 1)[1]
            paths.append(_normalize_repo_path(raw_path.strip('"')))
        return [path for path in paths if path]

    def _audit_file_boundaries(self, worker_input: CodexWorkerInput, changed_files: list[str]) -> list[str]:
        allowed = [_normalize_repo_path(path) for path in worker_input.allowed_files]
        allowed = [path for path in allowed if path]
        return [
            path
            for path in changed_files
            if not _is_allowed_changed_path(path, allowed) and not _is_ignorable_generated_file(path)
        ]

    def _rollback_task_changes(self, repository_path: str | Path, before: dict[str, FileSnapshot]) -> None:
        self._rollback_files(repository_path, self._task_changed_files(repository_path, before), before)

    def _rollback_files(
        self,
        repository_path: str | Path,
        files: list[str],
        before: dict[str, FileSnapshot] | None = None,
    ) -> None:
        if not files:
            return
        repo = Path(repository_path)
        before = before or {}
        fallback_files: list[str] = []
        for file_path in files:
            snapshot = before.get(file_path)
            if snapshot is None:
                fallback_files.append(file_path)
                continue
            self._restore_snapshot_file(repo, file_path, snapshot)
        files = fallback_files
        if not files:
            return
        tracked: list[str] = []
        untracked: list[str] = []
        for file_path in files:
            kwargs = {
                "cwd": repo,
                "input": "",
                "capture_output": True,
                "text": True,
                "timeout": 30,
                "check": False,
            }
            if self.runner is subprocess.run:
                kwargs["env"] = clean_git_env(repo)
            result = run_hidden(self.runner, ["git", "ls-files", "--error-unmatch", "--", file_path], **kwargs)
            if result.returncode == 0:
                tracked.append(file_path)
            else:
                untracked.append(file_path)
        if tracked:
            kwargs = {
                "cwd": repo,
                "input": "",
                "capture_output": True,
                "text": True,
                "timeout": 60,
                "check": False,
            }
            if self.runner is subprocess.run:
                kwargs["env"] = clean_git_env(repo)
            run_hidden(self.runner, ["git", "checkout", "--", *tracked], **kwargs)
        repo_root = repo.resolve()
        for file_path in untracked:
            target = (repo / file_path).resolve()
            try:
                target.relative_to(repo_root)
            except ValueError:
                continue
            if target.is_file():
                target.unlink()

    def _restore_snapshot_file(self, repo: Path, file_path: str, snapshot: FileSnapshot) -> None:
        repo_root = repo.resolve()
        target = (repo / file_path).resolve()
        try:
            target.relative_to(repo_root)
        except ValueError:
            return
        if snapshot.exists:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(snapshot.content)
            return
        if target.is_file():
            target.unlink()

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

    def _blocked(
        self,
        worker_input: CodexWorkerInput,
        summary: str,
        lifecycle_record: object | None = None,
    ) -> CodexWorkerResult:
        return CodexWorkerResult(
            task_id=worker_input.task_id,
            status="blocked",
            summary=summary,
            known_issues=[summary],
            confidence=0.0,
            worker_lifecycle=lifecycle_record.to_dict() if lifecycle_record is not None else {},
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


def _coerce_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _coerce_text_list(value: Any) -> list[str]:
    return [_truncate_text(str(item), limit=WORKER_TEXT_FIELD_LIMIT) for item in _coerce_list(value)]


def _coerce_command_result(value: Any) -> CommandResult:
    if isinstance(value, CommandResult):
        return value
    if isinstance(value, dict):
        return CommandResult.from_dict(value)
    if isinstance(value, str):
        return CommandResult(command=value, exit_code=0)
    return CommandResult(command=str(value), exit_code=0)


def _coerce_exit_code(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _coerce_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _decode_subprocess_output(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _truncate_text(value: str, *, limit: int) -> str:
    if len(value) <= limit:
        return value
    marker = f"...[truncated to {limit} chars; omitted {len(value) - limit} chars]..."
    if len(marker) >= limit:
        return value[:limit]
    budget = limit - len(marker)
    head = max(budget // 2, 0)
    tail = max(budget - head, 0)
    return value[:head] + marker + value[-tail:]


def _truncate_raw_output(output: str, *, limit: int = RAW_OUTPUT_LIMIT) -> str:
    if len(output) <= limit:
        return output
    marker = f"\n...[raw output truncated to {limit} chars; omitted {len(output) - limit} chars]...\n"
    if len(marker) >= limit:
        return output[-limit:]
    budget = limit - len(marker)
    head = budget // 2
    tail = budget - head
    return output[:head] + marker + output[-tail:]


def _codex_usage_limit_message(output: str) -> str:
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not line.startswith("{"):
            if any(marker in line.lower() for marker in CODEX_USAGE_LIMIT_MARKERS):
                return line
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        event_type = str(payload.get("type", "") or "")
        message = ""
        if event_type == "error":
            message = str(payload.get("message", "") or "")
        elif event_type in {"turn.failed", "response.failed"}:
            error = payload.get("error")
            if isinstance(error, dict):
                message = str(error.get("message", "") or "")
            message = message or str(payload.get("message", "") or "")
        if message and any(marker in message.lower() for marker in CODEX_USAGE_LIMIT_MARKERS):
            return message.strip()
    return ""


def _codex_config_failure_message(output: str) -> str:
    plain_lines: list[str] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower_line = line.lower()
        if not line.startswith("{"):
            plain_lines.append(line)
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        event_type = str(payload.get("type", "") or "")
        message = ""
        if event_type == "error":
            message = str(payload.get("message", "") or "")
        elif event_type in {"turn.failed", "response.failed"}:
            error = payload.get("error")
            if isinstance(error, dict):
                message = str(error.get("message", "") or "")
            message = message or str(payload.get("message", "") or "")
        if message and any(marker in message.lower() for marker in CODEX_CONFIG_FAILURE_MARKERS):
            return message.strip()
    plain_message = " ".join(plain_lines)
    if any(marker in plain_message.lower() for marker in CODEX_CONFIG_FAILURE_MARKERS):
        return plain_message.strip()
    return ""


CODEX_CONNECTIVITY_FAILURE_MARKERS = (
    "stream disconnected",
    "idle timeout waiting for sse",
    "failed to connect to websocket",
    "error sending request",
    "remote host closed",
    "peer closed connection",
    "os error 10054",
)


def _codex_connectivity_failure_message(output: str) -> str:
    fallback = ""
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower_line = line.lower()
        if any(marker in lower_line for marker in CODEX_CONNECTIVITY_FAILURE_MARKERS):
            fallback = fallback or line
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        event_type = str(payload.get("type", "") or "")
        message = ""
        if event_type == "error":
            message = str(payload.get("message", "") or "")
        elif event_type in {"turn.failed", "response.failed"}:
            error = payload.get("error")
            if isinstance(error, dict):
                message = str(error.get("message", "") or "")
            message = message or str(payload.get("message", "") or "")
        if message and any(marker in message.lower() for marker in CODEX_CONNECTIVITY_FAILURE_MARKERS):
            if event_type in {"turn.failed", "response.failed"}:
                return message.strip()
            fallback = fallback or message.strip()
    return fallback.strip()


def _normalize_repo_path(path: str) -> str:
    return path.replace(os.sep, "/").replace("\\", "/").strip("/")


def _is_allowed_changed_path(path: str, allowed_files: list[str]) -> bool:
    normalized = _normalize_repo_path(path)
    for allowed in allowed_files:
        if _allowed_pattern_matches(normalized, allowed):
            return True
    return False


def _allowed_pattern_matches(path: str, allowed: str) -> bool:
    clean = _normalize_repo_path(allowed)
    if not clean:
        return False
    if clean.endswith("/**") and not _has_glob_meta(clean[:-3]):
        prefix = clean[:-3].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    if clean.endswith("/*") and not _has_glob_meta(clean[:-2]):
        prefix = clean[:-2].rstrip("/")
        if not (path.startswith(prefix + "/")):
            return False
        return "/" not in path[len(prefix) + 1 :]
    if clean.endswith("/") and not _has_glob_meta(clean):
        return path.startswith(clean)
    if any(char in clean for char in "*?["):
        return _segment_glob_matches(path, clean)
    return path == clean


def _has_glob_meta(pattern: str) -> bool:
    return any(char in pattern for char in "*?[")


def _segment_glob_matches(path: str, pattern: str) -> bool:
    path_parts = [part for part in _normalize_repo_path(path).split("/") if part]
    pattern_parts = [part for part in _normalize_repo_path(pattern).split("/") if part]
    return _match_path_segments(path_parts, pattern_parts)


def _match_path_segments(path_parts: list[str], pattern_parts: list[str]) -> bool:
    if not pattern_parts:
        return not path_parts
    head, *tail = pattern_parts
    if head == "**":
        if _match_path_segments(path_parts, tail):
            return True
        return bool(path_parts) and _match_path_segments(path_parts[1:], pattern_parts)
    if not path_parts:
        return False
    if not fnmatch.fnmatchcase(path_parts[0], head):
        return False
    return _match_path_segments(path_parts[1:], tail)


def _is_ignorable_generated_file(path: str) -> bool:
    normalized = _normalize_repo_path(path)
    parts = normalized.split("/")
    if "__pycache__" in parts:
        return True
    if ".alchemy" in parts:
        return True
    if ".alchemy_tmp" in parts:
        return True
    if _is_codex_windows_scratch_file(normalized):
        return True
    if normalized.endswith((".pyc", ".pyo", ".pyd")):
        return True
    if "node_modules" in parts:
        return True
    if any(part.startswith(".gocache") or part.startswith(".gobuildcache") for part in parts):
        return True
    if ".entc" in parts:
        return True
    if any(part.startswith("pytest-cache-files-") for part in parts):
        return True
    if _is_test_runtime_artifact(parts):
        return True
    if normalized.endswith((".log", ".tmp")):
        return True
    return False


def _is_codex_windows_scratch_file(normalized: str) -> bool:
    name = normalized.rsplit("/", 1)[-1]
    if not name.startswith("_tmp_"):
        return False
    chunks = name.split("_", 3)
    if len(chunks) != 4 or chunks[1] != "tmp":
        return False
    pid, token = chunks[2], chunks[3]
    if not pid.isdigit() or len(token) < 12:
        return False
    return all(char in "0123456789abcdefABCDEF" for char in token)


def _cleanup_codex_windows_scratch_files(repository_path: str | Path) -> None:
    root = Path(repository_path)
    if not root.exists():
        return
    for path in root.rglob("_tmp_*"):
        try:
            if not path.is_file():
                continue
            normalized = _normalize_repo_path(str(path.relative_to(root)))
        except OSError:
            continue
        if not _is_codex_windows_scratch_file(normalized):
            continue
        try:
            path.unlink()
        except OSError:
            continue


def _should_bypass_codex_cli_sandbox(sandbox: str) -> bool:
    if _truthy_env(os.environ.get("ALCHEMY_DISABLE_CODEX_CLI_BYPASS", "")):
        return False
    if _truthy_env(os.environ.get("ALCHEMY_FORCE_CODEX_CLI_BYPASS", "")):
        return True
    return False


def _is_codex_cli_executable(executable: str) -> bool:
    return is_codex_command(executable)


def _fallback_codex_executable(executable: str) -> str:
    if not _is_codex_cli_executable(executable) or os.name != "nt":
        return ""
    for candidate in _windows_local_codex_executable_candidates():
        if candidate.is_file() and os.path.normcase(str(candidate)) != os.path.normcase(str(executable)):
            return str(candidate)
    return ""


def _windows_local_codex_executable_candidates() -> list[Path]:
    return [candidate for candidate in codex_executable_candidates("codex") if candidate.name.lower() == "codex.exe"]


def _timeout_progress_grace_seconds(timeout_seconds: int | None) -> float:
    if not timeout_seconds or timeout_seconds < 300:
        return 0.0
    return min(300.0, max(60.0, float(timeout_seconds) / 3.0))


def _build_codex_subprocess_env(repository_path: str | Path) -> dict[str, str]:
    env = os.environ.copy()
    repo_path = Path(repository_path)
    codex_home = env.get("CODEX_HOME", "").strip()
    redirected_home = False
    if not codex_home:
        codex_home = str(_select_codex_home(repo_path))
        env["CODEX_HOME"] = codex_home
        redirected_home = True
    target_home = Path(codex_home)
    target_home.mkdir(parents=True, exist_ok=True)
    if redirected_home:
        _seed_codex_home(target_home)
        _sanitize_worker_codex_config(target_home / "config.toml")
    temp_dir = str(Path(codex_home) / "tmp")
    Path(temp_dir).mkdir(parents=True, exist_ok=True)
    env["TMP"] = temp_dir
    env["TEMP"] = temp_dir
    env["TMPDIR"] = temp_dir
    _seed_tls_cert_env(env)
    _seed_go_worker_env(env, repo_path)
    return env


def _seed_go_worker_env(env: dict[str, str], repository_path: Path) -> None:
    if _truthy_env(env.get("ALCHEMY_DISABLE_GO_ENV_BOOTSTRAP", "")):
        return
    go_bin = _detect_go_bin(env)
    has_go_module = _repository_has_go_module(repository_path)
    if go_bin is None and not has_go_module:
        return
    if go_bin is not None:
        _prepend_path(env, go_bin)
    _set_env_if_blank(env, "GOTOOLCHAIN", "auto")
    mod_cache = _select_go_mod_cache(env, repository_path)
    if mod_cache is not None:
        _set_env_if_blank(env, "GOMODCACHE", str(mod_cache))
    build_cache = _select_go_build_cache(env, repository_path)
    if build_cache is not None:
        _set_env_if_blank(env, "GOCACHE", str(build_cache))
    _set_env_if_blank(env, "GOFLAGS", "-p=1")


def _detect_go_bin(env: dict[str, str]) -> Path | None:
    override = env.get("ALCHEMY_GO_BIN", "").strip() or env.get("ALCHEMY_GO_EXE", "").strip()
    if override:
        detected = _go_bin_from_override(Path(override))
        if detected is not None:
            return detected
    root_override = env.get("ALCHEMY_GO_ROOT", "").strip()
    if root_override:
        detected = _go_bin_from_override(Path(root_override) / "bin")
        if detected is not None:
            return detected
    existing = shutil.which("go", path=env.get("PATH", ""))
    if existing:
        return Path(existing).parent
    for candidate in _go_bin_candidates():
        if _go_executable(candidate).is_file():
            return candidate
    return None


def _go_bin_from_override(path: Path) -> Path | None:
    if path.is_file():
        return path.parent
    if path.is_dir() and _go_executable(path).is_file():
        return path
    return None


def _go_bin_candidates() -> list[Path]:
    candidates: list[Path] = []
    tools_root = Path.home() / "tools"
    if tools_root.is_dir():
        for child in sorted(tools_root.glob("go-*"), key=lambda item: item.name, reverse=True):
            candidates.extend([child / "go" / "bin", child / "bin"])
    if os.name == "nt":
        candidates.extend([Path("C:/Program Files/Go/bin"), Path("C:/Go/bin")])
    else:
        candidates.extend([Path("/usr/local/go/bin"), Path("/usr/bin")])
    return candidates


def _go_executable(bin_dir: Path) -> Path:
    return bin_dir / ("go.exe" if os.name == "nt" else "go")


def _prepend_path(env: dict[str, str], directory: Path) -> None:
    path_value = env.get("PATH", "")
    directory_text = str(directory)
    existing = [item for item in path_value.split(os.pathsep) if item]
    if any(item.lower() == directory_text.lower() for item in existing):
        return
    env["PATH"] = directory_text + (os.pathsep + path_value if path_value else "")


def _set_env_if_blank(env: dict[str, str], name: str, value: str) -> None:
    if not env.get(name, "").strip():
        env[name] = value


def _repository_has_go_module(repository_path: Path) -> bool:
    if (repository_path / "go.mod").is_file():
        return True
    try:
        children = list(repository_path.iterdir())
    except OSError:
        return False
    skip = {".git", ".alchemy", ".gocache", ".gobuildcache", "node_modules", "vendor"}
    return any(child.is_dir() and child.name not in skip and (child / "go.mod").is_file() for child in children)


def _select_go_mod_cache(env: dict[str, str], repository_path: Path) -> Path | None:
    for value in (env.get("ALCHEMY_GOMODCACHE", "").strip(), env.get("GOMODCACHE", "").strip()):
        if value:
            candidate = Path(value)
            return candidate if _probe_writable_dir(candidate) else None
    candidates: list[Path] = []
    gopath = env.get("GOPATH", "").strip()
    if gopath:
        candidates.append(Path(gopath) / "pkg" / "mod")
    candidates.extend(_shared_go_mod_cache_candidates(repository_path, env))
    for candidate in candidates:
        if _probe_writable_dir(candidate):
            return candidate
    return None


def _shared_go_mod_cache_candidates(repository_path: Path, env: dict[str, str]) -> list[Path]:
    candidates: list[Path] = []
    try:
        anchor = Path(repository_path.resolve().anchor)
    except OSError:
        anchor = Path(repository_path.anchor)
    if str(anchor):
        candidates.append(anchor / "AI" / ".tools" / "gopath" / "pkg" / "mod")
    candidates.append(Path.home() / "go" / "pkg" / "mod")
    local_app_data = env.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        candidates.append(Path(local_app_data) / "Alchemy" / "gopath" / "pkg" / "mod")
    candidates.append(Path.home() / ".cache" / "alchemy" / "gopath" / "pkg" / "mod")
    return candidates


def _select_go_build_cache(env: dict[str, str], repository_path: Path) -> Path | None:
    for value in (env.get("ALCHEMY_GOCACHE", "").strip(), env.get("GOCACHE", "").strip()):
        if value:
            candidate = Path(value)
            return candidate if _probe_writable_dir(candidate) else None
    candidates: list[Path] = []
    codex_home = env.get("CODEX_HOME", "").strip()
    if codex_home:
        candidates.append(Path(codex_home) / "tmp" / "go-build-cache")
    local_app_data = env.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        candidates.append(Path(local_app_data) / "Alchemy" / "go-build-cache")
    candidates.append(Path(tempfile.gettempdir()) / "alchemy-go-build-cache")
    candidates.append(repository_path / ".gocache-alchemy")
    for candidate in candidates:
        if _probe_writable_dir(candidate):
            return candidate
    return None


def _probe_writable_dir(candidate: Path) -> bool:
    probe = candidate / ".alchemy-go-env-probe"
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _truthy_env(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _select_codex_home(repository_path: Path) -> Path:
    slug = _codex_home_slug(repository_path)
    override_root = os.environ.get("ALCHEMY_CODEX_HOME_ROOT", "").strip()
    candidate_roots: list[Path] = []
    if override_root:
        candidate_roots.append(Path(override_root))
    candidate_roots.extend(
        [
            Path.home() / ".codex" / "memories" / "alchemy-worker-home",
            Path(tempfile.gettempdir()) / "alchemy-worker-home",
            repository_path / ".alchemy" / "codex-worker-home",
        ]
    )
    last_candidate = candidate_roots[-1] / slug
    for root in candidate_roots:
        candidate = root / slug
        if _probe_codex_home(candidate):
            return candidate
        last_candidate = candidate
    return last_candidate


def _probe_codex_home(candidate: Path) -> bool:
    probe = candidate / ".codex-home-probe"
    tmp_dir = candidate / "tmp"
    try:
        tmp_dir.mkdir(parents=True, exist_ok=True)
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _seed_codex_home(target_home: Path) -> None:
    source_home = _codex_source_home()
    try:
        if source_home.resolve() == target_home.resolve():
            return
    except OSError:
        return
    for name in ("auth.json", "config.toml", "cc-switch-model-catalog.json"):
        source = source_home / name
        if not source.is_file():
            continue
        destination = target_home / name
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                source_stat = source.stat()
                destination_stat = destination.stat()
                if (
                    destination_stat.st_size == source_stat.st_size
                    and destination_stat.st_mtime_ns >= source_stat.st_mtime_ns
                ):
                    continue
            shutil.copy2(source, destination)
        except OSError:
            continue


def _sanitize_worker_codex_config(path: Path) -> None:
    """Repair known-invalid copied values without mutating the user's source config."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    repaired = re.sub(
        r'(?m)^(\s*service_tier\s*=\s*)["\']default["\']\s*$',
        r'\1"fast"',
        text,
    )
    if repaired == text:
        return
    try:
        path.write_text(repaired, encoding="utf-8")
    except OSError:
        return


def _codex_source_home() -> Path:
    override_root = os.environ.get("ALCHEMY_CODEX_SOURCE_HOME", "").strip()
    if override_root:
        return Path(override_root)
    return Path.home() / ".codex"


def _codex_home_slug(repository_path: Path) -> str:
    resolved = repository_path.resolve()
    digest = sha1(str(resolved).encode("utf-8")).hexdigest()[:10]
    name = resolved.name or "workspace"
    safe_name = "".join(char if char.isalnum() or char in ("-", "_", ".") else "-" for char in name).strip(".-")
    if not safe_name:
        safe_name = "workspace"
    return f"{safe_name}-{digest}"


def _seed_tls_cert_env(env: dict[str, str]) -> None:
    cert_bundle = env.get("SSL_CERT_FILE", "").strip()
    if not cert_bundle:
        cert_bundle = _detect_cert_bundle()
    if not cert_bundle:
        return
    env["SSL_CERT_FILE"] = cert_bundle
    env.setdefault("REQUESTS_CA_BUNDLE", cert_bundle)
    env.setdefault("CURL_CA_BUNDLE", cert_bundle)


def _detect_cert_bundle() -> str:
    try:
        import certifi  # type: ignore[import-not-found]
    except ImportError:
        return ""
    try:
        return str(Path(certifi.where()).resolve())
    except (OSError, AttributeError):
        return ""


def _is_test_runtime_artifact(parts: list[str]) -> bool:
    for index, part in enumerate(parts[:-1]):
        if part == "tests" and index + 1 < len(parts) and parts[index + 1].startswith("_runtime_"):
            return True
    return False
