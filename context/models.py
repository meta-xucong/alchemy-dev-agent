"""Data structures for v2 context bundles."""

from __future__ import annotations

from dataclasses import dataclass, field

from intake.models import Blocker, utc_now_iso


@dataclass(slots=True)
class DocumentSummary:
    id: str
    path: str
    role: str
    content_hash: str
    parse_status: str
    summary: str
    key_requirements: list[str] = field(default_factory=list)
    confidence: str = "medium"

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "path": self.path,
            "role": self.role,
            "content_hash": self.content_hash,
            "parse_status": self.parse_status,
            "summary": self.summary,
            "key_requirements": list(self.key_requirements),
            "confidence": self.confidence,
        }


@dataclass(slots=True)
class RepositoryFile:
    path: str
    kind: str
    language: str = ""
    size_bytes: int = 0

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "path": self.path,
            "kind": self.kind,
        }
        if self.language:
            payload["language"] = self.language
        if self.size_bytes:
            payload["size_bytes"] = self.size_bytes
        return payload


@dataclass(slots=True)
class Requirement:
    id: str
    source_document_id: str
    text: str
    priority: str = "must"
    acceptance_criteria: list[str] = field(default_factory=list)
    related_files: list[str] = field(default_factory=list)
    planned_task_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "source_document_id": self.source_document_id,
            "text": self.text,
            "priority": self.priority,
            "acceptance_criteria": list(self.acceptance_criteria),
            "related_files": list(self.related_files),
            "planned_task_ids": list(self.planned_task_ids),
        }


@dataclass(slots=True)
class Risk:
    id: str
    type: str
    severity: str
    description: str
    mitigation: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "type": self.type,
            "severity": self.severity,
            "description": self.description,
            "mitigation": self.mitigation,
        }


@dataclass(slots=True)
class ContextBundle:
    project_id: str
    objective: str
    documents: list[DocumentSummary] = field(default_factory=list)
    repository_files: list[RepositoryFile] = field(default_factory=list)
    package_files: list[str] = field(default_factory=list)
    ci_files: list[str] = field(default_factory=list)
    requirements: list[Requirement] = field(default_factory=list)
    package_managers: list[str] = field(default_factory=list)
    test_commands: list[str] = field(default_factory=list)
    build_commands: list[str] = field(default_factory=list)
    lint_commands: list[str] = field(default_factory=list)
    coverage_unknown: bool = True
    risks: list[Risk] = field(default_factory=list)
    blockers: list[Blocker] = field(default_factory=list)
    root_path: str = ""
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "2.0",
            "project_id": self.project_id,
            "objective": self.objective,
            "document_index": {
                "documents": [document.to_dict() for document in self.documents],
            },
            "repository_map": {
                "root_path": self.root_path,
                "files": [repository_file.to_dict() for repository_file in self.repository_files],
                "package_files": list(self.package_files),
                "ci_files": list(self.ci_files),
            },
            "requirement_map": {
                "requirements": [requirement.to_dict() for requirement in self.requirements],
            },
            "test_profile": {
                "package_managers": list(self.package_managers),
                "test_commands": list(self.test_commands),
                "build_commands": list(self.build_commands),
                "lint_commands": list(self.lint_commands),
                "ci_files": list(self.ci_files),
                "coverage_unknown": self.coverage_unknown,
            },
            "risk_profile": {
                "risks": [risk.to_dict() for risk in self.risks],
            },
            "blockers": [blocker.to_dict() for blocker in self.blockers],
            "created_at": self.created_at,
        }
