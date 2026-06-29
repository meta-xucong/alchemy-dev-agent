# V2.149 Final Frontend View Page Timeout Split

## Problem

After V2.148, Billing Core `final_verification/run_attempt_023` resumed cleanly and advanced past the payment tail:
T026 `Repair final frontend admin payment refund dialog file`, T027
`Repair final frontend admin payment analytics components`, and T028
`Repair final frontend analytics and shared component contracts` all completed.

T029 `Repair final frontend view page contracts` then hit the 900 second worker timeout. Alchemy handled the stop boundary
correctly: it recorded `B-T029-1`, did not launch same-scope debug work, and did not dispatch downstream tasks.

The remaining view-page surface is large. It includes admin views, user/payment views, auth callbacks, public/setup pages,
and not-found pages. Replaying all of `frontend/src/views/**` as one worker would likely repeat the timeout.

## Change

- `planner/task_graph_builder.py` now recognizes a focused final-verification timeout on the view-page task.
- The next repair graph preserves T001-T028 and splits the old T029 into:
  - `Repair final frontend admin view page contracts`
  - `Repair final frontend user payment view page contracts`
  - `Repair final frontend auth public setup view contracts`
- Downstream state/composable, test/fixture, and final audit/check tasks keep their relative order after the split.

## Verification

- Focused document-to-plan regressions for the new view-page split and adjacent final-verification split preservation.
- Full `tests/test_document_to_plan.py`.
- Full `tests/test_full_roadmap_execution.py`.
- `python -B -m compileall planner tests -q`.
- `git diff --check`.
- Temporary graph probe against copied `run_attempt_023` artifacts confirmed the generated
  `final_verification_repair_resume_019.md` preserves T001-T028 and starts at
  `Repair final frontend admin view page contracts`, followed by user/payment and auth/public/setup view subtasks.
