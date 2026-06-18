# V2.16 Real-Run Worktree Lifecycle

## Purpose

V2.16 makes isolated git worktrees a first-class runtime boundary for real
Codex execution.

The goal is to prevent the source repository from being the direct mutation
target when `real_codex=true`. The source repository remains the trusted input;
the execution repository is a short-lived or retained worktree created from
`HEAD`.

## Lifecycle

For document-driven real runs, the runtime now follows this sequence:

1. Build the initial `ProjectBrief` from objective, documents, attachments, and
   repository metadata.
2. Run real-execution preflight against the source repository and requested
   tools.
3. If `real_codex=true` and isolation is enabled, create an isolated git
   worktree under the run output directory.
4. Rebuild `ContextBundle`, `TaskGraph`, `RuntimeState`, and worker packages
   against the isolated worktree path.
5. Execute Codex workers inside the worktree.
6. Persist the worktree session report in `document_run_report.json`.
7. Keep the worktree by default for audit, or remove it when cleanup is
   explicitly requested.

Dry-run execution does not create a worktree.

## Source Repository Requirements

The source path for an isolated real run must be:

- an existing directory
- a git repository root
- clean according to `git status --porcelain`

Dirty source repositories are blocked before worker execution. This prevents a
dangerous mismatch where the user expects uncommitted local changes to be
included, but `git worktree add` creates the execution copy from `HEAD`.

The run output directory is excluded from this dirty-check when it lives inside
the source repository.

## Runtime Contract

`DocumentRunResult` now includes:

```json
{
  "workspace": {
    "enabled": true,
    "status": "ready",
    "source_path": "/path/to/source-repo",
    "execution_path": "/path/to/run/workspaces/real_run_worktree_...",
    "worktree_path": "/path/to/run/workspaces/real_run_worktree_...",
    "branch": "agent/alchemy-real-run-...",
    "keep": true,
    "blockers": [],
    "warnings": [],
    "commands_run": []
  }
}
```

`RuntimeState.repository.path`, worker package `repository_path`, and
orchestrator `repository_path` all point to `workspace.execution_path` when the
worktree is ready.

## CLI Flags

Real Codex runs use isolated worktrees by default:

```bash
python -m autodev.document_run \
  --objective "Implement feature" \
  --document feature_spec.md \
  --repository-path /path/to/repo \
  --real-codex \
  --codex-executable /path/to/codex
```

Optional controls:

```text
--no-isolated-worktree   Run directly in the repository path.
--cleanup-worktree       Remove the worktree and branch after the run.
--worktree-branch-prefix Branch prefix for isolated real runs.
```

The API accepts equivalent run payload fields:

```json
{
  "real_codex": true,
  "isolate_real_run": true,
  "keep_worktree": true,
  "worktree_branch_prefix": "agent/alchemy-real-run"
}
```

## Safety Boundary

Worktree isolation complements, but does not replace, the V2.15 file-boundary
auditor:

- Worktree lifecycle protects the source repository.
- `allowed_files` auditing protects each task boundary inside the worktree.
- Timeout and out-of-scope rollback still operate inside the execution
  worktree.

## Remaining Gap

V2.16 does not yet implement full resumable task execution after a real worker
failure or timeout. The retained worktree and persisted state make that path
possible, but V2.17 should add explicit resume commands and task retry recovery
for real worker runs.
