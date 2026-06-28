# V2.118 Timeout Repair Context Bootstrap

## Problem

After V2.117, the real Billing Core resume created `run_attempt_018`, but the
document runner received only `phase_requirements.md`. It did not receive the
existing `phase_repair_001.md` through `phase_repair_007.md` chain, so the task
graph collapsed back to a stale T001/T002 broad schema/build graph.

This happened because worker-timeout stop boundaries intentionally make
`should_auto_repair_phase()` return false: the parent must not immediately
launch another same-scope attempt. That safety rule accidentally also prevented
the next supervised launch from reusing the repair briefs that had already been
written for a narrowed resume.

## Fix

`bootstrap_phase_repair_documents()` now reuses existing ordinary repair briefs
when the previous phase record stopped at a worker-timeout boundary. This does
not make Alchemy auto-retry the same timed-out task. It only lets a later
supervised relaunch rebuild the task graph from the focused repair context that
is already on disk.

## Verification

- Added a regression where `should_auto_repair_phase()` remains false for a
  worker-timeout stop boundary, but bootstrap still returns existing
  `phase_repair_NNN.md` documents.
- Full roadmap regression: `72 passed`.
- Real phase_011 bootstrap probe against `run_attempt_017` returns
  `phase_repair_001.md` through `phase_repair_007.md`.
