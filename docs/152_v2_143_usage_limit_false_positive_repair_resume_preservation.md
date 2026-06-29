# V2.143 Usage-Limit False Positive And Repair Resume Preservation

## Problem

After V2.142, Billing Core `final_verification/run_attempt_017` proved the new admin user split was useful:
T016 `Repair final frontend admin user access group components` completed and Alchemy advanced to T017.

T017 did not time out. The worker completed, but Alchemy marked it blocked as a Codex usage-limit environment blocker.
That classification was wrong: the triggering text was ordinary product/source output containing `usage limits`, not a real
Codex quota error.

The blocked attempt exposed a second recovery issue. The generated repair resume could reopen completed split tasks
because broad raw worker output contained historical paths such as `frontend/src/i18n/...`, causing the final-verification
graph to collapse back toward earlier frontend tasks.

## Change

- `runtime/codex_worker.py` no longer treats bare `usage limit` as a Codex quota marker. It now requires clearer quota
  phrases such as `you've hit your usage limit`, `you have hit your usage limit`, `usage limit reached`, or
  `purchase more credits`.
- `autodev/full_roadmap_executor.py` applies the same narrower non-repairable blocker markers.
- Completed-task reopen target extraction now ignores raw command output for reopen decisions and ignores
  `Codex CLI usage limit reached:` summaries when extracting paths. This prevents historical search/typecheck output from
  reopening unrelated completed split tasks.
- `planner/task_graph_builder.py` now preserves final frontend split shapes through later failed task IDs, including T017
  and downstream final-verification tail tasks.

## Verification

- Focused runtime usage-limit parser regressions.
- Focused full-roadmap blocker and completed-task preservation regressions.
- Focused planner regression for T017 API-key repair resume preservation.
- Full `tests/test_runtime.py`, `tests/test_document_to_plan.py`, and `tests/test_full_roadmap_execution.py`.
- Temporary graph probe against copied `run_attempt_017` artifacts confirmed the next resume preserves T001-T016 and starts
  at `Repair final frontend admin user API key component`.
