# V2.174 Route App Shell Timeout Narrowing

## Problem

After V2.173, `final_verification/run_attempt_047` successfully resumed the real Billing Core final repair graph:

- T006 `Repair final frontend API module contracts` completed.
- T009 `Repair final frontend route and app shell contracts` started in the inherited worktree.
- T009 timed out after the 900 second worker budget.

Alchemy handled the runtime boundary correctly:

- The worker lifecycle recorded `timed_out`.
- A non-partial `technical_limit` blocker was recorded for T009.
- No same-scope debug task was dispatched.
- T024/T039/T041/T056/T057 and final gates remained pending/ready.

The remaining problem was planning the next repair. Replaying T009 with the same `frontend/src/router/**` and `frontend/src/components/layout/**` scope would risk another 900 second timeout. Inserting new tasks before T010 would also risk task-ID drift because many downstream tasks were already preserved as completed.

## Change

`planner/task_graph_builder.py` now detects a focused timeout for T009 `Repair final frontend route and app shell contracts`.

Instead of inserting new tasks, the planner keeps the same T009 task ID and narrows it to concrete route/app-shell files:

- `frontend/src/router/index.ts`
- `frontend/src/components/layout/AppSidebar.vue`
- `frontend/src/App.vue`
- `frontend/src/stores/app.ts`
- frontend package manifest and lockfile companions

This keeps downstream completed IDs stable while reducing the scope enough for the next real worker to finish the `/admin/ops` route/navigation cleanup.

## Verification

- `tests/test_document_to_plan.py::DocumentToPlanTests::test_final_verification_route_app_shell_timeout_is_narrowed_without_id_drift`
- `tests/test_document_to_plan.py::DocumentToPlanTests::test_final_verification_frontend_routes_timeout_preserves_prior_frontend_split`
- `tests/test_document_to_plan.py`

## Real Billing Core Probe

The real `final_verification_resume_repair_documents` probe generated `final_verification_repair_resume_045.md` from `run_attempt_047`.

The real graph probe using `_045` produced 63 nodes:

- 53 completed
- 10 pending
- T009 pending as `Repair final frontend route registration file`
- T010 and T011 still completed, proving the graph did not drift
- pending follow-up repair tasks: T024, T039, T041, T056, T057
- pending gates: T060 final audit, T061 simulation probes, T062 real repository checks, T063 handoff review

The next controlled relaunch should start at narrowed T009 instead of replaying the broad route/app-shell worker.
