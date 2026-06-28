# V2.133 Final Backend Go Module Companions

## Context

After V2.132, Billing Core final verification `run_attempt_007` correctly
preserved T001/T002 and started the new T003 `Repair final backend Ent schema
contracts` task in the inherited worktree.

T003 completed before the 900 second timeout, but Alchemy boundary audit failed
the task because the Go toolchain updated `backend/go.sum` while the task
allowed only Ent paths. The worker changed Ent-generated files plus
`backend/go.sum`; the implementation changes were therefore treated as
out-of-scope and a debug worker was launched. The supervising thread stopped that
debug worker before it repeated the same narrow boundary.

## Changes

- Added `backend/go.mod` and `backend/go.sum` to the final backend Ent schema
  repair scope.
- Added the same Go module companion files to final backend domain/repository
  and service/handler/server repair scopes, because package-level Go checks can
  legitimately refresh module checksums.
- Updated the final verification repair graph regression so this companion scope
  cannot silently regress.

## Expected Billing Core Resume

The generated real graph now uses `final_verification_repair_resume_003.md`,
preserves T001/T002, and starts at T003 with:

```text
backend/ent/**
backend/ent/schema/**
backend/ent/migrate/**
backend/go.mod
backend/go.sum
```

T004 and T005 also include `backend/go.mod` and `backend/go.sum`.

## Verification

- `python -B -m pytest tests/test_document_to_plan.py::DocumentToPlanTests::test_final_verification_repair_context_builds_editable_repair_task -q`
- `python -B -m pytest tests/test_document_to_plan.py -q`
- `python -B -m pytest tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_final_verification_relaunch_writes_fresh_resume_for_latest_failed_attempt -q`
- `python -B -m compileall planner tests -q`
- `git diff --check`
- Real Billing Core final-verification graph probe against
  `.alchemy/billing_core_v274_20260624_012/final_verification`
