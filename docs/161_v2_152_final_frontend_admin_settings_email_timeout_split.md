# V2.152 Final Frontend Admin Settings Email Timeout Split

## Problem

After V2.151, Billing Core `final_verification/run_attempt_026` resumed correctly, preserved T001-T028, and completed
T029 `Repair final frontend admin dashboard view file`.

Alchemy then advanced to T030 `Repair final frontend admin settings email compliance files`. The scheduler behavior was
correct, but the task still timed out at 900 seconds:

- T029 completed in the inherited `real_run_worktree_20260623232224162902` worktree.
- T030 ran inside the same inherited worktree.
- Alchemy recorded `B-T030-1`.
- It did not create same-scope debug work and did not dispatch downstream tasks.

The remaining T030 scope still bundled the admin settings page, email template editor, compliance dialog, shared styles,
and shared types. That is too much for the current hard worker timeout, especially when the worker also runs frontend
type checks before returning.

## Change

- `planner/task_graph_builder.py` now recognizes focused timeouts on
  `Repair final frontend admin settings email compliance files`.
- The next repair graph preserves T001-T029 and splits that task into:
  - `Repair final frontend admin settings view file`
  - `Repair final frontend admin email template editor file`
  - `Repair final frontend admin compliance dialog file`
  - `Repair final frontend admin settings support files`
- Preservation logic also keeps the split graph stable if a later settings/email/compliance leaf task fails.
- The rest of the V2.151 dashboard/settings split remains ordered after those narrower tasks.

## Verification

- Focused regressions for broad view pages, admin view pages, dashboard/settings files, and settings/email/compliance
  files.
- Temporary graph probe against copied `run_attempt_026` artifacts confirmed the generated
  `final_verification_repair_resume_022.md` preserves T001-T029 and starts at the four settings/email/compliance leaf
  tasks before continuing the final-verification tail through T047.
- Full `tests/test_document_to_plan.py`.
- Full `tests/test_full_roadmap_execution.py`.
- `python -B -m compileall planner tests -q`.
- `git diff --check`.

## Follow-Up

If the exact-file settings tasks still take nearly the whole worker window, the next Alchemy optimization should reduce
per-task verification breadth or add structured checkpoints/partial-result handoff before adding another split layer.
