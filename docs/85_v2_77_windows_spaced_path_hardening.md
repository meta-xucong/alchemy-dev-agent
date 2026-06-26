# V2.77 Windows Spaced-Path Hardening

## Objective

V2.77 hardens the real Codex worker prompt for Windows environments where the
repository root or helper-script paths contain spaces.

The 2026-06-25/2026-06-26 recovery audit exposed a repeated command-shape gap
that remained after V2.75 and V2.76:

- `validate_state.py --project D:\AI\Alchemy Dev Agent System\alchemy-dev-agent`
  was emitted without quoting the spaced path, so PowerShell split the
  argument and argparse rejected `Dev Agent System\alchemy-dev-agent`;
- hidden relaunch attempts for `resume_billing_core_001.ps1` also showed that
  unquoted script paths can fail even when the underlying recovery logic is
  otherwise correct.

These failures are not repository-understanding problems. They are Windows
command-construction mistakes that should be prevented by the worker contract.

## Compatibility Contract

V2.77 does not change:

- task graph semantics;
- worker JSON result schema;
- retry or debug convergence rules;
- non-Windows behavior;
- repository-boundary rules.

The only behavior change is stronger worker guidance for Windows commands that
need to pass spaced filesystem paths.

## Design

### Quote Spaced Windows Paths

The worker prompt must explicitly tell Codex to quote Windows paths that
contain spaces before passing them to scripts or flags such as `--project`.

Examples:

```powershell
python "C:\Users\T14S\.codex\skills\long-running-task\scripts\validate_state.py" --project "D:\AI\Alchemy Dev Agent System\alchemy-dev-agent"
```

```powershell
& "D:\AI\Alchemy Dev Agent System\alchemy-dev-agent\.alchemy\billing_core_v274_20260624_012\resume_billing_core_001.ps1"
```

### Prefer Working-Directory-Aware Forms

When a command can operate relative to the working directory, the worker should
prefer that over embedding a long absolute path with spaces.

Preferred example:

```powershell
python "C:\Users\T14S\.codex\skills\long-running-task\scripts\validate_state.py" --project .
```

This lowers quoting complexity and reduces token waste on command repair.

### Failure Interpretation

The worker prompt must make one classification rule explicit:

- quoting failures around spaced paths are command-formulation problems first;
- the worker should reformulate the command before concluding anything about
  the repository or supervisor state.

## Acceptance Criteria

- the worker prompt explicitly tells Codex to quote Windows paths that contain
  spaces;
- the prompt references spaced paths passed to scripts or flags such as
  `--project`;
- the prompt tells Codex to prefer a working-directory-aware form when one is
  available;
- prompt-contract tests cover the new spaced-path guidance.

## Verification

Focused tests:

```powershell
python -B -m pytest tests/test_runtime.py::CodexWorkerTests::test_worker_prompt_includes_windows_powershell_command_hygiene tests/test_runtime.py::CodexWorkerTests::test_worker_prompt_includes_windows_spaced_path_hardening -q
```

Broader checkpoint:

```powershell
python -B -m pytest tests/test_runtime.py -q
python -B -m py_compile runtime/codex_worker.py tests/test_runtime.py
git diff --check -- runtime/codex_worker.py tests/test_runtime.py README.md docs/85_v2_77_windows_spaced_path_hardening.md
```
