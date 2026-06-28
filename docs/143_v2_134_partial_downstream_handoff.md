# V2.134 Partial Downstream Handoff

## Problem

Billing Core final verification `run_attempt_008` completed T003 and made real scoped progress in T004 `Repair final backend domain and repository contracts`.

T004 returned `partial` because repository no-test compile was blocked by `internal/service/payment_config_plans.go`, a service-layer file already covered by direct downstream task T005. The runtime treated every `partial` as a failed current task, created `T004-DEBUG-1`, and reset T004 for retry. That wasted a worker slot and risked replaying scoped repository work instead of continuing to the service/handler/server repair task.

## Change

- Added a conservative runtime handoff path in `runtime/orchestrator.py`.
- A partial worker result is marked completed only when all of these are true:
  - the task is not a debug task;
  - the result is not an environment blocker or timeout;
  - the worker made scoped progress through changed files, passing tests, or passing commands;
  - path evidence from summary, failed checks, known issues, follow-up tasks, command output, or raw output matches a direct downstream task scope.
- Handoff evidence preserves the original partial result under `handoff_original_result`, records `partial_handoff_to`, and moves old failing checks into `tests_deferred_to_downstream` so final evaluation is not polluted by a failure that belongs to the downstream task.
- Added matching final-verification resume handling in `autodev/full_roadmap_executor.py` so historical attempts like `run_attempt_008` preserve partial-handoff tasks when generating the next repair resume.

## Verification

- Focused runtime handoff tests passed.
- Adjacent debug, timeout, and non-partial blocker regressions passed.
- Full `tests/test_runtime.py` passed.
- Full `tests/test_full_roadmap_execution.py` passed.
- `compileall` and `git diff --check` passed.
- Real Billing Core resume probe generated `final_verification_repair_resume_004.md` and graph construction confirmed T001-T004 are completed with T005 ready.

## Recovery Impact

The corrected next final-verification graph starts at T005 `Repair final backend service handler server contracts`, not T004 or `T004-DEBUG-1`. Codex Desktop still only monitors and fixes Alchemy; the CRM product repair remains assigned to Alchemy workers in the inherited Billing Core worktree.
