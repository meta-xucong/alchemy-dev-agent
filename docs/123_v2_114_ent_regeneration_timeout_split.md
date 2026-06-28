# V2.114 Ent Regeneration Timeout Split

## Problem

`run_attempt_011` proved the schema/migration checkpoint chain could progress:
T003, T004, and T005 completed. The next task,
`T006 Regenerate Ent clients and migration artifacts`, then timed out after 900
seconds.

The parent launched `run_attempt_012` with the same broad T006 scope. Codex
Desktop stopped it before another full worker window was spent.

## Fix

Focused schema/build T006 timeout repairs now split Ent regeneration into:

- `Inventory Ent regeneration inputs`
- `Regenerate Ent generated clients`
- `Align repository callers after Ent regeneration`

Schema/build cumulative repair context now keeps at least six ordinary repair
briefs, so the new T006 repair does not drop the older T002/T003 split chain.

## Verification

- `tests/test_document_to_plan.py::DocumentToPlanTests::test_schema_ent_regeneration_timeout_repair_splits_regeneration_task`
- `tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_schema_phase_repair_context_keeps_full_split_chain_beyond_repair_budget`
- Real phase_011 bootstrap and graph probe using `phase_repair_005.md`.
- `python -B -m pytest tests/test_document_to_plan.py -q`
- `python -B -m pytest tests/test_full_roadmap_execution.py -q`
- `python -B -m pytest tests/test_runtime_handoff.py -q`
- `python -B -m compileall autodev planner tests -q`
