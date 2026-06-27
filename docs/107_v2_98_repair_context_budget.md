# V2.98 Repair Context Budget

## Problem

After V2.97, Billing Core `run_attempt_038` used the correct cumulative repair
context and made real progress:

- T001-T008 were preserved correctly.
- T009 `Complete remaining frontend shell and route closure` completed.
- T010 `Complete remaining frontend state and API closure` timed out at the
  900 second worker budget.

Alchemy correctly stopped on a non-partial timeout blocker without debug or
same-scope retry. However, the parent did not write the next repair brief
because the two historical context documents (`phase_repair_006.md` and
`phase_repair_007.md`) consumed the same count used for the per-run auto-repair
limit.

A second resume edge also needed protection: once `phase_record.json` is newer
than the ordinary repair docs, a blocked-phase resume can generate a
`phase_repair_resume_NNN.md` document. That resume document still needs recent
ordinary repair context so task IDs do not drift back to a pre-split graph.

## Fix

V2.98 separates repair context from new repair budget:

- Historical repair briefs passed to the document runner no longer consume the
  current parent run's allowance for newly generated repair documents.
- Blocked-phase resume repair documents include the recent ordinary repair
  briefs as context, even when those ordinary briefs are older than
  `phase_record.json`.

## Verification

- focused budget/context regressions: `2 passed`
- focused cumulative repair regressions: `3 passed`
- `python -B -m pytest tests/test_full_roadmap_execution.py -q` => `58 passed`
- `python -B -m pytest tests/test_document_to_plan.py -q` => `22 passed`
- `python -B -m py_compile autodev\full_roadmap_executor.py tests\test_full_roadmap_execution.py`
- real phase_010 resume-source probe reports no active resume source and no
  live blockers after the terminal T010 timeout state

## Assessment

This is another example of why the recent token cost is higher than normal
development supervision: Alchemy is learning the bookkeeping that a human
supervisor would do implicitly. The useful result is that the controller now
keeps repair context, avoids ID drift, and can still generate a new focused
repair after a later task times out.
