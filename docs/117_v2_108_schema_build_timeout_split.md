# V2.108 Schema/Build Timeout Split

## Problem

Billing Core phase_011 reached the correct schema-pruning phase after phase_010
promotion, but the first implementation task was still a broad
`Implement large refactor integration` worker covering backend, frontend, CI,
Docker, docs, and package files. That worker timed out after 900 seconds.

The full-roadmap controller correctly stopped on the non-partial timeout blocker
and wrote `phase_repair_001.md`, but the next repair attempt regenerated the
same broad T002 instead of splitting the schema/build work. Codex Desktop
supervision stopped that attempt before another full worker window was spent.

## Fix

`planner/task_graph_builder.py` now detects large-refactor schema/build phases
from Ent schema, Ent regeneration, migration, fresh DB, backend test, and
frontend build/typecheck markers.

When such a phase is planned or repaired, Alchemy emits narrower backend tasks:

- `Prune legacy Ent schemas and table contracts`
- `Regenerate Ent clients and migration artifacts`
- `Clean legacy backend services repositories and tests`
- `Stabilize schema and build verification contracts`

The generated tasks avoid the old `backend/**` plus `frontend/**` catch-all
scope, preserve completed repair tasks such as T001, and carry remaining
phase-level CRM constraints on the build-verification task instead of launching
another broad integration worker.

## Verification

- `tests/test_document_to_plan.py::DocumentToPlanTests::test_large_refactor_schema_timeout_repair_splits_backend_build_task`
- `tests/test_document_to_plan.py`
- `tests/test_runtime_handoff.py`
- `tests/test_full_roadmap_execution.py`
- `python -m compileall planner tests -q`
- Real phase_011 graph probe using
  `.alchemy/billing_core_v274_20260624_012/phases/phase_011/phase_requirements.md`
  and `phase_repair_001.md`.

The real probe now marks T001 completed and leaves T002-T005 as the four
schema/build split tasks, followed by verification and review.

## Operational Note

During this repair, D: was found with only about 100 KB free. That caused a
patch/Git write failure and temporarily truncated `planner/task_graph_builder.py`
to 0 bytes. The file was restored from Git after clearing only safe local cache
directories. Future real-worker relaunches should check free disk space first;
running Codex/Alchemy workers on a nearly full disk can create false failures or
corrupt transient writes.
