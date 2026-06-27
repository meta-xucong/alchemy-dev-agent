# V2.94 Disk Repair Brief Resume

## Objective

V2.94 closes the handoff gap between a parent full-roadmap run and a later
supervised relaunch. If Alchemy has already written a fresh
`phase_repair_NNN.md` but the parent process is stopped before it refreshes
`phase_record.json`, the next run must still use that repair brief instead of
falling back to the original broad phase document.

## Problem Evidence

After V2.93, the planner could split a focused T007 timeout repair into smaller
frontend copy tasks when `phase_repair_006.md` was supplied.

The live relaunch created `phase_010/run_attempt_033`, but the task graph still
contained the old broad `T007 Sweep frontend product copy and i18n` task and
started replaying earlier completed work. The reason was not the planner split:
`phase_repair_006.md` was correct, but the full-roadmap bootstrap path ignored
the existing disk repair brief because `phase_record.json` was stale and still
pointed at an older blocked attempt.

`run_attempt_033` was stopped with `supervisor_stop.json` to avoid burning
another wide T007 worker.

## Design

`bootstrap_phase_repair_documents()` now checks for a newer ordinary
`phase_repair_NNN.md` before bootstrapping from the previous phase record.

Rules:

- ignore `phase_repair_resume_NNN.md` files for this fallback;
- compare ordinary repair brief mtimes against `phase_record.json`;
- if one or more ordinary repair briefs are newer than the record, pass only
  the newest one to the document runner;
- otherwise keep the existing previous-record bootstrap behavior.

This keeps stale older repair briefs such as earlier T003/T005 fixes out of a
new T007 recovery, while preserving the fresh repair evidence that the stopped
parent already wrote.

## Verification

Focused checks:

```powershell
python -B -m pytest tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_executor_reuses_newer_disk_repair_brief_when_phase_record_is_stale tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_executor_bootstraps_blocked_phase_resume_with_repair_evidence -q
python -B -m pytest tests/test_document_to_plan.py::DocumentToPlanTests::test_large_refactor_frontend_timeout_repair_splits_copy_sweep_task -q
python -B -m py_compile autodev\full_roadmap_executor.py tests\test_full_roadmap_execution.py
```

Real Billing Core probes:

```text
bootstrap_phase_repair_documents(...) => phase_repair_006.md
```

and the real phase_010 document graph now produces:

```text
T007 Sweep frontend i18n product copy
T008 Sweep frontend view and component product copy
T009 Complete remaining frontend closure requirements
```

## Operational Note

Seeing T001 at the start of a new attempt is normal because every document run
has a planning task. It becomes suspicious when the new graph drops focused
repair evidence and replays already completed implementation tasks. V2.94 fixes
that specific replay path.
