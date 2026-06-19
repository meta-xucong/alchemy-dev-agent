"""Data structures for v2 project intake."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

InputMode = Literal["document_driven", "one_line_fallback"]
FileRole = Literal[
    "primary_requirements",
    "supplemental",
    "api_spec",
    "database_schema",
    "design",
    "test_plan",
    "feedback",
    "reference_code",
    "data_sample",
    "other",
]
ParseStatus = Literal["pending", "parsed", "unsupported", "failed"]
Visibility = Literal["public", "private", "unknown"]
AccessStatus = Literal["unchecked", "available", "auth_required", "access_denied", "not_found", "failed"]
BlockerSeverity = Literal["warning", "hard"]
SourceConfidence = Literal["high", "medium", "low"]


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class Blocker:
    code: str
    message: str
    severity: BlockerSeverity = "hard"

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass(slots=True)
class ProjectFile:
    id: str
    name: str
    path: str
    media_type: str
    role: FileRole
    required: bool
    content_hash: str
    parse_status: ParseStatus
    summary: str = ""

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "media_type": self.media_type,
            "role": self.role,
            "required": self.required,
            "content_hash": self.content_hash,
            "parse_status": self.parse_status,
        }
        if self.summary:
            payload["summary"] = self.summary
        return payload


RepositoryProvider = Literal["github", "local"]


@dataclass(slots=True)
class RepositorySource:
    provider: RepositoryProvider
    url: str
    owner: str
    name: str
    target_branch: str
    local_path: str
    visibility: Visibility
    gh_auth_required: bool
    access_status: AccessStatus
    base_branch: str = ""

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "provider": self.provider,
            "url": self.url,
            "owner": self.owner,
            "name": self.name,
            "target_branch": self.target_branch,
            "local_path": self.local_path,
            "visibility": self.visibility,
            "gh_auth_required": self.gh_auth_required,
            "access_status": self.access_status,
        }
        if self.base_branch:
            payload["base_branch"] = self.base_branch
        return payload


@dataclass(slots=True)
class ProjectBrief:
    project_id: str
    objective: str
    primary_input_mode: InputMode
    documents: list[ProjectFile] = field(default_factory=list)
    attachments: list[ProjectFile] = field(default_factory=list)
    repository: RepositorySource | None = None
    constraints: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    generated_from_one_liner: bool = False
    blockers: list[Blocker] = field(default_factory=list)
    source_confidence: SourceConfidence = "high"
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "2.0",
            "project_id": self.project_id,
            "objective": self.objective,
            "primary_input_mode": self.primary_input_mode,
            "documents": [document.to_dict() for document in self.documents],
            "attachments": [attachment.to_dict() for attachment in self.attachments],
            "repository": self.repository.to_dict() if self.repository else None,
            "constraints": list(self.constraints),
            "acceptance_criteria": list(self.acceptance_criteria),
            "generated_from_one_liner": self.generated_from_one_liner,
            "source_confidence": self.source_confidence,
            "blockers": [blocker.to_dict() for blocker in self.blockers],
            "created_at": self.created_at,
        }
