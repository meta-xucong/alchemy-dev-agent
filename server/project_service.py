"""Persistent project service for the local API runtime."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autodev import DocumentRunPipeline
from autodev.real_env_check import RealEnvironmentCheck
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

    def __init__(self, storage_root: str | Path = ".alchemy/server") -> None:
        self.storage_root = Path(storage_root)
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
        project_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(project_dir / "project.json", record.to_dict())
        self._write_json(project_dir / "brief.json", brief.to_dict())
        return {
            "project": record.to_dict(),
            "brief": brief.to_dict(),
        }

    def check_environment(self, payload: dict[str, Any] | None = None) -> dict[str, object]:
        payload = payload or {}
        codex_executable = str(payload.get("codex_executable", "codex") or "codex")
        output_dir = payload.get("output_dir")
        if output_dir:
            output_path = Path(str(output_dir))
        else:
            output_path = self.storage_root / "environment"
        report = RealEnvironmentCheck().run(output_dir=output_path, codex_executable=codex_executable)
        return report.to_dict()

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

    def add_files(self, project_id: str, payload: dict[str, Any]) -> dict[str, object]:
        record = self.load_project(project_id)
        normalized = normalize_project_payload(payload)
        merged = record.to_dict()
        merged["documents"] = dedupe([*record.documents, *normalized["documents"]])
        merged["attachments"] = dedupe([*record.attachments, *normalized["attachments"]])
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

    def get_run_job(self, project_id: str, run_id: str) -> dict[str, object]:
        path = self.project_dir(project_id) / "runs" / run_id / "job.json"
        if not path.exists():
            raise ApiError(404, "run_not_found", f"Run job not found: {run_id}")
        return self.job_store(project_id).load(run_id).to_dict()

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
            resumed = self.start_run(project_id, run_payload)
            store.append_event(job, "resume_started", "api", f"Started resumed run {resumed['run_id']} from {run_id}.")
            self._update_project_status(record, "running")
            return {
                "project_id": project_id,
                "run_id": run_id,
                "job": job.to_dict(),
                "resumed_run_id": resumed["run_id"],
                "resumed_job": resumed["job"],
            }
        return {"project_id": project_id, "run_id": run_id, "job": job.to_dict()}

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
        run = self.get_run(project_id, latest)
        return {
            "project_id": project_id,
            "latest_run_id": latest,
            "status": run.get("status"),
            "runtime_state": run.get("runtime_state", {}),
            "preflight": run.get("preflight", {}),
            "output_dir": run.get("output_dir", ""),
        }

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
        result = DocumentRunPipeline().run(
            objective=record.objective,
            documents=record.documents,
            attachments=record.attachments,
            repository_url=record.repository_url,
            repository_path=record.repository_path or None,
            output_dir=output_dir,
            max_iterations=int(run_payload.get("max_iterations", 50)),
            prepare_repository=bool(run_payload.get("prepare_repository", False)),
            real_codex=bool(run_payload.get("real_codex", False)),
            real_github=bool(run_payload.get("real_github", False)),
            codex_executable=str(run_payload.get("codex_executable", "codex")),
            max_worker_seconds=int(run_payload.get("max_worker_seconds", 1800)),
            isolate_real_run=bool(run_payload.get("isolate_real_run", True)),
            keep_worktree=bool(run_payload.get("keep_worktree", True)),
            worktree_branch_prefix=str(run_payload.get("worktree_branch_prefix", "agent/alchemy-real-run")),
            resume_from=self._resume_source_path(record.project_id, run_payload),
            resume_tasks=[str(task_id) for task_id in run_payload.get("resume_tasks", [])],
            controller=controller,
        )
        result_payload = result.to_dict()
        result_payload["run_id"] = run_id
        result_payload["project_id"] = record.project_id
        self._write_json(output_dir / "run.json", result_payload)
        return result_payload

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

    def _build_brief(self, payload: dict[str, Any]) -> ProjectBrief:
        project_id_override = str(payload.get("project_id", ""))
        normalized = normalize_project_payload(payload)
        brief = ProjectBriefBuilder().build(
            objective=str(normalized["objective"]),
            documents=list(normalized["documents"]),
            attachments=list(normalized["attachments"]),
            primary_input_mode=normalized["primary_input_mode"],
            repository_url=str(normalized["repository_url"]),
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
        updated = ProjectRecord.from_dict(record.to_dict())
        updated.status = status
        updated.updated_at = utc_now_iso()
        self._write_json(self.project_dir(updated.project_id) / "project.json", updated.to_dict())
        return updated

    def _read_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
        if role == "primary_requirements" or required and not documents:
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


def project_status_for_run(run_status: str) -> str:
    if run_status == "done":
        return "done"
    if run_status == "blocked":
        return "blocked"
    return "running"


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


def has_history_type(result: dict[str, object], event_type: str) -> bool:
    runtime_state = result.get("runtime_state", {})
    if not isinstance(runtime_state, dict):
        return False
    history = runtime_state.get("iteration_history", runtime_state.get("execution_history", []))
    if not isinstance(history, list):
        return False
    return any(isinstance(item, dict) and item.get("type") == event_type for item in history)
