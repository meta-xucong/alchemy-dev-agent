# V2.135 Timeout False Positive And Reopen

## Problem

Billing Core final verification `run_attempt_009` resumed correctly after V2.134 and started at T005. The worker made real service-layer progress and returned `partial`, not timeout:

- `backend/internal/service/payment_config_plans.go` was updated.
- targeted service, handler, and server no-test checks passed.
- command-package verification was blocked by `backend/internal/repository/account_repo.go`, which is outside T005 scope.

Alchemy still recorded a timeout blocker because timeout detection scanned broad worker text and matched the supervision constraint that says worker timeout is a stop boundary. The next resume also needed to reopen the preserved repository task when a later task found a repository-scoped blocker.

## Change

- Narrowed `_worker_result_timed_out` in `runtime/orchestrator.py`.
  - It trusts structured lifecycle timeout fields and the worker result summary.
  - It no longer scans raw output, evidence, or prompt context for timeout phrases.
  - Explicit `status=timed_out` is still treated as a timeout for compatibility.
- Updated `autodev/full_roadmap_executor.py` repair-resume preservation.
  - Completed task IDs are reopened when unresolved later repair evidence names files inside their relevant scope.
  - This lets final verification return from T005 to T004 when T005 reveals a remaining repository caller such as `backend/internal/repository/account_repo.go`.

## Verification

- Focused runtime false-positive and real-timeout regressions passed.
- Focused final-verification resume reopen regressions passed.
- Full `OrchestratorTests` passed.
- Full `tests/test_full_roadmap_execution.py` passed.
- `compileall` and `git diff --check` passed.
- Real Billing Core resume probe generated `final_verification_repair_resume_005.md`; graph construction confirmed T001-T003 are completed and T004 is ready.

## Recovery Impact

The next controlled Billing Core final-verification run should repair repository residuals at T004 before re-entering T005. Codex Desktop remains supervisor-only; product code changes continue to be made by Alchemy workers in the inherited worktree.
