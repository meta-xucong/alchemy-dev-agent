# V2.156 Final Frontend Drifted Promo Recovery

## Problem

After V2.155, `final_verification/run_attempt_030` preserved the API/i18n/constants split correctly, but it still did
not reopen the announcement/backup/promo split. The latest repair resume had inherited the stopped drifted
`run_attempt_029` context:

- Primary failed task: T034.
- Task title: `Repair final frontend admin promo codes view file`.
- Worker summary: operator stop request.

That context did not match the V2.154 trigger, so Alchemy rebuilt T034 as the old bundled
`Repair final frontend admin announcement backup promo files` task. Codex Desktop stopped `run_attempt_030` before that
old bundle could run again.

## Change

- `should_split_final_frontend_admin_announcement_backup_promo_timeout` now treats drifted split titles as part of the
  same announcement/backup/promo recovery family:
  - `Repair final frontend admin announcements view file`
  - `Repair final frontend admin backup view file`
  - `Repair final frontend admin promo codes view file`
- Added a regression matching `final_verification_repair_resume_025.md`, where T034 is the stopped drifted promo-code
  task. The expected graph reopens the full split sequence at T034:
  - announcements view
  - backup view
  - promo-code view
  - announcement component/support files

## Verification

- Focused drifted promo-code recovery regression.
- Seven-layer focused final-frontend split regression.
- Full `tests/test_document_to_plan.py`.
- Full `tests/test_full_roadmap_execution.py`.

## Follow-Up

The next relaunch must show T034 as `Repair final frontend admin announcements view file`, not the old bundled task and
not the drifted promo-code leaf.
