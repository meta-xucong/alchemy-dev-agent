# V2.73 Large Refactor Execution Mode

## Objective

V2.73 adds a first-class execution mode for product-scale repository
transformations while preserving the existing strict task-boundary behavior.

The immediate finding came from a Billing Core validation run where Alchemy was
asked to convert a token relay product into an independent identity, billing,
wallet, metering, and statistics service. The run proved that real Codex
workers could launch and produce useful edits, but the controller stopped before
delivery because its planning and boundary model was tuned for small scoped
tasks.

## Failure Summary

The failed validation showed three controller-side issues:

1. Document requirements that were really constraints became implementation
   tasks with no `relevant_files`.
2. Empty `relevant_files` became empty `allowed_files`, so workers were
   correctly told not to edit repository files and returned blocked/partial.
3. A later worker completed successfully, but the runtime state still showed
   the task as active. The worker had also produced a large Go cache directory,
   making the post-worker Git scan heavy and fragile.

This was not a GitHub authentication failure and not proof that the target
refactor was infeasible. It was a mismatch between the default task-boundary
strategy and a whole-repository migration.

## Compatibility Contract

The existing V2.15 boundary contract remains the default:

- architecture, review, and test tasks stay read-only;
- implementation tasks may edit only `relevant_files`;
- empty `allowed_files` means no repository edits;
- out-of-scope source changes are rolled back;
- explicit scope locks such as V3 Foundation `target_files` remain strict.

Large refactor behavior is available only when the runtime can justify it by
explicit mode or conservative auto-detection. Small repairs, central
auto-iteration, scoped V3 tasks, and document-only generated artifacts must keep
the old behavior.

## New Mode

`scope_controls.boundary_mode = "large_refactor"` means:

- Build one primary integration task that covers the whole product migration.
- Treat document constraints as acceptance criteria, not independent edit tasks.
- Use broad but repository-local write scopes instead of per-requirement
  `relevant_files`.
- Keep protected prefixes excluded.
- Run normal verification, review, GitHub delivery, artifact, and requirement
  coverage gates after the integration worker.

The integration task is still bounded. It does not mean "write anywhere on the
machine"; it means "write within the execution repository worktree according to
the derived repository-local allowlist."

## Write Scope Derivation

When explicit `target_files` or `allowed_prefixes` are supplied, they remain the
authoritative scope.

Otherwise large refactor mode derives a repository-local allowlist from common
project roots and tracked top-level files:

- source roots such as `backend/**`, `frontend/**`, `src/**`, `cmd/**`,
  `internal/**`, `pkg/**`, `server/**`, `runtime/**`, `autodev/**`;
- schema, migration, deploy, CI, docs, examples, scripts, and tests roots;
- package/config files such as `go.mod`, `go.sum`, `package.json`,
  `pnpm-lock.yaml`, `pyproject.toml`, `README.md`, `docker-compose*.yml`,
  `Makefile`, and `.github/**`.

If the derived scope is still empty, the mode falls back to `**` only inside an
isolated execution worktree and records that broad scope in worker evidence.

## Auto-Detection

Auto-detection is intentionally conservative. It may enable large refactor mode
when all of these signals are present:

- a real repository exists with source/package files;
- the request is document-driven, not a one-line generated artifact;
- the objective or documents include migration/refactor/product-conversion
  language such as `large refactor`, `whole-repository`, `standalone service`,
  `整仓`, `大型重构`, `整体改造`, `独立运行`, or `脱胎换骨`;
- the requirement set is broad enough that per-requirement file targeting would
  be unreliable.

Operators can still force the mode with `--boundary-mode large_refactor` or an
API/unified-run payload field of `"boundary_mode": "large_refactor"`. The value
is normalized into `scope_controls.boundary_mode`.

## Runtime Robustness

The worker boundary auditor must ignore deterministic local build caches that
are not source changes, including:

- `__pycache__`;
- `.alchemy` and `.alchemy_tmp`;
- `node_modules`;
- `pytest-cache-files-*`;
- test `_runtime_*` directories;
- Go cache directories such as `.gocache-*`;
- Ent scratch directories such as `.entc`.

Interrupted runs must not leave completed workers permanently marked active.
Recovery should reset active tasks to pending, and the next run should be able
to re-dispatch or finish with a normal report.

## Non-Goals

- Do not weaken default scoped repair behavior.
- Do not allow edits outside the execution repository.
- Do not bypass final verification, review, or delivery evidence.
- Do not hide failed tests or unresolved blockers.
- Do not automatically apply this mode to small feedback repairs.

## Acceptance Criteria

- Default document-driven runs still produce per-requirement implementation
  tasks with strict `allowed_files`.
- Scoped V3-style `target_files` runs still keep exact allowed files and
  protected prefixes.
- A broad product-conversion document produces one integration implementation
  task with `scope_controls.boundary_mode=large_refactor`.
- The large-refactor worker package includes broad repository-local
  `allowed_files` and large-refactor constraints.
- Constraint-only requirements with no target files do not create blocked
  empty-allowlist implementation tasks in large-refactor mode.
- Go cache and Ent scratch artifacts do not trigger boundary rollback.
- Recovery from an interrupted active task resets the task so a retained
  worktree can continue instead of staying active forever.

## Verification

Focused tests:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -m unittest tests.test_document_to_plan tests.test_runtime_handoff tests.test_runtime.CodexWorkerTests -v
```

Adjacent tests:

```powershell
python -B -m unittest tests.test_document_run_pipeline tests.test_unified_run.UnifiedRunTests.test_unified_request_serializes_document_run_kwargs -v
```

Static checks:

```powershell
python -B -m py_compile planner\task_graph_builder.py runtime\handoff.py runtime\orchestrator.py runtime\codex_worker.py autodev\document_run.py autodev\unified_request.py context\models.py context\builder.py context\requirement_extractor.py
python C:\Users\T14S\.codex\skills\long-running-task\scripts\validate_state.py --project .
git diff --check -- docs/81_v2_73_large_refactor_execution_mode.md planner/task_graph_builder.py runtime/handoff.py runtime/orchestrator.py runtime/codex_worker.py autodev/document_run.py autodev/unified_request.py context/models.py context/builder.py context/requirement_extractor.py tests/test_document_to_plan.py tests/test_runtime_handoff.py tests/test_runtime.py
```
