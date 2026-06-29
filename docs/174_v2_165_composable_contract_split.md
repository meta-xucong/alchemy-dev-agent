# V2.165 Composable Contract Split

## Context

The V2.164 final verification resume correctly preserved the completed frontend
store repair and resumed the next narrowed task:

- `T049 Repair final frontend store contracts` completed in `run_attempt_037`.
- `T050 Repair final frontend composable contracts` timed out after the 900 second
  worker budget.
- The scheduler stopped at the non-partial blocker `B-T050-1` and did not launch
  same-scope debug or downstream work.

The remaining problem was task granularity. `frontend/src/composables/**` was still
too broad for the final frontend closure tail.

## Change

`planner/task_graph_builder.py` now detects timeout reports for
`Repair final frontend composable contracts` and splits that task into narrower
subtasks:

- `Repair final frontend identity OAuth composables`
- `Repair final frontend metering entitlement composables`
- `Repair final frontend table navigation composables`

The existing state/composable/utility split is preserved, so completed store work
stays completed and the utility, test, audit, simulation, real-check, review, and
delivery tasks continue after the new composable subtasks.

## Verification

Focused and regression checks:

- `python -B -m pytest tests/test_document_to_plan.py::DocumentToPlanTests::test_final_verification_composable_contracts_timeout_is_split_again tests/test_document_to_plan.py::DocumentToPlanTests::test_final_verification_state_composable_utility_timeout_is_split_again -q`
- `python -B -m compileall planner tests -q`
- `python -B -m pytest tests/test_document_to_plan.py -q`
- `python -B -m pytest tests/test_full_roadmap_execution.py -q`

Real artifact probe:

- Generated `.alchemy/billing_core_v274_20260624_012/final_verification/final_verification_repair_resume_034.md`
  from the real `run_attempt_037` failure report.
- Rebuilt the graph from that resume document and confirmed:
  - `T049` remains completed.
  - `T050`, `T051`, and `T052` are the new composable subtasks.
  - Utility, test, audit, simulation, real repository checks, review, and delivery
    remain pending after the split.
