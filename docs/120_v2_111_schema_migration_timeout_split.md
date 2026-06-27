# V2.111 Schema Migration Timeout Split

## Problem

After V2.110, Billing Core phase_011 resumed through the correct repair chain.
`run_attempt_006` completed `T002 Prune Ent schema definitions`, then timed out
on `T003 Align Ent migration and server table contracts`.

Alchemy correctly recorded a non-partial timeout blocker and wrote
`phase_repair_003.md`, but the next attempt replayed the same T003 scope.
Codex Desktop stopped `run_attempt_007` before another 900 second worker window
was spent.

## Fix

`planner/task_graph_builder.py` now performs another timeout split when a
schema/build repair identifies failed `T003`.

The previous `Align Ent migration and server table contracts` task is replaced
by:

- `Align Ent migration contracts`
- `Align server and domain table contracts`

These split tasks restrict their relevant files to their own spec files, so
repair-document `Previous relevant files` evidence cannot merge the two scopes
back together.

## Verification

- `tests/test_document_to_plan.py::DocumentToPlanTests::test_schema_migration_timeout_repair_splits_timed_out_contract_task_again`
- Real phase_011 graph probe using `phase_repair_001.md`,
  `phase_repair_002.md`, and `phase_repair_003.md`.
- `python -B -m pytest tests/test_document_to_plan.py -q`
- `python -B -m pytest tests/test_full_roadmap_execution.py -q`
- `python -B -m pytest tests/test_runtime_handoff.py -q`
- `python -B -m compileall planner tests -q`

The real graph probe now produces:

- `Prune Ent schema definitions`
- `Align Ent migration contracts`
- `Align server and domain table contracts`
- `Regenerate Ent clients and migration artifacts`
- `Clean legacy backend services repositories and tests`
- `Stabilize schema and build verification contracts`
