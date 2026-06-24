# V2.69 Runtime Artifact Boundary Hardening

## Objective

Keep full-roadmap execution moving when a target project's tests generate deterministic runtime artifacts inside the declared project scope.

The original goal remains unchanged:

```text
user supplies objective/docs/repository
-> Alchemy Dev Agent extracts the full roadmap
-> Codex workers implement each phase
-> tests and central review run after each phase
-> false blockers are removed automatically
-> execution stops only at final completion or a real blocker
```

## Real-Run Finding

During the `alchemy-media-agent` V3 full-roadmap validation, phase `V3.5 Product API and Minimal UX` implemented successfully and the target test suite passed:

```text
66 tests passed
```

However, pytest and V3-owned brand-memory tests generated runtime files such as:

```text
alchemy_creative_agent_3_0/tests/_runtime_product_api/select_.../brands/brand_product_api.json
pytest-cache-files-.../
```

The boundary auditor treated those files as unauthorized changes, rolled them back, and triggered repeated debug tasks. This was a controller false blocker, not a target-project implementation failure.

## Required Behavior

- Generated test runtime artifacts must not fail task-boundary auditing.
- V3 implementation boundaries must remain strict for real source, docs, API, UI, and protected V1/V2 paths.
- Test artifacts under `*/tests/_runtime_*/*` are treated as generated evidence.
- Root-level `pytest-cache-files-*` directories are treated like pytest/cache artifacts.
- Passing test evidence must be allowed to promote the phase when no real source boundary violation exists.

## Non-Goals

- Do not allow edits to V1/V2, Alchemy Lab, or protected legacy paths.
- Do not allow arbitrary files under `tests/`; only generated `_runtime_*` test-output directories are ignored.
- Do not weaken the rollback behavior for genuine out-of-scope source changes.

## Verification

Focused regression:

```bash
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest tests.test_runtime.CodexWorkerTests.test_real_worker_ignores_test_runtime_artifacts_for_boundary_audit -v
```

Relevant broader checks:

```bash
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest tests.test_runtime.CodexWorkerTests -v
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest tests.test_full_roadmap_execution tests.test_runtime_handoff -v
```
