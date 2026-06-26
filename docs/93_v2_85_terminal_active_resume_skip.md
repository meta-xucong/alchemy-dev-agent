# V2.85 Terminal Active Resume Skip

## Problem

After stopping a Billing Core probe that had already timed out, the latest
phase attempt still had `active_tasks=["T002"]`. Its worker lifecycle evidence
showed terminal timeout records, but the full-roadmap resume selector treated
any active-task attempt without a live worker process as resumable.

Runtime recovery resets active tasks to pending, so resuming that attempt would
replay the same timed-out task even after V2.84 taught the orchestrator to stop
future timeout loops.

## Fix

`autodev.full_roadmap_executor.interrupted_phase_resume_source()` now
distinguishes two cases:

- active task plus live running worker PID: block and ask the operator to wait
  or stop the live worker;
- active task plus terminal lifecycle evidence (`completed`, `failed`,
  `timed_out`, or `cancelled`): treat the attempt as terminal stale state and
  start a fresh attempt instead of using it as `resume_from`.

Attempts with active tasks and no terminal lifecycle evidence remain resumable,
preserving the existing interrupted-run behavior.

## Verification

- Added a Billing-shaped regression for `run_attempt_019`: active `T002` with
  terminal `timed_out` lifecycle is not selected as `resume_from`.
- Preserved the existing regression where an interrupted active task with a
  dead `running` PID remains resumable.
- Preserved the V2.82 regression that newer terminal attempts supersede older
  stale active attempts.

## Operational Notes

Billing Core should now create a fresh phase_010 attempt after the stopped
`run_attempt_019` probe. It should not resume the stale active T002 state from
that attempt.
