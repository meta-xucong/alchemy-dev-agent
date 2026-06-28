# V2.141 Final Frontend Admin Account Modal Timeout Split

## Problem

After V2.140, Billing Core `final_verification/run_attempt_015` proved the smaller admin-account split was useful:
T011 `Repair final frontend admin account table components` completed and Alchemy advanced to T012.

T012 `Repair final frontend admin account modal components` then timed out after 900 seconds. The scheduler again behaved
correctly: T011 stayed completed, T012 was marked failed with `B-T012-1`, no same-scope debug task was launched, and no
downstream task was dispatched.

The remaining issue is task granularity. T012 still bundled four component families plus tests and shared types:

- `AccountTestModal.vue`
- `ImportDataModal.vue`
- `ReAuthAccountModal.vue`
- `ScheduledTestsPanel.vue`
- account modal tests

## Change

`planner/task_graph_builder.py` now detects repeated T012 admin account modal timeout context and splits it into
single-file-oriented serial scopes:

- `Repair final frontend admin account test modal component`
- `Repair final frontend admin account import modal component`
- `Repair final frontend admin account reauth modal component`
- `Repair final frontend admin scheduled account tests panel`

The graph preserves T001-T011, then continues into the existing user account, user balance/quota, announcement/compliance,
connector/channel, monitor, usage/payment, analytics/shared, view, state, test, and final audit tasks.

## Verification

- Focused document-to-plan regression for T012 account modal timeout splitting.
- Focused full-roadmap regression for writing `final_verification_repair_resume_011.md`.
- Existing V2.140 admin account identity split regressions remain in place.
