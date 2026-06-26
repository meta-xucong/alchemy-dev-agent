# V2.84 Worker Timeout Stop

## Problem

Billing Core phase_010 reached the correct isolated worktree after V2.83, but a
large frontend task timed out after the configured worker budget. The runtime
then created a same-scope debug task with the same relevant files and command
surface. That debug task also timed out, after which the old convergence logic
reset the original task for another full retry.

That behavior is risky for large real-Codex runs: a timeout is usually a task
sizing or budget boundary, not evidence that the same work should be replayed.

## Fix

`runtime.orchestrator.Orchestrator` now treats worker timeout results as
non-partial technical blockers:

- a normal task timeout records a blocker immediately and does not create a
  debug task;
- a debug task timeout blocks the parent task instead of resetting it for a
  same-scope retry;
- timeout detection uses both worker lifecycle status and structured result
  text;
- latest worker-result lookup skips non-worker evidence so debug convergence
  metadata cannot hide the actual worker timeout result.

This preserves ordinary retry/debug behavior for normal failed tasks while
stopping unproductive timeout loops.

## Verification

- Added regression coverage for a normal worker timeout that must not create
  `T002-DEBUG-1`.
- Added regression coverage for a debug timeout that must not replay `T002`.
- Re-ran the existing debug/retry and non-partial blocker focused regressions.

## Operational Notes

When this blocker appears in a real project, the next operator action should be
one of:

- split the timed-out task into smaller Alchemy task graph nodes;
- raise the worker timeout for a deliberately large bounded task;
- inspect whether the task is doing unnecessary work before rerunning.

Do not resume the same attempt with the old active worker state. Start a fresh
Alchemy attempt after the framework fix is committed and verified.
