# V2.110 Supervisor-Stopped Repair Doc Retention

## Problem

V2.109 fixed the planner-level schema-prune split, but a real Billing Core
phase_011 relaunch still rebuilt the stale graph. `run_attempt_005` started
with `T001` active and `T002 Prune legacy Ent schemas and table contracts`
pending, which proved the full-roadmap parent had not passed
`phase_repair_001.md` / `phase_repair_002.md` back into the document runner.

Codex Desktop wrote `run_attempt_005/supervisor_stop.json` and the live marker
controller cancelled the T001 worker before the old T002 scope could run.

The root cause was repair-document retention. A supervisor-stopped phase record
can be newer than useful on-disk repair briefs. The old bootstrap logic treated
those repair briefs as stale, then an operator/supervisor stop could be
classified as non-repairable and return an empty repair-document list.

## Fix

`bootstrap_phase_repair_documents()` now keeps existing repair briefs for a
previous attempt that contains a `supervisor_stop.json` or `operator_stop.json`
marker, even when `phase_record.json` is newer than those repair briefs.

If a supervisor-stopped attempt also has completed-task context, that context is
deduplicated with the retained ordinary repair docs.

## Verification

- `tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_supervisor_stopped_phase_keeps_existing_repair_docs_when_record_is_newer`
- Real phase_011 bootstrap probe after `run_attempt_005` supervisor stop.
- Real phase_011 graph probe using the bootstrapped repair docs.
- `python -B -m pytest tests/test_full_roadmap_execution.py -q`
- `python -B -m pytest tests/test_document_to_plan.py -q`
- `python -B -m pytest tests/test_runtime_handoff.py -q`
- `python -B -m compileall autodev planner tests -q`

The real bootstrap now retains `phase_repair_001.md` and
`phase_repair_002.md`, and the resulting graph starts with:

- `Prune Ent schema definitions`
- `Align Ent migration and server table contracts`
- `Regenerate Ent clients and migration artifacts`
- `Clean legacy backend services repositories and tests`
- `Stabilize schema and build verification contracts`
