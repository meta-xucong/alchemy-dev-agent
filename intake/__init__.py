"""Document-driven project intake runtime."""

from .document_loader import DocumentLoader
from .github_source import parse_github_source
from .models import Blocker, ProjectBrief, ProjectFile, RepositorySource
from .schema_validation import validate_project_brief_contract

__all__ = [
    "Blocker",
    "DocumentLoader",
    "GitHubSourceResult",
    "GitHubSourceRuntime",
    "GitHubAuthPreflight",
    "GitHubAuthResult",
    "ProjectBrief",
    "ProjectBriefBuilder",
    "ProjectFile",
    "PrivateGitHubSourceResult",
    "PrivateGitHubSourceRuntime",
    "RepositorySource",
    "parse_github_source",
    "validate_project_brief_contract",
]


def __getattr__(name: str):
    if name == "ProjectBriefBuilder":
        from .project_brief import ProjectBriefBuilder

        return ProjectBriefBuilder
    if name in {"GitHubSourceResult", "GitHubSourceRuntime"}:
        from .github_runtime import GitHubSourceResult, GitHubSourceRuntime

        exports = {
            "GitHubSourceResult": GitHubSourceResult,
            "GitHubSourceRuntime": GitHubSourceRuntime,
        }
        return exports[name]
    if name in {"GitHubAuthPreflight", "GitHubAuthResult"}:
        from .gh_auth import GitHubAuthPreflight, GitHubAuthResult

        exports = {
            "GitHubAuthPreflight": GitHubAuthPreflight,
            "GitHubAuthResult": GitHubAuthResult,
        }
        return exports[name]
    if name in {"PrivateGitHubSourceResult", "PrivateGitHubSourceRuntime"}:
        from .private_github_runtime import PrivateGitHubSourceResult, PrivateGitHubSourceRuntime

        exports = {
            "PrivateGitHubSourceResult": PrivateGitHubSourceResult,
            "PrivateGitHubSourceRuntime": PrivateGitHubSourceRuntime,
        }
        return exports[name]
    raise AttributeError(f"module 'intake' has no attribute {name!r}")
