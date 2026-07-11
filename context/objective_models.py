"""V2.187 objective contract data structures."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal

from runtime.models import utc_now_iso

RequirementClass = Literal[
    "must_implement",
    "must_preserve",
    "must_absent_runtime",
    "must_absent_source",
    "must_absent_fresh_schema",
    "must_absent_public_contract",
    "must_reference",
    "must_verify",
    "must_decide",
    "may_reframe",
    "may_waive",
]


@dataclass(slots=True)
class RequirementSource:
    document: str
    section: str = ""
    line_start: int = 0
    line_end: int = 0
    quote_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "document": self.document,
            "section": self.section,
            "line_start": self.line_start,
            "line_end": self.line_end or self.line_start,
            "quote_hash": self.quote_hash,
        }


@dataclass(slots=True)
class ObjectiveRequirement:
    id: str
    source: RequirementSource
    statement: str
    strength: str
    class_name: RequirementClass
    domain: str = ""
    subjects: list[str] = field(default_factory=list)
    scope: list[str] = field(default_factory=list)
    allowed_exceptions: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    conflicts_with: list[str] = field(default_factory=list)
    proof_obligations: list[str] = field(default_factory=list)
    status: str = "unproven"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source.to_dict(),
            "statement": self.statement,
            "strength": self.strength,
            "class": self.class_name,
            "domain": self.domain,
            "subjects": list(self.subjects),
            "scope": list(self.scope),
            "allowed_exceptions": list(self.allowed_exceptions),
            "depends_on": list(self.depends_on),
            "conflicts_with": list(self.conflicts_with),
            "proof_obligations": list(self.proof_obligations),
            "status": self.status,
        }


@dataclass(slots=True)
class ObjectiveContract:
    objective: str
    requirements: list[ObjectiveRequirement]
    source_documents: list[str] = field(default_factory=list)
    schema_version: str = "2.187"
    revision: str = ""
    validation_errors: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "objective": self.objective,
            "revision": self.revision or self.compute_revision(),
            "source_documents": list(self.source_documents),
            "requirements": [requirement.to_dict() for requirement in self.requirements],
            "validation_errors": list(self.validation_errors),
            "created_at": self.created_at,
        }
        return payload

    def compute_revision(self) -> str:
        canonical = {
            "objective": self.objective,
            "requirements": [requirement.to_dict() for requirement in self.requirements],
            "source_documents": list(self.source_documents),
        }
        encoded = json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()
