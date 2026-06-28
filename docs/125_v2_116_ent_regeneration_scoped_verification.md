# V2.116 Ent Regeneration Scoped Verification

## Problem

After V2.115, Billing Core `run_attempt_016` completed read-only
`T006 Inventory Ent regeneration inputs` and moved into `T007 Regenerate Ent
generated clients`.

T007 regenerated Ent artifacts and passed `go test ./ent/...`, but its task
package still carried the full backend verification command `cd backend &&
go test ./...`. That command failed in downstream repository/service/server
callers that are intentionally owned by the following caller-alignment task, so
Alchemy marked T007 partial and launched a same-scope debug worker.

## Fix

- The Ent generated-client task now has task-specific acceptance criteria.
- Its command list is scoped to `cd backend && go test ./ent/...`.
- Full backend verification remains on the downstream caller-alignment and
  stabilization tasks.

This keeps task boundaries aligned with the split graph: generated Ent artifacts
are verified in T007, while caller migrations remain in T008/T010.

## Verification

- Focused planner regression: `1 passed`.
- `tests/test_document_to_plan.py`: `30 passed`.
- Focused full-roadmap stop-boundary regression: `1 passed`.
- Focused runtime read-only inventory regression: `1 passed`.
- Real phase_011 graph probe: T007 commands are exactly
  `cd backend && go test ./ent/...`; T008 retains full backend verification.
