# V2.151 Final Frontend Admin Dashboard Settings Timeout Split

## Problem

After V2.150, Billing Core `final_verification/run_attempt_025` resumed correctly and started the smaller T029
`Repair final frontend admin dashboard settings view contracts` task.

Alchemy again handled the timeout boundary correctly:

- T029 ran inside the inherited `real_run_worktree_20260623232224162902` worktree.
- The worker timed out at 900 seconds.
- Alchemy recorded `B-T029-1`.
- It did not create same-scope debug work and did not dispatch downstream tasks.

The remaining task still covered too much: dashboard, settings, announcements, backup, promo codes, email templates,
compliance dialog, shared styles, shared types, and package metadata.

## Change

- `planner/task_graph_builder.py` now recognizes focused timeouts on
  `Repair final frontend admin dashboard settings view contracts`.
- The next repair graph preserves T001-T028 and splits that task into:
  - `Repair final frontend admin dashboard view file`
  - `Repair final frontend admin settings email compliance files`
  - `Repair final frontend admin announcement backup promo files`
  - `Repair final frontend admin dashboard settings support files`
- The rest of the V2.150 admin view split remains ordered after those file-level tasks.

## Verification

- Focused regressions for all three split levels: broad view pages, admin view pages, and dashboard/settings files.
- Temporary graph probe against copied `run_attempt_025` artifacts confirmed the generated
  `final_verification_repair_resume_021.md` preserves T001-T028 and starts at the four smaller dashboard/settings
  tasks before continuing the admin/user/payment/ops/final-verification tail.
- Full `tests/test_document_to_plan.py`.
- Full `tests/test_full_roadmap_execution.py`.
- `python -B -m compileall planner tests -q`.
- `git diff --check`.

## Follow-Up

If even an exact-file dashboard task times out, the next Alchemy optimization should add worker checkpoint/partial-result
support instead of continuing to split by file count alone.
