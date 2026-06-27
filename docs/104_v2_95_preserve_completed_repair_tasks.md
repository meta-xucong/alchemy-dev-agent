# V2.95 Preserve Completed Repair Tasks

## Objective

V2.95 prevents focused repair resumes from replaying tasks that the previous
attempt already completed. When a repair brief says `Completed tasks to
preserve`, the rebuilt task graph should carry that evidence forward instead of
dispatching those tasks again.

## Problem Evidence

V2.94 fixed the disk repair brief handoff. The next Billing Core relaunch,
`phase_010/run_attempt_034`, correctly selected `phase_repair_006.md` and
generated the split timeout tasks:

```text
T007 Sweep frontend i18n product copy
T008 Sweep frontend view and component product copy
```

However, the graph still marked T002 through T006 as ready after T001
completed, even though the same repair brief explicitly said:

```text
Completed tasks to preserve: T001, T002, T003, T004, T005, T006.
```

That was not the old broad-graph loop, but it still wasted worker budget and
risked re-editing already verified Billing Core work.

`run_attempt_034` was stopped with `supervisor_stop.json` before it could spend
more time rerunning the completed frontend workflow tasks.

## Design

The planner now parses focused repair briefs for completed-task preservation
lines:

```text
Completed tasks to preserve: T001, T002, ...
```

For matching task IDs in the rebuilt graph, it:

- sets the node status to `completed`;
- attaches `focused_repair_preserved_task` evidence;
- leaves the failed or remaining task IDs pending.

Runtime already treats `completed` and `skipped` dependencies as satisfied, so
no orchestrator change is required.

## Verification

Focused and regression checks:

```powershell
python -B -m pytest tests/test_document_to_plan.py::DocumentToPlanTests::test_large_refactor_frontend_timeout_repair_splits_copy_sweep_task -q
python -B -m pytest tests/test_document_to_plan.py -q
python -B -m pytest tests/test_document_run_pipeline.py -q
python -B -m py_compile planner\task_graph_builder.py tests\test_document_to_plan.py
```

Real Billing Core phase_010 graph probe with `phase_repair_006.md` now shows:

```text
T001 completed
T002 completed
T003 completed
T004 completed
T005 completed
T006 completed
T007 pending
T008 pending
T009 pending
```

## Operational Note

A new attempt may still contain a planning task in its graph, but if that task
is listed in completed-task preservation evidence it should be marked completed
before scheduling. Seeing T002-T006 ready again after a focused T007 repair is a
regression.
