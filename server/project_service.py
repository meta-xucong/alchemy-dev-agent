"""Persistent project service for the local API runtime."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from autodev import AutoDevPipeline, DocumentRunPipeline
from autodev.artifact_manifest import ArtifactContent, build_artifact_manifest, resolve_artifact_content
from autodev.auto_iteration import (
    auto_feedback_markdown,
    build_auto_iteration_preview,
    build_auto_iteration_report,
    repair_plan_markdown,
    target_files_from_text,
)
from autodev.benchmark_regression import BenchmarkRegressionGate
from autodev.central_review import build_central_review
from autodev.delivery_evidence import build_delivery_evidence
from autodev.evidence_package import EvidencePackageExporter
from autodev.evidence_readiness import EvidenceReadinessGate
from autodev.full_roadmap_executor import FullRoadmapExecutor
from autodev.real_env_check import RealEnvironmentCheck, detect_environment_defaults
from autodev.real_probe_index import RealProbeIndexer
from autodev.recovery_comparison import build_recovery_comparison
from autodev.unified_preflight import UnifiedRunPreflight
from autodev.unified_request import AutoDevRunRequest
from context import ContextBundleBuilder
from intake import GitHubSourceRuntime, PrivateGitHubSourceRuntime, ProjectBriefBuilder
from intake.models import FileRole, ProjectBrief, utc_now_iso
from planner import TaskGraphBuilder

from .jobs import JobExecutionController, JobStore, start_background_job


class ApiError(Exception):
    """Structured error raised by the project service."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message

    def to_dict(self) -> dict[str, object]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
            }
        }


@dataclass(slots=True)
class ProjectRecord:
    project_id: str
    objective: str
    primary_input_mode: str
    status: str
    created_at: str
    updated_at: str
    documents: list[str]
    attachments: list[str]
    repository_url: str = ""
    repository_path: str = ""
    target_branch: str = "main"
    base_branch: str = ""
    repository_visibility: str = "public"
    constraints: list[str] | None = None
    acceptance_criteria: list[str] | None = None
    file_roles: dict[str, str] | None = None
    required_attachments: list[str] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "objective": self.objective,
            "primary_input_mode": self.primary_input_mode,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "documents": list(self.documents),
            "attachments": list(self.attachments),
            "repository_url": self.repository_url,
            "repository_path": self.repository_path,
            "target_branch": self.target_branch,
            "base_branch": self.base_branch,
            "repository_visibility": self.repository_visibility,
            "constraints": list(self.constraints or []),
            "acceptance_criteria": list(self.acceptance_criteria or []),
            "file_roles": dict(self.file_roles or {}),
            "required_attachments": list(self.required_attachments or []),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ProjectRecord":
        return cls(
            project_id=str(payload["project_id"]),
            objective=str(payload["objective"]),
            primary_input_mode=str(payload["primary_input_mode"]),
            status=str(payload["status"]),
            created_at=str(payload["created_at"]),
            updated_at=str(payload["updated_at"]),
            documents=[str(path) for path in payload.get("documents", [])],
            attachments=[str(path) for path in payload.get("attachments", [])],
            repository_url=str(payload.get("repository_url", "")),
            repository_path=str(payload.get("repository_path", "")),
            target_branch=str(payload.get("target_branch", "main")),
            base_branch=str(payload.get("base_branch", "")),
            repository_visibility=str(payload.get("repository_visibility", "public")),
            constraints=[str(item) for item in payload.get("constraints", [])],
            acceptance_criteria=[str(item) for item in payload.get("acceptance_criteria", [])],
            file_roles={str(key): str(value) for key, value in payload.get("file_roles", {}).items()},
            required_attachments=[str(path) for path in payload.get("required_attachments", [])],
        )


