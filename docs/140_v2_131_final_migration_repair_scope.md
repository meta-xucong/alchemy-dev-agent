# V2.131 Final Migration Repair Scope

## Problem

V2.130 split final source-boundary repair, but the first split task still used
`backend/migrations/**`. On the Billing Core worktree that scope was enough to
stall the real worker until the 900 second timeout, with no commands, no
evidence, and no preserved file changes.

## Fix

V2.131 narrows the first final repair task to the exact files named by the final
audit evidence:

- `backend/migrations/001_init.sql`
- `backend/migrations/003_subscription.sql`
- `backend/migrations/081_create_channels.sql`
- `backend/migrations/125_add_channel_monitors.sql`
- `backend/cmd/server/database_contract.go`
- `backend/cmd/server/database_contract_test.go`

The later backend schema/domain and frontend tasks remain split for subsequent
repair phases.

## Verification

- Focused final-verification repair planner test passed.
- Real Billing Core final-verification graph probe shows the exact migration
  repair file list.
- Full `tests/test_document_to_plan.py` passed.
- Full `tests/test_full_roadmap_execution.py` passed.
- `compileall` passed for `planner` and `tests`.
