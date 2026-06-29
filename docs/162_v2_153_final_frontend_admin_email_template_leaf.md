# V2.153 Final Frontend Admin Email Template Leaf

## Problem

After V2.152, Billing Core `final_verification/run_attempt_027` proved that the execution chain was advancing again:

- T029 `Repair final frontend admin dashboard view file` was already completed.
- T030 `Repair final frontend admin settings view file` completed successfully in about five minutes.
- Alchemy then advanced to T031 `Repair final frontend admin email template editor file`.

The scheduler behavior remained correct, but T031 timed out at 900 seconds. The stopped task still allowed
`EmailTemplateEditor.vue`, `onboarding.css`, and shared frontend types in one worker scope, so the worker could reopen
support files and broad verification before returning.

## Change

- `planner/task_graph_builder.py` now recognizes focused T031 timeouts on
  `Repair final frontend admin email template editor file`.
- The next repair graph preserves T001-T030 and narrows T031 to:
  - `Repair final frontend admin email template editor leaf file`
- The leaf task only grants edit scope to
  `frontend/src/views/admin/settings/EmailTemplateEditor.vue`.
- Shared styles and types remain in the later support-file task, so Alchemy does not lose coverage while avoiding the
  over-wide worker surface that just timed out.
- Preservation logic keeps the email-template leaf split stable if later settings/email/compliance tasks fail.

## Verification

- Focused regression matching the `run_attempt_027` failure shape.
- Five-layer focused split regression: broad view pages, admin view pages, dashboard/settings, settings/email/compliance,
  and email-template leaf.
- Full `tests/test_document_to_plan.py`.
- Full `tests/test_full_roadmap_execution.py`.

## Follow-Up

If the single-file email template leaf still times out, the problem is likely no longer file count. The next Alchemy
optimization should focus on worker prompt budgeting, progress checkpoints, or limiting per-task verification commands
instead of only splitting task scopes further.
