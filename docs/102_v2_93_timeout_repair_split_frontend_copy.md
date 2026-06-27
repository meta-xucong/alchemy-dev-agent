# V2.93 Timeout Repair Split For Frontend Copy Sweep

## Objective

V2.93 makes timeout repair actionable for the Billing Core frontend copy/i18n
sweep. A timeout repair brief should create smaller follow-up tasks, not replay
the same broad worker scope.

## Problem Evidence

After V2.92, Billing Core `phase_010/run_attempt_031` made substantial forward
progress:

- T001 through T006 completed.
- T006 crossed the previous hard frontend blocker and passed frontend tests and
  typecheck.
- T007, `Sweep frontend product copy and i18n`, timed out at the 900 second
  worker boundary.

The timeout stop itself behaved correctly: no same-scope debug task was
launched and the worker process tree was cleaned up. The parent executor then
wrote `phase_repair_006.md`, which correctly said to checkpoint or split the
workflow before increasing the hard timeout.

However, the rebuilt graph in `run_attempt_032` still replayed the broad phase
from T001 with the same single T007 copy/i18n task. That risked repeating the
same 900 second timeout.

## Design

V2.93 adds a frontend large-refactor planner rule for focused T007 timeout
repairs. When repair evidence contains:

- `Primary failed task IDs: T007`
- timeout/timed-out wording
- split/checkpoint guidance

the planner replaces the broad `Sweep frontend product copy and i18n` task with
two smaller tasks:

- `Sweep frontend i18n product copy`
  - `frontend/src/i18n/**`
  - `frontend/package.json`
- `Sweep frontend view and component product copy`
  - `frontend/src/views/**`
  - `frontend/src/components/**`
  - `frontend/src/styles/**`
  - `frontend/src/stores/**`
  - `frontend/src/constants/**`
  - `frontend/package.json`

This keeps the hard timeout as a guardrail while reducing the work package that
caused the timeout.

`run_attempt_032` was marked with `supervisor_stop.json` because it was created
with the pre-V2.93 broad timeout-repair graph.

## Verification

Focused checks:

```powershell
python -B -m pytest tests/test_document_to_plan.py::DocumentToPlanTests::test_large_refactor_frontend_timeout_repair_splits_copy_sweep_task tests/test_document_to_plan.py::DocumentToPlanTests::test_large_refactor_frontend_repair_docs_do_not_collapse_to_scoped_router_task -q
```

Regression:

```powershell
python -B -m pytest tests/test_document_to_plan.py -q
python -B -m py_compile planner\task_graph_builder.py tests\test_document_to_plan.py
python -B -m pytest tests/test_document_run_pipeline.py -q
python -B -m pytest tests/test_full_roadmap_execution.py -q
```

Real Billing Core graph probe with `phase_repair_006.md` now generates:

```text
T007 Sweep frontend i18n product copy
T008 Sweep frontend view and component product copy
T009 Complete remaining frontend closure requirements
```

## Remaining Follow-Up

This is the first progress-aware timeout improvement. A later enhancement should
add worker heartbeats/checkpoints so Alchemy can tell the difference between a
stuck worker and one that is actively making progress near the timeout boundary.
