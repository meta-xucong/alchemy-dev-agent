# V2.112 Schema Migration Checkpoint Split

## Problem

V2.111 split the combined migration/server task, but the migration-only task
`Align Ent migration contracts` still timed out in `run_attempt_008`.

The parent wrote `phase_repair_004.md`, then relaunched `run_attempt_009` with
the same migration-only T003 scope. Codex Desktop stopped it before another full
900 second worker window was spent.

At this point the scope was already narrowed to `backend/ent/migrate/**` and
`backend/go.mod`, so another directory split was not useful. The repair needed
a checkpoint-style split.

## Fix

Focused schema/build T003 timeout repairs now produce checkpoint tasks instead
of replaying the same migration task:

- `Inventory Ent migration contract deltas`
- `Patch Ent migration contract deltas`
- `Align server and domain table contracts`

The inventory and patch tasks are restricted to
`backend/ent/migrate/schema.go` and `backend/go.mod` so previous broad
repair evidence cannot expand them.

## Verification

- `tests/test_document_to_plan.py::DocumentToPlanTests::test_schema_migration_timeout_repair_splits_timed_out_contract_task_again`
- `tests/test_document_to_plan.py::DocumentToPlanTests::test_schema_migration_contract_timeout_repair_adds_checkpoint_tasks`
- Real phase_011 graph probe using `phase_repair_004.md`.
- `python -B -m pytest tests/test_document_to_plan.py -q`
- `python -B -m pytest tests/test_full_roadmap_execution.py -q`
- `python -B -m pytest tests/test_runtime_handoff.py -q`
- `python -B -m compileall planner tests -q`

The real graph now starts the next repair at
`Inventory Ent migration contract deltas`, followed by
`Patch Ent migration contract deltas`.
