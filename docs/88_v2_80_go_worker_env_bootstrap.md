# V2.80 Go Worker Environment Bootstrap

## Objective

V2.80 makes the real Codex worker environment safer for Windows-hosted Go
repositories. The Billing Core recovery proved that prompt guidance alone was
not enough: the operator still had to inject `PATH`, `GOMODCACHE`,
`GOTOOLCHAIN`, `GOCACHE`, and `GOFLAGS` by hand before a resumed run could
verify Go code reliably.

That setup belongs in Alchemy because it is an execution-environment concern,
not a Billing Core product-code concern.

## Problem Evidence

The Billing Core run exposed several repeatable environment failures:

- `go` was not on the worker shell `PATH` even though a local Go install was
  available at `C:\Users\T14S\tools\go-1.26.3\go\bin\go.exe`;
- `backend/go.mod` requested a newer patch toolchain than the launcher binary,
  so workers needed `GOTOOLCHAIN=auto`;
- fresh worktree-local module caches triggered Windows rename
  `Access is denied` failures during module downloads;
- manually overriding `APPDATA` hid GitHub CLI authentication and caused a
  false preflight block.

## Design

`runtime.codex_worker._build_codex_subprocess_env()` now seeds Go-related
environment variables for real Codex worker subprocesses only.

The bootstrap:

- honors `ALCHEMY_DISABLE_GO_ENV_BOOTSTRAP=1` as an escape hatch;
- discovers Go from `ALCHEMY_GO_BIN`, `ALCHEMY_GO_EXE`, `ALCHEMY_GO_ROOT`,
  existing `PATH`, common user tool installs, and standard Go install paths;
- prepends the detected Go bin directory to the worker `PATH`;
- sets `GOTOOLCHAIN=auto` when the caller did not provide one;
- chooses a writable shared `GOMODCACHE`, preferring explicit overrides and
  known shared tool-cache locations;
- sets a worktree-local `.gocache-alchemy` build cache when no `GOCACHE` is
  already configured;
- sets `GOFLAGS=-p=1` only when the caller did not provide `GOFLAGS`.

The bootstrap deliberately does not override `APPDATA`, preserving GitHub CLI
authentication and other user-level tool state.

## Compatibility Contract

V2.80 does not change:

- worker JSON result schema;
- task graph scheduling semantics;
- sandbox mode;
- repository boundary auditing;
- global Go configuration;
- GitHub CLI authentication paths.

All Go environment changes are scoped to the worker subprocess environment.

## Acceptance Criteria

- real Codex worker environments can discover a local Go install that is not on
  `PATH`;
- a writable shared module cache is selected without requiring `go env -w`;
- a worktree-local Go build cache is available;
- `APPDATA` is preserved;
- the bootstrap can be disabled for unusual repositories;
- runtime tests cover both the enabled and disabled paths.

## Verification

Focused tests:

```powershell
python -B -m pytest tests/test_runtime.py::CodexWorkerTests::test_build_codex_subprocess_env_bootstraps_go_worker_environment tests/test_runtime.py::CodexWorkerTests::test_build_codex_subprocess_env_can_disable_go_bootstrap -q
```

Broader checkpoint:

```powershell
python -B -m pytest tests/test_runtime.py -q
python -B -m pytest tests/test_full_roadmap_execution.py -q
python -B -m py_compile runtime\codex_worker.py tests\test_runtime.py
git diff --check -- runtime/codex_worker.py tests/test_runtime.py README.md docs/88_v2_80_go_worker_env_bootstrap.md
```
