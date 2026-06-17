"""Document-driven project intake runtime."""

from .document_loader import DocumentLoader
from .github_source import parse_github_source
from .models import Blocker, ProjectBrief, ProjectFile, RepositorySource
from .schema_validation import validate_project_brief_contract

__all__ = [
    "Blocker",
    "DocumentLoader",
    "ProjectBrief",
    "ProjectBriefBuilder",
    "ProjectFile",
    "RepositorySource",
    "parse_github_source",
    "validate_project_brief_contract",
]


def __getattr__(name: str):
    if name == "ProjectBriefBuilder":
        from .project_brief import ProjectBriefBuilder

        return ProjectBriefBuilder
    raise AttributeError(f"module 'intake' has no attribute {name!r}")
