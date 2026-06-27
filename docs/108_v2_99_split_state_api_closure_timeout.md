# V2.99 Split State/API Closure Timeout

## Problem

V2.98 allowed Billing Core to relaunch with the correct cumulative repair
context and a generated `phase_repair_resume_004.md`. The rebuilt graph carried
`phase_repair_006.md`, `phase_repair_007.md`, and the resume repair document,
but it still replayed the previously timed-out T010 task:

- `Complete remaining frontend state and API closure`

That task had already consumed a full 900 second worker window in
`run_attempt_038`, so replaying it unchanged would waste another worker budget.

## Fix

The frontend large-refactor planner now recognizes focused T010 timeout repair
evidence and replaces the state/API closure task with smaller tasks:

- `Complete remaining frontend API service closure`
- `Complete remaining frontend store and composable closure`
- `Complete remaining frontend constants and type closure`

The existing view workflow closure task remains separate.

## Verification

- focused planner regressions for T009 and T010 timeout splitting: `2 passed`
- real phase_010 graph probe with `phase_repair_006.md`,
  `phase_repair_007.md`, and `phase_repair_resume_004.md`
- `python -B -m pytest tests/test_document_to_plan.py -q` => `23 passed`
- `python -B -m pytest tests/test_full_roadmap_execution.py -q` => `58 passed`
- `python -B -m py_compile planner\task_graph_builder.py tests\test_document_to_plan.py`

The real graph now preserves T001-T009 and leaves T010-T013 as narrower
frontend closure tasks.
