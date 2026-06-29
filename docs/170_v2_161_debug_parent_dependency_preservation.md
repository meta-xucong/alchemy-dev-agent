# V2.161 Debug Parent Dependency Preservation

## Problem

V2.160 mapped stopped debug tasks back to their parent task, but a second interaction remained: completed-task reopen logic could remove completed dependency-chain tasks when the stopped debug task's evidence mentioned broad allowed files or out-of-scope paths.

Against the real Billing Core `run_attempt_033` report, the focused task correctly became T042, but completed preservation initially omitted T038-T041. That would risk replaying recently completed final-frontend tail work before T042.

## Change

When a final-verification repair resume maps a failed debug task back to a non-debug parent, dependency-chain completed tasks for that parent are now protected from target-path reopen pruning.

Normal later-failure behavior is preserved: if a non-debug failure truly targets a completed task scope, the completed task can still be reopened.

## Verification

- Real Billing Core report probe now computes `Primary failed task IDs: T042` and preserves T001-T041.
- `python -B -m pytest tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_final_verification_resume_preserves_partial_downstream_handoff tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_final_verification_resume_maps_stopped_debug_to_parent_and_dependency_preserve tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_final_verification_relaunch_writes_fresh_resume_for_latest_failed_attempt tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_final_verification_resume_reopens_preserved_task_when_later_failure_targets_its_scope -q`
- `python -B -m compileall autodev tests -q`
- `python -B -m pytest tests/test_full_roadmap_execution.py -q`
- `python -B -m pytest tests/test_document_to_plan.py -q`

## Billing Core Resume Note

The existing stale `final_verification_repair_resume_029.md` still contains the old debug focus. The next controlled relaunch should write a newer resume document because V2.160/V2.161 focus matching rejects that stale focus, then resume T042 with T001-T041 preserved.
