# V2.109 Schema Prune Second Timeout Split

## Problem

After V2.108, Billing Core phase_011 no longer regenerated the original broad
`Implement large refactor integration` worker. The next repair attempt correctly
split schema/build work, but `T002 Prune legacy Ent schemas and table contracts`
still timed out after 900 seconds.

The parent then wrote `phase_repair_002.md` and relaunched another attempt with
the same `Prune legacy Ent schemas and table contracts` scope. Codex Desktop
supervision stopped that attempt before another full worker window was spent.
This was not a completed phase; it was a guarded stop to avoid a same-scope
timeout loop.

## Fix

`planner/task_graph_builder.py` now performs a second-level split when a
large-refactor schema/build repair identifies failed task `T002`.

The previous `Prune legacy Ent schemas and table contracts` task is replaced by:

- `Prune Ent schema definitions`
- `Align Ent migration and server table contracts`

This keeps Ent schema-file edits separate from migration/server table-contract
alignment while preserving the later regeneration, cleanup, and verification
tasks from V2.108.

## Verification

- Real phase_011 graph probe using `phase_repair_001.md`.
- Real phase_011 graph probe using `phase_repair_002.md`.
- Real phase_011 graph probe using both repair docs together.
- `python -B -m pytest tests/test_document_to_plan.py -q`
- `python -B -m pytest tests/test_runtime_handoff.py -q`
- `python -B -m pytest tests/test_full_roadmap_execution.py -q`
- `python -B -m compileall planner tests -q`

All real probes now produce:

- `T002 Prune Ent schema definitions`
- `T003 Align Ent migration and server table contracts`
- `T004 Regenerate Ent clients and migration artifacts`
- `T005 Clean legacy backend services repositories and tests`
- `T006 Stabilize schema and build verification contracts`

The old `Implement large refactor integration` and
`Prune legacy Ent schemas and table contracts` tasks no longer appear in these
repair graphs.
