# V2.147 Final Frontend Admin Payment Refund Leaf Task

## Problem

After V2.146, Billing Core `final_verification/run_attempt_021` resumed correctly from the payment split.
T025 `Repair final frontend admin payment order detail components` completed, proving the payment split was useful.

T026 `Repair final frontend admin payment refund dialog component` still timed out after 900 seconds. This task already
targeted one component, but it still allowed `frontend/src/types/**`, `frontend/package.json`, and
`frontend/pnpm-lock.yaml`. For a final-verification source-boundary cleanup leaf task, that scope can encourage the
worker to widen search and type/package repair even when the immediate product-language cleanup should stay inside the
component.

Alchemy handled the timeout boundary correctly: it recorded `B-T026-1`, did not launch same-scope debug work, and did
not dispatch downstream final-verification tasks.

## Change

- `planner/task_graph_builder.py` now recognizes a focused timeout on the admin payment refund dialog task.
- The next repair graph preserves T001-T025 and replaces the broader refund task with
  `Repair final frontend admin payment refund dialog file`.
- The leaf task allows only `frontend/src/components/admin/payment/AdminRefundDialog.vue`.
- If a shared type or package metadata change is actually required, the leaf task must report the exact follow-up path
  instead of widening itself.

## Verification

- Focused document-to-plan regressions for the new refund leaf task and adjacent payment split preservation.
- Full `tests/test_document_to_plan.py`.
- Full `tests/test_full_roadmap_execution.py`.
- `python -B -m compileall planner tests -q`.
- `git diff --check`.
- Temporary graph probe against copied `run_attempt_021` artifacts confirmed the generated
  `final_verification_repair_resume_017.md` preserves T001-T025 and starts at
  `Repair final frontend admin payment refund dialog file` with only `AdminRefundDialog.vue` in scope.
