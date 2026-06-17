# V2.3 Public GitHub Source Runtime

## Purpose

V2.3 makes public GitHub repositories the primary repository source path.

The runtime prepares a linked public repository before context indexing:

```text
RepositorySource
  -> GitHubSourceRuntime
  -> local git checkout
  -> RepositoryIndexer
  -> ContextBundle
```

This closes the gap between URL-only repository metadata and the V2.2 local repository context runtime.

## Supported Path

The supported path is:

- Public GitHub repository URL.
- Target branch, defaulting to `main`.
- Local checkout path, defaulting to `.alchemy/projects/{project_id}/repo`.
- Clone if the local checkout path does not exist.
- Fetch and deterministic checkout if the local checkout path already contains a git repository.

Public repositories do not require `gh` login, tokens, or application-managed credentials.

## Runtime Contract

Input is a `RepositorySource` object:

```json
{
  "provider": "github",
  "url": "https://github.com/example/saas-dashboard",
  "owner": "example",
  "name": "saas-dashboard",
  "target_branch": "main",
  "local_path": ".alchemy/projects/proj_workspace_support/repo",
  "visibility": "public",
  "gh_auth_required": false,
  "access_status": "unchecked"
}
```

Output is a source preparation result:

```json
{
  "status": "available",
  "repository": {
    "provider": "github",
    "url": "https://github.com/example/saas-dashboard",
    "owner": "example",
    "name": "saas-dashboard",
    "target_branch": "main",
    "local_path": ".alchemy/projects/proj_workspace_support/repo",
    "visibility": "public",
    "gh_auth_required": false,
    "access_status": "available"
  },
  "commands_run": [
    ["git", "clone", "--branch", "main", "--single-branch", "https://github.com/example/saas-dashboard", ".alchemy/projects/proj_workspace_support/repo"]
  ],
  "blockers": [],
  "summary": "Repository cloned for public source intake."
}
```

If a checkout already exists, the runtime runs:

```text
git fetch origin <target_branch>
git checkout -B <target_branch> origin/<target_branch>
```

The `checkout -B` form is intentional. It makes repeated source preparation deterministic and aligns the local branch to the selected remote branch before repository indexing.

## Blockers

The runtime returns structured blockers for:

- `private_repository_not_supported_in_public_runtime`
- `repository_path_not_empty`
- `repository_clone_failed`
- `repository_fetch_failed`
- `repository_checkout_failed`
- `invalid_github_url`

Private repository input is not treated as the default path. When `visibility=private` or `gh_auth_required=true`, the public runtime returns an explicit blocker and does not ask the user for a token.

## CLI Usage

```bash
python -m intake.github_runtime \
  --repository https://github.com/example/saas-dashboard \
  --project-id proj_workspace_support \
  --target-branch main
```

The command exits with `0` when the repository is available and `1` when source preparation fails or is blocked.

## Relationship To V2.2

V2.2 indexes a local repository checkout. V2.3 prepares that checkout from a public GitHub repository URL.

The combined flow is:

```text
ProjectBrief.repository.url
  -> public clone/fetch
  -> ProjectBrief.repository.local_path
  -> repository index
  -> ContextBundle.repository_map
  -> ContextBundle.test_profile
```

## Non-Goals

V2.3 does not implement:

- Private GitHub clone/fetch through `gh`.
- GitHub token storage.
- GitHub App installation flow.
- CI log ingestion.
- Pull request creation.
- Deep semantic code summarization.

Those belong to later authenticated source, GitHub delivery, and planning stages.
