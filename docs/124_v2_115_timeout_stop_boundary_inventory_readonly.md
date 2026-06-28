# V2.115 Timeout Stop Boundary and Read-Only Inventory

## Problem

Billing Core `phase_011/run_attempt_013` correctly used the V2.114 split graph, but
`T006 Inventory Ent regeneration inputs` still timed out after 900 seconds. The
full-roadmap parent then launched `run_attempt_014` with the same T006 scope,
despite the non-partial worker-timeout blocker.

The inventory task also inherited heavy backend verification commands and editable
file scope, so a checkpoint worker could behave like an implementation worker.

## Fix

- Full-roadmap phase loops now treat non-partial Codex worker timeouts as an
  attempt-level stop boundary. They may write a repair brief, but they do not
  launch another attempt in the same parent loop.
- Schema/build inventory tasks now carry no heavy verification commands.
- Runtime worker packaging treats no-command inventory/checkpoint tasks as
  read-only: relevant files remain visible, but `allowed_files` is empty and the
  worker prompt explicitly forbids edits and unlisted heavy build/test commands.

## Verification

- Focused planner/runtime/full-roadmap regressions: `5 passed`.
- `tests/test_document_to_plan.py`: `30 passed`.
- `tests/test_full_roadmap_execution.py`: `71 passed`.
- `tests/test_runtime.py`: `133 passed`.
- Real phase_011 graph/worker-package probe: T006 has `commands=[]`,
  `allowed_files=[]`, and read-only inventory constraints.
