"""GitHub source normalization for project intake."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from .models import RepositorySource, Visibility

_SSH_PATTERN = re.compile(r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$")


def parse_github_source(
    url: str,
    *,
    project_id: str,
    target_branch: str = "main",
    base_branch: str = "",
    visibility: Visibility = "public",
    local_path: str = "",
) -> RepositorySource | None:
    """Parse a GitHub URL without performing network access."""

    owner_name = parse_github_owner_repo(url)
    if owner_name is None:
        return None

    owner, repo_name = owner_name
    normalized = normalize_github_url(owner, repo_name)
    auth_required = visibility == "private"
    return RepositorySource(
        provider="github",
        url=normalized,
        owner=owner,
        name=repo_name,
        target_branch=target_branch or "main",
        base_branch=base_branch,
        local_path=local_path or f".alchemy/projects/{project_id}/repo",
        visibility=visibility,
        gh_auth_required=auth_required,
        access_status="unchecked",
    )


def parse_github_owner_repo(url: str) -> tuple[str, str] | None:
    candidate = url.strip()
    if not candidate:
        return None

    ssh_match = _SSH_PATTERN.match(candidate)
    if ssh_match:
        return ssh_match.group("owner"), strip_git_suffix(ssh_match.group("repo"))

    parsed = urlparse(candidate)
    host = parsed.netloc.lower()
    if "@" in host:
        host = host.rsplit("@", 1)[1]
    if parsed.scheme in {"http", "https", "ssh"} and host == "github.com":
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and strip_git_suffix(parts[1]):
            return parts[0], strip_git_suffix(parts[1])

    if candidate.startswith("github.com/"):
        parts = candidate.split("/")
        if len(parts) >= 3 and strip_git_suffix(parts[2]):
            return parts[1], strip_git_suffix(parts[2])

    return None


def strip_git_suffix(repo_name: str) -> str:
    if repo_name.endswith(".git"):
        return repo_name[:-4]
    return repo_name


def normalize_github_url(owner: str, repo_name: str) -> str:
    return f"https://github.com/{owner}/{strip_git_suffix(repo_name)}"
