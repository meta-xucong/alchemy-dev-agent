# V2.11 Private GitHub Source Adapter

## Purpose

V2.11 adds an optional private GitHub source adapter that uses local GitHub CLI authentication.

Public repositories remain the default path and still use token-free `git clone` / `git fetch`.

## Runtime

New module:

```text
intake/private_github_runtime.py
```

The adapter:

- Runs the V2.10 `gh` auth preflight first.
- Clones private repositories with `gh repo clone`.
- Updates existing private checkouts with `git fetch` and deterministic `git checkout -B`.
- Records commands, blockers, auth status, and repository source state.
- Does not read or store GitHub tokens.

## Clone Command

```text
gh repo clone OWNER/REPO <local_path> -- --branch <branch> --single-branch
```

## Existing Checkout Update

```text
git fetch origin <branch>
git checkout -B <branch> origin/<branch>
```

## Integration

`autodev.document_run --prepare-repository --repository-visibility private` now uses the private adapter.

The local API `POST /projects/{project_id}/github/inspect` supports:

```json
{
  "prepare": true
}
```

When the project repository is private, that path uses the private adapter. When it is public, it uses the public adapter.

## Boundary

This adapter enables source preparation for private repositories, but it does not yet prove end-to-end private repository delivery. Real-world validation still needs:

- a representative private repository
- local `gh` login with access
- controlled Codex worker execution
- GitHub PR/CI verification
