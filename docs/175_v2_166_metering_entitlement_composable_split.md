# V2.166 Metering Entitlement Composable Split

## Context

After V2.165, the real final verification resume advanced further:

- `T050 Repair final frontend identity OAuth composables` completed in
  `run_attempt_038`.
- `T051 Repair final frontend metering entitlement composables` timed out after
  the 900 second worker budget.
- The scheduler stopped at the non-partial blocker `B-T051-1` without launching
  same-scope debug or downstream tasks.

This showed that the domain composable task was still too broad for the final
frontend closure tail.

## Change

`planner/task_graph_builder.py` now detects timeout reports for
`Repair final frontend metering entitlement composables` and splits that task into:

- `Repair final frontend channel monitor format composable`
- `Repair final frontend model entitlement composable`
- `Repair final frontend onboarding quota composables`

The broader composable split remains preserved, so completed identity/OAuth work
stays completed, the table/navigation composable task remains downstream, and the
utility, test, audit, simulation, real repository check, review, and delivery tasks
continue after the new leaves.

## Verification

Focused and regression checks:

- `python -B -m pytest tests/test_document_to_plan.py::DocumentToPlanTests::test_final_verification_metering_entitlement_composables_timeout_is_split_again tests/test_document_to_plan.py::DocumentToPlanTests::test_final_verification_composable_contracts_timeout_is_split_again -q`
- `python -B -m compileall planner tests -q`
- `python -B -m pytest tests/test_document_to_plan.py -q`
- `python -B -m pytest tests/test_full_roadmap_execution.py -q`

Real artifact probe:

- Generated `.alchemy/billing_core_v274_20260624_012/final_verification/final_verification_repair_resume_035.md`
  from the real `run_attempt_038` failure report.
- Rebuilt the graph from that resume document and confirmed:
  - `T050` remains completed.
  - `T051`, `T052`, and `T053` are the new metering/entitlement composable leaves.
  - Table/navigation composables, utility/type repair, tests, audit, simulation,
    real repository checks, review, and delivery remain pending after the split.
