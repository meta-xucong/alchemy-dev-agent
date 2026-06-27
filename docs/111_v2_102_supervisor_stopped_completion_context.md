# V2.102 Supervisor-Stopped Completion Context

## Problem

After V2.101 stopped `run_attempt_040`, the latest durable
`phase_record.json` still pointed at the older `run_attempt_038` T010 timeout.
That stale record did not know that `run_attempt_040` had already completed:

- T010 `Complete remaining frontend API service closure`
- T011 `Complete remaining frontend store and composable closure`

If Alchemy bootstrapped only from the stale phase record, it could generate a
repair brief that preserved only T001-T009 and replayed or mis-mapped T010/T011.
The first graph probe confirmed this risk: T011 could drift to the older
`Complete remaining frontend view workflow closure` title.

## Fix

Full-roadmap bootstrap now detects newer supervisor-stopped attempts whose
state file is newer than `phase_record.json`.

When such an attempt contains completed tasks, Alchemy writes or reuses a
`phase_repair_resume_NNN.md` context brief that:

- says the stopped attempt must not be resumed directly;
- lists completed task IDs to preserve from the stopped attempt;
- lists active task IDs at the stop boundary;
- preserves the prior T010 timeout split context when the stopped task set is
  in the T010-T013 frontend closure split range.

The focused timeout matcher now parses task ID lists such as
`Primary failed task IDs: T012, T010`, rather than only matching a single exact
task ID after the colon.

## Billing Core Probe

The real phase_010 bootstrap now produces a stopped-attempt context brief
(`phase_repair_resume_007.md` in the current artifact set) that preserves
T010/T011 and keeps the T010 split context active.

A real graph rebuild with the current phase_010 documents now shows:

- T001-T011 completed;
- T012 pending `Complete remaining frontend constants and type closure`;
- T013 pending `Complete remaining frontend view workflow closure`;
- T014/T015 pending verification and review.

This is the correct continuation boundary. It is not a full restart and should
not replay T010/T011.

## Verification

- focused full-roadmap stopped-attempt context test => `1 passed`
- focused planner/full-roadmap split tests => `3 passed`
- `python -B -m pytest tests/test_document_to_plan.py -q` => `24 passed`
- `python -B -m pytest tests/test_full_roadmap_execution.py -q` => `59 passed`
- real phase_010 graph probe confirms T010/T011 completed and T012/T013 pending
