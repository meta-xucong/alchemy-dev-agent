# V2.144 Final Frontend Admin User Create/Edit Timeout Split

## Problem

After V2.143, Billing Core `final_verification/run_attempt_018` resumed correctly and completed T017
`Repair final frontend admin user API key component`.

The next task, T018 `Repair final frontend admin user create edit components`, still bundled both
`UserCreateModal.vue` and `UserEditModal.vue` plus shared frontend typing/package surfaces. It hit the
900 second worker timeout with no task-local evidence. Alchemy handled the stop boundary correctly: it recorded
`B-T018-1`, did not launch same-scope debug work, and did not dispatch downstream final-verification tasks.

The remaining issue was task sizing. Replaying the same create/edit task would likely spend another worker window on the
same surface.

## Change

- `planner/task_graph_builder.py` now recognizes a focused final-verification timeout on the admin user create/edit task.
- The next repair graph preserves T001-T017 and splits the old T018 into:
  - `Repair final frontend admin user create modal component`
  - `Repair final frontend admin user edit modal component`
- The downstream admin user balance/quota and final-verification tail tasks keep their relative order after the split.

## Verification

- Full `tests/test_document_to_plan.py`.
- Full `tests/test_full_roadmap_execution.py`.
- `python -B -m compileall planner tests -q`.
- `git diff --check`.
- Temporary graph probe against copied `run_attempt_018` artifacts confirmed the generated
  `final_verification_repair_resume_014.md` preserves T001-T017 and starts at
  `Repair final frontend admin user create modal component`, followed by
  `Repair final frontend admin user edit modal component`.
