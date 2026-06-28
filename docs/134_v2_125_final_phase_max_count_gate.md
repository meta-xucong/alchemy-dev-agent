# V2.125 Final Phase Max-Count Gate

## Problem

After V2.124, Billing Core phase_012 completed successfully:

- T001 planning completed.
- T002 demo-smoke implementation completed.
- T003 verification failed once, then T003-DEBUG-1 repaired the evidence.
- T003 rerun completed.
- T004 review and T005 delivery evidence completed.

The phase promoted with score 0.94. All twelve roadmap phases were now done.

The parent full-roadmap report still ended as blocked because
`FullRoadmapExecutor` appended `Maximum roadmap phase count reached.` whenever
`phase_count >= max_phases`, even when the just-completed phase was the last
required phase. That artificial blocker prevented the final full-system audit
worker from running.

## Fix

The max-phase-count blocker is now emitted only when the phase budget is reached
and `next_ready_phase(plan)` still finds an unfinished required phase.

If the final required phase completes exactly at the configured phase limit,
Alchemy proceeds to the final verification worker and final audit.

## Verification

- Focused regression: a full roadmap with `max_phases` equal to the total phase
  count runs the final verification worker and does not emit the max-count
  blocker.
- Full `tests/test_full_roadmap_execution.py`.
- `compileall`.
- `git diff --check`.
