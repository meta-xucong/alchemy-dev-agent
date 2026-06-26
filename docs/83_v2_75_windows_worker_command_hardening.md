# V2.75 Windows Worker Command Hardening

## Objective

V2.75 hardens the real Codex worker prompt for Windows PowerShell runs so large
repository migrations waste fewer tokens on shell-formulation mistakes.

The Billing Core resume on 2026-06-26 showed a specific gap that V2.74 did not
cover. The controller had already improved package-manager detection and debug
convergence, but the worker could still spend meaningful effort on avoidable
Windows command issues inside a single run:

- wildcard paths such as `backend/internal/handler/admin/*test.go` were passed
  to `rg` as literal file arguments, causing Windows path syntax errors;
- `Select-Object -Index 330..470` was used as if it accepted a range literal,
  causing a PowerShell parameter-conversion failure;
- guessed paths were opened directly without first confirming them from
  repository evidence;
- inline commands with regex alternation such as `|` risked being parsed by the
  shell instead of being treated as search input.

These failures do not usually require a new task graph, a new debug branch, or
more repository reasoning. They are command-hygiene misses inside the worker.

## Compatibility Contract

V2.75 does not change:

- task graph semantics;
- retry or debug promotion rules;
- file-boundary enforcement;
- package-manager-aware verification planning from V2.74;
- deterministic dry-run behavior;
- non-Windows repository support.

The only behavior change is the worker instruction contract. Real Codex workers
now receive explicit Windows PowerShell guidance for path discovery, glob-safe
search, line-range reads, and shell-safe regex usage.

## Design

### Repository Path Confirmation

Before directly reading or patching a file whose path is uncertain, the worker
should confirm the actual path from repository evidence such as:

- `rg --files`
- `rg -n`

This reduces hallucinated reads against nonexistent files such as legacy or
wrongly named DTO/helper modules.

### PowerShell-Safe Search Forms

The worker prompt must tell Codex not to hand wildcard paths directly to
commands that expect literal file arguments.

Preferred approaches:

- search a directory tree directly;
- use `rg --glob "*test.go" pattern backend/internal/handler/admin`;
- avoid `Get-Content` on guessed wildcard-like paths.

### PowerShell-Safe Line Range Reads

The worker prompt must explicitly steer away from:

```powershell
Get-Content path | Select-Object -Index 330..470
```

and toward:

```powershell
$lines = Get-Content path
$lines[330..470]
```

### Shell-Parsing-Aware Regex Commands

The worker prompt must tell Codex that inline commands containing unescaped `|`
can be misparsed by PowerShell. When a simpler split command is available, the
worker should prefer that instead of risking shell interpretation.

### Failure Interpretation

The worker prompt must make one classification rule explicit:

- shell globbing, quoting, and path-syntax errors are command-formulation
  problems first;
- they should be reformulated before the worker concludes anything about the
  repository.

## Acceptance Criteria

- the worker prompt explicitly tells Codex to confirm uncertain paths with
  repository evidence such as `rg --files` or `rg -n`;
- the worker prompt explicitly mentions Windows PowerShell command hygiene;
- the worker prompt tells Codex not to use wildcard paths as literal arguments
  to `rg` or `Get-Content`;
- the worker prompt documents the safe line-range pattern using
  `$lines[start..end]` instead of `Select-Object -Index start..end`;
- the worker prompt warns about unescaped `|` in inline shell commands;
- existing prompt-contract tests and real-worker adapter tests continue to pass.

## Verification

Focused tests:

```powershell
python -B -m pytest tests/test_runtime.py::CodexWorkerTests::test_worker_prompt_allows_dependency_installs_without_manifest_drift tests/test_runtime.py::CodexWorkerTests::test_worker_prompt_includes_windows_powershell_command_hygiene -q
```

Broader checkpoint:

```powershell
python -B -m pytest tests/test_runtime.py -q
python -B -m py_compile runtime/codex_worker.py tests/test_runtime.py
git diff --check -- runtime/codex_worker.py tests/test_runtime.py README.md docs/83_v2_75_windows_worker_command_hardening.md
```
