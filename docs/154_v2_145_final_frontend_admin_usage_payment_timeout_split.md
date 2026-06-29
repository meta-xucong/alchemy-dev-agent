# V2.145 Final Frontend Admin Usage/Payment Timeout Split

## Problem

After V2.144, Billing Core `final_verification/run_attempt_019` proved the new create/edit split was useful:
T018 `Repair final frontend admin user create modal component`, T019 `Repair final frontend admin user edit modal
component`, T020 `Repair final frontend admin user balance quota components`, T021
`Repair final frontend admin announcement compliance components`, T022
`Repair final frontend admin connector channel components`, and T023
`Repair final frontend admin monitor components` all completed in the inherited worktree.

T024 `Repair final frontend admin usage payment components` then hit the 900 second worker timeout. Alchemy handled the
stop boundary correctly: it recorded `B-T024-1`, did not launch same-scope debug work, and did not dispatch downstream
final-verification tasks.

The remaining issue was again task size. Usage and payment are related but separable CRM surfaces, and replaying them as
one worker risked spending another full timeout window.

## Change

- `planner/task_graph_builder.py` now recognizes a focused final-verification timeout on the admin usage/payment task.
- The next repair graph preserves T001-T023 and splits the old T024 into:
  - `Repair final frontend admin usage component`
  - `Repair final frontend admin payment component`
- Downstream analytics, view, state/composable, test/fixture, and final audit/check tasks keep their relative order after
  the split.

## Verification

- Focused document-to-plan regressions for the new usage/payment split and adjacent final-verification split preservation.
- Full `tests/test_document_to_plan.py`.
- Full `tests/test_full_roadmap_execution.py`.
- `python -B -m compileall planner tests -q`.
- `git diff --check`.
- Temporary graph probe against copied `run_attempt_019` artifacts confirmed the generated
  `final_verification_repair_resume_015.md` preserves T001-T023 and starts at
  `Repair final frontend admin usage component`, followed by
  `Repair final frontend admin payment component`.
