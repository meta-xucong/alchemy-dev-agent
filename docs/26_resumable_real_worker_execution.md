# V2.17 Resumable Worker Execution

## Purpose

V2.17 adds explicit recovery controls for runs that stop before delivery.

The target cases are:

- operator pause or stop at a task boundary
- worker failure with remaining retry attempts
- blocked task that should be retried after local correction
- interrupted real Codex runs with retained state and worktree evidence

Recovery does not silently mutate an old run. It creates a new run output that
references the previous state and records a recovery checkpoint.

## Recovery Contract

A resumed run loads one of:

```text
prior-run-directory/
prior-run-directory/run.json
prior-run-directory/document_run_report.json
prior-run-directory/state.json
```

The recovery controller then:

1. Loads the prior `RuntimeState`.
2. Resets active tasks to `pending`.
3. Resets failed tasks with remaining retry budget to `pending`.
4. Optionally resets blocked tasks with remaining retry budget to `pending`.
5. Clears blockers tied to reset tasks.
6. Clears `B-RUN-STOPPED` so operator stop can resume.
7. Records a `recovery_checkpoint` event in `iteration_history`.
8. Runs the normal orchestrator loop against the recovered state.

The checkpoint is persisted under `runtime_state.recovery` and in the top-level
document-run report:

```json
{
  "recovery": {
    "checkpoint": {
      "source_run_id": "run_001",
      "reset_task_ids": ["T002"],
      "continued_task_ids": ["T003"],
      "cleared_blocker_ids": ["B-RUN-STOPPED"]
    },
    "blockers": []
  }
}
```

## CLI Usage

Resume from a previous document-run directory:

```bash
python -m autodev.document_run \
  --objective "Add workspace support" \
  --document workspace_feature_spec.md \
  --repository-path /path/to/repo \
  --output .alchemy/document_run_resume \
  --resume-from .alchemy/document_run_previous
```

Retry only selected tasks:

```bash
python -m autodev.document_run \
  --objective "Add workspace support" \
  --document workspace_feature_spec.md \
  --resume-from .alchemy/document_run_previous \
  --resume-task T002
```

For real Codex runs, the resumed state should point to the retained isolated
worktree from V2.16. The run still performs preflight before dispatch.

## API Usage

Start a recovery run from a prior project run:

```json
{
  "async": true,
  "resume_from_run_id": "run_001",
  "real_codex": true,
  "codex_executable": "D:\\AI\\Tools\\CodexCLI\\bin\\codex.exe",
  "isolate_real_run": true,
  "keep_worktree": true
}
```

The browser `Resume` button now starts a new recovery run when the source job is
paused. The UI switches monitoring to the new `resumed_run_id`.

## Boundaries

This phase adds resumable state recovery and task-boundary resume. It does not
yet implement hard cancellation of an already-running Codex subprocess. A worker
that is currently inside `codex exec` still completes, fails, or times out at the
subprocess boundary.

## Verification

V2.17 is verified by:

- focused recovery unit tests for failed, blocked, active, and non-retryable
  state
- document-run resume tests from a stopped run state
- API resume tests that convert a paused source job into a new recovery run
- the full repository unit test suite
- the local acceptance harness
- a bounded real Codex recovery smoke that resumed an active read-only review
  task, cleared `B-RUN-STOPPED`, completed the task, and left the source
  repository clean
