# V2.120 Backend Cleanup Timeout Split

## Problem

Billing Core phase_011 `run_attempt_020` proved that the V2.119 repository
caller split works: T009 through T013 completed in the inherited worktree. The
run then timed out on T014 `Clean legacy backend services repositories and
tests`.

The timeout stop boundary behaved correctly:

- No same-scope debug task was launched.
- No T015 verification task was dispatched after the non-partial blocker.
- Task-local changes were rolled back.
- `phase_repair_009.md` preserved completed T001 through T013.

The remaining issue was task granularity. T014 still combined service cleanup,
repository cleanup, handler/server route cleanup, residual tests, and backend
verification into one worker window.

## Fix

Focused schema/build repairs that identify a backend cleanup timeout now replace
the broad cleanup task with:

- `Inventory legacy backend cleanup leftovers`
- `Clean service and repository legacy contracts`
- `Clean handler and server legacy routes`
- `Compile residual backend cleanup contracts`

The first task is read-only and records the remaining cleanup targets before
editable workers run. The editable tasks use narrower package compile checks
such as `go test ./internal/service/... ./internal/repository/... -run '^$'`
and leave full backend/frontend verification to the later stabilization task.

The schema/build cumulative repair-context floor is raised to twelve ordinary
repair briefs so the longer T002/T003/T006/T008/T009/T014 split chain remains
available across later resumes.

## Verification

- Focused planner regression for T014 backend cleanup timeout splitting.
- Focused full-roadmap regression for an eleven-brief schema/build repair
  chain.
- Real phase_011 graph probe with `phase_repair_001.md` through
  `phase_repair_009.md`: T009 through T013 are preserved completed, T014 starts
  as read-only cleanup inventory, and T015 through T017 contain the narrowed
  cleanup tasks.
