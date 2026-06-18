# V2.15 Real Codex Worker Hardening

## Purpose

V2.15 hardens real Codex worker execution after controlled validation against
the `alchemy-dev-agent` repository showed that a live worker can produce useful
changes but may also modify files outside the intended task boundary.

The goal is to keep real Codex execution enabled while making task-local
boundaries machine-enforced instead of prompt-only.

## Validation Finding

The V2.15 controlled run used:

- repository: `https://github.com/meta-xucong/alchemy-dev-agent`
- mode: `real_codex=true`
- GitHub delivery: `real_github=false`
- execution target: isolated git worktree under `.alchemy/`

Observed behavior:

- Codex CLI launched and wrote the requested smoke document.
- No GitHub push or pull request was created.
- The overall document-run did not reach DONE within the bounded runtime.
- The worker modified files outside the task's intended scope.

Conclusion:

Real worker invocation works, but reliable autonomous delivery requires strict
post-execution diff auditing.

## Boundary Contract

Each real worker package now includes:

```json
{
  "relevant_files": [],
  "allowed_files": [],
  "constraints": [
    "Do not edit files outside allowed_files.",
    "If allowed_files is empty, do not edit repository files."
  ]
}
```

Rules:

- `allowed_files` is the only write allowlist for the task.
- Architecture, review, and test tasks are read-only by default.
- Implementation/debug/documentation/integration tasks may edit only their
  `relevant_files`.
- If the task needs edits but `allowed_files` is empty, the worker should return
  `partial` or `blocked`.

## Machine Enforcement

Prompt instructions are not treated as sufficient.

For real Codex runs, the worker adapter:

1. Captures `git status --porcelain` before worker dispatch.
2. Runs `codex exec --json --sandbox workspace-write`.
3. Captures `git status --porcelain` after completion.
4. Computes files newly changed by the task.
5. Compares changed files against `allowed_files`.
6. Rolls back out-of-scope files.
7. Marks the task `failed` with boundary evidence.

On timeout, task-local changed files are rolled back and the task is marked
`failed`.

## Rollback Scope

Rollback is path-scoped:

- Tracked out-of-scope files are restored through `git checkout -- <paths>`.
- Untracked out-of-scope files are removed only when their resolved path stays
  inside the repository root.

V2.16 adds first-class isolated worktree lifecycle management so real Codex
document-runs no longer need to target the source repository directly.

## Remaining Gap

V2.15 prevents uncontrolled file drift, and V2.16 protects the source
repository through isolated worktree execution. The next required improvements
are:

- resumable real worker runs
- smaller task packages for real Codex
- real test command execution and Debug Agent repair loops
- final PR/CI validation under `real_github=true`
