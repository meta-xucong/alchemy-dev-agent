# V2.164 Final State/Composable/Utility Timeout Split

## Context

After V2.163, Billing Core final verification `run_attempt_036` resumed from split setup/not-found work. T046 setup view, T047 NotFoundView, and T048 auth/public/setup support files completed. T049 `Repair final frontend state composable utility contracts` then timed out after 900 seconds.

Alchemy handled the timeout boundary correctly by recording a non-partial blocker and stopping without a same-scope debug task.

## Change

V2.164 splits T049 into:

- `Repair final frontend store contracts`
- `Repair final frontend composable contracts`
- `Repair final frontend utility constant type contracts`

It also preserves the earlier V2.163 setup/not-found split by completed task IDs. Without that preservation, a later T049 resume could collapse setup and NotFound back into the old combined task, shifting the new store task into a completed task ID.

## Verification

- `python -B -m pytest tests/test_document_to_plan.py::DocumentToPlanTests::test_final_verification_state_composable_utility_timeout_is_split_again tests/test_document_to_plan.py::DocumentToPlanTests::test_final_verification_setup_not_found_timeout_is_split_again tests/test_document_to_plan.py::DocumentToPlanTests::test_final_verification_auth_public_setup_timeout_is_split_again -q`
- `python -B -m compileall planner tests -q`
- Real `final_verification_repair_resume_033.md` graph probe: T043-T048 remained completed; T049/T050/T051 became store, composable, and utility/constant/type tasks.
- `python -B -m pytest tests/test_document_to_plan.py -q`
- `python -B -m pytest tests/test_full_roadmap_execution.py -q`
