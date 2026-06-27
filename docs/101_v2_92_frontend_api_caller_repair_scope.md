# V2.92 Frontend API Caller Repair Scope

## Objective

V2.92 prevents focused frontend repair attempts from replaying an already known
API-service blocker before later tasks can edit the caller files that resolve it.

## Problem Evidence

After V2.91, Billing Core `phase_010/run_attempt_029` advanced correctly:

- T001 completed.
- T002 completed.
- T003 completed task-local API quarantine checks but stopped as a non-partial
  technical blocker after retry exhaustion.

The blocker was legitimate: remaining direct retired API callers were in
`frontend/src/components/**`, `frontend/src/composables/**`, and
`frontend/src/constants/**`, while T003's allowed files were still limited to
API/types/stores/views/utils/i18n.

The parent executor wrote `phase_repair_005.md` with the correct focused
instruction to expand those files. However, the rebuilt graph put those paths
mostly in the later usage/admin task, while T003 remained on the old API-only
scope. Since T003 executes before the later task and can stop the run with a
non-partial blocker, the repair attempt risked replaying the same failure.

## Design

V2.92 treats frontend API-service cleanup as both API barrel cleanup and caller
cleanup. The `Clean frontend API service references` task now includes:

- `frontend/src/api/**`
- `frontend/src/components/**`
- `frontend/src/composables/**`
- `frontend/src/constants/**`
- the existing types/stores/views/utils/i18n/package files

This keeps the task's title and blocker evidence aligned: if the worker finds
remaining retired API callers, it has permission to remove or quarantine them in
the same task instead of waiting for a later task that may never run.

`run_attempt_030` was marked with `supervisor_stop.json` because it was created
with the pre-V2.92 graph and would have retried the same stale T003 scope.

## Verification

Focused checks:

```powershell
python -B -m pytest tests/test_document_to_plan.py::DocumentToPlanTests::test_large_refactor_frontend_repair_docs_do_not_collapse_to_scoped_router_task tests/test_document_to_plan.py::DocumentToPlanTests::test_large_refactor_frontend_phase_survives_repository_index_cap -q
```

Regression:

```powershell
python -B -m pytest tests/test_document_to_plan.py -q
python -B -m py_compile planner\task_graph_builder.py tests\test_document_to_plan.py
```

Real Billing Core graph probe:

```text
phase_010 + phase_repair_005.md now gives T003:
frontend/src/api/**
frontend/src/components/**
frontend/src/composables/**
frontend/src/constants/**
...
```

## Next Action

Relaunch Billing Core through Alchemy only. The next attempt should skip
`run_attempt_030` and let T003 repair the caller surface directly.
