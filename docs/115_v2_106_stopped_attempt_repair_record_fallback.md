# V2.106 Stopped Attempt Repair Record Fallback

## Problem

After V2.105, the supervisor relaunched Billing Core phase_010 through the
correct Alchemy entrypoint. The run entered the inherited isolated worktree, but
`run_attempt_045` rebuilt a broad original phase graph:

- T001 planning active
- T002-T008 original frontend implementation tasks pending
- verification/review/release pending

This was not normal progress. It happened because the previous meaningful
attempt, `run_attempt_044`, had `status=blocked` with no runtime blockers but
with final-gate evidence: score `0.7018` and missing requirement coverage.
`should_auto_repair_phase()` only treated `status=done` low-score results as
repairable, so bootstrap returned no repair documents. The document runner then
saw only the original phase requirements and regenerated the wide graph.

The supervisor stopped `run_attempt_045` immediately and wrote
`supervisor_stop.json`. That created another recovery wrinkle: the latest
`phase_record.json` now pointed at an empty operator-stopped attempt with no
completed tasks. A future relaunch had to ignore that stop record and recover
the prior meaningful gate state.

## Fix

V2.106 makes two recovery changes:

- A blocked phase with no runtime blockers is auto-repairable when its final
  gate has repairable evidence such as low score, required changes, hard
  failures, or low dimensions.
- When bootstrap sees a latest phase record for an empty
  supervisor-stopped attempt, it scans older run attempts and selects the newest
  document-run report that is still auto-repairable.

Credential, external, policy, preflight, and operator-control blockers remain
non-repairable. The fallback only applies when the newest stopped attempt has no
completed task evidence and an older run contains a repairable gate result.

## Billing Core Probe

Using the current real phase_010 artifacts after stopping `run_attempt_045`,
bootstrap now selects:

- `phase_repair_008.md`
- `phase_repair_009.md`
- `phase_repair_resume_010.md`

The generated resume brief contains the missing-coverage gate evidence from
`run_attempt_044`, does not contain the operator-stop text from `run_attempt_045`,
and does not revive the stale T014 verification issue.

A real graph rebuild with those documents produces:

- T001-T008 completed
- T021 `Verify implementation against project checks` pending
- T022 `Review delivery readiness` pending

No broad frontend implementation worker is dispatched.

## Verification

- focused recovery regressions => `7 passed`
- `python -m pytest tests/test_full_roadmap_execution.py -q` => `67 passed`
- `python -m pytest tests/test_document_to_plan.py -q` => `25 passed`
- `python -m compileall autodev planner tests -q` => passed
- real phase_010 bootstrap/graph probe => only verification/review pending
