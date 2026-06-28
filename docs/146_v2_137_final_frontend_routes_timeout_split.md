# V2.137 Final Frontend Routes/Views Timeout Split

## Problem

After V2.136, Billing Core `final_verification/run_attempt_011` successfully completed the split frontend
API, i18n, and constants/types repair tasks:

- T006 `Repair final frontend API module contracts`
- T007 `Repair final frontend i18n locale contracts`
- T008 `Repair final frontend constants and shared types contracts`

T008 correctly handed downstream consumer failures to T009, but T009
`Repair final frontend routes views and tests` was still broad enough to time out after 900 seconds without
task-local evidence.

The timeout stop boundary behaved correctly again: Alchemy recorded `B-T009-1` and did not launch a same-scope
debug task. The remaining issue was the next resume graph: it needed to preserve the V2.136 split shape for
T006-T008 and split T009 without drifting completed task IDs onto unrelated new tasks.

## Change

`planner/task_graph_builder.py` now detects final-verification T009 timeout repair context and:

- preserves the V2.136 T006/T007/T008 split task shape when completed-task evidence references those IDs;
- replaces the broad T009 route/view/test task with narrower serial tasks:
  - `Repair final frontend route and app shell contracts`
  - `Repair final frontend view and component contracts`
  - `Repair final frontend state composable utility contracts`
  - `Repair final frontend test and fixture contracts`
- includes `frontend/src/utils/**` in the downstream state/composable/utility repair scope because T008 evidence
  showed shared-type migration failures in utility consumers.

## Verification

- `python -B -m pytest tests/test_document_to_plan.py::DocumentToPlanTests::test_final_verification_frontend_routes_timeout_preserves_prior_frontend_split tests/test_document_to_plan.py::DocumentToPlanTests::test_final_verification_frontend_api_i18n_timeout_is_split -q`
- `python -B -m pytest tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_final_verification_resume_records_frontend_routes_timeout_focus tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_final_verification_resume_records_frontend_api_i18n_timeout_focus -q`
- `python -B -m pytest tests/test_document_to_plan.py -q`
- `python -B -m pytest tests/test_full_roadmap_execution.py -q`
- `python -B -m compileall planner autodev tests -q`

Real Billing Core probe:

- Generated `final_verification_repair_resume_007.md` from `run_attempt_011`.
- Graph probe shows T001-T008 preserved completed.
- Graph probe starts the next editable work at split frontend T009/T010/T011/T012 before final gates.
