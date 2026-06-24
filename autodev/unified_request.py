"""Unified run request contract for CLI, API, and console entrypoints."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

DEFAULT_ONE_LINE_OBJECTIVE = "Build the requested software system from the supplied objective."

SOURCE_MODES = {"auto", "none", "local", "github_public", "github_private"}
EXECUTION_MODES = {"dry_run", "real_codex"}
DELIVERY_MODES = {"report_only", "local", "github_pr"}
BOUNDARY_MODES = {"auto", "strict", "large_refactor"}


@dataclass(frozen=True, slots=True)
class AutoDevRunRequest:
    """Normalized request shared by every user-facing run entrypoint."""

    objective: str = DEFAULT_ONE_LINE_OBJECTIVE
    documents: tuple[str, ...] = ()
    attachments: tuple[str, ...] = ()
    repository_url: str = ""
    repository_path: str = ""
    repository_visibility: str = "public"
    source_mode: str = "auto"
    execution_mode: str = "dry_run"
    delivery_mode: str = "report_only"
    output_dir: str = ".alchemy/unified_run"
    target_branch: str = "main"
    base_branch: str = ""
    prepare_repository: bool = False
    max_iterations: int = 50
    codex_executable: str = "codex"
    max_worker_seconds: int = 0
    github_collect_ci: bool = True
    github_ci_wait_seconds: float = 120.0
    github_ci_poll_interval_seconds: float = 10.0
    isolate_real_run: bool = True
    keep_worktree: bool = True
    worktree_branch_prefix: str = "agent/alchemy-real-run"
    resume_from: str = ""
    resume_tasks: tuple[str, ...] = ()
    feedback_files: tuple[str, ...] = ()
    project_id: str = ""
    source_run_id: str = ""
    auto_browser_verify: bool = False
    generate_static_ci: bool = True
    write_native_ui_tests: bool = False
    auto_merge: bool = False
    full_roadmap: bool = False
    max_phases: int = 50
    boundary_mode: str = "auto"
    constraints: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()
    files: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None) -> "AutoDevRunRequest":
        source = _mapping(payload, "source")
        execution = _mapping(payload, "execution")
        delivery = _mapping(payload, "delivery")
        verification = _mapping(payload, "verification")
        payload = payload or {}

        real_codex = _bool(payload.get("real_codex", execution.get("real_codex")), False)
        real_github = _bool(payload.get("real_github", delivery.get("real_github")), False)

        source_mode = str(payload.get("source_mode", source.get("mode", "auto")) or "auto")
        execution_mode = str(payload.get("execution_mode", execution.get("mode", "")) or "")
        delivery_mode = str(payload.get("delivery_mode", delivery.get("mode", "")) or "")

        if real_codex:
            execution_mode = "real_codex"
        if real_github:
            delivery_mode = "github_pr"

        repository_url = str(
            payload.get(
                "repository_url",
                payload.get("repository", source.get("repository_url", source.get("repository", ""))),
            )
            or ""
        )
        repository_path = str(payload.get("repository_path", source.get("repository_path", "")) or "")
        repository_visibility = str(
            payload.get("repository_visibility", source.get("repository_visibility", source.get("visibility", "public")))
            or "public"
        )

        output_dir = str(payload.get("output_dir", payload.get("output", delivery.get("output_dir", ".alchemy/unified_run"))) or ".alchemy/unified_run")
        documents = _string_tuple(payload.get("documents", payload.get("document", source.get("documents", ()))))
        attachments = _string_tuple(payload.get("attachments", payload.get("attachment", source.get("attachments", ()))))
        resume_tasks = _string_tuple(payload.get("resume_tasks", payload.get("resume_task", execution.get("resume_tasks", ()))))
        feedback_files = _string_tuple(payload.get("feedback_files", payload.get("feedback_file", ())))
        constraints = _string_tuple(payload.get("constraints", ()))
        boundary_mode = str(payload.get("boundary_mode", execution.get("boundary_mode", "auto")) or "auto")
        acceptance = _string_tuple(payload.get("acceptance_criteria", payload.get("acceptance", ())))
        files = tuple(item for item in payload.get("files", ()) if isinstance(item, dict))

        request = cls(
            objective=str(payload.get("objective", "") or DEFAULT_ONE_LINE_OBJECTIVE).strip() or DEFAULT_ONE_LINE_OBJECTIVE,
            documents=documents,
            attachments=attachments,
            repository_url=repository_url,
            repository_path=repository_path,
            repository_visibility=repository_visibility,
            source_mode=source_mode,
            execution_mode=execution_mode or "dry_run",
            delivery_mode=delivery_mode or ("github_pr" if real_github else "report_only"),
            output_dir=output_dir,
            target_branch=str(payload.get("target_branch", source.get("target_branch", "main")) or "main"),
            base_branch=str(payload.get("base_branch", source.get("base_branch", "")) or ""),
            prepare_repository=_bool(payload.get("prepare_repository", source.get("prepare_repository")), False),
            max_iterations=_int(payload.get("max_iterations", execution.get("max_iterations")), 50),
            codex_executable=str(payload.get("codex_executable", execution.get("codex_executable", "codex")) or "codex"),
            max_worker_seconds=_int(payload.get("max_worker_seconds", execution.get("max_worker_seconds")), 0),
            github_collect_ci=_bool(payload.get("github_collect_ci", verification.get("github_collect_ci")), True),
            github_ci_wait_seconds=_float(payload.get("github_ci_wait_seconds", verification.get("github_ci_wait_seconds")), 120.0),
            github_ci_poll_interval_seconds=_float(
                payload.get("github_ci_poll_interval_seconds", verification.get("github_ci_poll_interval_seconds")),
                10.0,
            ),
            isolate_real_run=_bool(payload.get("isolate_real_run", execution.get("isolate_real_run")), True),
            keep_worktree=_bool(payload.get("keep_worktree", execution.get("keep_worktree")), True),
            worktree_branch_prefix=str(
                payload.get("worktree_branch_prefix", execution.get("worktree_branch_prefix", "agent/alchemy-real-run"))
                or "agent/alchemy-real-run"
            ),
            resume_from=str(payload.get("resume_from", execution.get("resume_from", "")) or ""),
            resume_tasks=resume_tasks,
            feedback_files=feedback_files,
            project_id=str(payload.get("project_id", "") or ""),
            source_run_id=str(payload.get("source_run_id", payload.get("resume_from_run_id", "")) or ""),
            auto_browser_verify=_bool(payload.get("auto_browser_verify", verification.get("auto_browser_verify")), False),
            generate_static_ci=_bool(payload.get("generate_static_ci", delivery.get("generate_static_ci")), True),
            write_native_ui_tests=_bool(payload.get("write_native_ui_tests", verification.get("write_native_ui_tests")), False),
            auto_merge=_bool(payload.get("auto_merge", delivery.get("auto_merge")), False),
            full_roadmap=_bool(payload.get("full_roadmap", execution.get("full_roadmap")), False),
            max_phases=_int(payload.get("max_phases", execution.get("max_phases")), 50),
            boundary_mode=boundary_mode,
            constraints=constraints,
            acceptance_criteria=acceptance,
            files=files,
        )
        return request.normalized()

    def normalized(self) -> "AutoDevRunRequest":
        source_mode = self.source_mode if self.source_mode in SOURCE_MODES else "auto"
        execution_mode = self.execution_mode if self.execution_mode in EXECUTION_MODES else "dry_run"
        delivery_mode = self.delivery_mode if self.delivery_mode in DELIVERY_MODES else "report_only"
        boundary_mode = self.boundary_mode if self.boundary_mode in BOUNDARY_MODES else "auto"
        if source_mode == "auto":
            source_mode = self.inferred_source_mode()
        if delivery_mode == "report_only" and self.real_github:
            delivery_mode = "github_pr"
        return AutoDevRunRequest(
            objective=self.objective,
            documents=self.documents,
            attachments=self.attachments,
            repository_url=self.repository_url,
            repository_path=self.repository_path,
            repository_visibility=self.repository_visibility,
            source_mode=source_mode,
            execution_mode=execution_mode,
            delivery_mode=delivery_mode,
            output_dir=self.output_dir,
            target_branch=self.target_branch,
            base_branch=self.base_branch,
            prepare_repository=self.prepare_repository,
            max_iterations=self.max_iterations,
            codex_executable=self.codex_executable,
            max_worker_seconds=self.max_worker_seconds,
            github_collect_ci=self.github_collect_ci,
            github_ci_wait_seconds=self.github_ci_wait_seconds,
            github_ci_poll_interval_seconds=self.github_ci_poll_interval_seconds,
            isolate_real_run=self.isolate_real_run,
            keep_worktree=self.keep_worktree,
            worktree_branch_prefix=self.worktree_branch_prefix,
            resume_from=self.resume_from,
            resume_tasks=self.resume_tasks,
            feedback_files=self.feedback_files,
            project_id=self.project_id,
            source_run_id=self.source_run_id,
            auto_browser_verify=self.auto_browser_verify,
            generate_static_ci=self.generate_static_ci,
            write_native_ui_tests=self.write_native_ui_tests,
            auto_merge=self.auto_merge,
            full_roadmap=self.full_roadmap,
            max_phases=self.max_phases,
            boundary_mode=boundary_mode,
            constraints=self.constraints,
            acceptance_criteria=self.acceptance_criteria,
            files=self.files,
        )

    @property
    def route(self) -> str:
        if self.feedback_files:
            return "feedback_reopen"
        if self.documents or self.attachments or self.repository_url or self.repository_path or self.files or self.resume_from:
            return "document_run"
        return "one_line_fallback"

    @property
    def real_codex(self) -> bool:
        return self.execution_mode == "real_codex"

    @property
    def real_github(self) -> bool:
        return self.delivery_mode == "github_pr"

    @property
    def primary_input_mode(self) -> str:
        return "one_line_fallback" if self.route == "one_line_fallback" else "document_driven"

    def inferred_source_mode(self) -> str:
        if self.repository_path:
            return "local"
        if self.repository_url:
            return "github_private" if self.repository_visibility == "private" else "github_public"
        return "none"

    def validate_paths(self) -> list[str]:
        errors: list[str] = []
        for path in self.documents:
            if not Path(path).exists():
                errors.append(f"Document path does not exist: {path}")
        for path in self.attachments:
            if not Path(path).exists():
                errors.append(f"Attachment path does not exist: {path}")
        for path in self.feedback_files:
            if not Path(path).exists():
                errors.append(f"Feedback file path does not exist: {path}")
        repository_path_is_checkout_target = bool(self.repository_url and self.prepare_repository)
        if self.repository_path and not repository_path_is_checkout_target and not Path(self.repository_path).exists():
            errors.append(f"Repository path does not exist: {self.repository_path}")
        if self.resume_from and not Path(self.resume_from).exists():
            errors.append(f"Resume source does not exist: {self.resume_from}")
        if not self.objective.strip():
            errors.append("Objective is required.")
        return errors

    def to_project_payload(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "primary_input_mode": self.primary_input_mode,
            "documents": list(self.documents),
            "attachments": list(self.attachments),
            "repository": self.repository_url,
            "repository_url": self.repository_url,
            "repository_path": self.repository_path,
            "repository_visibility": self.repository_visibility,
            "target_branch": self.target_branch,
            "base_branch": self.base_branch,
            "constraints": list(self.constraints),
            "acceptance_criteria": list(self.acceptance_criteria),
            "boundary_mode": self.boundary_mode,
            "files": [dict(item) for item in self.files],
        }

    def to_run_payload(self) -> dict[str, Any]:
        return {
            "max_iterations": self.max_iterations,
            "prepare_repository": self.prepare_repository,
            "real_codex": self.real_codex,
            "real_github": self.real_github,
            "codex_executable": self.codex_executable,
            "max_worker_seconds": self.max_worker_seconds,
            "github_collect_ci": self.github_collect_ci,
            "github_ci_wait_seconds": self.github_ci_wait_seconds,
            "github_ci_poll_interval_seconds": self.github_ci_poll_interval_seconds,
            "isolate_real_run": self.isolate_real_run,
            "keep_worktree": self.keep_worktree,
            "worktree_branch_prefix": self.worktree_branch_prefix,
            "resume_from": self.resume_from,
            "resume_tasks": list(self.resume_tasks),
            "feedback_files": list(self.feedback_files),
            "project_id": self.project_id,
            "source_run_id": self.source_run_id,
            "auto_browser_verify": self.auto_browser_verify,
            "generate_static_ci": self.generate_static_ci,
            "write_native_ui_tests": self.write_native_ui_tests,
            "auto_merge": self.auto_merge,
            "full_roadmap": self.full_roadmap,
            "max_phases": self.max_phases,
            "boundary_mode": self.boundary_mode,
            "constraints": list(self.document_run_constraints()),
        }

    def to_document_run_kwargs(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "documents": list(self.documents),
            "attachments": list(self.attachments),
            "primary_input_mode": self.primary_input_mode,
            "repository_url": self.repository_url,
            "repository_path": self.repository_path or None,
            "repository_visibility": self.repository_visibility,
            "output_dir": self.output_dir,
            "max_iterations": self.max_iterations,
            "prepare_repository": self.prepare_repository,
            "real_codex": self.real_codex,
            "real_github": self.real_github,
            "codex_executable": self.codex_executable,
            "max_worker_seconds": self.max_worker_seconds,
            "github_collect_ci": self.github_collect_ci,
            "github_ci_wait_seconds": self.github_ci_wait_seconds,
            "github_ci_poll_interval_seconds": self.github_ci_poll_interval_seconds,
            "isolate_real_run": self.isolate_real_run,
            "keep_worktree": self.keep_worktree,
            "worktree_branch_prefix": self.worktree_branch_prefix,
            "resume_from": self.resume_from,
            "resume_tasks": list(self.resume_tasks),
            "auto_browser_verify": self.auto_browser_verify,
            "generate_static_ci": self.generate_static_ci,
            "write_native_ui_tests": self.write_native_ui_tests,
            "auto_merge": self.auto_merge,
            "constraints": list(self.document_run_constraints()),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "documents": list(self.documents),
            "attachments": list(self.attachments),
            "repository_url": self.repository_url,
            "repository_path": self.repository_path,
            "repository_visibility": self.repository_visibility,
            "source_mode": self.source_mode,
            "execution_mode": self.execution_mode,
            "delivery_mode": self.delivery_mode,
            "route": self.route,
            "output_dir": self.output_dir,
            "target_branch": self.target_branch,
            "base_branch": self.base_branch,
            "prepare_repository": self.prepare_repository,
            "max_iterations": self.max_iterations,
            "codex_executable": self.codex_executable,
            "max_worker_seconds": self.max_worker_seconds,
            "github_collect_ci": self.github_collect_ci,
            "github_ci_wait_seconds": self.github_ci_wait_seconds,
            "github_ci_poll_interval_seconds": self.github_ci_poll_interval_seconds,
            "isolate_real_run": self.isolate_real_run,
            "keep_worktree": self.keep_worktree,
            "worktree_branch_prefix": self.worktree_branch_prefix,
            "resume_from": self.resume_from,
            "resume_tasks": list(self.resume_tasks),
            "feedback_files": list(self.feedback_files),
            "project_id": self.project_id,
            "source_run_id": self.source_run_id,
            "auto_browser_verify": self.auto_browser_verify,
            "generate_static_ci": self.generate_static_ci,
            "write_native_ui_tests": self.write_native_ui_tests,
            "auto_merge": self.auto_merge,
            "full_roadmap": self.full_roadmap,
            "max_phases": self.max_phases,
            "boundary_mode": self.boundary_mode,
            "constraints": list(self.constraints),
            "acceptance_criteria": list(self.acceptance_criteria),
            "files": [dict(item) for item in self.files],
        }

    def document_run_constraints(self) -> tuple[str, ...]:
        if self.boundary_mode in {"strict", "large_refactor"}:
            return (*self.constraints, f"Scope boundary mode: {self.boundary_mode}")
        return self.constraints


def build_unified_run_report(
    *,
    request: AutoDevRunRequest,
    result_payload: Mapping[str, Any],
    related_report: str = "",
) -> dict[str, Any]:
    delivery_report = _dict(result_payload.get("delivery_report", {}))
    final_gate = _dict(delivery_report.get("final_gate", {}))
    artifact_report = _dict(result_payload.get("artifact_report", {}))
    artifact_profile = _dict(artifact_report.get("artifact_profile", {}))
    project_brief = _dict(result_payload.get("project_brief", {}))
    development_cycle = _dict(result_payload.get("development_cycle", {}))
    status = str(result_payload.get("status", "blocked") or "blocked")
    project_id = str(result_payload.get("project_id", project_brief.get("project_id", "")) or "")
    run_id = str(result_payload.get("run_id", "") or "")
    blockers = _list_of_dicts(result_payload.get("blockers", delivery_report.get("blockers", ())))
    if not blockers:
        blockers = _list_of_dicts(project_brief.get("blockers", ()))
    ready_for_review = bool(delivery_report.get("ready_for_review", status == "done"))
    final_score = final_gate.get("score", final_gate.get("final_score", None))

    return {
        "schema_version": "2.40",
        "status": status,
        "route": request.route,
        "source_mode": request.source_mode,
        "execution_mode": request.execution_mode,
        "delivery_mode": request.delivery_mode,
        "project_id": project_id,
        "run_id": run_id,
        "objective": request.objective,
        "ready_for_review": ready_for_review,
        "final_gate_score": final_score,
        "selected_project_profile": str(artifact_profile.get("name", "one_line_fallback" if request.route == "one_line_fallback" else "unknown")),
        "request": request.to_dict(),
        "report_paths": {
            "unified_run_report": str(Path(request.output_dir) / "unified_run_report.json"),
            "unified_preflight_report": str(Path(request.output_dir) / "unified_preflight_report.json"),
            "related_report": related_report,
        },
        "unified_preflight": _dict(result_payload.get("unified_preflight", {})),
        "delivery": {
            "ready_for_review": ready_for_review,
            "final_gate": final_gate,
            "blockers": blockers,
            "next_actions": list(delivery_report.get("next_actions", ())) if isinstance(delivery_report.get("next_actions", ()), list) else [],
        },
        "artifacts": list(result_payload.get("artifacts", ())) if isinstance(result_payload.get("artifacts", ()), list) else [],
        "development_cycle": development_cycle,
        "validation_errors": list(result_payload.get("validation_errors", ())) if isinstance(result_payload.get("validation_errors", ()), list) else [],
    }


def write_unified_run_outputs(
    output_dir: str | Path,
    *,
    request: AutoDevRunRequest,
    result_payload: Mapping[str, Any],
    related_report: str = "",
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report = build_unified_run_report(request=request, result_payload=result_payload, related_report=related_report)
    _write_json(output / "unified_run_report.json", report)
    for key, filename in {
        "project_brief": "project_brief.json",
        "context_bundle": "context_bundle.json",
        "task_graph": "task_graph.json",
        "runtime_state": "runtime_state.json",
        "delivery_report": "delivery_report.json",
        "development_cycle": "development_cycle.json",
    }.items():
        value = result_payload.get(key, {})
        if isinstance(value, Mapping):
            _write_json(output / filename, dict(value))
    return report


def unified_run_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": report.get("status", ""),
        "route": report.get("route", ""),
        "source_mode": report.get("source_mode", ""),
        "execution_mode": report.get("execution_mode", ""),
        "delivery_mode": report.get("delivery_mode", ""),
        "project_id": report.get("project_id", ""),
        "run_id": report.get("run_id", ""),
        "ready_for_review": report.get("ready_for_review", False),
        "final_gate_score": report.get("final_gate_score", None),
        "selected_project_profile": report.get("selected_project_profile", ""),
        "unified_run_report": _dict(report.get("report_paths", {})).get("unified_run_report", ""),
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _mapping(payload: Mapping[str, Any] | None, key: str) -> Mapping[str, Any]:
    value = (payload or {}).get(key, {})
    return value if isinstance(value, Mapping) else {}


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    if isinstance(value, (str, Path)):
        return (str(value),)
    if isinstance(value, Iterable):
        return tuple(str(item) for item in value if str(item))
    return (str(value),)


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]
