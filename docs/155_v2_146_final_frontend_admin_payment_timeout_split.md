# V2.146 Final Frontend Admin Payment Timeout Split

## Problem

After V2.145, Billing Core `final_verification/run_attempt_020` resumed correctly from the split usage/payment tail.
T024 `Repair final frontend admin usage component` completed, proving the V2.145 split was useful.

T025 `Repair final frontend admin payment component` still timed out after 900 seconds. Alchemy again handled the stop
boundary correctly: it recorded `B-T025-2`, did not launch same-scope debug work, and did not dispatch downstream
final-verification tasks.

The remaining payment surface is still not a single small edit. The inherited worktree currently has separate payment
order/detail, refund, and analytics/chart components:

- `AdminOrderTable.vue`
- `AdminOrderDetail.vue`
- `AdminRefundDialog.vue`
- `DailyRevenueChart.vue`
- `PaymentMethodChart.vue`
- `OrderStatsCards.vue`
- `TopUsersLeaderboard.vue`

## Change

- `planner/task_graph_builder.py` now recognizes a focused final-verification timeout on the admin payment task.
- The next repair graph preserves T001-T024 and splits the old T025 into:
  - `Repair final frontend admin payment order detail components`
  - `Repair final frontend admin payment refund dialog component`
  - `Repair final frontend admin payment analytics components`
- Downstream analytics/shared, view, state/composable, test/fixture, and final audit/check tasks keep their relative order
  after the split.
- Split preservation also covers later payment subtask failures, so a timeout in refund or analytics does not collapse the
  graph back to the broader payment task.

## Verification

- Focused document-to-plan regressions for the new payment split and adjacent usage/payment split preservation.
- Full `tests/test_document_to_plan.py`.
- Full `tests/test_full_roadmap_execution.py`.
- `python -B -m compileall planner tests -q`.
- `git diff --check`.
- Temporary graph probe against copied `run_attempt_020` artifacts confirmed the generated
  `final_verification_repair_resume_016.md` preserves T001-T024 and starts at
  `Repair final frontend admin payment order detail components`, followed by refund and payment analytics subtasks.
