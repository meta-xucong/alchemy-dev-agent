# V2.175 Final Gate Waits For Reopened Repairs

## Problem

After V2.174, `final_verification/run_attempt_048` correctly resumed with narrowed T009:

- T009 `Repair final frontend route registration file` completed quickly.
- The route and sidebar `/admin/ops` exposure was removed from the scoped files.

However, Alchemy then dispatched T060 `Audit final requirements and phase evidence` while other reopened repair tasks were still ready or pending:

- T024 frontend admin usage component
- T039 admin user/usage/redeem views
- T041 admin operations views
- T056 API/integration tests
- T057 component/composable tests

This happened because final-verification repair graphs used a serial dependency chain and the final audit depended only on the last repair-spec ID. When downstream tasks were preserved as completed, a reopened earlier task could be bypassed by the final gate.

The supervisor wrote `supervisor_stop.json`; Alchemy cancelled the wrongly dispatched T060 worker and exited without leaving residual worker processes.

## Change

`planner/task_graph_builder.py` now makes the final audit depend on every repair task in the deterministic final-verification repair graph, not just the last repair task.

The graph still keeps the normal repair-task chain, but T060 cannot become ready until all reopened repair tasks are completed, even when later nodes were preserved as completed from previous attempts.

## Verification

- `tests/test_document_to_plan.py::DocumentToPlanTests::test_final_audit_focus_keeps_deep_tail_shape_when_tail_tasks_reopen`
- `tests/test_document_to_plan.py::DocumentToPlanTests::test_final_verification_route_app_shell_timeout_is_narrowed_without_id_drift`
- `tests/test_document_to_plan.py::DocumentToPlanTests::test_final_audit_focus_preserves_test_fixture_split_tail`

## Real Billing Core Probe

The real graph probe using `final_verification_repair_resume_045.md` still produces 63 nodes.

T060 now depends on all repair specs, including:

- T009 narrowed route registration
- T024 usage component
- T039 admin user/usage/redeem views
- T041 admin operations views
- T056 API/integration tests
- T057 component/composable tests
- T059 final test config/fixture contracts

The next controlled relaunch should continue from narrowed T009 if needed and then run T024/T039/T041/T056/T057 before T060 can start.
