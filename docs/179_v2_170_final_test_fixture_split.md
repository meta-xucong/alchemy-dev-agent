# V2.170 Final Test Fixture Timeout Split

## Problem

After V2.169 restored the correct final-verification graph, Billing Core `run_attempt_043` finally resumed the real T056 task:

`Repair final frontend test and fixture contracts`

The task ran in the inherited worktree and timed out after the 900 second worker budget. Alchemy handled the timeout correctly as a non-partial blocker and did not launch debug or downstream work, but the task scope was still too broad for one worker.

## Change

The final frontend test/fixture repair now splits after a T056 timeout into four smaller leaf tasks:

- `Repair final frontend API and integration test contracts`
- `Repair final frontend component and composable test contracts`
- `Repair final frontend view router i18n utility test contracts`
- `Repair final frontend test config and fixture contracts`

The split keeps the deep final frontend repair graph intact and preserves completed T001-T055 evidence.

## Verification

- `tests/test_document_to_plan.py::DocumentToPlanTests::test_final_verification_test_fixture_focus_preserves_deep_tail_graph`
- `tests/test_document_to_plan.py::DocumentToPlanTests::test_final_verification_metering_entitlement_composables_timeout_is_split_again`
- `tests/test_document_to_plan.py`
- `tests/test_full_roadmap_execution.py`

## Real Billing Core Probe

The real helper generated `final_verification_repair_resume_039.md` from `run_attempt_043` with T056 focused and T001-T055 preserved.

A graph probe using `_039` produced a 63-node graph:

- T054/T055 completed
- T056 API/integration test contracts pending
- T057 component/composable test contracts pending
- T058 view/router/i18n/utility test contracts pending
- T059 test config/fixture contracts pending
- T060-T063 final audit, simulation, real checks, and review pending
