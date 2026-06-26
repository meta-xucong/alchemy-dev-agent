# V2.87 Dead Debug Resume Skip

## Problem

After the V2.85 Billing Core probe was manually stopped, `run_attempt_020`
retained `active_tasks=["T002-DEBUG-1"]`. Its worker lifecycle file still said
`status="running"`, but the recorded worker PID no longer existed.

V2.85 intentionally kept ordinary interrupted active attempts resumable when no
live process remains, but replaying this dead debug task would route the next
Billing Core recovery through stale debug work that existed only because V2.86
fixed the original package-lock boundary false failure.

## Fix

`autodev.full_roadmap_executor.interrupted_phase_resume_source()` now skips a
stale attempt when all active tasks are debug tasks and each corresponding
lifecycle record is `running` with no live PID.

Ordinary active implementation tasks with dead PIDs remain resumable, preserving
the normal interrupted-run recovery behavior. Active attempts with live worker
PIDs still block new launches.

## Verification

- Added `test_dead_debug_active_phase_attempt_is_not_resumed`.
- Preserved the regression where an ordinary interrupted active task remains
  resumable.
- Preserved terminal-active and newer-terminal resume ordering regressions.
- Full `tests/test_runtime.py` passed.
- Full `tests/test_full_roadmap_execution.py` passed.
- `py_compile` and `git diff --check` passed.

## Operational Notes

The next Billing Core launch should skip stale `run_attempt_020` debug state
and create a fresh phase attempt instead of resuming `T002-DEBUG-1`.
