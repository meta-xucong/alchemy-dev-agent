# V2.160 Final Resume Debug Parent Focus

## Problem

After V2.159, Billing Core `run_attempt_033` was operator-stopped while `T042-DEBUG-1` was active. The final-verification repair resume generator could write a new resume document for the stopped attempt, but it focused on the debug task itself:

- primary failed task became `T042-DEBUG-1`
- the root task `T042` was not reopened
- completed-task preservation could be incomplete when `runtime_state.completed_tasks` was sparse
- an existing resume that mentioned the latest attempt was treated as reusable even if its focus was stale

That would make the next final-verification graph drift or replay debug work instead of repairing the legacy-admin boundary failure.

## Change

Final-verification repair resume generation now:

- maps failed or blocked debug task IDs back to the nearest non-debug parent task
- preserves completed dependency-chain tasks for the focused parent task even when `completed_tasks` is incomplete
- treats operator-stop, supervisor-stop, out-of-scope, and outside-boundary evidence as repair-resume-worthy
- reuses an existing final-verification repair resume only when both the attempt marker and focused primary task line match

## Verification

- `python -B -m pytest tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_final_verification_resume_preserves_partial_downstream_handoff tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_final_verification_resume_maps_stopped_debug_to_parent_and_dependency_preserve tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_final_verification_relaunch_writes_fresh_resume_for_latest_failed_attempt -q`
- `python -B -m compileall autodev tests -q`
- `python -B -m pytest tests/test_full_roadmap_execution.py -q`
- `python -B -m pytest tests/test_document_to_plan.py -q`

## Billing Core Resume Note

The stale `final_verification_repair_resume_029.md` produced during diagnosis should not be reused because it focuses `T042-DEBUG-1`. With V2.160, the next controlled relaunch should write a newer resume that focuses root task `T042` and preserves T036-T041 before building the next graph.
