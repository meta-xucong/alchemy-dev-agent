# V2.113 Cumulative Schema Repair Context

## Problem

After V2.112, the next Billing Core phase_011 relaunch lost the early schema
repair context. `run_attempt_010` only carried the latest repair briefs, so the
graph collapsed back to an older shape with `Prune legacy Ent schemas and table
contracts` marked completed and `Regenerate Ent clients and migration artifacts`
active.

Codex Desktop stopped the attempt before the stale graph could spend another
worker window.

The root cause was that schema/build repair chains had grown beyond the default
two repair-document context limit. Keeping only the latest two repair briefs
lost the earlier T002 split evidence.

## Fix

`bootstrap_phase_repair_documents()` now uses a larger cumulative repair-context
limit for schema/build phases. This does not increase the number of new repair
attempts; it only retains enough existing ordinary repair briefs to preserve the
split chain.

For schema/build phases, the retained ordinary repair context is at least four
documents.

## Verification

- `tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_schema_phase_repair_context_keeps_full_split_chain_beyond_repair_budget`
- Real phase_011 bootstrap and graph probe after `run_attempt_010`.
- `python -B -m pytest tests/test_full_roadmap_execution.py -q`
- `python -B -m pytest tests/test_document_to_plan.py -q`
- `python -B -m pytest tests/test_runtime_handoff.py -q`
- `python -B -m compileall autodev planner tests -q`

The real probe now retains `phase_repair_001.md` through
`phase_repair_004.md` and rebuilds the correct schema-prune and migration
checkpoint graph.
