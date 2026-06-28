# V2.136 Final Frontend API/I18n Timeout Split

## Problem

Billing Core `final_verification/run_attempt_010` correctly preserved T001-T005 and advanced into
`T006 Repair final frontend API and i18n contracts`, but that final repair task timed out after 900 seconds
without producing task-local evidence.

The timeout stop boundary behaved correctly: Alchemy recorded `B-T006-1` and did not launch a same-scope
debug task. The remaining problem was resume quality. The final-verification repair graph still rebuilt the
same broad frontend API/i18n/constants/types worker, even though older large-refactor phase repair logic
already knew how to split frontend timeout repairs.

## Change

`planner/task_graph_builder.py` now recognizes final-verification repair resumes where the focused failed task
is the final frontend API/i18n repair and the evidence indicates a worker timeout.

When that pattern appears, Alchemy replaces the single broad task with:

- `Repair final frontend API module contracts`
- `Repair final frontend i18n locale contracts`
- `Repair final frontend constants and shared types contracts`

The existing `Repair final frontend routes views and tests` task remains after those three narrower tasks, and
the final audit/simulation/real-check/review gates are shifted behind it.

## Verification

- `python -B -m pytest tests/test_document_to_plan.py::DocumentToPlanTests::test_final_verification_frontend_api_i18n_timeout_is_split -q`
- `python -B -m pytest tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_final_verification_resume_records_frontend_api_i18n_timeout_focus -q`
- `python -B -m pytest tests/test_document_to_plan.py -q`
- `python -B -m pytest tests/test_full_roadmap_execution.py -q`
- `python -B -m compileall planner autodev tests -q`

Real Billing Core probe:

- Generated `final_verification_repair_resume_006.md` from `run_attempt_010`.
- Graph probe shows T001-T005 preserved completed.
- Graph probe starts the next editable work at split frontend T006/T007/T008, then continues to routes/views/tests and final gates.
