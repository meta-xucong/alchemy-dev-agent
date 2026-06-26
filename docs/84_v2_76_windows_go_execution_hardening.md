# V2.76 Windows Go Execution Hardening

## Objective

V2.76 hardens the real Codex worker prompt for Windows-hosted Go repositories so
the worker wastes fewer iterations on environment-shape mistakes that are
predictable from repository evidence.

The Billing Core resume on 2026-06-26 exposed three gaps that remained after
V2.75:

- the worker still assumed the repository root was the Go module root even when
  the active `go.mod` lived under `backend/`;
- PowerShell-safe search guidance existed, but the worker still tried
  `go test -run` commands whose inline regex alternation used `|`, which
  PowerShell parsed as shell syntax instead of test-filter text;
- the worker switched from a known-good shared `GOMODCACHE` to a fresh local
  module cache and then launched multiple `go test` processes in parallel,
  which triggered Windows temp-file rename `Access is denied` failures while Go
  downloaded modules concurrently.

These are execution-strategy failures, not product-code failures. They should be
prevented by the worker contract before a long run burns more tokens.

## Compatibility Contract

V2.76 does not change:

- task packaging;
- sandbox behavior;
- worker JSON result schema;
- repository-boundary rules;
- non-Go repository behavior;
- non-Windows repository behavior.

The only behavior change is stronger worker-prompt guidance for Windows-hosted
Go verification.

## Design

### Go Module Root Confirmation

Before running `go test` or `go build`, the worker must confirm the active
module root from repository evidence instead of assuming the repository root is
the module root.

When the relevant module is nested, the prompt should explicitly steer the
worker toward forms such as:

```powershell
cd backend && go test ./...
```

### PowerShell-Safe `go test -run`

The worker prompt already warns about unescaped `|` in inline shell commands,
but the Billing Core run showed that this warning was not concrete enough for Go
test filters.

The prompt must now state a Go-specific rule:

- on Windows PowerShell, do not send alternation like `|` through inline
  `go test -run` commands;
- prefer separate `go test -run ^TestName$` commands or another shell-safe
  formulation.

### Stable Go Cache Strategy

The worker prompt must treat Go cache selection as a Windows stability concern:

- prefer a known-writable, already populated `GOMODCACHE` when one exists;
- do not create multiple parallel `go test` processes against a fresh shared
  module cache;
- if a cold cache must be used, warm it or run sequentially before any
  parallelized verification.

This keeps the worker from converting module download/setup problems into fake
code failures.

## Acceptance Criteria

- the worker prompt tells Codex to confirm the active Go module root from
  repository evidence before running Go verification;
- the prompt includes a nested-module example such as
  `cd backend && go test ./...`;
- the prompt contains a Go-specific Windows PowerShell rule against inline
  `-run` alternation with `|`;
- the prompt tells Codex to prefer an existing writable `GOMODCACHE`;
- the prompt forbids parallel `go test` runs against a fresh shared module
  cache on Windows;
- prompt-contract tests cover the new Windows Go guidance.

## Verification

Focused tests:

```powershell
python -B -m pytest tests/test_runtime.py::CodexWorkerTests::test_worker_prompt_includes_windows_powershell_command_hygiene tests/test_runtime.py::CodexWorkerTests::test_worker_prompt_includes_windows_go_execution_hardening -q
```

Broader checkpoint:

```powershell
python -B -m py_compile runtime/codex_worker.py tests/test_runtime.py
git diff --check -- runtime/codex_worker.py tests/test_runtime.py README.md docs/84_v2_76_windows_go_execution_hardening.md
```
