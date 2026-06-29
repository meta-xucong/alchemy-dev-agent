# V2.169 Final Tail Resume Preservation

## Problem

After V2.168 generated a T056-focused resume document, the next Billing Core relaunch created `run_attempt_042` with a compressed final-verification graph. The rebuilt graph marked `Repair final frontend test and fixture contracts` completed under a lower task id and reopened earlier frontend API/i18n work.

That was not a normal retry. It meant the final-verification planner did not preserve the deep split graph when the failed task id was in the final frontend tail.

## Change

- Boundary-violation worker evidence no longer causes completed predecessor tasks to be reopened from changed-path text.
- Final-verification resume matching now checks both the primary failed task line and the completed-task preservation line before reusing an existing resume document.
- Added a deep-tail preservation trigger for T050+ final frontend repair resumes.
- When a deep final frontend tail task such as T056 is focused, the planner forces the previously introduced API/i18n, view/component, admin, auth/setup, store/composable, metering, utility, and test split families to remain expanded.
- Operator/supervisor stop blockers are detected from blocker descriptions, even when they are classified as `technical_limit`.

## Verification

- `tests/test_document_to_plan.py::DocumentToPlanTests::test_final_verification_test_fixture_focus_preserves_deep_tail_graph`
- `tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_final_verification_resume_uses_latest_non_stopped_failed_state`
- `tests/test_document_to_plan.py`
- `tests/test_full_roadmap_execution.py`

## Real Billing Core Probe

The real helper probe generated `final_verification_repair_resume_038.md` from `run_attempt_039` with:

- `Primary failed task IDs: T056`
- `Completed tasks to preserve: T001` through `T055`

A graph probe using that resume kept T050-T055 completed and left T056 pending, avoiding the T006/T025 compressed-graph replay seen in `run_attempt_042`.
