# V2.74 Alchemy Stability Hardening

## Objective

V2.74 hardens Alchemy Dev Agent before any further Billing Core resume. The
goal is to make the controller behave more like a human supervisor when a large
frontend or product migration hits environment, boundary, or debug-loop
problems.

Billing Core Phase 7 exposed that Alchemy could make useful progress, but still
spent too many worker runs on issues that should have been resolved by the
controller:

- frontend verification ran before dependencies were installed;
- a pnpm-locked frontend was planned with npm commands;
- debug evidence that clearly described an environment setup gap was retried as
  implementation work;
- a failed debug branch could be collapsed, but the parent task was retried
  without a more useful setup or blocker decision;
- frontend large-refactor tasks were still wide enough to burn large worker
  budgets when their verification preconditions were missing.

## Compatibility Contract

The default strict task-boundary model remains intact:

- small scoped tasks still edit only their `relevant_files`;
- documentation, review, and deterministic test tasks remain read-only unless a
  specific deterministic handler owns the work;
- out-of-scope source changes are still rolled back;
- generated cache/dependency directories such as `node_modules` remain ignored
  for boundary auditing, not treated as source edits;
- existing npm-only projects continue to use npm commands.

The new behavior is limited to package-manager-aware planning, frontend
verification setup, and debug convergence when evidence proves that repeated
worker attempts would not add implementation value.

## Design

### Package Manager Detection

Repository indexing must treat lockfiles as package evidence:

- `pnpm-lock.yaml` selects pnpm;
- `yarn.lock` selects yarn;
- `bun.lockb` selects bun;
- `package-lock.json` or no lockfile keeps npm.

For nested packages, a lockfile in the package directory wins. A repository-root
lockfile can also govern nested frontend packages.

### Verification Command Planning

When a package script is discovered, Alchemy should emit commands for the
detected package manager:

- npm: `npm --prefix frontend test`;
- pnpm: `pnpm --dir frontend test`;
- yarn: `yarn --cwd frontend test`;
- bun: `bun --cwd frontend run test`.

Frontend large-refactor implementation tasks should prepend an idempotent
dependency setup command before tests when the package manager requires local
dependencies:

- pnpm: `pnpm --dir frontend install --frozen-lockfile`;
- npm: `npm --prefix frontend install`;
- yarn: `yarn --cwd frontend install --frozen-lockfile`;
- bun: `bun --cwd frontend install`.

The setup command is verification setup, not a request to modify manifests.
Lockfile or manifest drift remains disallowed unless those files are explicitly
in the task scope.

### Debug Convergence

When debug evidence says verification cannot run because dependencies or a test
runner are missing, the scheduler should record an environment blocker on the
root task instead of launching another implementation retry.

Examples include:

- `node_modules is missing`;
- `vitest is not recognized`;
- `frontend dependencies are absent`;
- `test runner unavailable`;
- `dependencies are not installed`.

This should not disable legitimate debug repair promotion. A completed debug
task with clean verification can still promote a failed parent, and a
non-environment partial can still lead to one bounded parent retry.

## Acceptance Criteria

- pnpm-locked frontend repositories produce pnpm test/build/lint commands.
- npm-only repositories keep npm commands.
- frontend large-refactor tasks include dependency setup before frontend tests.
- dependency setup commands are de-duplicated and do not appear for unrelated
  backend-only tasks.
- debug evidence for missing frontend dependencies blocks the root task with a
  clear environment blocker instead of spawning or retrying more worker work.
- existing debug promotion, nested debug collapse, filename-glob boundary
  matching, and runtime worker lifecycle tests continue to pass.

## Verification

Focused tests:

```powershell
python -B -m pytest tests/test_repository_context.py tests/test_document_to_plan.py::DocumentToPlanTests::test_large_refactor_frontend_phase_uses_pnpm_lock_commands tests/test_runtime.py::OrchestratorTests::test_debug_environment_blocker_blocks_parent_without_retry -q
```

Adjacent runtime tests:

```powershell
python -B -m pytest tests/test_runtime.py::CodexWorkerTests::test_real_worker_allows_filename_glob_scope tests/test_runtime.py::OrchestratorTests::test_failed_debug_task_resets_parent_without_nested_debug_loop tests/test_runtime.py::OrchestratorTests::test_completed_nested_debug_evidence_promotes_failed_parent_and_continues -q
```

Broader checkpoint:

```powershell
python -B -m pytest tests/test_repository_context.py tests/test_document_to_plan.py tests/test_runtime.py -q
python -B -m py_compile context\repository_indexer.py planner\task_graph_builder.py runtime\orchestrator.py tests\test_repository_context.py tests\test_document_to_plan.py tests\test_runtime.py
git diff --check -- docs/82_v2_74_alchemy_stability_hardening.md README.md context/repository_indexer.py planner/task_graph_builder.py runtime/orchestrator.py tests/test_repository_context.py tests/test_document_to_plan.py tests/test_runtime.py
python C:\Users\T14S\.codex\skills\long-running-task\scripts\validate_state.py --project .
```
