# V2.150 Final Frontend Admin View Page Timeout Split

## Problem

After V2.149, Billing Core `final_verification/run_attempt_024` resumed through the correct final-verification repair
entry and started the new T029 `Repair final frontend admin view page contracts` task in the inherited worktree.

The recovery chain was correct:

- `final_verification_repair_resume_019.md` preserved T001-T028.
- T029 was active in the inherited `real_run_worktree_20260623232224162902` worktree.
- The worker stopped at the 900 second budget with `B-T029-1`.
- Alchemy did not create same-scope debug work and did not dispatch T030.

The task was still too wide. It allowed all admin views plus all admin components, so a single worker had to reason about
dashboard/settings pages, users, usage, redeem flows, payment/order pages, ops dashboards, and legacy relay admin pages.

## Change

- `planner/task_graph_builder.py` now recognizes focused timeouts on
  `Repair final frontend admin view page contracts`.
- The next repair graph preserves T001-T028 and splits the old admin view task into:
  - `Repair final frontend admin dashboard settings view contracts`
  - `Repair final frontend admin user usage redeem view contracts`
  - `Repair final frontend admin payment order plan view contracts`
  - `Repair final frontend admin operations view contracts`
  - `Repair final frontend legacy admin view cleanup`
- The existing user/payment view, auth/public/setup view, state/composable, test, audit, simulation, real-check, and
  handoff tasks stay ordered after those admin leaves.

## Verification

- Focused document-to-plan regressions for the V2.149 top-level view split and V2.150 admin view split.
- Temporary graph probe against copied `run_attempt_024` artifacts confirmed the generated
  `final_verification_repair_resume_020.md` preserves T001-T028 and starts at the five smaller admin view tasks.
- Full `tests/test_document_to_plan.py`.
- Full `tests/test_full_roadmap_execution.py`.
- `python -B -m compileall planner tests -q`.
- `git diff --check`.

## Follow-Up

The hard timeout behaved safely, but it is still not progress-aware enough. T029 wrote real worktree changes before the
timeout, yet Alchemy only knew that the process exceeded 900 seconds. A later controller improvement should add bounded
worker checkpoints or heartbeat summaries so large-but-progressing workers can stop with structured partial evidence.
