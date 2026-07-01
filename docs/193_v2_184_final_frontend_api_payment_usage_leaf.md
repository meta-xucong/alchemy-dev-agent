# V2.184 Final Frontend API Payment Usage Leaf

## Problem

Billing Core `final_verification/run_attempt_058` consumed the V2.183 graph and correctly ran T006 as `Repair final frontend admin billing API contract leaf`, but that leaf still exhausted the 900 second worker timeout.

The scheduler again stopped safely without launching T009, T060, or same-scope debug work. The next resume needed another checkpoint instead of replaying the same admin billing API leaf.

## Fix

`planner/task_graph_builder.py` now detects repeated T006 timeout evidence where the focused timeout title is `Repair final frontend admin billing API contract leaf`.

The rebuilt graph keeps task ID T006 stable and narrows the next retry to `Repair final frontend payment usage API contract leaf`, covering only payment/usage API files and their focused tests.

## Verification

- `python -m pytest tests/test_document_to_plan.py -k "frontend_api"`
- `python -m pytest tests/test_document_to_plan.py`
- `python -m pytest tests/test_full_roadmap_execution.py -k "final_verification_resume_preserves_supervisor_stopped_progress or final_verification_resume_uses_latest_non_stopped_failed_state"`
- `python -m compileall autodev planner tests -q`
- Real helper probe generated `final_verification_repair_resume_061.md`
- Real graph probe using `_061`

The real `_061` graph keeps T006 stable, narrows it to payment/usage API files, preserves completed backend/frontend split tasks, and keeps T009/T060/final gates behind T006.
