# V2.88 Focused Phase Repair Resume

## Objective

V2.88 makes full-roadmap phase recovery narrower after a blocked Alchemy run.
When a phase stops on a repairable technical blocker, the next resume now
starts with the prior blocker evidence instead of planning from only the
original broad phase requirements.

## Problem Evidence

Billing Core `phase_010` reached `run_attempt_023` with T001-T005 completed and
T006 blocked:

- `B-T006-2` reported retry exhaustion for the user API key/admin usage
  workflow.
- The task-local frontend checks passed.
- Full frontend tests and typecheck still failed in files outside the task's
  allowed scope, such as `AccountUsageCell`, `EmailVerifyView`, `UsageTable`,
  `usePersistedPageSize`, and `DashboardView`.

That is a legitimate product blocker, but it exposed two controller problems:

- A resumed blocked phase could enter the next attempt with only the original
  phase document, which encourages a broad task graph instead of a T006-focused
  repair.
- The blocker classifier treated any description containing `api key` or `auth`
  as a non-repairable credential problem. In this case those words described
  product features, not missing external credentials.

## Design

`FullRoadmapExecutor` now captures the previous blocked `PhaseExecutionRecord`
before removing it from the active record list. If the previous blocker is
autonomously repairable and phase repair attempts are enabled, the executor
writes `phase_repair_resume_NNN.md` and includes it in the first resumed phase
attempt.

New ordinary repair briefs use the next available `phase_repair_NNN.md` path so
older repair briefs in a long-running phase directory are preserved.

Repair documents now include a focused repair section with:

- primary failed task IDs from blocker `task_ids`;
- completed phase tasks that should be preserved;
- latest worker summary, tests passed, tests failed, known issues, follow-up
  tasks, changed files, retry state, and relevant files;
- instructions to create focused follow-up tasks for out-of-scope full-suite
  failures;
- timeout guidance that treats hard timeout as a stop boundary, then favors
  checkpointing or task splitting before increasing worker budgets.

The non-repairable blocker markers were narrowed from bare `api key` and `auth`
to credential-shaped phrases such as `missing api key`, `api key required`,
`auth required`, and `authentication required`.

## Compatibility Contract

V2.88 does not allow workers to continue past runtime non-partial blockers.
Runtime orchestration still stops. The change only improves the parent
full-roadmap handoff into a new phase attempt.

V2.88 also does not make Codex Desktop edit Billing Core product files directly.
CRM product work must still be performed by Alchemy workers inside the isolated
worktree.

## Billing Core Impact

The next supervised Billing Core resume should start `phase_010` from the
current inherited worktree and provide a focused repair brief for T006. The
expected next product scope is not "redo all frontend closure"; it is to turn
the out-of-scope full-suite/typecheck failures into narrower Alchemy tasks with
the required files explicitly in scope.

Current CRM status remains partial:

- identity, wallet, recharge, redeem, usage, and admin foundations have
  accumulated in the Alchemy worktree;
- frontend closure is still incomplete at T006;
- schema pruning, final demo smoke, and authoritative worktree handoff remain
  open delivery gates.

## Verification

Focused checks:

```powershell
python -B -m pytest tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_phase_repair_document_path_preserves_existing_repair_briefs tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_phase_repair_document_includes_focused_failed_task_evidence tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_executor_bootstraps_blocked_phase_resume_with_repair_evidence tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_phase_repair_distinguishes_technical_and_environment_blockers -q
```

Regression:

```powershell
python -B -m pytest tests/test_full_roadmap_execution.py -q
python -B -m py_compile autodev\full_roadmap_executor.py tests\test_full_roadmap_execution.py
```
