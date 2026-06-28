# V2.130 Final Repair Timeout Split

## Problem

After V2.129, Billing Core final verification correctly launched an editable
T002 `Repair final source-boundary defects` task. That task was still too wide:
it bundled backend migrations, generated/schema/domain cleanup, frontend API
and copy cleanup, route/view/test cleanup, and verification preparation into one
worker. It timed out after 900 seconds and Alchemy correctly stopped without
dispatching a same-scope debug task, but the timeout rollback meant no product
changes were preserved.

## Fix

V2.130 splits final source-boundary repair into serial, smaller tasks:

1. `Repair final backend migration contracts`
2. `Repair final backend schema and domain contracts`
3. `Repair final frontend API and i18n contracts`
4. `Repair final frontend routes views and tests`
5. final audit
6. simulation probes
7. real repository checks
8. review

The final verification worker also receives a minimum `max_iterations` of 12 so
the split repair chain can reach audit/review instead of exhausting the old
four-iteration supervised resume budget.

## Verification

- Focused final-verification repair planner test passed.
- Focused final-verification worker attempt/relaunch tests passed.
- Real Billing Core final-verification graph probe now shows T002-T005 split
  repair tasks followed by T006 audit, T007 simulation, T008 real checks, and
  T009 review.
- Full `tests/test_document_to_plan.py` passed.
- Full `tests/test_full_roadmap_execution.py` passed.
- `compileall` passed for `planner`, `autodev`, and `tests`.
