# V2.89 Repair Scope Handoff

## Objective

V2.89 fixes the next Billing Core recovery gap found after V2.88: repair
documents contained the right evidence, but the planner still collapsed the next
phase attempt into the same narrow `frontend/package.json` plus router task.

## Problem Evidence

The supervised V2.88 probe created `phase_010/run_attempt_024` and then
`run_attempt_025`.

The repair evidence was good:

- `phase_repair_resume_001.md` preserved T006 blocker evidence.
- `phase_repair_003.md` named the remaining out-of-scope frontend failures:
  `AccountUsageCell`, `UsageTable`, `EmailVerifyView`,
  `usePersistedPageSize`, `DashboardView`, router/sidebar wiring, and the
  backend insufficient-balance follow-up.

The task graph was not good:

- T002 was still `Implement scoped V3 foundation target files`.
- T002 was assigned to `backend` even though the phase is frontend closure.
- T002 used `boundary_mode=strict`.
- T002 relevant files were only `frontend/package.json` and
  `frontend/src/router/index.ts`.
- T002 implementation commands included both frontend tests and Go backend
  tests.

This made the run look like it was starting over. It was not intentional
from-scratch replanning; it was a planner handoff bug.

## Root Causes

Two Alchemy planner/parser issues combined:

- Natural-language repair text such as "in allowed scope" could put the scope
  parser into allowed-mode, and later path-bearing lines such as "Previous
  relevant files" were misread as global allowed paths.
- `_implementation_nodes()` handled scoped targets before `large_refactor`, so
  any scoped file evidence short-circuited frontend large-refactor
  decomposition.

A smaller extraction gap also mattered: `.vue` files were not recognized by the
explicit-path matcher, so repair docs could mention Vue files without those
paths becoming planner evidence.

## Design

V2.89 changes the planning path as follows:

- Repair narrative lines no longer seed global scope controls just because they
  mention allowed/protected scope words.
- Bullet `Target files:` feedback still seeds requirement-level related files,
  but it no longer becomes a graph-wide scope contract.
- `.vue` paths are now recognized by explicit path extraction.
- Frontend `large_refactor` phases no longer collapse into the generic scoped
  T002 path. Documentation-only scopes still keep the lightweight scoped
  documentation task.
- If a frontend large-refactor phase inherits stale file-level frontend scopes,
  the planner relaxes them to `frontend/` while preserving protected paths.
- The usage/API-key/admin user workflow task now includes the failure files
  exposed by Billing Core's full frontend suite.
- `supervisor_stop.json` and `operator_stop.json` are treated as terminal
  recovery markers for a run attempt, so a manually stopped bad attempt is not
  reused as a resume source.

## Timeout Follow-Up

The fixed `max_worker_seconds` budget remains useful as a burn-rate guard. The
current protection is now:

- a timeout records a non-partial technical blocker;
- debug timeout does not replay the same parent task;
- repair docs instruct workers to split or checkpoint wide tasks before raising
  budgets.

This is better than unlimited execution, but still not fully progress-aware.
The later timeout optimization should add explicit worker heartbeats, artifact
checkpoints, and bounded grace only when files/tests/evidence are still moving.
It should not silently turn hard timeouts into unbounded runs.

## Billing Core Impact

Rebuilding the current `phase_010` inputs after this fix produces seven
frontend `large_refactor` implementation tasks:

- router/menu/direct pages;
- frontend API service references;
- wallet/recharge/payment/order surfaces;
- redeem code pages;
- usage/API-key/admin user workflows;
- product copy and i18n;
- remaining frontend closure requirements.

The usage task now includes:

- `frontend/src/components/account/**`;
- `frontend/src/components/admin/usage/**`;
- `frontend/src/components/layout/AppSidebar.vue`;
- `frontend/src/composables/**`;
- `frontend/src/router/index.ts`;
- `frontend/src/views/admin/DashboardView.vue`;
- `frontend/src/views/auth/**`.

The next Billing Core launch should therefore continue in the inherited
isolated worktree with focused frontend repair tasks instead of replaying the
same narrow router/package task.

## Verification

Focused checks:

```powershell
python -B -m pytest tests/test_document_to_plan.py::DocumentToPlanTests::test_repair_narrative_allowed_scope_does_not_seed_scope_controls tests/test_document_to_plan.py::DocumentToPlanTests::test_large_refactor_frontend_repair_docs_do_not_collapse_to_scoped_router_task tests/test_document_to_plan.py::DocumentToPlanTests::test_large_refactor_frontend_phase_survives_repository_index_cap tests/test_document_to_plan.py::DocumentToPlanTests::test_docs_only_scope_builds_documentation_task_with_lightweight_verification -q
python -B -m pytest tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_supervisor_stopped_active_phase_attempt_is_not_resumed tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_interrupted_active_phase_attempt_is_resumable tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_terminal_active_phase_attempt_is_not_resumed tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_dead_debug_active_phase_attempt_is_not_resumed -q
```

Regression:

```powershell
python -B -m pytest tests/test_document_to_plan.py -q
python -B -m py_compile context\requirement_extractor.py planner\task_graph_builder.py autodev\full_roadmap_executor.py tests\test_document_to_plan.py tests\test_full_roadmap_execution.py
```