class ProjectService:
    """Create, persist, plan, and execute document-driven projects locally."""

    def __init__(
        self,
        storage_root: str | Path = ".alchemy/server",
        evidence_root: str | Path | None = None,
        folder_opener: Callable[[Path], None] | None = None,
    ) -> None:
        self.storage_root = Path(storage_root)
        self.evidence_root = Path(evidence_root) if evidence_root is not None else Path(".alchemy")
        self.folder_opener = folder_opener or open_folder_with_os
        self.projects_root = self.storage_root / "projects"
        self.projects_root.mkdir(parents=True, exist_ok=True)

    def create_project(self, payload: dict[str, Any]) -> dict[str, object]:
        normalized = normalize_project_payload(payload)
        brief = self._build_brief(normalized)
        status = "intake_blocked" if brief.blockers else "intake_ready"
        now = utc_now_iso()
        record = ProjectRecord(
            project_id=brief.project_id,
            objective=brief.objective,
            primary_input_mode=str(normalized["primary_input_mode"]),
            status=status,
            created_at=now,
            updated_at=now,
            documents=list(normalized["documents"]),
            attachments=list(normalized["attachments"]),
            repository_url=str(normalized["repository_url"]),
            repository_path=str(normalized["repository_path"]),
            target_branch=str(normalized["target_branch"]),
            base_branch=str(normalized["base_branch"]),
            repository_visibility=str(normalized["repository_visibility"]),
            constraints=list(normalized["constraints"]),
            acceptance_criteria=list(normalized["acceptance_criteria"]),
            file_roles=dict(normalized["file_roles"]),
            required_attachments=list(normalized["required_attachments"]),
        )
        project_dir = self.project_dir(record.project_id)
        self._bind_repository_path_to_project(record, brief)
        project_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(project_dir / "project.json", record.to_dict())
        self._write_json(project_dir / "brief.json", brief.to_dict())
        return {
            "project": record.to_dict(),
            "brief": brief.to_dict(),
        }

    def list_projects(self, *, limit: int = 50) -> dict[str, object]:
        """Return beginner-facing project history summaries."""

        projects: list[dict[str, object]] = []
        if not self.projects_root.exists():
            return {"projects": projects}
        for project_json in self.projects_root.glob("*/project.json"):
            try:
                record = ProjectRecord.from_dict(self._read_json(project_json))
            except (ApiError, KeyError, TypeError, json.JSONDecodeError, OSError, ValueError):
                continue
            projects.append(self.project_history_summary(record))
        projects.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
        return {"projects": projects[: max(0, limit)]}

    def project_history_summary(self, record: ProjectRecord) -> dict[str, object]:
        project_dir = self.project_dir(record.project_id)
        runs_dir = project_dir / "runs"
        run_dirs = sorted(
            path
            for path in runs_dir.iterdir()
            if runs_dir.exists() and path.is_dir() and path.name.startswith("run_")
        ) if runs_dir.exists() else []
        latest_run_id = run_dirs[-1].name if run_dirs else ""
        latest_run_status = ""
        latest_score: object = None
        local_delivery = True
        if latest_run_id:
            run_path = runs_dir / latest_run_id / "run.json"
            job_path = runs_dir / latest_run_id / "job.json"
            run = self._read_json(run_path) if run_path.exists() else {}
            job = self._read_json(job_path) if job_path.exists() else {}
            latest_run_status = str(run.get("status") or job.get("status") or "")
            delivery_report = run.get("delivery_report", {})
            final_gate = delivery_report.get("final_gate", {}) if isinstance(delivery_report, dict) else {}
            latest_score = final_gate.get("score") if isinstance(final_gate, dict) else None
            local_delivery = not bool(github_pr_url(run))
        console_url = f"/?project_id={record.project_id}"
        if latest_run_id:
            console_url = f"{console_url}&run_id={latest_run_id}"
        return {
            "project_id": record.project_id,
            "objective": record.objective,
            "primary_input_mode": record.primary_input_mode,
            "status": record.status,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "workspace_path": str(project_dir.resolve()),
            "repository_url": record.repository_url,
            "repository_path": record.repository_path,
            "run_count": len(run_dirs),
            "latest_run_id": latest_run_id,
            "latest_run_status": latest_run_status,
            "latest_score": latest_score,
            "local_delivery": local_delivery,
            "console_url": console_url,
        }

    def run_unified_request(self, payload: dict[str, Any]) -> dict[str, object]:
        payload = self._normalize_service_unified_payload(payload)
        payload = self._expand_one_line_source_payload(payload)
        request = AutoDevRunRequest.from_mapping(payload)
        preflight = self.preflight_unified_request(payload)
        if preflight.get("status") == "blocked":
            blockers = preflight.get("blockers", [])
            messages = [
                str(item.get("message", ""))
                for item in blockers
                if isinstance(item, dict) and str(item.get("message", "")).strip()
            ]
            raise ApiError(400, "unified_preflight_blocked", "; ".join(messages) or "Unified run preflight blocked the request.")
        validation_errors = request.validate_paths()
        if validation_errors:
            raise ApiError(400, "invalid_unified_run_request", "; ".join(validation_errors))

        if request.route == "feedback_reopen":
            if not request.project_id:
                raise ApiError(400, "feedback_project_missing", "project_id is required for unified feedback reopen.")
            run = self.reopen_with_feedback(
                request.project_id,
                {
                    "source_run_id": request.source_run_id,
                    "feedback_files": list(request.feedback_files),
                    "run": request.to_run_payload(),
                },
            )
            run_id = str(run.get("run_id", ""))
            urls = unified_run_urls(request.project_id, run_id)
            return {
                "accepted": False,
                "async": False,
                "project_id": request.project_id,
                "run_id": run_id,
                "status": str(run.get("status", "")),
                "events_url": urls["events"],
                "events_stream_url": urls["events_stream"],
                "delivery_url": urls["delivery"],
                "artifact_manifest_url": urls["artifacts"],
                "route": request.route,
                "source_mode": request.source_mode,
                "execution_mode": request.execution_mode,
                "delivery_mode": request.delivery_mode,
                "preflight": preflight,
                "run": run,
                "urls": urls,
            }

        created = self.create_project(request.to_project_payload())
        project = created["project"]
        if not isinstance(project, dict):
            raise ApiError(500, "invalid_project_record", "Project creation did not return a project record.")
        project_id = str(project["project_id"])
        run_payload = normalize_unified_run_payload_for_project(request.to_run_payload(), project)
        async_requested = bool(payload.get("async", True))

        if async_requested:
            run_result = self.start_run(project_id, {"async": True, **run_payload})
            run_id = str(run_result.get("run_id", ""))
            urls = unified_run_urls(project_id, run_id)
            job = run_result.get("job", {})
            status = str(job.get("status", "queued")) if isinstance(job, dict) else "queued"
            return {
                "accepted": True,
                "async": True,
                "project_id": project_id,
                "run_id": run_id,
                "status": status,
                "events_url": urls["events"],
                "events_stream_url": urls["events_stream"],
                "delivery_url": urls["delivery"],
                "artifact_manifest_url": urls["artifacts"],
                "route": request.route,
                "source_mode": request.source_mode,
                "execution_mode": request.execution_mode,
                "delivery_mode": request.delivery_mode,
                "preflight": preflight,
                "project": project,
                "brief": created.get("brief", {}),
                "job": job,
                "urls": urls,
            }

        run_result = self.run_project(project_id, run_payload)
        run_id = str(run_result.get("run_id", ""))
        urls = unified_run_urls(project_id, run_id)
        status = str(run_result.get("status", ""))
        return {
            "accepted": False,
            "async": False,
            "project_id": project_id,
            "run_id": run_id,
            "status": status,
            "events_url": urls["events"],
            "events_stream_url": urls["events_stream"],
            "delivery_url": urls["delivery"],
            "artifact_manifest_url": urls["artifacts"],
            "route": request.route,
            "source_mode": request.source_mode,
            "execution_mode": request.execution_mode,
            "delivery_mode": request.delivery_mode,
            "preflight": preflight,
            "project": project,
            "brief": created.get("brief", {}),
            "run": run_result,
            "urls": urls,
        }

    def preflight_unified_request(self, payload: dict[str, Any]) -> dict[str, object]:
        payload = self._normalize_service_unified_payload(payload)
        payload = self._expand_one_line_source_payload(payload)
        request = AutoDevRunRequest.from_mapping(payload)
        report = UnifiedRunPreflight().run(request).to_dict()
        if request.route == "feedback_reopen" and request.project_id:
            try:
                self.load_project(request.project_id)
            except ApiError:
                report["status"] = "blocked"
                report["can_start"] = False
                blockers = report.setdefault("blockers", [])
                if isinstance(blockers, list):
                    blockers.append(
                        {
                            "code": "feedback_project_not_found",
                            "severity": "hard",
                            "message": f"Project not found: {request.project_id}",
                            "required_resolution": "Provide an existing stored project_id before reopening with feedback.",
                        }
                    )
        return report

    def _normalize_service_unified_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        repository_url = str(normalized.get("repository_url", normalized.get("repository", "")) or "").strip()
        if repository_url and bool(normalized.get("prepare_repository", False)):
            normalized.setdefault("output_dir", str(self.storage_root))
            if not str(normalized.get("repository_path", "") or "").strip():
                preview = self._build_brief(normalize_project_payload(normalized))
                normalized["repository_path"] = str(self.project_dir(preview.project_id) / "repo")
        return normalized

    def check_environment(self, payload: dict[str, Any] | None = None) -> dict[str, object]:
        payload = payload or {}
        codex_executable = str(payload.get("codex_executable", "codex") or "codex")
        require_browser = bool(payload.get("require_browser", False) or payload.get("auto_browser_verify", False))
        model_provider = str(payload.get("model_provider", "codex_cli") or "codex_cli")
        model_api_key_env = str(payload.get("model_api_key_env", "") or "")
        model_base_url = str(payload.get("model_base_url", "") or "")
        output_dir = payload.get("output_dir")
        if output_dir:
            output_path = Path(str(output_dir))
        else:
            output_path = self.storage_root / "environment"
        output_path.mkdir(parents=True, exist_ok=True)
        report = RealEnvironmentCheck().run(
            output_dir=output_path,
            codex_executable=codex_executable,
            require_browser=require_browser,
            model_provider=model_provider,
            model_api_key_env=model_api_key_env,
            model_base_url=model_base_url,
        )
        return report.to_dict()

    def environment_defaults(self) -> dict[str, object]:
        return detect_environment_defaults()

    def _expand_one_line_source_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not payload.get("expand_one_line"):
            return payload
        if self._has_concrete_input_source(payload):
            return payload
        objective = str(payload.get("objective", "") or "").strip()
        if not objective:
            return payload
        document_path = self._write_generated_one_line_document(objective)
        expanded = dict(payload)
        expanded["documents"] = [str(document_path)]
        expanded["primary_input_mode"] = "document_driven"
        expanded["source_mode"] = "none"
        expanded["generated_from_one_line"] = True
        expanded["generated_requirements_document"] = str(document_path)
        return expanded

    def _has_concrete_input_source(self, payload: dict[str, Any]) -> bool:
        return any(
            bool(payload.get(key))
            for key in (
                "documents",
                "attachments",
                "repository",
                "repository_url",
                "repository_path",
                "files",
                "feedback_files",
                "resume_from",
            )
        )

    def _write_generated_one_line_document(self, objective: str) -> Path:
        digest = hashlib.sha256(objective.encode("utf-8")).hexdigest()[:16]
        path = self.storage_root / "generated_requirements" / f"one_line_{digest}.md"
        content = generated_one_line_document(objective)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            path.write_text(content, encoding="utf-8")
        return path

    def get_project(self, project_id: str) -> dict[str, object]:
        record = self.load_project(project_id)
        payload = record.to_dict()
        brief_path = self.project_dir(project_id) / "brief.json"
        if brief_path.exists():
            payload["brief"] = self._read_json(brief_path)
        context_path = self.project_dir(project_id) / "context.json"
        if context_path.exists():
            payload["context"] = self._read_json(context_path)
        graph_path = self.project_dir(project_id) / "task_graph.json"
        if graph_path.exists():
            payload["task_graph"] = self._read_json(graph_path)
        return payload

    def list_files(self, project_id: str) -> dict[str, object]:
        brief = self.get_brief(project_id)
        return {
            "project_id": project_id,
            "files": list(brief.get("documents", [])) + list(brief.get("attachments", [])),
        }

    def update_file(self, project_id: str, file_id: str, payload: dict[str, Any]) -> dict[str, object]:
        record = self.load_project(project_id)
        brief = self.get_brief(project_id)
        file_payload = find_file_payload(brief, file_id)
        if file_payload is None:
            raise ApiError(404, "file_not_found", f"Project file not found: {file_id}")

        path = str(file_payload.get("path", ""))
        merged_roles = dict(record.file_roles or {})
        required_attachments = list(record.required_attachments or [])
        documents = list(record.documents)
        attachments = list(record.attachments)

        role = str(payload.get("role", file_payload.get("role", "")) or "supplemental")
        required = bool(payload.get("required", file_payload.get("required", False)))
        content = payload.get("content")
        if content is not None:
            target = Path(path)
            upload_root = (self.project_dir(project_id) / "uploads").resolve()
            try:
                resolved = target.resolve()
            except OSError as exc:
                raise ApiError(400, "file_update_failed", f"Cannot resolve file path: {exc}") from exc
            if upload_root not in [resolved, *resolved.parents]:
                raise ApiError(409, "external_file_update_forbidden", "Only uploaded project files can be edited through the API.")
            target.write_text(str(content), encoding="utf-8")

        if role == "primary_requirements":
            documents = dedupe([*documents, path])
            attachments = [item for item in attachments if item != path]
            required_attachments = [item for item in required_attachments if item != path]
        else:
            attachments = dedupe([*attachments, path])
            documents = [item for item in documents if item != path]
            if required:
                required_attachments = dedupe([*required_attachments, path])
            else:
                required_attachments = [item for item in required_attachments if item != path]
        merged_roles[path] = role

        updated = ProjectRecord.from_dict(record.to_dict())
        updated.documents = documents
        updated.attachments = attachments
        updated.file_roles = merged_roles
        updated.required_attachments = required_attachments
        updated.status = "intake_pending"
        updated.updated_at = utc_now_iso()
        self._write_json(self.project_dir(project_id) / "project.json", updated.to_dict())
        return self.build_intake(project_id)

    def delete_file(self, project_id: str, file_id: str) -> dict[str, object]:
        record = self.load_project(project_id)
        brief = self.get_brief(project_id)
        file_payload = find_file_payload(brief, file_id)
        if file_payload is None:
            raise ApiError(404, "file_not_found", f"Project file not found: {file_id}")
        path = str(file_payload.get("path", ""))

        updated = ProjectRecord.from_dict(record.to_dict())
        updated.documents = [item for item in record.documents if item != path]
        updated.attachments = [item for item in record.attachments if item != path]
        updated.required_attachments = [item for item in (record.required_attachments or []) if item != path]
        updated.file_roles = {key: value for key, value in (record.file_roles or {}).items() if key != path}
        updated.status = "intake_pending"
        updated.updated_at = utc_now_iso()

        target = Path(path)
        upload_root = (self.project_dir(project_id) / "uploads").resolve()
        try:
            resolved = target.resolve()
        except OSError:
            resolved = target
        if upload_root in [resolved, *resolved.parents] and target.exists() and target.is_file():
            target.unlink()

        self._write_json(self.project_dir(project_id) / "project.json", updated.to_dict())
        return self.build_intake(project_id)

    def add_files(self, project_id: str, payload: dict[str, Any]) -> dict[str, object]:
        record = self.load_project(project_id)
        normalized = normalize_project_payload(payload)
        merged = record.to_dict()
        merged["documents"] = dedupe([*record.documents, *normalized["documents"]])
        required_only_attachments = [
            path
            for path in normalized["required_attachments"]
            if normalized["file_roles"].get(path) != "primary_requirements"
        ]
        merged["attachments"] = dedupe([*record.attachments, *normalized["attachments"], *required_only_attachments])
        merged["file_roles"] = {**(record.file_roles or {}), **normalized["file_roles"]}
        merged["required_attachments"] = dedupe([*(record.required_attachments or []), *normalized["required_attachments"]])
        updated_record = ProjectRecord.from_dict(merged)
        updated_record.status = "intake_pending"
        updated_record.updated_at = utc_now_iso()
        self._write_json(self.project_dir(project_id) / "project.json", updated_record.to_dict())
        return self.build_intake(project_id)

    def upload_files(self, project_id: str, uploads: list[dict[str, Any]], fields: dict[str, str] | None = None) -> dict[str, object]:
        if not uploads:
            raise ApiError(400, "missing_upload", "At least one uploaded file is required.")
        record = self.load_project(project_id)
        fields = fields or {}
        upload_dir = self.project_dir(project_id) / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        documents = list(record.documents)
        attachments = list(record.attachments)
        file_roles = dict(record.file_roles or {})
        required_attachments = list(record.required_attachments or [])
        uploaded_files = []

        for index, upload in enumerate(uploads):
            filename = safe_filename(str(upload.get("filename", "")))
            content = upload.get("content", b"")
            if not isinstance(content, bytes):
                raise ApiError(400, "invalid_upload", f"Uploaded content for {filename} is not bytes.")
            target = unique_upload_path(upload_dir, filename)
            target.write_bytes(content)
            path = str(target)
            role = str(upload.get("role") or fields.get("role") or "")
            if not role:
                role = "primary_requirements" if not documents and index == 0 else "supplemental"
            required = parse_bool(str(upload.get("required", fields.get("required", "")))) or role == "primary_requirements"

            if role == "primary_requirements":
                documents = dedupe([*documents, path])
            else:
                attachments = dedupe([*attachments, path])
                if required:
                    required_attachments = dedupe([*required_attachments, path])
            file_roles[path] = role
            uploaded_files.append(
                {
                    "name": filename,
                    "path": path,
                    "role": role,
                    "required": required,
                    "media_type": str(upload.get("content_type", "")),
                }
            )

        updated = ProjectRecord.from_dict(record.to_dict())
        updated.documents = documents
        updated.attachments = attachments
        updated.file_roles = file_roles
        updated.required_attachments = required_attachments
        updated.status = "intake_pending"
        updated.updated_at = utc_now_iso()
        self._write_json(self.project_dir(project_id) / "project.json", updated.to_dict())
        result = self.build_intake(project_id)
        result["uploaded_files"] = uploaded_files
        return result

    def build_intake(self, project_id: str) -> dict[str, object]:
        record = self.load_project(project_id)
        brief = self._build_brief(record.to_dict())
        self._bind_repository_path_to_project(record, brief)
        status = "intake_blocked" if brief.blockers else "intake_ready"
        updated = self._update_project_status(record, status)
        project_dir = self.project_dir(project_id)
        self._write_json(project_dir / "brief.json", brief.to_dict())
        return {
            "project": updated.to_dict(),
            "brief": brief.to_dict(),
        }

    def inspect_github(self, project_id: str, payload: dict[str, Any] | None = None) -> dict[str, object]:
        payload = payload or {}
        record = self.load_project(project_id)
        intake = self.build_intake(project_id)
        brief = intake["brief"]
        repository = brief.get("repository") if isinstance(brief, dict) else None
        if not isinstance(repository, dict):
            raise ApiError(409, "repository_missing", "Project does not include a GitHub repository.")
        if not payload.get("prepare", False):
            return intake

        built_brief = self._build_brief(record.to_dict())
        if not built_brief.repository:
            raise ApiError(409, "repository_missing", "Project does not include a GitHub repository.")
        source_runtime = (
            PrivateGitHubSourceRuntime()
            if built_brief.repository.visibility == "private" or built_brief.repository.gh_auth_required
            else GitHubSourceRuntime()
        )
        result = source_runtime.prepare(built_brief.repository)
        if result.blockers:
            built_brief.blockers.extend(result.blockers)
        updated_record = ProjectRecord.from_dict(record.to_dict())
        updated_record.repository_path = built_brief.repository.local_path
        updated_record.status = "intake_blocked" if built_brief.blockers else "intake_ready"
        updated_record.updated_at = utc_now_iso()
        self._write_json(self.project_dir(project_id) / "project.json", updated_record.to_dict())
        self._write_json(self.project_dir(project_id) / "brief.json", built_brief.to_dict())
        return {
            "project": updated_record.to_dict(),
            "brief": built_brief.to_dict(),
            "source": result.to_dict(),
        }

    def get_brief(self, project_id: str) -> dict[str, object]:
        path = self.project_dir(project_id) / "brief.json"
        if not path.exists():
            return self.build_intake(project_id)["brief"]
        return self._read_json(path)

    def build_plan(self, project_id: str) -> dict[str, object]:
        record = self.load_project(project_id)
        if record.status == "intake_blocked":
            raise ApiError(409, "intake_blocked", "Resolve intake blockers before planning.")
        brief_payload = self.get_brief(project_id)
        context_bundle = ContextBundleBuilder().build(brief_payload)
        task_graph = TaskGraphBuilder().build(context_bundle)
        project_dir = self.project_dir(project_id)
        self._write_json(project_dir / "context.json", context_bundle.to_dict())
        self._write_json(project_dir / "task_graph.json", task_graph.to_dict())
        updated = self._update_project_status(record, "planned")
        return {
            "project": updated.to_dict(),
            "context": context_bundle.to_dict(),
            "task_graph": task_graph.to_dict(),
        }

    def get_context(self, project_id: str) -> dict[str, object]:
        path = self.project_dir(project_id) / "context.json"
        if not path.exists():
            return self.build_plan(project_id)["context"]
        return self._read_json(path)

    def get_task_graph(self, project_id: str) -> dict[str, object]:
        path = self.project_dir(project_id) / "task_graph.json"
        if not path.exists():
            return self.build_plan(project_id)["task_graph"]
        return self._read_json(path)

    def delete_project(self, project_id: str) -> dict[str, object]:
        """Remove one Alchemy-managed project and all generated local files."""

        project_dir = self.project_dir(project_id)
        if not (project_dir / "project.json").exists():
            raise ApiError(404, "project_not_found", f"Project not found: {project_id}")

        active_run_id = self.active_run(project_id)
        if active_run_id:
            raise ApiError(
                409,
                "project_has_active_run",
                f"Project has an active run ({active_run_id}). Stop it before deleting the project.",
            )

        projects_root = self.projects_root.resolve()
        target = project_dir.resolve()
        if target == projects_root:
            raise ApiError(400, "unsafe_project_delete", "Refusing to delete the projects root.")
        try:
            target.relative_to(projects_root)
        except ValueError as exc:
            raise ApiError(400, "unsafe_project_delete", "Project folder is outside the managed projects root.") from exc

        shutil.rmtree(target)
        return {
            "project_id": safe_identifier(project_id, "project_id"),
            "status": "deleted",
            "deleted_path": str(target),
        }

    def run_project(self, project_id: str, payload: dict[str, Any] | None = None) -> dict[str, object]:
        record = self.load_project(project_id)
        if record.status not in {"intake_ready", "planned", "done", "blocked"}:
            raise ApiError(409, "project_not_ready", f"Project status '{record.status}' cannot start execution.")
        run_payload = payload or {}
        if record.status != "planned":
            self.build_plan(project_id)
            record = self.load_project(project_id)

        run_id = self.next_run_id(project_id)
        result_payload = self._execute_run(record, run_id, run_payload)
        self._update_project_status(record, project_status_for_run(str(result_payload.get("status", ""))))
        return result_payload

    def start_run(self, project_id: str, payload: dict[str, Any] | None = None) -> dict[str, object]:
        record = self.load_project(project_id)
        if record.status not in {"intake_ready", "planned", "done", "blocked"}:
            raise ApiError(409, "project_not_ready", f"Project status '{record.status}' cannot start execution.")
        if self.active_run(project_id):
            raise ApiError(409, "run_already_active", "A run is already active for this project.")
        if record.status != "planned":
            self.build_plan(project_id)
            record = self.load_project(project_id)

        run_id = self.next_run_id(project_id)
        job_store = self.job_store(project_id)
        job = job_store.create(project_id, run_id)
        self._update_project_status(record, "running")

        run_payload = dict(payload or {})

        def worker() -> None:
            try:
                job_store.transition(run_id, "running", "Run started.", source="runtime")
                result = self._execute_run(record, run_id, run_payload, controller=JobExecutionController(job_store, run_id))
                result_path = self.project_dir(project_id) / "runs" / run_id / "run.json"
                job_status = project_status_for_run(str(result.get("status", "")))
                if result.get("runtime_state", {}).get("iteration_history", []) and has_history_type(result, "run_paused"):
                    job_status = "paused"
                current_job = job_store.load(run_id)
                if current_job.status == "resumed":
                    current_job.result_path = str(result_path)
                    job_store.save(current_job)
                    job_store.append_event(current_job, "source_result_recorded", "runtime", "Source run result recorded after resume handoff.")
                else:
                    job_store.set_result(run_id, result_path, job_status)
                self._update_project_status(record, job_status)
            except Exception as exc:  # pragma: no cover - thread boundary defense.
                job_store.transition(run_id, "failed", "Run failed.", source="runtime", error=str(exc))
                self._update_project_status(record, "failed")

        start_background_job(worker)
        return {
            "project_id": project_id,
            "run_id": run_id,
            "job": job.to_dict(),
        }

    def get_run(self, project_id: str, run_id: str) -> dict[str, object]:
        path = self.project_dir(project_id) / "runs" / run_id / "run.json"
        if not path.exists():
            raise ApiError(404, "run_not_found", f"Run not found: {run_id}")
        return self._read_json(path)

    def get_run_artifacts(self, project_id: str, run_id: str) -> dict[str, object]:
        record = self.load_project(project_id)
        run = self.get_run(project_id, run_id)
        return build_artifact_manifest(
            project_id=project_id,
            run_id=run_id,
            run=run,
            project_dir=self.project_dir(project_id),
            repository_path=record.repository_path or None,
        )

    def get_run_artifact_content(self, project_id: str, run_id: str, artifact_id: str) -> ArtifactContent:
        record = self.load_project(project_id)
        run = self.get_run(project_id, run_id)
        content = resolve_artifact_content(
            project_id=project_id,
            run_id=run_id,
            artifact_id=artifact_id,
            run=run,
            project_dir=self.project_dir(project_id),
            repository_path=record.repository_path or None,
        )
        if content is None:
            raise ApiError(404, "artifact_not_found", f"Artifact not found: {artifact_id}")
        return content

    def get_run_preview_content(self, project_id: str, run_id: str, preview_path: str = "index.html") -> ArtifactContent:
        record = self.load_project(project_id)
        run = self.get_run(project_id, run_id)
        preview_root = best_preview_root(
            project_id=project_id,
            run_id=run_id,
            run=run,
            project_dir=self.project_dir(project_id),
            repository_path=record.repository_path or None,
        )
        if preview_root is None:
            raise ApiError(404, "preview_not_found", "No runnable web preview is available for this run.")
        target = safe_preview_file(preview_root, preview_path or "index.html")
        if target is None:
            raise ApiError(404, "preview_file_not_found", f"Preview file not found: {preview_path}")
        return ArtifactContent(
            artifact_id="preview",
            path=target,
            media_type=media_type_for_preview(target),
            filename=target.name,
        )

    def get_run_status(self, project_id: str, run_id: str, *, stall_seconds: float = 1800.0) -> dict[str, object]:
        record = self.load_project(project_id)
        job = self.get_run_job(project_id, run_id) if (self.project_dir(project_id) / "runs" / run_id / "job.json").exists() else {}
        run_path = self.project_dir(project_id) / "runs" / run_id / "run.json"
        run = self._read_json(run_path) if run_path.exists() else {}
        events = self.job_store(project_id).events(run_id)
        artifact_manifest = (
            build_artifact_manifest(
                project_id=project_id,
                run_id=run_id,
                run=run,
                project_dir=self.project_dir(project_id),
                repository_path=record.repository_path or None,
            )
            if run
            else {"project_id": project_id, "run_id": run_id, "items": []}
        )
        status = str(job.get("status") or run.get("status") or "unknown")
        tasks = summarize_run_tasks(run)
        progress = progress_percent(status=status, tasks=tasks, has_run=bool(run))
        last_activity_at = latest_activity_timestamp(
            [
                str(job.get("updated_at", "") or ""),
                *[str(event.get("timestamp", "") or "") for event in events if isinstance(event, dict)],
            ],
            [
                run_path,
                self.project_dir(project_id) / "runs" / run_id / "events.jsonl",
                self.project_dir(project_id) / "runs" / run_id / "job.json",
                self.project_dir(project_id) / "runs" / run_id / "workers",
            ],
        )
        last_activity_seconds = seconds_since_iso(last_activity_at)
        delivery_actions = build_delivery_actions(
            project_id=project_id,
            run_id=run_id,
            run=run,
            project=record,
            artifact_manifest=artifact_manifest,
        )
        current = current_task_summary(run)
        central_review = build_central_review(
            status=status,
            run=run,
            job=job,
            artifact_manifest=artifact_manifest,
            delivery_actions=delivery_actions,
            is_stalled=status in {"queued", "running"} and last_activity_seconds >= stall_seconds,
        )
        return {
            "project_id": project_id,
            "run_id": run_id,
            "status": status,
            "phase": user_phase(status, run=run, tasks=tasks),
            "progress_percent": progress,
            "summary": progress_summary(status=status, run=run, tasks=tasks),
            "elapsed_seconds": elapsed_seconds(str(job.get("created_at", "") or ""), last_activity_at),
            "last_activity_at": last_activity_at,
            "last_activity_seconds": last_activity_seconds,
            "stall_seconds": stall_seconds,
            "is_stalled": status in {"queued", "running"} and last_activity_seconds >= stall_seconds,
            "tasks": tasks,
            "current_task": current["task"],
            "current_agent": current["agent"],
            "delivery_actions": delivery_actions,
            "artifact_manifest": artifact_manifest,
            "local_delivery": not bool(github_pr_url(run)),
            "central_review": central_review,
            "roadmap_progress": roadmap_progress_for_run(run),
        }

    def preview_auto_iteration(self, project_id: str, run_id: str) -> dict[str, object]:
        record = self.load_project(project_id)
        run = self.get_run(project_id, run_id)
        central_review = self._central_review_for_run(record, run_id, run)
        preview = build_auto_iteration_preview(
            project_id=project_id,
            source_run_id=run_id,
            central_review=central_review,
            run=run,
            delivery_report=run.get("delivery_report", {}) if isinstance(run.get("delivery_report", {}), dict) else {},
            artifact_report=run.get("artifact_report", {}) if isinstance(run.get("artifact_report", {}), dict) else {},
            requirement_coverage=run.get("requirement_coverage", {}) if isinstance(run.get("requirement_coverage", {}), dict) else {},
            development_cycle=run.get("development_cycle", {}) if isinstance(run.get("development_cycle", {}), dict) else {},
            previous_reports=self._auto_iteration_reports(project_id),
        )
        return preview

    def start_auto_iteration(self, project_id: str, run_id: str, payload: dict[str, Any] | None = None) -> dict[str, object]:
        payload = payload or {}
        preview = self.preview_auto_iteration(project_id, run_id)
        repair_plan = dict(preview.get("repair_plan", {})) if isinstance(preview.get("repair_plan", {}), dict) else {}
        auto_execution = repair_plan.get("auto_execution", {}) if isinstance(repair_plan.get("auto_execution", {}), dict) else {}
        if not auto_execution.get("allowed"):
            report = dict(preview.get("auto_iteration_report", {})) if isinstance(preview.get("auto_iteration_report", {}), dict) else {}
            self._persist_auto_iteration_artifacts(project_id, run_id, repair_plan, report)
            return {
                "project_id": project_id,
                "source_run_id": run_id,
                "status": "blocked",
                "repair_run_id": None,
                "repair_plan": repair_plan,
                "auto_iteration_report": report,
            }

        paths = self._persist_auto_iteration_artifacts(
            project_id,
            run_id,
            repair_plan,
            dict(preview.get("auto_iteration_report", {})) if isinstance(preview.get("auto_iteration_report", {}), dict) else {},
        )
        run_payload = dict(payload.get("run", {})) if isinstance(payload.get("run", {}), dict) else {}
        run_payload.setdefault("auto_browser_verify", True)
        run_payload.setdefault("generate_static_ci", True)
        run_payload["central_auto_iteration"] = True
        run_payload["repair_plan_id"] = repair_plan.get("repair_plan_id", "")
        run_payload["repair_target_files"] = repair_plan_target_files(repair_plan)
        run_payload["repair_required_tests"] = repair_plan_acceptance_checks(repair_plan)
        reopened = self.reopen_with_feedback(
            project_id,
            {
                "source_run_id": run_id,
                "feedback_files": [paths["auto_feedback"]],
                "async": bool(payload.get("async", False)),
                "run": run_payload,
            },
        )
        repair_run_id = str(reopened.get("run_id", ""))
        repair_plan["status"] = "started"
        report = build_auto_iteration_report(
            project_id=project_id,
            source_run_id=run_id,
            central_review=preview["central_review"] if isinstance(preview.get("central_review"), dict) else {},
            repair_plan=repair_plan,
            repair_run_id=repair_run_id,
            repair_plan_path=paths["repair_plan_json"],
        )
        self._persist_auto_iteration_artifacts(project_id, run_id, repair_plan, report)
        reopened["central_auto_iteration"] = {
            "status": "started",
            "source_run_id": run_id,
            "repair_plan_id": repair_plan.get("repair_plan_id", ""),
            "repair_plan_path": paths["repair_plan_json"],
            "auto_feedback_file": paths["auto_feedback"],
        }
        repair_run_dir = self.project_dir(project_id) / "runs" / repair_run_id
        self._write_json(repair_run_dir / "repair_source.json", {
            "source_run_id": run_id,
            "repair_plan_id": repair_plan.get("repair_plan_id", ""),
            "repair_plan_path": paths["repair_plan_json"],
            "auto_feedback_file": paths["auto_feedback"],
            "reopen_reason": "central_auto_iteration",
        })
        repair_run_path = repair_run_dir / "run.json"
        if repair_run_path.exists():
            repair_run = self._read_json(repair_run_path)
            repair_run["central_auto_iteration"] = reopened["central_auto_iteration"]
            self._write_json(repair_run_path, repair_run)
        return {
            "project_id": project_id,
            "source_run_id": run_id,
            "status": "started",
            "repair_run_id": repair_run_id,
            "repair_plan": repair_plan,
            "auto_iteration_report": report,
            "run": reopened,
            "job": reopened.get("job", {}),
        }

    def open_run_result_folder(self, project_id: str, run_id: str) -> dict[str, object]:
        record = self.load_project(project_id)
        run = self.get_run(project_id, run_id)
        target = best_result_folder(
            project_dir=self.project_dir(project_id),
            run_id=run_id,
            run=run,
            repository_path=record.repository_path or "",
        )
        allowed_roots = [
            self.project_dir(project_id).resolve(),
            *[Path(path).resolve() for path in result_folder_candidate_paths(run, record.repository_path or "")],
        ]
        if not target.exists() or not target.is_dir() or not is_under_any(target.resolve(), allowed_roots):
            raise ApiError(404, "result_folder_not_found", "No safe local result folder is available for this run.")
        self.folder_opener(target.resolve())
        return {
            "project_id": project_id,
            "run_id": run_id,
            "status": "opened",
            "path": str(target.resolve()),
        }

    def get_run_events(self, project_id: str, run_id: str) -> dict[str, object]:
        stored_events = self.job_store(project_id).events(run_id)
        run_path = self.project_dir(project_id) / "runs" / run_id / "run.json"
        run = self._read_json(run_path) if run_path.exists() else {}
        runtime_state = run.get("runtime_state", {})
        history = runtime_state.get("execution_history", []) if isinstance(runtime_state, dict) else []
        events = list(stored_events)
        for index, item in enumerate(history, start=1):
            event = dict(item) if isinstance(item, dict) else {"message": str(item)}
            event.setdefault("event_id", f"{run_id}-runtime-{index:03d}")
            event.setdefault("run_id", run_id)
            event.setdefault("level", "info")
            event.setdefault("source", "runtime")
            event.setdefault("task_id", event.get("task", {}).get("id", "") if isinstance(event.get("task"), dict) else "")
            event.setdefault("agent", event.get("task", {}).get("assigned_agent", "") if isinstance(event.get("task"), dict) else "")
            events.append(event)
        return {
            "project_id": project_id,
            "run_id": run_id,
            "events": events,
        }

    def stream_run_events(
        self,
        project_id: str,
        run_id: str,
        *,
        last_event_id: str = "",
        timeout_seconds: float = 30.0,
        poll_interval_seconds: float = 0.25,
    ):
        job_path = self.project_dir(project_id) / "runs" / run_id / "job.json"
        run_path = self.project_dir(project_id) / "runs" / run_id / "run.json"
        if not job_path.exists() and not run_path.exists():
            raise ApiError(404, "run_not_found", f"Run not found: {run_id}")
        return self.job_store(project_id).stream_events(
            run_id,
            last_event_id=last_event_id,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )

    def get_run_job(self, project_id: str, run_id: str) -> dict[str, object]:
        try:
            return self.job_store(project_id).load(run_id).to_dict()
        except FileNotFoundError:
            raise ApiError(404, "run_not_found", f"Run job not found: {run_id}")

    def pause_run(self, project_id: str, run_id: str) -> dict[str, object]:
        job = self.job_store(project_id).update_control(
            run_id,
            "pause_requested",
            True,
            "Pause requested. Current synchronous worker will pause at the next controllable boundary.",
        )
        return {"project_id": project_id, "run_id": run_id, "job": job.to_dict()}

    def resume_run(self, project_id: str, run_id: str, payload: dict[str, Any] | None = None) -> dict[str, object]:
        payload = payload or {}
        store = self.job_store(project_id)
        job = store.update_control(run_id, "pause_requested", False, "Resume requested.")
        if job.status == "paused":
            record = self.load_project(project_id)
            run_payload = dict(payload)
            run_payload["resume_from_run_id"] = run_id
            job.status = "resumed"
            store.save(job)
            store.append_event(job, "resumed", "api", "Source run handed off to a new recovery run.")
            self._update_project_status(record, "planned")
            resumed_run_id = self.next_run_id(project_id)
            resumed_job = store.create(project_id, resumed_run_id)
            resumed_job = store.ensure_created(project_id, resumed_run_id)
            self._update_project_status(record, "running")

            def worker() -> None:
                try:
                    store.transition(resumed_run_id, "running", "Run started.", source="runtime")
                    result = self._execute_run(
                        record,
                        resumed_run_id,
                        run_payload,
                        controller=JobExecutionController(store, resumed_run_id),
                    )
                    result_path = self.project_dir(project_id) / "runs" / resumed_run_id / "run.json"
                    job_status = project_status_for_run(str(result.get("status", "")))
                    store.set_result(resumed_run_id, result_path, job_status)
                    self._update_project_status(record, job_status)
                except Exception as exc:  # pragma: no cover - thread boundary defense.
                    store.transition(resumed_run_id, "failed", "Run failed.", source="runtime", error=str(exc))
                    self._update_project_status(record, "failed")

            start_background_job(worker)
            resumed = {
                "project_id": project_id,
                "run_id": resumed_run_id,
                "job": resumed_job.to_dict(),
            }
            store.append_event(job, "resume_started", "api", f"Started resumed run {resumed['run_id']} from {run_id}.")
            return {
                "project_id": project_id,
                "run_id": run_id,
                "job": job.to_dict(),
                "resumed_run_id": resumed["run_id"],
                "resumed_job": resumed["job"],
            }
        return {"project_id": project_id, "run_id": run_id, "job": job.to_dict()}

    def reopen_with_feedback(self, project_id: str, payload: dict[str, Any] | None = None) -> dict[str, object]:
        payload = payload or {}
        source_run_id = str(payload.get("source_run_id", "") or "")
        if not source_run_id:
            source_run_id = self.latest_run_id(project_id)
        source_run = self.get_run(project_id, source_run_id)
        feedback_files = [str(path) for path in payload.get("feedback_files", payload.get("files", [])) if str(path)]
        if not feedback_files:
            raise ApiError(400, "feedback_missing", "At least one feedback file is required to reopen a delivered run.")

        self.add_files(
            project_id,
            {
                "files": [
                    {"path": path, "role": "feedback", "required": True}
                    for path in feedback_files
                ]
            },
        )
        plan = self.build_plan(project_id)
        run_payload = dict(payload.get("run", {})) if isinstance(payload.get("run", {}), dict) else {}
        run_payload.setdefault("worktree_branch_prefix", "agent/feedback-recovery")
        run_payload.setdefault("auto_browser_verify", True)
        run_payload.setdefault("generate_static_ci", True)
        run_payload["feedback_reopen"] = True
        run_payload["feedback_source_run_id"] = source_run_id
        run_payload["feedback_files"] = feedback_files
        target_files = dedupe([
            *[str(item) for item in run_payload.get("repair_target_files", []) if str(item)],
            *feedback_target_files(feedback_files),
        ])
        if target_files:
            run_payload["repair_target_files"] = target_files
        run_payload["feedback_reopen_context"] = {
            "source_run_id": source_run_id,
            "source_status": source_run.get("status", ""),
            "feedback_files": feedback_files,
            "target_files": list(run_payload.get("repair_target_files", [])),
            "task_graph": plan["task_graph"],
            "worktree_branch_prefix": run_payload["worktree_branch_prefix"],
        }
        if bool(payload.get("async", False)):
            started = self.start_run(project_id, run_payload)
            run_id = str(started.get("run_id", ""))
            started["feedback_reopen"] = {
                **run_payload["feedback_reopen_context"],
                "status": "queued",
                "run_id": run_id,
            }
            return started

        run = self.run_project(project_id, run_payload)
        run["feedback_reopen"] = {
            **run_payload["feedback_reopen_context"],
            "status": "started",
            "run_id": run.get("run_id", ""),
        }
        run["recovery_comparison"] = build_recovery_comparison(source_run=source_run, current_run=run)
        self._write_json(self.project_dir(project_id) / "runs" / str(run["run_id"]) / "run.json", run)
        return run

    def stop_run(self, project_id: str, run_id: str) -> dict[str, object]:
        job = self.job_store(project_id).update_control(
            run_id,
            "stop_requested",
            True,
            "Stop requested. Current synchronous worker will stop at the next controllable boundary.",
        )
        return {"project_id": project_id, "run_id": run_id, "job": job.to_dict()}

    def get_delivery(self, project_id: str) -> dict[str, object]:
        runs_dir = self.project_dir(project_id) / "runs"
        if not runs_dir.exists():
            raise ApiError(404, "delivery_not_found", "No execution run has been recorded for this project.")
        run_dirs = sorted(path for path in runs_dir.iterdir() if path.is_dir())
        if not run_dirs:
            raise ApiError(404, "delivery_not_found", "No execution run has been recorded for this project.")
        latest = run_dirs[-1].name
        return self.get_delivery_for_run(project_id, latest)

    def get_delivery_for_run(self, project_id: str, run_id: str) -> dict[str, object]:
        record = self.load_project(project_id)
        run = self.get_run(project_id, run_id)
        delivery_report = run.get("delivery_report", {})
        artifact_report = run.get("artifact_report", {})
        requirement_coverage = run.get("requirement_coverage", {})
        generated_ci = run.get("generated_ci", {})
        development_cycle = run.get("development_cycle", {})
        recovery_comparison = self._recovery_comparison_for_run(project_id, run)
        artifact_manifest = build_artifact_manifest(
            project_id=project_id,
            run_id=run_id,
            run=run,
            project_dir=self.project_dir(project_id),
            repository_path=record.repository_path or None,
        )
        delivery_actions = build_delivery_actions(
            project_id=project_id,
            run_id=run_id,
            run=run,
            project=record,
            artifact_manifest=artifact_manifest,
        )
        delivery_evidence = build_delivery_evidence(
            status=str(run.get("status", "")),
            delivery_report=delivery_report if isinstance(delivery_report, dict) else {},
            artifact_report=artifact_report if isinstance(artifact_report, dict) else {},
            requirement_coverage=requirement_coverage if isinstance(requirement_coverage, dict) else {},
            generated_ci=generated_ci if isinstance(generated_ci, dict) else {},
            development_cycle=development_cycle if isinstance(development_cycle, dict) else {},
            recovery_comparison=recovery_comparison,
        )
        central_review = build_central_review(
            status=str(run.get("status", "")),
            run=run,
            delivery_report=delivery_report if isinstance(delivery_report, dict) else {},
            artifact_report=artifact_report if isinstance(artifact_report, dict) else {},
            requirement_coverage=requirement_coverage if isinstance(requirement_coverage, dict) else {},
            development_cycle=development_cycle if isinstance(development_cycle, dict) else {},
            artifact_manifest=artifact_manifest,
            delivery_actions=delivery_actions,
        )
        auto_iteration = self._read_auto_iteration_report(project_id, run_id)
        repair_plan = self._read_repair_plan(project_id, run_id)
        if (
            str(central_review.get("decision", "")) == "iterate"
            and not auto_iteration
            and not repair_plan
        ):
            preview = self.preview_auto_iteration(project_id, run_id)
            auto_iteration = preview.get("auto_iteration_report", {}) if isinstance(preview.get("auto_iteration_report"), dict) else {}
            repair_plan = preview.get("repair_plan", {}) if isinstance(preview.get("repair_plan"), dict) else {}
        return {
            "project_id": project_id,
            "latest_run_id": run_id,
            "status": run.get("status"),
            "runtime_state": run.get("runtime_state", {}),
            "preflight": run.get("preflight", {}),
            "artifact_report": artifact_report,
            "requirement_coverage": requirement_coverage,
            "generated_ci": generated_ci,
            "delivery_report": delivery_report,
            "delivery_evidence": delivery_evidence,
            "artifact_manifest": artifact_manifest,
            "delivery_actions": delivery_actions,
            "local_delivery": not bool(github_pr_url(run)),
            "development_cycle": development_cycle,
            "recovery_comparison": recovery_comparison,
            "central_review": central_review,
            "auto_iteration": auto_iteration,
            "repair_plan": repair_plan,
            "output_dir": run.get("output_dir", ""),
        }

    def get_evidence_index(self, payload: dict[str, Any] | None = None) -> dict[str, object]:
        payload = payload or {}
        roots = evidence_roots(payload.get("roots", payload.get("root")), default=self.evidence_root)
        output = Path(str(payload.get("output", "") or self.storage_root / "evidence" / "real_probe_index.json"))
        index = RealProbeIndexer().build(roots=roots, output_path=output)
        return index.to_dict()

    def export_evidence_package(self, payload: dict[str, Any] | None = None) -> dict[str, object]:
        payload = payload or {}
        roots = evidence_roots(payload.get("roots", payload.get("root")), default=self.evidence_root)
        output = Path(str(payload.get("output", "") or self.storage_root / "evidence_package"))
        report = EvidencePackageExporter().export(
            roots=roots,
            output_dir=output,
            include_unknown_json=bool(payload.get("include_unknown_json", False)),
            clean_output=bool(payload.get("clean_output", True)),
        )
        return report.to_dict()

    def compare_benchmark_regression(self, payload: dict[str, Any] | None = None) -> dict[str, object]:
        payload = payload or {}
        baseline = str(payload.get("baseline", "") or "")
        current = str(payload.get("current", "") or "")
        if not baseline:
            raise ApiError(400, "benchmark_baseline_missing", "baseline is required.")
        if not current:
            raise ApiError(400, "benchmark_current_missing", "current is required.")
        output = Path(str(payload.get("output", "") or self.storage_root / "benchmark_regression"))
        report = BenchmarkRegressionGate().compare(
            baseline=baseline,
            current=current,
            output_dir=output,
        )
        return report.to_dict()

    def evaluate_evidence_readiness(self, payload: dict[str, Any] | None = None) -> dict[str, object]:
        payload = payload or {}
        evidence_index = str(payload.get("evidence_index", "") or "")
        evidence_package = str(payload.get("evidence_package", "") or "")
        if not evidence_index:
            raise ApiError(400, "evidence_index_missing", "evidence_index is required.")
        if not evidence_package:
            raise ApiError(400, "evidence_package_missing", "evidence_package is required.")
        benchmark_regression = str(payload.get("benchmark_regression", "") or "")
        output = Path(str(payload.get("output", "") or self.storage_root / "evidence_readiness"))
        report = EvidenceReadinessGate().evaluate(
            evidence_index=evidence_index,
            evidence_package=evidence_package,
            benchmark_regression=benchmark_regression or None,
            output_dir=output,
        )
        return report.to_dict()

    def load_project(self, project_id: str) -> ProjectRecord:
        path = self.project_dir(project_id) / "project.json"
        if not path.exists():
            raise ApiError(404, "project_not_found", f"Project not found: {project_id}")
        return ProjectRecord.from_dict(self._read_json(path))

    def project_dir(self, project_id: str) -> Path:
        safe = safe_identifier(project_id, "project_id")
        return self.projects_root / safe

    def next_run_id(self, project_id: str) -> str:
        runs_dir = self.project_dir(project_id) / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        existing = [path.name for path in runs_dir.iterdir() if path.is_dir() and path.name.startswith("run_")]
        numbers = [int(name.split("_", 1)[1]) for name in existing if name.split("_", 1)[1].isdigit()]
        return f"run_{(max(numbers) if numbers else 0) + 1:03d}"

    def latest_run_id(self, project_id: str) -> str:
        runs_dir = self.project_dir(project_id) / "runs"
        if not runs_dir.exists():
            raise ApiError(404, "run_not_found", "No source run exists for feedback reopen.")
        run_dirs = sorted(path for path in runs_dir.iterdir() if path.is_dir() and path.name.startswith("run_"))
        if not run_dirs:
            raise ApiError(404, "run_not_found", "No source run exists for feedback reopen.")
        return run_dirs[-1].name

    def active_run(self, project_id: str) -> str:
        runs_dir = self.project_dir(project_id) / "runs"
        if not runs_dir.exists():
            return ""
        for run_dir in sorted(runs_dir.iterdir()):
            job_path = run_dir / "job.json"
            if not job_path.exists():
                continue
            job = self.job_store(project_id).load(run_dir.name)
            if job.status in {"queued", "running", "paused"}:
                return job.run_id
        return ""

    def job_store(self, project_id: str) -> JobStore:
        return JobStore(self.project_dir(project_id))

    def _execute_run(
        self,
        record: ProjectRecord,
        run_id: str,
        run_payload: dict[str, Any],
        *,
        controller: Any = None,
    ) -> dict[str, object]:
        output_dir = self.project_dir(record.project_id) / "runs" / run_id
        if bool(run_payload.get("full_roadmap", False)):
            result = FullRoadmapExecutor().run(
                objective=record.objective,
                documents=record.documents,
                attachments=record.attachments,
                primary_input_mode=record.primary_input_mode,
                repository_url=record.repository_url,
                repository_path=record.repository_path or None,
                repository_visibility=record.repository_visibility,
                output_dir=output_dir,
                max_phases=int(run_payload.get("max_phases", 50)),
                run_payload=run_payload,
            )
            result_payload = result.to_dict()
            result_payload["run_id"] = run_id
            result_payload["project_id"] = record.project_id
            result_payload["delivery_report"] = full_roadmap_delivery_report(result_payload)
            result_payload["runtime_state"] = full_roadmap_runtime_state(result_payload)
            result_payload["task_graph"] = full_roadmap_task_graph(result_payload)
            result_payload["artifact_report"] = {"artifact_profile": {"name": "full_roadmap"}, "artifact_files": []}
            result_payload["requirement_coverage"] = full_roadmap_requirement_coverage(result_payload)
            self._write_json(output_dir / "run.json", result_payload)
            return result_payload
        if record.primary_input_mode == "one_line_fallback":
            result = AutoDevPipeline().run(record.objective, output_dir)
            result_payload = build_one_line_run_payload(result.to_dict(), project_id=record.project_id, run_id=run_id)
            self._write_json(output_dir / "run.json", result_payload)
            return result_payload
        result = DocumentRunPipeline().run(
            objective=record.objective,
            documents=record.documents,
            attachments=record.attachments,
            primary_input_mode=record.primary_input_mode,
            repository_url=record.repository_url,
            repository_path=record.repository_path or None,
            output_dir=output_dir,
            max_iterations=int(run_payload.get("max_iterations", 50)),
            prepare_repository=bool(run_payload.get("prepare_repository", False)),
            real_codex=bool(run_payload.get("real_codex", False)),
            real_github=bool(run_payload.get("real_github", False)),
            codex_executable=str(run_payload.get("codex_executable", "codex")),
            max_worker_seconds=int(run_payload.get("max_worker_seconds", 0) or 0),
            github_collect_ci=bool(run_payload.get("github_collect_ci", True)),
            github_ci_wait_seconds=float(run_payload.get("github_ci_wait_seconds", 120)),
            github_ci_poll_interval_seconds=float(run_payload.get("github_ci_poll_interval_seconds", 10)),
            isolate_real_run=self._should_isolate_real_run(record, run_payload),
            keep_worktree=bool(run_payload.get("keep_worktree", True)),
            worktree_branch_prefix=str(run_payload.get("worktree_branch_prefix", "agent/alchemy-real-run")),
            resume_from=self._resume_source_path(record.project_id, run_payload),
            resume_tasks=[str(task_id) for task_id in run_payload.get("resume_tasks", [])],
            auto_browser_verify=bool(run_payload.get("auto_browser_verify", False)),
            generate_static_ci=bool(run_payload.get("generate_static_ci", True)),
            write_native_ui_tests=bool(run_payload.get("write_native_ui_tests", False)),
            auto_merge=bool(run_payload.get("auto_merge", False)),
            constraints=boundary_mode_constraints(run_payload),
            controller=controller,
            repair_convergence=self._repair_convergence_config(run_payload),
        )
        result_payload = result.to_dict()
        result_payload["run_id"] = run_id
        result_payload["project_id"] = record.project_id
        self._attach_run_payload_metadata(record.project_id, run_id, result_payload, run_payload)
        self._write_json(output_dir / "run.json", result_payload)
        return result_payload

    def _attach_run_payload_metadata(
        self,
        project_id: str,
        run_id: str,
        result_payload: dict[str, object],
        run_payload: dict[str, Any],
    ) -> None:
        feedback_context = run_payload.get("feedback_reopen_context", {})
        if isinstance(feedback_context, dict) and feedback_context:
            feedback_reopen = dict(feedback_context)
            feedback_reopen.update({
                "status": "started",
                "run_id": run_id,
            })
            result_payload["feedback_reopen"] = feedback_reopen
            source_run_id = str(feedback_context.get("source_run_id", "") or "")
            if source_run_id:
                try:
                    source_run = self.get_run(project_id, source_run_id)
                    result_payload["recovery_comparison"] = build_recovery_comparison(
                        source_run=source_run,
                        current_run=result_payload,
                    )
                except ApiError:
                    pass

        if bool(run_payload.get("central_auto_iteration", False)):
            existing = result_payload.get("central_auto_iteration", {})
            central_auto_iteration = dict(existing) if isinstance(existing, dict) else {}
            central_auto_iteration.update({
                "status": central_auto_iteration.get("status", "started"),
                "source_run_id": str(run_payload.get("feedback_source_run_id", "") or ""),
                "repair_plan_id": str(run_payload.get("repair_plan_id", "") or ""),
            })
            result_payload["central_auto_iteration"] = central_auto_iteration

    def _should_isolate_real_run(self, record: ProjectRecord, run_payload: dict[str, Any]) -> bool:
        if not bool(run_payload.get("isolate_real_run", True)):
            return False
        if record.repository_path:
            return True
        if record.repository_url and bool(run_payload.get("prepare_repository", False)):
            return True
        return False

    def _resume_source_path(self, project_id: str, run_payload: dict[str, Any]) -> str | None:
        resume_from_run_id = str(run_payload.get("resume_from_run_id", "") or "")
        resume_from = str(run_payload.get("resume_from", "") or "")
        if resume_from_run_id:
            source_dir = self.project_dir(project_id) / "runs" / safe_identifier(resume_from_run_id, "resume_from_run_id")
            if not source_dir.exists():
                raise ApiError(404, "run_not_found", f"Resume source run not found: {resume_from_run_id}")
            return str(source_dir)
        if resume_from:
            return resume_from
        return None

    def _repair_convergence_config(self, run_payload: dict[str, Any]) -> dict[str, object] | None:
        if not (run_payload.get("feedback_reopen") or run_payload.get("central_auto_iteration")):
            return None
        return {
            "enabled": True,
            "source_run_id": str(run_payload.get("feedback_source_run_id", "") or ""),
            "repair_plan_id": str(run_payload.get("repair_plan_id", "") or ""),
            "feedback_files": [str(item) for item in run_payload.get("feedback_files", []) if str(item)],
            "target_files": [str(item) for item in run_payload.get("repair_target_files", []) if str(item)],
            "required_tests": [str(item) for item in run_payload.get("repair_required_tests", []) if str(item)],
        }

    def _recovery_comparison_for_run(self, project_id: str, run: dict[str, object]) -> dict[str, object]:
        stored = run.get("recovery_comparison", {})
        if isinstance(stored, dict) and stored:
            return stored
        source_run_id = comparison_source_run_id(run)
        if not source_run_id:
            return {}
        try:
            source_run = self.get_run(project_id, source_run_id)
        except ApiError:
            return {}
        return build_recovery_comparison(source_run=source_run, current_run=run)

    def _central_review_for_run(self, record: ProjectRecord, run_id: str, run: dict[str, object]) -> dict[str, Any]:
        artifact_manifest = build_artifact_manifest(
            project_id=record.project_id,
            run_id=run_id,
            run=run,
            project_dir=self.project_dir(record.project_id),
            repository_path=record.repository_path or None,
        )
        delivery_actions = build_delivery_actions(
            project_id=record.project_id,
            run_id=run_id,
            run=run,
            project=record,
            artifact_manifest=artifact_manifest,
        )
        return build_central_review(
            status=str(run.get("status", "")),
            run=run,
            delivery_report=run.get("delivery_report", {}) if isinstance(run.get("delivery_report", {}), dict) else {},
            artifact_report=run.get("artifact_report", {}) if isinstance(run.get("artifact_report", {}), dict) else {},
            requirement_coverage=run.get("requirement_coverage", {}) if isinstance(run.get("requirement_coverage", {}), dict) else {},
            development_cycle=run.get("development_cycle", {}) if isinstance(run.get("development_cycle", {}), dict) else {},
            artifact_manifest=artifact_manifest,
            delivery_actions=delivery_actions,
        )

    def _auto_iteration_reports(self, project_id: str) -> list[dict[str, Any]]:
        reports: list[dict[str, Any]] = []
        runs_dir = self.project_dir(project_id) / "runs"
        if not runs_dir.exists():
            return reports
        for report_path in sorted(runs_dir.glob("run_*/auto_iteration_report.json")):
            try:
                report = self._read_json(report_path)
            except (OSError, json.JSONDecodeError):
                continue
            plan_path = report_path.parent / "repair_plan.json"
            if plan_path.exists():
                try:
                    report["repair_plan"] = self._read_json(plan_path)
                except (OSError, json.JSONDecodeError):
                    pass
            reports.append(report)
        return reports

    def _read_auto_iteration_report(self, project_id: str, run_id: str) -> dict[str, object]:
        path = self.project_dir(project_id) / "runs" / run_id / "auto_iteration_report.json"
        return self._read_json(path) if path.exists() else {}

    def _read_repair_plan(self, project_id: str, run_id: str) -> dict[str, object]:
        path = self.project_dir(project_id) / "runs" / run_id / "repair_plan.json"
        return self._read_json(path) if path.exists() else {}

    def _persist_auto_iteration_artifacts(
        self,
        project_id: str,
        run_id: str,
        repair_plan: dict[str, Any],
        auto_iteration_report: dict[str, Any],
    ) -> dict[str, str]:
        run_dir = self.project_dir(project_id) / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        repair_json = run_dir / "repair_plan.json"
        repair_md = run_dir / "repair_plan.md"
        feedback_md = run_dir / "auto_feedback.md"
        report_json = run_dir / "auto_iteration_report.json"
        self._write_json(repair_json, repair_plan)
        repair_md.write_text(repair_plan_markdown(repair_plan), encoding="utf-8")
        feedback_md.write_text(auto_feedback_markdown(repair_plan), encoding="utf-8")
        if auto_iteration_report:
            self._write_json(report_json, auto_iteration_report)
        return {
            "repair_plan_json": str(repair_json),
            "repair_plan_markdown": str(repair_md),
            "auto_feedback": str(feedback_md),
            "auto_iteration_report": str(report_json),
        }

    def _build_brief(self, payload: dict[str, Any]) -> ProjectBrief:
        project_id_override = str(payload.get("project_id", ""))
        normalized = normalize_project_payload(payload)
        brief = ProjectBriefBuilder().build(
            objective=str(normalized["objective"]),
            documents=list(normalized["documents"]),
            attachments=list(normalized["attachments"]),
            primary_input_mode=normalized["primary_input_mode"],
            repository_url=str(normalized["repository_url"]),
            repository_path=str(normalized["repository_path"]),
            target_branch=str(normalized["target_branch"]),
            base_branch=str(normalized["base_branch"]),
            repository_visibility=normalized["repository_visibility"],
            constraints=list(normalized["constraints"]),
            acceptance_criteria=list(normalized["acceptance_criteria"]),
            file_roles={str(path): role for path, role in normalized["file_roles"].items()},
            required_attachments=list(normalized["required_attachments"]),
        )
        if project_id_override:
            brief.project_id = project_id_override
        return brief

    def _update_project_status(self, record: ProjectRecord, status: str) -> ProjectRecord:
        current_path = self.project_dir(record.project_id) / "project.json"
        updated = ProjectRecord.from_dict(record.to_dict())
        if current_path.exists():
            try:
                current = ProjectRecord.from_dict(self._read_json(current_path))
                if current.status in {"intake_pending", "intake_blocked"} and status not in {"intake_ready", "intake_blocked", "planned", "running"}:
                    return current
                updated = current
            except (KeyError, TypeError, json.JSONDecodeError, OSError, ValueError):
                updated = ProjectRecord.from_dict(record.to_dict())
        updated.status = status
        updated.updated_at = utc_now_iso()
        self._write_json(current_path, updated.to_dict())
        return updated

    def _bind_repository_path_to_project(self, record: ProjectRecord, brief: ProjectBrief | None = None) -> None:
        if not brief or not brief.repository:
            return
        if record.repository_path:
            brief.repository.local_path = record.repository_path
        elif record.repository_url:
            brief.repository.local_path = ""

    def _read_json(self, path: Path) -> dict[str, Any]:
        last_error: json.JSONDecodeError | FileNotFoundError | PermissionError | None = None
        for _ in range(50):
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError, PermissionError) as exc:
                last_error = exc
                time.sleep(0.02)
        if last_error:
            raise last_error
        raise FileNotFoundError(path)

    def _write_json(self, path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        temp_path = path.with_name(f"{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
        try:
            for attempt in range(10):
                try:
                    temp_path.write_text(content, encoding="utf-8")
                    temp_path.replace(path)
                    return
                except PermissionError:
                    if attempt == 9:
                        raise
                    time.sleep(0.02)
        finally:
            if temp_path.exists():
                temp_path.unlink()


def normalize_project_payload(payload: dict[str, Any]) -> dict[str, Any]:
    documents = [str(path) for path in payload.get("documents", [])]
    attachments = [str(path) for path in payload.get("attachments", [])]
    file_roles: dict[str, FileRole] = {
        str(key): value
        for key, value in payload.get("file_roles", {}).items()
        if value
    }

    required_attachments = [str(path) for path in payload.get("required_attachments", [])]

    for file_payload in payload.get("files", []):
        if not isinstance(file_payload, dict):
            continue
        path = str(file_payload.get("path", ""))
        if not path:
            continue
        role = str(file_payload.get("role", "supplemental"))
        required = bool(file_payload.get("required", role == "primary_requirements"))
        if role == "primary_requirements" or (required and not documents and role in {"", "supplemental"}):
            if path not in documents:
                documents.append(path)
        elif path not in attachments:
            attachments.append(path)
        if role:
            file_roles[path] = role
        if required and path not in documents and path not in required_attachments:
            required_attachments.append(path)

    return {
        "objective": str(payload.get("objective", "")),
        "primary_input_mode": str(payload.get("primary_input_mode", "document_driven")),
        "documents": documents,
        "attachments": attachments,
        "repository_url": str(payload.get("repository_url", payload.get("repository", "")) or ""),
        "repository_path": str(payload.get("repository_path", "") or ""),
        "target_branch": str(payload.get("target_branch", "main") or "main"),
        "base_branch": str(payload.get("base_branch", "") or ""),
        "repository_visibility": str(payload.get("repository_visibility", "public") or "public"),
        "constraints": [str(item) for item in payload.get("constraints", [])],
        "acceptance_criteria": [str(item) for item in payload.get("acceptance_criteria", [])],
        "file_roles": file_roles,
        "required_attachments": required_attachments,
    }


def normalize_unified_run_payload_for_project(run_payload: dict[str, Any], project: dict[str, object]) -> dict[str, Any]:
    normalized = dict(run_payload)
    has_repository_path = bool(str(project.get("repository_path", "") or ""))
    has_prepared_repository = bool(str(project.get("repository_url", "") or "")) and bool(normalized.get("prepare_repository", False))
    if bool(normalized.get("real_codex", False)) and not has_repository_path and not has_prepared_repository:
        normalized["isolate_real_run"] = False
    return normalized


def generated_one_line_document(objective: str) -> str:
    quoted_objective = "\n".join(f"> {line}" for line in objective.strip().splitlines() if line.strip())
    artifact = one_line_artifact_contract(objective)
    return f"""# Generated Development Brief

## Source

This document was generated from the one-line objective submitted in the browser console. It converts the idea prompt into a document-driven project contract so the runtime can use the full autonomous development loop instead of the legacy one-line fallback.

## Original Objective

{quoted_objective}

## Product Goal

Build a complete, runnable software artifact that satisfies the original objective. If the objective is underspecified, make conservative product and technical assumptions, record them in the delivery evidence, and implement the smallest complete version that can be tested end to end.

## Artifact Contract

- Must deliver a local browser application with `index.html` as the entrypoint.
- Must implement application behavior in `src/main.js`.
- Must implement visual styling in `src/styles.css`.
- Must provide deterministic validation in `tests/static_checks.js`.
- Should include usage notes in `README.md`.
- Suggested artifact type: {artifact["name"]}.

## Required Development Flow

- Analyze the objective and derive concrete requirements before writing code.
- Create or update the project structure needed for a runnable artifact.
- Implement the core user-facing behavior.
- Add deterministic validation through tests, static checks, or browser verification when applicable.
- Run the review and evaluation gate before marking the work done.

## Functional Requirements

- Must create `index.html`, `src/main.js`, and `src/styles.css` so the artifact can run locally from a checkout.
- Must implement the primary workflow implied by the objective in `src/main.js` without requiring manual code changes.
- Must expose visible UI state and interactive controls in `index.html` and `src/main.js`.
- Must document how to run the artifact in `README.md`.
- Must add deterministic validation in `tests/static_checks.js` for the generated artifact.
{artifact["requirements"]}

## Acceptance Criteria

- `index.html` loads the app shell and references `src/main.js` and `src/styles.css`.
- `src/main.js` implements the main user workflow from the objective.
- `src/styles.css` provides a polished, readable interface.
- `tests/static_checks.js` can inspect the generated files and fail on missing critical behavior.
- Runtime output includes task graph, execution history, artifact report, requirement coverage, and final gate evaluation.
{artifact["acceptance"]}
"""


def one_line_artifact_contract(objective: str) -> dict[str, str]:
    lowered = objective.lower()
    is_game = any(marker in lowered or marker in objective for marker in ("game", "platform", "platformer", "游戏", "关卡", "闯关"))
    if is_game:
        return {
            "name": "static canvas game",
            "requirements": "\n".join(
                [
                    "- Must use `index.html` and `src/main.js` to provide a playable canvas or DOM-based game loop.",
                    "- Must include player controls, score or progress state, win/lose or restart behavior, and a complete first playable scenario in `src/main.js`.",
                    "- Must avoid protected external assets and use original generated visuals in `src/styles.css` and `src/main.js`.",
                ]
            ),
            "acceptance": "\n".join(
                [
                    "- Game starts from `index.html` and is playable with keyboard or on-screen controls.",
                    "- The first level or scenario has a clear start, challenge, and completion state.",
                    "- Validation checks confirm that player control, collision or state progression, and restart/completion hooks exist.",
                ]
            ),
        }
    return {
        "name": "static web app",
        "requirements": "\n".join(
            [
                "- Must implement data/state transitions for the main workflow in `src/main.js`.",
                "- Must include at least one interactive path that changes visible UI state in `index.html`.",
            ]
        ),
        "acceptance": "\n".join(
            [
                "- The user can complete the primary workflow from the objective in the browser.",
                "- Validation checks confirm that the core interaction and visible state update are implemented.",
            ]
        ),
    }


def evidence_roots(value: object, *, default: Path) -> list[Path]:
    if value is None or value == "":
        return [default]
    if isinstance(value, (str, Path)):
        return [Path(value)]
    if isinstance(value, list):
        roots = [Path(str(item)) for item in value if str(item)]
        return roots or [default]
    return [default]


def safe_identifier(value: str, field_name: str) -> str:
    if not value:
        raise ApiError(400, "invalid_identifier", f"{field_name} is required.")
    if any(char in value for char in ("/", "\\", "..")):
        raise ApiError(400, "invalid_identifier", f"{field_name} contains unsafe path characters.")
    return value


def dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value)
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def repair_plan_target_files(plan: dict[str, object]) -> list[str]:
    items = plan.get("items", [])
    if not isinstance(items, list):
        return []
    values: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        values.extend(str(value) for value in item.get("target_files", []) if str(value))
    return dedupe(values)


def repair_plan_acceptance_checks(plan: dict[str, object]) -> list[str]:
    items = plan.get("items", [])
    if not isinstance(items, list):
        return []
    values: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        acceptance = str(item.get("acceptance_check", "") or "")
        if acceptance:
            values.append(acceptance)
        values.extend(str(value) for value in item.get("required_evidence", []) if str(value))
    return dedupe(values)


def feedback_target_files(feedback_files: list[str]) -> list[str]:
    values: list[str] = []
    for feedback_file in feedback_files:
        path = Path(feedback_file)
        if not path.exists() or not path.is_file():
            continue
        try:
            values.extend(target_files_from_text(path.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    return dedupe(values)


def boundary_mode_constraints(run_payload: dict[str, Any]) -> list[str]:
    mode = str(run_payload.get("boundary_mode", "auto") or "auto")
    if mode in {"strict", "large_refactor"}:
        return [f"Scope boundary mode: {mode}"]
    return []


def project_status_for_run(run_status: str) -> str:
    if run_status == "done":
        return "done"
    if run_status == "blocked":
        return "blocked"
    if run_status == "in_progress":
        return "needs_iteration"
    if run_status == "failed":
        return "failed"
    return "running"


def summarize_run_tasks(run: dict[str, object]) -> dict[str, int]:
    nodes = task_nodes_from_run(run)
    total = len(nodes)
    completed = sum(1 for node in nodes if str(node.get("status", "")).lower() in {"completed", "done", "passed"})
    running = sum(1 for node in nodes if str(node.get("status", "")).lower() in {"running", "in_progress", "active"})
    failed = sum(1 for node in nodes if str(node.get("status", "")).lower() in {"failed", "blocked"})
    return {
        "total": total,
        "completed": completed,
        "running": running,
        "failed": failed,
    }


def task_nodes_from_run(run: dict[str, object]) -> list[dict[str, object]]:
    graph = run.get("task_graph", {})
    if not isinstance(graph, dict):
        runtime_state = run.get("runtime_state", {})
        graph = runtime_state.get("task_graph", {}) if isinstance(runtime_state, dict) else {}
    nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
    return [dict(node) for node in nodes if isinstance(node, dict)]


def progress_percent(*, status: str, tasks: dict[str, int], has_run: bool) -> int:
    normalized = status.lower()
    if normalized in {"done", "ready"}:
        return 100
    if normalized in {"failed", "blocked", "needs_iteration"}:
        computed = _task_progress(tasks) if tasks["total"] else (80 if has_run else 20)
        return max(20, min(95, computed))
    if normalized == "paused":
        return max(10, min(95, _task_progress(tasks) if tasks["total"] else 35))
    if normalized == "queued":
        return 5
    if normalized == "running":
        return max(15, min(95, _task_progress(tasks) if tasks["total"] else 15))
    return 0


def _task_progress(tasks: dict[str, int]) -> int:
    total = max(1, tasks["total"])
    weighted = tasks["completed"] + (tasks["running"] * 0.35)
    return int(round(10 + (weighted / total) * 75))


def user_phase(status: str, *, run: dict[str, object], tasks: dict[str, int]) -> str:
    normalized = status.lower()
    if normalized == "queued":
        return "planning"
    if normalized == "running":
        if tasks["failed"]:
            return "testing"
        if tasks["completed"]:
            return "developing"
        return "planning"
    if normalized == "paused":
        return "developing"
    if normalized == "done":
        return "ready"
    if normalized in {"failed", "blocked", "needs_iteration"}:
        return "blocked" if not has_reviewable_artifact(run) else "reviewing"
    return "choose_source"


def progress_summary(*, status: str, run: dict[str, object], tasks: dict[str, int]) -> str:
    normalized = status.lower()
    if normalized == "done":
        return "Ready to review. The generated result and delivery evidence are available."
    if normalized == "queued":
        return "Queued. The system is preparing the development run."
    if normalized == "running":
        if tasks["total"]:
            return f"Developing. {tasks['completed']} of {tasks['total']} tasks are complete."
        return "Developing. The system is planning or executing the first tasks."
    if normalized == "paused":
        return "Paused. Resume when you want the agent loop to continue."
    if normalized in {"failed", "blocked", "needs_iteration"}:
        if has_reviewable_artifact(run):
            return "Stopped with reviewable output. Open the result and decide whether to iterate."
        return "Stopped before a reviewable result was produced. Check blockers or developer details."
    return "Waiting for a development source."


def current_task_summary(run: dict[str, object]) -> dict[str, str]:
    nodes = task_nodes_from_run(run)
    for status in ("running", "in_progress", "active"):
        for node in nodes:
            if str(node.get("status", "")).lower() == status:
                return {
                    "task": str(node.get("title", node.get("id", "")) or ""),
                    "agent": str(node.get("assigned_agent", "") or ""),
                }
    for node in nodes:
        if str(node.get("status", "")).lower() not in {"completed", "done", "passed"}:
            return {
                "task": str(node.get("title", node.get("id", "")) or ""),
                "agent": str(node.get("assigned_agent", "") or ""),
            }
    return {"task": "", "agent": ""}


def build_delivery_actions(
    *,
    project_id: str,
    run_id: str,
    run: dict[str, object],
    project: ProjectRecord,
    artifact_manifest: dict[str, object],
) -> list[dict[str, object]]:
    actions: list[dict[str, object]] = []
    best_artifact = best_browser_artifact(artifact_manifest)
    if best_artifact:
        preview_url = web_preview_url(project_id=project_id, run_id=run_id, artifact=best_artifact)
        actions.append(
            {
                "id": "open_result",
                "kind": "browser",
                "label": "Open result",
                "label_zh": "打开作品",
                "enabled": True,
                "url": preview_url,
                "artifact_url": best_artifact["url"],
                "description": "Open the generated web result with its CSS and JavaScript assets.",
            }
        )
    folder = best_result_folder(
        project_dir=Path(""),
        run_id=run_id,
        run=run,
        repository_path=project.repository_path,
    )
    actions.append(
        {
            "id": "open_folder",
            "kind": "local_folder",
            "label": "Open folder",
            "label_zh": "打开结果文件夹",
            "enabled": True,
            "url": f"/projects/{project_id}/runs/{run_id}/open-folder",
            "method": "POST",
            "path_hint": folder.as_posix() if str(folder) else "",
            "description": "Open the local folder that contains the generated result.",
        }
    )
    pr_url = github_pr_url(run)
    if pr_url:
        actions.append(
            {
                "id": "open_pr",
                "kind": "github_pr",
                "label": "Open PR",
                "label_zh": "打开 PR",
                "enabled": True,
                "url": pr_url,
                "description": "Open the GitHub pull request for this run.",
            }
        )
    else:
        actions.append(
            {
                "id": "publish_github",
                "kind": "github_publish",
                "label": "Publish to GitHub",
                "label_zh": "发布到 GitHub",
                "enabled": False,
                "url": "",
                "description": "Local delivery. No pull request was created for this source.",
            }
        )
    return actions


def best_browser_artifact(manifest: dict[str, object]) -> dict[str, object] | None:
    items = [dict(item) for item in manifest.get("items", []) if isinstance(item, dict)]
    if not items:
        return None
    html_items = [item for item in items if item.get("kind") == "artifact_file" and str(item.get("path", "")).lower().endswith(("index.html", ".html", ".htm"))]
    if html_items:
        return html_items[0]
    html_items = [item for item in items if str(item.get("media_type", "")).startswith("text/html")]
    if html_items:
        return html_items[0]
    previewable = [item for item in items if str(item.get("url", "")) and item.get("preview") in {"text", "image"}]
    return previewable[0] if previewable else items[0]


def web_preview_url(*, project_id: str, run_id: str, artifact: dict[str, object]) -> str:
    path = str(artifact.get("path", "") or "index.html").replace("\\", "/").lstrip("/")
    if not path or path.endswith("/"):
        path = "index.html"
    quoted_path = "/".join(quote(part) for part in path.split("/") if part)
    return f"/projects/{quote(project_id)}/runs/{quote(run_id)}/preview/{quoted_path or 'index.html'}"


def best_preview_root(
    *,
    project_id: str,
    run_id: str,
    run: dict[str, object],
    project_dir: Path,
    repository_path: str | Path | None,
) -> Path | None:
    manifest = build_artifact_manifest(
        project_id=project_id,
        run_id=run_id,
        run=run,
        project_dir=project_dir,
        repository_path=repository_path,
        include_internal=True,
    )
    best = best_browser_artifact(manifest)
    if not best:
        return None
    absolute_path = Path(str(best.get("_absolute_path", "")))
    if not absolute_path.is_file():
        return None
    display_path = str(best.get("path", "") or absolute_path.name).replace("\\", "/")
    parts = [part for part in display_path.split("/") if part and part not in {".", ".."}]
    root = absolute_path.parent
    for _ in parts[:-1]:
        root = root.parent
    try:
        absolute_path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return absolute_path.parent.resolve()
    return root.resolve()


def safe_preview_file(root: Path, preview_path: str) -> Path | None:
    normalized = str(preview_path or "index.html").replace("\\", "/").lstrip("/")
    if not normalized or normalized.endswith("/"):
        normalized = f"{normalized}index.html"
    if any(part in {"", ".", ".."} for part in normalized.split("/")):
        return None
    try:
        candidate = (root / normalized).resolve()
        candidate.relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    if candidate.is_dir():
        candidate = candidate / "index.html"
    return candidate if candidate.is_file() else None


def media_type_for_preview(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".htm", ".html"}:
        return "text/html; charset=utf-8"
    if suffix == ".css":
        return "text/css; charset=utf-8"
    if suffix in {".js", ".mjs"}:
        return "application/javascript; charset=utf-8"
    if suffix in {".json", ".map"}:
        return "application/json; charset=utf-8"
    if suffix == ".svg":
        return "image/svg+xml"
    if suffix in {".txt", ".md"}:
        return "text/plain; charset=utf-8"
    return "application/octet-stream"


def best_result_folder(*, project_dir: Path, run_id: str, run: dict[str, object], repository_path: str) -> Path:
    run_root = project_dir / "runs" / run_id if str(project_dir) else Path("")
    generated = run_root / "generated_repository" if str(run_root) else Path("generated_repository")
    candidates = [generated, *[Path(path) for path in result_folder_candidate_paths(run, repository_path)], run_root]
    for candidate in candidates:
        if str(candidate) and candidate.exists() and candidate.is_dir():
            return candidate
    for candidate in candidates:
        if str(candidate):
            return candidate
    return run_root


def result_folder_candidate_paths(run: dict[str, object], repository_path: str) -> list[str]:
    candidates: list[str] = []

    def add(value: object) -> None:
        path = str(value or "")
        if path and path not in candidates:
            candidates.append(path)

    runtime_state = run.get("runtime_state", {})
    runtime_repo = runtime_state.get("repository", {}) if isinstance(runtime_state, dict) else {}
    if isinstance(runtime_repo, dict):
        add(runtime_repo.get("path", ""))
        source = runtime_repo.get("source", {})
        if isinstance(source, dict):
            add(source.get("local_path", ""))

    project_brief = run.get("project_brief", {})
    brief_repo = project_brief.get("repository", {}) if isinstance(project_brief, dict) else {}
    if isinstance(brief_repo, dict):
        add(brief_repo.get("local_path", ""))

    delivery_report = run.get("delivery_report", {})
    workspace = delivery_report.get("workspace", {}) if isinstance(delivery_report, dict) else {}
    if isinstance(workspace, dict):
        add(workspace.get("execution_path", ""))
        add(workspace.get("source_path", ""))

    add(repository_path)
    return candidates


def has_reviewable_artifact(run: dict[str, object]) -> bool:
    artifact_report = run.get("artifact_report", {})
    if not isinstance(artifact_report, dict):
        return False
    return bool(artifact_report.get("artifact_files") or artifact_report.get("browser_verification"))


def github_pr_url(run: dict[str, object]) -> str:
    delivery = run.get("delivery_report", {})
    github = delivery.get("github", {}) if isinstance(delivery, dict) else {}
    runtime_state = run.get("runtime_state", {})
    runtime_github = runtime_state.get("github", {}) if isinstance(runtime_state, dict) else {}
    for source in (github, runtime_github):
        if isinstance(source, dict):
            value = str(source.get("pull_request_url", source.get("pr_url", "")) or "")
            if value and not value.startswith("dry-run://"):
                return value
    return ""


def latest_activity_timestamp(iso_values: list[str], paths: list[Path]) -> str:
    candidates = [value for value in iso_values if value]
    for path in paths:
        candidates.extend(path_activity_iso(path))
    parsed = [(parse_iso_timestamp(value), value) for value in candidates]
    parsed = [(dt, value) for dt, value in parsed if dt is not None]
    if not parsed:
        return ""
    parsed.sort(key=lambda item: item[0])
    return parsed[-1][0].astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def path_activity_iso(path: Path) -> list[str]:
    if not path.exists():
        return []
    paths = [path]
    if path.is_dir():
        paths.extend(child for child in path.rglob("*") if child.is_file())
    values: list[str] = []
    for candidate in paths:
        try:
            values.append(datetime.fromtimestamp(candidate.stat().st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z"))
        except OSError:
            continue
    return values


def parse_iso_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def seconds_since_iso(value: str) -> float:
    parsed = parse_iso_timestamp(value)
    if parsed is None:
        return 0.0
    return max(0.0, time.time() - parsed.timestamp())


def elapsed_seconds(started_at: str, ended_at: str) -> float:
    start = parse_iso_timestamp(started_at)
    end = parse_iso_timestamp(ended_at)
    if start is None:
        return 0.0
    if end is None:
        end = datetime.now(timezone.utc)
    return max(0.0, end.timestamp() - start.timestamp())


def is_under_any(path: Path, roots: list[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def open_folder_with_os(path: Path) -> None:
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    if sys_platform() == "darwin":
        subprocess.Popen(["open", str(path)])
        return
    subprocess.Popen(["xdg-open", str(path)])


def sys_platform() -> str:
    import sys

    return sys.platform


def unified_run_urls(project_id: str, run_id: str) -> dict[str, str]:
    return {
        "project": f"/projects/{project_id}",
        "run": f"/projects/{project_id}/runs/{run_id}",
        "job": f"/projects/{project_id}/runs/{run_id}/job",
        "status": f"/projects/{project_id}/runs/{run_id}/status",
        "events": f"/projects/{project_id}/runs/{run_id}/events",
        "events_stream": f"/projects/{project_id}/runs/{run_id}/events-stream",
        "delivery": f"/projects/{project_id}/runs/{run_id}/delivery",
        "artifacts": f"/projects/{project_id}/runs/{run_id}/artifacts",
    }


def safe_filename(filename: str) -> str:
    if not filename:
        raise ApiError(400, "invalid_filename", "Uploaded filename is required.")
    if filename != Path(filename).name or any(part in filename for part in ("/", "\\", "..")):
        raise ApiError(400, "invalid_filename", f"Unsafe uploaded filename: {filename}")
    return filename


def unique_upload_path(upload_dir: Path, filename: str) -> Path:
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    candidate = upload_dir / filename
    counter = 1
    while candidate.exists():
        candidate = upload_dir / f"{stem}-{counter}{suffix}"
        counter += 1
    return candidate


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def find_file_payload(brief: dict[str, object], file_id: str) -> dict[str, object] | None:
    for collection in ("documents", "attachments"):
        files = brief.get(collection, [])
        if not isinstance(files, list):
            continue
        for item in files:
            if isinstance(item, dict) and str(item.get("id", "")) == file_id:
                return item
    return None


def has_history_type(result: dict[str, object], event_type: str) -> bool:
    runtime_state = result.get("runtime_state", {})
    if not isinstance(runtime_state, dict):
        return False
    history = runtime_state.get("iteration_history", runtime_state.get("execution_history", []))
    if not isinstance(history, list):
        return False
    return any(isinstance(item, dict) and item.get("type") == event_type for item in history)


def build_one_line_run_payload(result: dict[str, object], *, project_id: str, run_id: str) -> dict[str, object]:
    artifacts = one_line_artifact_files(result)
    runtime_state = {
        "objective": str(result.get("project_brief", {}).get("objective", "")) if isinstance(result.get("project_brief"), dict) else "",
        "done": result.get("status") == "done",
        "task_graph": result.get("task_graph", {}),
        "evaluation": {
            "done": result.get("status") == "done",
            "final_gate_score": 0.95 if result.get("status") == "done" else 0.0,
            "reason": "One-line fallback artifact generated by local agent cluster.",
            "hard_failures": [],
            "required_changes": [],
        },
        "github": {
            "status": "recorded",
            "pull_request_url": "dry-run://one-line-fallback",
            "branch": "",
            "commit": "",
            "ci_status": "waived",
            "ci_details": [],
            "commands_run": [],
        },
        "execution_history": [
            {
                "type": "agent_event",
                "agent": event.get("agent", ""),
                "task_id": event.get("task_id", ""),
                "status": event.get("status", ""),
                "message": event.get("summary", ""),
            }
            for event in result.get("agent_events", [])
            if isinstance(event, dict)
        ],
        "blockers": [],
    }
    artifact_report = {
        "artifact_profile": {"name": "one_line_fallback", "confidence": "medium"},
        "artifact_files": artifacts,
        "static_verification": {"status": "passed" if artifacts else "skipped"},
        "browser_verification": {"status": "skipped"},
    }
    requirement_coverage = {
        "status": "passed",
        "coverage_score": 1.0,
        "entries": [],
        "missing_must_requirement_ids": [],
        "partial_must_requirement_ids": [],
    }
    delivery_report = build_one_line_delivery_report(
        status=str(result.get("status", "")),
        runtime_state=runtime_state,
        artifact_report=artifact_report,
        requirement_coverage=requirement_coverage,
    )
    return {
        "status": result.get("status", "failed"),
        "project_id": project_id,
        "run_id": run_id,
        "project_brief": result.get("project_brief", {}),
        "context_bundle": result.get("context_bundle", {}),
        "task_graph": result.get("task_graph", {}),
        "runtime_state": runtime_state,
        "artifact_report": artifact_report,
        "requirement_coverage": requirement_coverage,
        "delivery_report": delivery_report,
        "development_cycle": {
            "status": "passed" if result.get("status") == "done" else "failed",
            "cycle_model": "one_line_fallback_local_agent_cluster",
            "agent_events": result.get("agent_events", []),
        },
        "output_dir": result.get("output_dir", ""),
        "artifacts": artifacts,
        "validation_errors": result.get("validation_errors", []),
    }


def build_one_line_delivery_report(
    *,
    status: str,
    runtime_state: dict[str, object],
    artifact_report: dict[str, object],
    requirement_coverage: dict[str, object],
) -> dict[str, object]:
    score = runtime_state.get("evaluation", {}).get("final_gate_score", 0) if isinstance(runtime_state.get("evaluation"), dict) else 0
    return {
        "status": status,
        "ready_for_review": status == "done",
        "summary": "One-line fallback generated a reviewable local artifact." if status == "done" else "One-line fallback did not complete.",
        "final_gate": {
            "score": score,
            "reason": "One-line fallback artifact generated by local agent cluster.",
            "hard_failures": [],
            "required_changes": [],
        },
        "github": dict(runtime_state.get("github", {})) if isinstance(runtime_state.get("github"), dict) else {},
        "artifact": {
            "profile": "one_line_fallback",
            "static_status": artifact_report.get("static_verification", {}).get("status", "") if isinstance(artifact_report.get("static_verification"), dict) else "",
            "browser_status": "skipped",
            "artifact_files": list(artifact_report.get("artifact_files", [])) if isinstance(artifact_report.get("artifact_files"), list) else [],
        },
        "requirements": {
            "status": requirement_coverage.get("status", ""),
            "coverage_score": requirement_coverage.get("coverage_score", 0),
            "total": len(requirement_coverage.get("entries", [])) if isinstance(requirement_coverage.get("entries"), list) else 0,
            "missing_must_requirement_ids": [],
            "partial_must_requirement_ids": [],
        },
        "generated_ci": {},
        "blockers": [],
        "readiness_issues": [],
        "next_actions": [],
    }


def full_roadmap_delivery_report(result: dict[str, object]) -> dict[str, object]:
    final_audit = result.get("final_audit", {}) if isinstance(result.get("final_audit"), dict) else {}
    phase_records = result.get("phase_records", []) if isinstance(result.get("phase_records"), list) else []
    project_analysis = result.get("project_analysis", {}) if isinstance(result.get("project_analysis"), dict) else {}
    blockers = [str(item) for item in result.get("blockers", [])] if isinstance(result.get("blockers"), list) else []
    status = str(result.get("status", "blocked") or "blocked")
    ready = status == "done" and bool(final_audit.get("ready_for_final_handoff", False))
    return {
        "status": status,
        "ready_for_review": ready,
        "summary": (
            "Full roadmap execution completed every required phase."
            if ready
            else "Full roadmap execution stopped before final handoff."
        ),
        "final_gate": {
            "score": 0.95 if ready else 0.0,
            "reason": "Full roadmap final audit passed." if ready else "Full roadmap final audit did not pass.",
            "hard_failures": blockers,
            "required_changes": [],
        },
        "roadmap": {
            "phase_total": len(phase_records),
            "phase_completed": sum(1 for item in phase_records if isinstance(item, dict) and item.get("status") == "done"),
            "final_audit": final_audit,
        },
        "project_analysis": {
            "start_decision": str(project_analysis.get("start_decision", "")),
            "confidence": project_analysis.get("confidence", 0),
            "valid_phase_count": len(project_analysis.get("valid_phases", [])) if isinstance(project_analysis.get("valid_phases"), list) else 0,
            "ignored_candidate_count": len(project_analysis.get("ignored_phase_candidates", [])) if isinstance(project_analysis.get("ignored_phase_candidates"), list) else 0,
            "ready_to_start": bool(project_analysis.get("ready_to_start", False)),
        },
        "github": {},
        "artifact": {"profile": "full_roadmap", "artifact_files": []},
        "requirements": {
            "status": "passed" if ready else "blocked",
            "coverage_score": 1.0 if ready else 0.0,
            "missing_must_requirement_ids": [],
            "partial_must_requirement_ids": [],
        },
        "generated_ci": {},
        "blockers": blockers,
        "readiness_issues": blockers,
        "next_actions": [] if ready else blockers,
    }


def full_roadmap_runtime_state(result: dict[str, object]) -> dict[str, object]:
    phase_records = result.get("phase_records", []) if isinstance(result.get("phase_records"), list) else []
    blockers = [str(item) for item in result.get("blockers", [])] if isinstance(result.get("blockers"), list) else []
    done = str(result.get("status", "")) == "done"
    project_analysis = result.get("project_analysis", {}) if isinstance(result.get("project_analysis"), dict) else {}
    return {
        "objective": str(result.get("roadmap", {}).get("root_objective", "")) if isinstance(result.get("roadmap"), dict) else "",
        "done": done,
        "blockers": blockers,
        "evaluation": {
            "done": done,
            "final_gate_score": 0.95 if done else 0.0,
            "reason": "Full roadmap final audit passed." if done else "Full roadmap blocked before final handoff.",
            "hard_failures": blockers,
            "required_changes": [],
        },
        "task_graph": full_roadmap_task_graph(result),
        "repository": {"artifact_profile": "full_roadmap"},
        "project_analysis": {
            "start_decision": str(project_analysis.get("start_decision", "")),
            "confidence": project_analysis.get("confidence", 0),
            "ready_to_start": bool(project_analysis.get("ready_to_start", False)),
        },
        "execution_history": [
            {
                "type": "roadmap_phase",
                "phase_id": str(item.get("phase_id", "")),
                "status": str(item.get("status", "")),
                "summary": str(item.get("title", "")),
            }
            for item in phase_records
            if isinstance(item, dict)
        ],
    }


def full_roadmap_task_graph(result: dict[str, object]) -> dict[str, object]:
    phase_records = result.get("phase_records", []) if isinstance(result.get("phase_records"), list) else []
    nodes = []
    dependencies = []
    previous_id = ""
    for index, item in enumerate(phase_records, start=1):
        if not isinstance(item, dict):
            continue
        node_id = str(item.get("phase_id") or f"phase_{index:03d}")
        nodes.append(
            {
                "id": node_id,
                "title": str(item.get("title", node_id)),
                "type": "roadmap_phase",
                "assigned_agent": "orchestrator",
                "status": "completed" if item.get("status") == "done" else "blocked",
                "dependencies": [previous_id] if previous_id else [],
                "completion_criteria": ["Phase promotion gate passes."],
                "evidence": [item.get("promotion", {})],
            }
        )
        if previous_id:
            dependencies.append({"source": previous_id, "target": node_id, "type": "phase_sequence"})
        previous_id = node_id
    return {
        "graph_id": "full-roadmap-execution",
        "version": 1,
        "nodes": nodes,
        "dependencies": dependencies,
    }


def full_roadmap_requirement_coverage(result: dict[str, object]) -> dict[str, object]:
    phase_records = result.get("phase_records", []) if isinstance(result.get("phase_records"), list) else []
    entries = []
    for item in phase_records:
        if not isinstance(item, dict):
            continue
        entries.append(
            {
                "requirement_id": str(item.get("phase_id", "")),
                "text": str(item.get("title", "")),
                "priority": "must",
                "coverage_status": "covered" if item.get("status") == "done" else "missing",
                "planned_task_ids": [str(item.get("phase_id", ""))],
                "implementation_files": [],
                "verification_evidence": ["Full-roadmap phase promotion gate."],
            }
        )
    missing = [entry["requirement_id"] for entry in entries if entry["coverage_status"] != "covered"]
    return {
        "status": "passed" if not missing else "failed",
        "coverage_score": 1.0 if not missing else 0.0,
        "entries": entries,
        "missing_must_requirement_ids": missing,
        "partial_must_requirement_ids": [],
    }


def roadmap_progress_for_run(run: dict[str, object]) -> dict[str, object]:
    roadmap = run.get("roadmap", {}) if isinstance(run.get("roadmap"), dict) else {}
    phases = roadmap.get("phases", []) if isinstance(roadmap.get("phases"), list) else []
    phase_records = run.get("phase_records", []) if isinstance(run.get("phase_records"), list) else []
    record_by_id = {
        str(item.get("phase_id", "")): item
        for item in phase_records
        if isinstance(item, dict)
    }
    items: list[dict[str, object]] = []
    for index, phase in enumerate(phases, start=1):
        if not isinstance(phase, dict):
            continue
        phase_id = str(phase.get("phase_id", f"phase_{index:03d}"))
        record = record_by_id.get(phase_id, {})
        status = str(phase.get("status") or record.get("status") or "pending")
        if status == "done":
            status = "completed"
        items.append(
            {
                "phase_id": phase_id,
                "title": str(phase.get("title", phase_id)),
                "status": status,
                "phase_type": str(phase.get("phase_type", "")),
                "record_status": str(record.get("status", "")) if isinstance(record, dict) else "",
            }
        )
    total = len(items)
    completed = sum(1 for item in items if item["status"] in {"completed", "skipped"})
    blocked = [item for item in items if item["status"] == "blocked"]
    current = next((item for item in items if item["status"] in {"running", "blocked", "pending"}), None)
    return {
        "enabled": bool(items),
        "total": total,
        "completed": completed,
        "blocked": len(blocked),
        "progress_percent": int(round((completed / total) * 100)) if total else 0,
        "current_phase": current or {},
        "phases": items,
    }


def one_line_artifact_files(result: dict[str, object]) -> list[str]:
    output_dir = Path(str(result.get("output_dir", ""))).resolve()
    artifact_files: list[str] = []
    for value in result.get("artifacts", []):
        raw = Path(str(value))
        candidate = raw if raw.is_absolute() else (Path.cwd() / raw)
        try:
            artifact_files.append(candidate.resolve().relative_to(output_dir).as_posix())
        except (OSError, ValueError):
            artifact_files.append(str(value))
    return artifact_files


def comparison_source_run_id(run: dict[str, object]) -> str:
    feedback = run.get("feedback_reopen", {})
    if isinstance(feedback, dict):
        source_run_id = str(feedback.get("source_run_id", "") or "")
        if source_run_id:
            return source_run_id
    recovery = run.get("recovery", {})
    if isinstance(recovery, dict):
        checkpoint = recovery.get("checkpoint", {})
        if isinstance(checkpoint, dict):
            source_run_id = str(checkpoint.get("source_run_id", "") or "")
            if source_run_id:
                return source_run_id
    return ""
