# V2.155 Final Frontend Deep Split API Preservation

## Problem

V2.154 split T034 `Repair final frontend admin announcement backup promo files`, but the first real relaunch
(`final_verification/run_attempt_029`) showed a task-ID drift:

- `Repair final frontend admin announcements view file` and `Repair final frontend admin backup view file` were marked
  completed immediately.
- The active task became `Repair final frontend admin promo codes view file`.
- The graph had collapsed V2.136's API/i18n/constants split back into the single
  `Repair final frontend API and i18n contracts` task, shifting all later task IDs left by two.

Codex Desktop wrote a `supervisor_stop.json` marker for `run_attempt_029` before product work continued on the drifted
graph. Alchemy honored the stop marker and no residual worker remained.

## Change

- `should_preserve_final_frontend_api_i18n_split` now preserves the API/i18n/constants split through the final-verification
  tail instead of only through earlier T009-T032 failures.
- Deep T034+ announcement/backup/promo failures now force `split_api_i18n=True`.
- The V2.154 focused regression now explicitly asserts that:
  - `Repair final frontend API module contracts` is present.
  - `Repair final frontend i18n locale contracts` is present.
  - `Repair final frontend constants and shared types contracts` is present.
  - the old `Repair final frontend API and i18n contracts` bundle is absent.

## Verification

- Focused V2.154/V2.155 regression.
- Six-layer focused final-frontend split regression.
- Full `tests/test_document_to_plan.py`.
- Full `tests/test_full_roadmap_execution.py`.

## Follow-Up

The next relaunch must verify that Alchemy does not continue from the stopped drifted `run_attempt_029` graph. The
correct next graph should preserve T001-T033 from `run_attempt_028` and restart at the announcement split sequence
without skipping announcements or backup.
