# V2.163 Final Setup/Not-Found View Timeout Split

## Context

After V2.162, Billing Core final verification `run_attempt_035` resumed from split T044 auth/public/setup tasks. The split proved useful: T044 auth views and T045 public legal views completed. T046 `Repair final frontend setup and not-found view contracts` then timed out after the base 900 second worker budget.

Alchemy again handled the timeout boundary correctly: it recorded a non-partial timeout blocker, did not launch a same-scope debug task, and did not dispatch downstream tasks.

## Change

V2.163 adds a second-level split for T046:

- `Repair final frontend setup view contracts`
- `Repair final frontend not-found view file`

The existing auth/public/setup support-file task remains downstream, so shared style/type/package edits stay separate from the leaf view-file work.

## Verification

- `python -B -m pytest tests/test_document_to_plan.py::DocumentToPlanTests::test_final_verification_setup_not_found_timeout_is_split_again tests/test_document_to_plan.py::DocumentToPlanTests::test_final_verification_auth_public_setup_timeout_is_split_again -q`
- `python -B -m compileall planner tests -q`
- `python -B -m pytest tests/test_document_to_plan.py -q`
- `python -B -m pytest tests/test_full_roadmap_execution.py -q`

The real `final_verification_repair_resume_032.md` now produces a graph that preserves T043-T045 and starts the next editable work at split T046 setup-view cleanup, followed by a NotFoundView-only task.
