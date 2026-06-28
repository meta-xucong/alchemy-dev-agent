# V2.126 Final Verification Worktree Inheritance

## Problem

After all twelve Billing Core roadmap phases promoted, V2.125 allowed the final
verification worker to run. The worker still failed before executing audit work
because it attempted real-run worktree preparation from the original repository
path instead of using the last completed full-roadmap worktree.

The final report showed:

- all roadmap phases completed
- final verification worker started
- final verification attempt blocked at `B-WORKTREE`
- `FINAL_AUDIT_STATUS`, `SIMULATION_TEST_STATUS`, and `REAL_TEST_STATUS` were
  missing because the audit worker never reached the real verification task

This was an Alchemy orchestration issue, not a CRM product-code failure.

## Fix

The final verification worker now uses the same inherited-worktree selection as
normal later roadmap phases:

- choose the last completed phase runtime/workspace repository path with
  `phase_repository_path`
- pass that path to the document runner
- disable fresh isolated worktree creation when the inherited path differs from
  the original repository path

This keeps final audit execution on the actual Billing Core CRM worktree that
contains all promoted phase changes.

## Verification

- Focused regression: final verification worker receives the last completed
  phase worktree path and runs with `isolate_real_run=False`.
- Focused max-phase final-audit regression still passes.
- Full `tests/test_full_roadmap_execution.py`.
- `compileall`.
- `git diff --check`.
