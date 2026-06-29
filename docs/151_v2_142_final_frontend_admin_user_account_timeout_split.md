# V2.142 Final Frontend Admin User Account Timeout Split

## Problem

After V2.141, Billing Core `final_verification/run_attempt_016` proved the account modal split was effective:
T012 through T015 completed and Alchemy advanced to T016.

T016 `Repair final frontend admin user account components` then timed out after 900 seconds. The scheduler behaved
correctly: T001 through T015 stayed completed, T016 was marked failed with `B-T016-1`, no same-scope debug task was
launched, and no downstream task was dispatched.

The remaining issue is task granularity. T016 still bundled multiple admin user account modals:

- `GroupReplaceModal.vue`
- `UserAllowedGroupsModal.vue`
- `UserApiKeysModal.vue`
- `UserCreateModal.vue`
- `UserEditModal.vue`

## Change

`planner/task_graph_builder.py` now detects repeated T016 admin user account timeout context and splits it into smaller
serial scopes:

- `Repair final frontend admin user access group components`
- `Repair final frontend admin user API key component`
- `Repair final frontend admin user create edit components`

The graph preserves T001-T015, keeps the V2.141 account modal split shape, then continues into balance/quota,
announcement/compliance, connector/channel, monitor, usage/payment, analytics/shared, view, state, test, and final audit
tasks.

## Verification

- Focused document-to-plan regression for T016 admin user account timeout splitting.
- Focused full-roadmap regression for writing `final_verification_repair_resume_012.md`.
- Existing V2.141 account modal split regressions remain in place.
