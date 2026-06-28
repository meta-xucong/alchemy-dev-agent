# V2.140 Final Frontend Admin Account Timeout Split

## Problem

After V2.139, Billing Core `final_verification/run_attempt_014` correctly preserved T001-T010 and started
T011 `Repair final frontend admin account identity components` in the inherited worktree.

That task was smaller than the prior broad admin operation task, but it still covered account, user, announcement,
compliance, shared types, and package metadata together. It timed out after 900 seconds.

The scheduler behavior was correct: Alchemy recorded `B-T011-1`, stopped the run, and did not launch same-scope
debug work or downstream tasks. The next resume graph still needed another split so it would not replay the same
admin account identity worker.

A related evidence issue became visible: timeout results said task-local changes were rolled back, while the worktree
still showed dirty files. This can be legitimate when the worker started from an already-dirty baseline: rollback
restores the pre-task snapshot, not necessarily a clean git checkout.

## Change

`planner/task_graph_builder.py` now detects repeated T011 admin account identity timeout context and splits it into
smaller serial scopes:

- `Repair final frontend admin account table components`
- `Repair final frontend admin account modal components`
- `Repair final frontend admin user account components`
- `Repair final frontend admin user balance quota components`
- `Repair final frontend admin announcement compliance components`

The rest of the V2.139 admin split then continues with connector/channel, monitor, usage/payment, shared analytics,
view pages, state/composables/utilities, tests, and final audit gates.

`runtime/codex_worker.py` now reports timeout rollback as restoring the pre-task snapshot and notes that pre-existing
dirty files may remain.

## Verification

- Focused document-to-plan regression for repeated T011 admin account identity timeout splitting.
- Focused full-roadmap regression for writing `final_verification_repair_resume_010.md`.
- Existing V2.139 admin operation split regressions remain in place.
