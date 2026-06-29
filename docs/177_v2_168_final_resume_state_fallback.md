# V2.168 Final Verification State Fallback

## Problem

After V2.167, the final-verification parent correctly stopped at a non-partial blocker. A controlled relaunch then exposed a resume-context problem: the latest failed report could come from a supervisor-stopped replay attempt, while the useful failure evidence lived in an earlier attempt state.

In the Billing Core run, `run_attempt_041` was stopped because it replayed already completed T051-T055 work. The real repair target was still `run_attempt_039` / T056, where the worker had completed but boundary audit failed on frontend test allowlist matching.

## Change

- `final_verification_resume_repair_documents` now checks the latest failed attempt state as a fallback source.
- If the latest worker report points to an operator/supervisor-stopped environment attempt, Alchemy falls back to the newest failed attempt state with concrete blockers.
- Supervisor stop markers no longer disqualify a state that already contains a useful technical blocker, such as a boundary failure.
- Added `failed_task_ids_from_state` and final-verification state filtering helpers.

## Verification

- `tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_final_verification_resume_uses_latest_non_stopped_failed_state`
- Real Billing Core helper probe generated `final_verification_repair_resume_036.md` with:
  - `Repair attempt: run_attempt_039`
  - `Primary failed task IDs: T056`
  - completed task preservation through the final-verification chain

## Expected Billing Core Impact

The next controlled final-verification relaunch should consume `final_verification_repair_resume_036.md`, preserve T051-T055, and resume at T056 instead of replaying the already completed composable and utility repair tasks.
