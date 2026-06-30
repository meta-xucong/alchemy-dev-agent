# V2.176 Reopened Final Repair Order

## Problem

Billing Core `final_verification/run_attempt_049` consumed the focused final repair graph and completed narrowed T009, but the scheduler then dispatched T056 while earlier reopened product repairs T024, T039, and T041 were still ready.

V2.175 correctly made final audit wait for every reopened repair task, so T060 could no longer bypass remaining work. However, preserved completed intermediate nodes could still make a later reopened test/fixture repair task ready before earlier reopened product repairs finished.

## Fix

`planner/task_graph_builder.py` now enforces ordering among reopened final-verification repair tasks after preserved tasks are marked completed.

The ordering helper walks the final repair task IDs in graph order, remembers repair tasks that remain open, and adds those open predecessors to later repair tasks only when the later task is not already waiting on an open predecessor. This preserves normal serial dependencies for ordinary split chains while preventing preserved intermediate nodes from creating a scheduling shortcut.

## Verification

- `python -m pytest tests/test_document_to_plan.py`
- `python -m pytest tests/test_full_roadmap_execution.py`
- `python -m py_compile planner\task_graph_builder.py tests\test_document_to_plan.py`
- Real graph probe using `.alchemy/billing_core_v274_20260624_012/final_verification/final_verification_repair_resume_045.md`

The real probe produced a 63-node final-verification graph where T056 depends on T009, T024, T039, and T041. T060 still depends on all reopened repairs and cannot run early.

## Next Step

Relaunch the supervised Billing Core final verification through the existing V2.88 resume entrypoint. The expected healthy path is to preserve completed T009 evidence if the new resume document captures run_attempt_049 progress, then dispatch T024 before T056 or T060.
