# V2.86 Package Lock Boundary Expansion

## Problem

Billing Core `run_attempt_020` proved that the real Codex worker chain was
finally entering the correct inherited worktree, but T002 failed before Alchemy
could use the worker's structured result. The worker touched
`frontend/pnpm-lock.yaml` while the generated task boundary only listed
`frontend/package.json`, so Alchemy rolled the change back as out-of-scope.

That was a framework boundary mismatch. A task that explicitly allows a package
manifest and asks the worker to install or verify dependencies must also allow
the package manager's same-directory lockfile companion.

## Fix

`runtime.orchestrator.Orchestrator._allowed_files_for_task()` now expands
`package.json` entries with common lockfile companions in the same directory:

- `pnpm-lock.yaml`
- `package-lock.json`
- `npm-shrinkwrap.json`
- `yarn.lock`
- `bun.lockb`

The expansion happens before worker input is built, so the worker prompt and
the post-run boundary audit share the same allowed file list.

## Verification

- Added `test_worker_inputs_expand_package_lockfile_boundaries`.
- Preserved `test_worker_inputs_include_file_boundaries`.
- Full `tests/test_runtime.py` passed.
- Full `tests/test_full_roadmap_execution.py` passed.
- `py_compile` and `git diff --check` passed.

## Operational Notes

The next Billing Core attempt should no longer treat
`frontend/pnpm-lock.yaml` as an out-of-scope file when the task already allows
`frontend/package.json`.
