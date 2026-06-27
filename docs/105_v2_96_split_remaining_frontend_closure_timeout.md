# V2.96 Split Remaining Frontend Closure Timeout

## Problem

Billing Core `phase_010/run_attempt_035` completed the split T007 and T008
frontend copy tasks, then timed out on T009:

- `T007 Sweep frontend i18n product copy` completed.
- `T008 Sweep frontend view and component product copy` completed.
- `T009 Complete remaining frontend closure requirements` timed out at the
  900 second worker budget.

The parent wrote `phase_repair_007.md` with the correct focused timeout
guidance:

- primary failed task: `T009`
- completed tasks to preserve: `T001` through `T008`
- split or checkpoint before replaying the same wide workflow

After V2.95, completed task preservation worked, but the rebuilt graph still
contained one broad remaining closure task with `frontend/**`. That meant the
next attempt could spend another full worker window on the same undivided
scope.

## Fix

The frontend large-refactor planner now recognizes focused T009 timeout repair
evidence and splits the fallback remaining-closure task into three narrower
tasks:

- `Complete remaining frontend shell and route closure`
- `Complete remaining frontend state and API closure`
- `Complete remaining frontend view workflow closure`

The split path also removes `frontend/**` from timeout-split relevant files so
old "previous relevant files" evidence cannot widen the new tasks back to the
scope that timed out.

## Verification

- `python -B -m pytest tests/test_document_to_plan.py::DocumentToPlanTests::test_large_refactor_frontend_timeout_repair_splits_copy_sweep_task tests/test_document_to_plan.py::DocumentToPlanTests::test_large_refactor_frontend_timeout_repair_splits_remaining_closure_task -q`
- `python -B -m pytest tests/test_document_to_plan.py -q`
- `python -B -m py_compile planner\task_graph_builder.py tests\test_document_to_plan.py`
- real Billing Core graph probe with `phase_requirements.md`,
  `phase_repair_006.md`, and `phase_repair_007.md`
- `python -B -m pytest tests/test_document_run_pipeline.py -q`
- `python -B -m pytest tests/test_full_roadmap_execution.py -q`

The real probe now preserves T001-T008 as completed and leaves T009-T011 as
the three narrower frontend closure tasks.

## Token-Cost Assessment

Many T001 entries are expected because each document-run attempt starts with a
planning node. The expensive abnormal pattern was not the T001 label itself;
it was repair resumes that failed to reuse enough prior evidence:

- V2.94 fixed losing a newer `phase_repair_NNN.md` behind a stale
  `phase_record.json`.
- V2.95 fixed redispatching completed tasks listed in repair evidence.
- V2.96 fixes replaying an over-wide remaining frontend task after timeout.

This means the high token burn in the recent runs is mostly bootstrapping and
debugging Alchemy's Windows/resume/timeout controller around a large legacy
project. It should not be treated as the steady-state cost target for mature
Alchemy development, but it does identify real controller features Alchemy
needs before it can beat careful human supervision consistently.
