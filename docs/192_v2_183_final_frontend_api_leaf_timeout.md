# V2.183 Final Frontend API Leaf Timeout

## Problem

Billing Core `final_verification/run_attempt_057` completed the V2.182 backend leaf T004 and then completed T005. The next task, T006 `Repair final frontend API module contracts`, timed out at the 900 second worker boundary.

The scheduler stopped correctly without dispatching T009, T060, or same-scope debug work. The next resume needed to avoid replaying broad `frontend/src/api/**`.

## Fix

`planner/task_graph_builder.py` now detects a focused T006 timeout where the timed-out task title is `Repair final frontend API module contracts`.

The next graph keeps task ID T006 stable and narrows it to `Repair final frontend admin billing API contract leaf` with admin/payment/usage/redeem/settings/retired API files plus focused API tests.

## Verification

- `python -m pytest tests/test_document_to_plan.py -k "frontend_api"`
- `python -m pytest tests/test_document_to_plan.py`
- `python -m pytest tests/test_full_roadmap_execution.py -k "final_verification_resume_preserves_supervisor_stopped_progress or final_verification_resume_uses_latest_non_stopped_failed_state"`
- `python -m compileall autodev planner tests -q`
- Real helper probe generated `final_verification_repair_resume_060.md`
- Real graph probe using `_060`

The real `_060` graph keeps T004/T005 completed, narrows T006 to the admin billing API leaf, and preserves the T009/frontend, T060 delivery, and final gate dependency chain.
