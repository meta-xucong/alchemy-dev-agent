# V2.138 Final Frontend View/Component Timeout Split

## Problem

After V2.137, Billing Core `final_verification/run_attempt_012` correctly resumed from split T009 and completed
`Repair final frontend route and app shell contracts`.

The next task, T010 `Repair final frontend view and component contracts`, still covered too many frontend surfaces.
It timed out after 900 seconds while editing a large number of view, component, type, package, and fixture files.

The timeout boundary behaved correctly: Alchemy recorded `B-T010-1`, stopped the final verification run, did not
launch same-scope debug work, and did not dispatch downstream T011. The remaining issue was the next resume graph:
it must preserve T001-T009 and split T010 instead of replaying the same broad view/component worker.

## Change

`planner/task_graph_builder.py` now detects final-verification T010 view/component timeout repair context and splits
the broad T010 into smaller serial scopes:

- `Repair final frontend account component contracts`
- `Repair final frontend admin operation component contracts`
- `Repair final frontend analytics and shared component contracts`
- `Repair final frontend view page contracts`
- existing state/composable/utility repair
- existing test/fixture repair

The split preserves the prior V2.136/V2.137 task shapes so completed-task IDs do not drift:

- T006 API module repair
- T007 i18n locale repair
- T008 constants/shared-types repair
- T009 route/app-shell repair

## Verification

- Focused document-to-plan regression for T010 timeout second-level split.
- Focused full-roadmap regression for writing `final_verification_repair_resume_008.md`.
- Adjacent V2.137 route/view timeout regressions.
- Real Billing Core graph probe generated `final_verification_repair_resume_008.md` from `run_attempt_012` and showed
  T001-T009 preserved completed with T010 starting at account component repair.
