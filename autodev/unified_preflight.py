"""Request-level preflight for the unified autonomous development entrypoint."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from intake import ProjectBriefBuilder

from .preflight import ExecutionPreflight, PreflightCheck
from .unified_request import AutoDevRunRequest


@dataclass(slots=True)
class UnifiedPreflightIssue:
    code: str
    severity: str
    message: str
    required_resolution: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "required_resolution": self.required_resolution,
        }


@dataclass(slots=True)
class UnifiedPreflightReport:
    status: str
    can_start: bool
    route: str
    source_mode: str
    execution_mode: str
    delivery_mode: str
    objective: str
    repository_path: str
    planned_repository_path: str = ""
    checks: list[PreflightCheck] = field(default_factory=list)
    blockers: list[UnifiedPreflightIssue] = field(default_factory=list)
    warnings: list[UnifiedPreflightIssue] = field(default_factory=list)
    request: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "2.40",
            "status": self.status,
            "can_start": self.can_start,
            "route": self.route,
            "source_mode": self.source_mode,
            "execution_mode": self.execution_mode,
            "delivery_mode": self.delivery_mode,
            "objective": self.objective,
            "repository_path": self.repository_path,
            "planned_repository_path": self.planned_repository_path,
            "checks": [check.to_dict() for check in self.checks],
            "blockers": [issue.to_dict() for issue in self.blockers],
            "warnings": [issue.to_dict() for issue in self.warnings],
            "request": dict(self.request),
        }


class UnifiedRunPreflight:
    """Validate that a normalized unified request can safely start."""

    def __init__(self, execution_preflight: ExecutionPreflight | None = None) -> None:
        self.execution_preflight = execution_preflight or ExecutionPreflight()

    def run(self, request: AutoDevRunRequest) -> UnifiedPreflightReport:
        checks: list[PreflightCheck] = []
        blockers: list[UnifiedPreflightIssue] = []
        warnings: list[UnifiedPreflightIssue] = []

        for error in request.validate_paths():
            blockers.append(
                UnifiedPreflightIssue(
                    code="invalid_input_path",
                    severity="hard",
                    message=error,
                    required_resolution="Fix the supplied file or repository path before starting the run.",
                )
            )

        self._append_source_mode_issues(request, blockers=blockers, warnings=warnings)
        self._append_mode_issues(request, blockers=blockers, warnings=warnings)

        repository_path, planned_repository_path, repository_required, require_git = self._repository_plan(request)
        if request.route != "feedback_reopen":
            execution = self.execution_preflight.check(
                repository_path=repository_path or ".",
                real_codex=request.real_codex,
                real_github=request.real_github,
                codex_executable=request.codex_executable,
                private_repository=self._requires_private_github(request),
                repository_required=repository_required,
                require_git=require_git,
            )
            checks.extend(execution.checks)
            if execution.status == "blocked":
                for check in execution.checks:
                    if check.required and check.status != "passed":
                        blockers.append(
                            UnifiedPreflightIssue(
                                code=f"preflight_{check.name}",
                                severity="hard",
                                message=check.summary,
                                required_resolution="Install or configure the required local tool, provide a valid repository, or switch to dry-run/report-only mode.",
                            )
                        )
        else:
            checks.append(
                PreflightCheck(
                    "feedback_project",
                    "passed" if request.project_id else "failed",
                    "Feedback reopen targets an existing stored project." if request.project_id else "project_id is required for feedback reopen.",
                    required=True,
                )
            )
            if not request.project_id:
                blockers.append(
                    UnifiedPreflightIssue(
                        code="feedback_project_missing",
                        severity="hard",
                        message="project_id is required for unified feedback reopen.",
                        required_resolution="Start from a delivered project/run or provide project_id and source_run_id.",
                    )
                )

        status = "blocked" if blockers else "passed"
        return UnifiedPreflightReport(
            status=status,
            can_start=status == "passed",
            route=request.route,
            source_mode=request.source_mode,
            execution_mode=request.execution_mode,
            delivery_mode=request.delivery_mode,
            objective=request.objective,
            repository_path=repository_path,
            planned_repository_path=planned_repository_path,
            checks=checks,
            blockers=dedupe_issues(blockers),
            warnings=dedupe_issues(warnings),
            request=request.to_dict(),
        )

    def _append_source_mode_issues(
        self,
        request: AutoDevRunRequest,
        *,
        blockers: list[UnifiedPreflightIssue],
        warnings: list[UnifiedPreflightIssue],
    ) -> None:
        if request.source_mode == "local" and not request.repository_path:
            blockers.append(
                UnifiedPreflightIssue(
                    code="local_repository_missing",
                    severity="hard",
                    message="source_mode=local requires repository_path.",
                    required_resolution="Provide a local repository path or use source_mode=none/github_public/github_private.",
                )
            )
        if request.source_mode in {"github_public", "github_private"} and not request.repository_url:
            blockers.append(
                UnifiedPreflightIssue(
                    code="github_repository_missing",
                    severity="hard",
                    message=f"source_mode={request.source_mode} requires repository_url.",
                    required_resolution="Provide a GitHub repository URL or switch to local/no-repository mode.",
                )
            )
        if request.repository_path and request.repository_url and not request.prepare_repository:
            warnings.append(
                UnifiedPreflightIssue(
                    code="dual_repository_sources",
                    severity="warning",
                    message="Both repository_path and repository_url were supplied; runtime will prefer the local path unless repository preparation is requested.",
                    required_resolution="Use one source of truth when possible.",
                )
            )
        if request.repository_url and not request.repository_path and not request.prepare_repository:
            warnings.append(
                UnifiedPreflightIssue(
                    code="github_source_not_prepared",
                    severity="warning",
                    message="A GitHub URL was supplied without repository_path or prepare_repository; intake can record metadata but cannot inspect source files before execution.",
                    required_resolution="Enable prepare_repository or provide repository_path for full source analysis.",
                )
            )
            if request.real_codex or request.real_github:
                blockers.append(
                    UnifiedPreflightIssue(
                        code="github_source_unprepared_for_real_execution",
                        severity="hard",
                        message="Real Codex/GitHub execution with a GitHub URL requires prepare_repository or repository_path so workers operate on a local checkout.",
                        required_resolution="Enable prepare_repository, provide repository_path, or switch to dry-run/report-only mode.",
                    )
                )

    def _append_mode_issues(
        self,
        request: AutoDevRunRequest,
        *,
        blockers: list[UnifiedPreflightIssue],
        warnings: list[UnifiedPreflightIssue],
    ) -> None:
        if request.route == "one_line_fallback" and (request.real_codex or request.real_github):
            blockers.append(
                UnifiedPreflightIssue(
                    code="one_line_real_execution_unsupported",
                    severity="hard",
                    message="One-line fallback currently supports deterministic local artifact generation only; real Codex/GitHub execution requires documents, files, a repository, or a resume package.",
                    required_resolution="Provide a development document or repository package, or run the one-line fallback in dry-run/report-only mode.",
                )
            )
        if request.real_github and not request.real_codex:
            blockers.append(
                UnifiedPreflightIssue(
                    code="github_delivery_requires_real_codex",
                    severity="hard",
                    message="GitHub PR delivery requires real Codex execution so there is a real branch diff to submit.",
                    required_resolution="Enable real Codex execution or switch delivery_mode to report_only/local.",
                )
            )
        if request.auto_merge and not request.real_github:
            warnings.append(
                UnifiedPreflightIssue(
                    code="auto_merge_ignored",
                    severity="warning",
                    message="auto_merge has no effect unless GitHub PR delivery is enabled.",
                    required_resolution="Enable real GitHub delivery or disable auto_merge.",
                )
            )
        if request.auto_merge and not request.github_collect_ci:
            blockers.append(
                UnifiedPreflightIssue(
                    code="auto_merge_requires_ci",
                    severity="hard",
                    message="auto_merge requires GitHub CI collection so the runtime has merge evidence.",
                    required_resolution="Enable github_collect_ci or disable auto_merge.",
                )
            )

    def _repository_plan(self, request: AutoDevRunRequest) -> tuple[str, str, bool, bool]:
        if request.repository_path:
            return request.repository_path, "", True, False
        if request.route == "document_run" and not request.repository_url:
            planned = str(Path(request.output_dir) / "generated_repository")
            return planned, planned, False, False
        if request.repository_url and request.prepare_repository:
            planned = self._planned_github_checkout_path(request)
            return planned, planned, False, True
        if request.repository_url:
            return str(Path(request.output_dir) / "unprepared_repository"), "", False, False
        return ".", "", False, False

    def _requires_private_github(self, request: AutoDevRunRequest) -> bool:
        return request.source_mode == "github_private" or request.repository_visibility == "private"

    def _planned_github_checkout_path(self, request: AutoDevRunRequest) -> str:
        brief = ProjectBriefBuilder().build(
            objective=request.objective,
            documents=request.documents,
            attachments=request.attachments,
            primary_input_mode=request.primary_input_mode,  # type: ignore[arg-type]
            repository_url=request.repository_url,
            repository_visibility=request.repository_visibility,  # type: ignore[arg-type]
            target_branch=request.target_branch,
            base_branch=request.base_branch,
            constraints=request.constraints,
            acceptance_criteria=request.acceptance_criteria,
        )
        if brief.repository and brief.repository.local_path:
            return brief.repository.local_path
        return str(Path(request.output_dir) / "prepared_repository")


def write_unified_preflight_report(output_dir: str | Path, report: Mapping[str, object]) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "unified_preflight_report.json"
    path.write_text(json.dumps(dict(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def unified_preflight_summary(report: Mapping[str, Any]) -> dict[str, object]:
    return {
        "status": report.get("status", ""),
        "can_start": report.get("can_start", False),
        "route": report.get("route", ""),
        "source_mode": report.get("source_mode", ""),
        "execution_mode": report.get("execution_mode", ""),
        "delivery_mode": report.get("delivery_mode", ""),
        "blocker_count": len(report.get("blockers", [])) if isinstance(report.get("blockers"), list) else 0,
        "warning_count": len(report.get("warnings", [])) if isinstance(report.get("warnings"), list) else 0,
        "preflight_report": str(Path(str(report.get("request", {}).get("output_dir", ".alchemy/unified_run"))) / "unified_preflight_report.json")
        if isinstance(report.get("request"), Mapping)
        else "",
    }


def dedupe_issues(issues: list[UnifiedPreflightIssue]) -> list[UnifiedPreflightIssue]:
    seen: set[tuple[str, str]] = set()
    unique: list[UnifiedPreflightIssue] = []
    for issue in issues:
        key = (issue.code, issue.message)
        if key in seen:
            continue
        seen.add(key)
        unique.append(issue)
    return unique
