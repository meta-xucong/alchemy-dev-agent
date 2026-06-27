# V2.97 Cumulative Repair Brief Context

## Problem

V2.96 correctly split the timed-out T009 remaining frontend closure task, but
the next real Billing Core relaunch exposed a second resume issue.

`run_attempt_037` used only `phase_repair_007.md`. That document preserved
T001-T008 and described the T009 timeout, but it did not carry the earlier
`phase_repair_006.md` instruction that split the original broad copy task into
T007 and T008.

The rebuilt graph therefore shifted task IDs:

- T007 became the old broad copy task again.
- T008 became the new shell/route closure task.
- `Completed tasks to preserve: T008` was applied to that new T008, even
  though the completed T008 evidence referred to the prior view/component copy
  task.

The supervisor stopped `run_attempt_037` before continuing on that drifted
graph.

## Fix

`latest_existing_phase_repair_documents(...)` now returns the most recent
ordinary repair briefs up to `max_repair_documents`, ordered from older to
newer, instead of returning only the newest file.

For Billing Core phase_010 this means a relaunch receives both:

- `phase_repair_006.md`, which carries the T007 copy-sweep split context.
- `phase_repair_007.md`, which carries the T009 remaining-closure timeout and
  completed-task preservation evidence.

## Verification

- focused full-roadmap regressions for stale phase records and cumulative
  repair brief reuse: `2 passed`
- real phase_010 bootstrap probe returns `phase_repair_006.md` and
  `phase_repair_007.md`
- real phase_010 graph probe preserves T001-T008 and leaves T009-T011 pending
  as the three remaining closure tasks
- `python -B -m pytest tests/test_full_roadmap_execution.py -q` => `56 passed`
- `python -B -m pytest tests/test_document_to_plan.py -q` => `22 passed`
- `python -B -m py_compile autodev\full_roadmap_executor.py tests\test_full_roadmap_execution.py`

## Assessment

This was another token-waste source that a human supervisor would usually avoid
by keeping the previous repair note in mind. Alchemy now retains that context
in the document runner input, reducing ID drift and false completed-task
preservation on long multi-repair phases.
