# V2.129 Final Verification Repair Handoff

## Problem

Billing Core final verification reached the correct audit graph and found real
source-boundary defects: residual relay-era migrations/schema/frontend API/i18n
surfaces still contradicted the CRM Billing Core contract. The first audit task
was read-only, which was correct, but its generated debug task inherited
`relevant_files` and wrote retry notes into source documents, including the
original Billing Core checkout document.

That exposed two controller issues:

1. Debug tasks for read-only test/review/architecture tasks could become
   writable by inheriting their `relevant_files`.
2. A failed final audit did not persist a relaunch-safe repair document that
   could generate a focused editable repair task on the next run.

## Fix

V2.129 changes three areas:

- Runtime debug task creation keeps architecture/test/review debug tasks
  read-only by clearing inherited `relevant_files`.
- Full-roadmap final verification relaunches convert the previous failed worker
  report into `final_verification_repair_resume_NNN.md` when the report includes
  final audit failure, source-boundary, or `allowed_files` evidence.
- The planner recognizes that repair context and creates
  `Repair final source-boundary defects` before the audit/test marker tasks,
  with explicit edit scope for backend migrations, Ent/schema/generated/domain
  and backend service/handler/server/cmd surfaces, plus frontend API/i18n/router
  view/component/composable/constants/type/store/test surfaces.

The out-of-bound debug appendix was removed from the original Billing Core
development document; the diagnosis remains in Alchemy run artifacts and the
repair resume document.

## Verification

- Focused runtime debug inheritance tests passed.
- Focused final-verification repair planner tests passed.
- Focused final-verification relaunch repair-document test passed.
- Real Billing Core final-verification graph probe now starts with editable
  T002 `Repair final source-boundary defects`, then T003 audit, T004 simulation,
  T005 real checks, and T006 review.
- Full `tests/test_runtime.py` passed.
- Full `tests/test_document_to_plan.py` passed.
- Full `tests/test_full_roadmap_execution.py` passed.
- `compileall` passed for `runtime`, `planner`, `autodev`, and `tests`.
