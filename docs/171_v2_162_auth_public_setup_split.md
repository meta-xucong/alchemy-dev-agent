# V2.162 Final Auth/Public/Setup View Timeout Split

## Context

Billing Core final verification `run_attempt_034` correctly resumed from the V2.161 T042-focused repair document. T042 and T043 completed, but T044 `Repair final frontend auth public setup view contracts` timed out after the base 900 second worker budget.

Alchemy handled the timeout boundary correctly: it recorded a non-partial timeout blocker, did not launch a same-scope debug task, and did not dispatch downstream T045. The remaining problem was task granularity rather than scheduler control.

## Change

V2.162 teaches the final frontend task graph to split a timed-out auth/public/setup view cleanup into smaller tasks:

- `Repair final frontend auth view contracts`
- `Repair final frontend public legal view contracts`
- `Repair final frontend setup and not-found view contracts`
- `Repair final frontend auth public setup support files`

The split is also preserved on later final-verification resumes so downstream failures do not collapse the graph back into the broad T044 task and drift completed task IDs.

## Verification

- `python -B -m pytest tests/test_document_to_plan.py::DocumentToPlanTests::test_final_verification_auth_public_setup_timeout_is_split_again -q`
- `python -B -m compileall planner tests -q`
- `python -B -m pytest tests/test_document_to_plan.py::DocumentToPlanTests::test_final_verification_admin_view_page_timeout_is_split_again tests/test_document_to_plan.py::DocumentToPlanTests::test_final_verification_admin_dashboard_settings_timeout_is_split_again tests/test_document_to_plan.py::DocumentToPlanTests::test_final_verification_admin_settings_email_timeout_is_split_again tests/test_document_to_plan.py::DocumentToPlanTests::test_final_verification_admin_announcement_backup_promo_timeout_is_split_again tests/test_document_to_plan.py::DocumentToPlanTests::test_final_verification_auth_public_setup_timeout_is_split_again -q`
- `python -B -m pytest tests/test_document_to_plan.py -q`
- `python -B -m pytest tests/test_full_roadmap_execution.py -q`

The real `final_verification_repair_resume_031.md` now produces a graph that preserves T040-T043 and starts the next editable work at split T044 auth view cleanup.
