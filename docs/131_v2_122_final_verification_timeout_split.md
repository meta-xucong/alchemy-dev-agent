# V2.122 Final Verification Timeout Split

## Problem

After V2.121, Billing Core phase_011 resumed from the correct inherited
worktree and completed the narrowed handler/server cleanup chain:

- T016 `Inventory handler and server cleanup leftovers`
- T017 `Clean handler legacy route contracts`
- T018 `Clean server route and command wiring`
- T019 `Compile handler and server cleanup contracts`
- T020 `Compile residual backend cleanup contracts`
- T021 `Stabilize schema and build verification contracts`

The final generic verification task, T022 `Verify implementation against
project checks`, still bundled backend tests, frontend tests, backend build,
frontend build, and frontend lint into one Codex worker. That worker timed out
after 900 seconds. The timeout stop boundary behaved correctly, but a direct
resume would have replayed another over-wide verification worker.

## Fix

Schema/build phases now detect focused timeout repair evidence for the final
generic verification task and split it into a serial verification chain:

- `Verify backend tests`
- `Verify frontend tests`
- `Verify backend build`
- `Verify frontend build and lint`

The split reuses detected project commands when available and falls back to the
standard Billing Core commands only for missing groups. The tasks run serially
so heavy backend and frontend checks do not contend with each other, and the
review task depends on the last split verification task.

The schema/build repair-context retention floor is raised from twelve to
fourteen ordinary repair briefs so final verification split attempts do not drop
the earlier schema/build split chain.

## Verification

- Focused planner regression for T022 final verification timeout splitting.
- Focused full-roadmap regression for the fourteen-document schema/build repair
  context floor.
- Real phase_011 graph probe with `phase_repair_001.md` through
  `phase_repair_011.md`: T016-T21 are preserved completed; T022-T25 are
  backend tests, frontend tests, backend build, and frontend build/lint; T026 is
  the final review gate.
- Full `tests/test_document_to_plan.py` (36 tests).
- Full `tests/test_full_roadmap_execution.py`.
