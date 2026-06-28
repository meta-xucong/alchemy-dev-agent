# V2.119 Repository Caller Timeout Split

## Problem

V2.117 and V2.118 restored the correct Billing Core phase_011 execution chain:

- T006/T007 were preserved as completed.
- T008 `Inventory Ent caller alignment failures` completed successfully.
- The run advanced to T009 `Align repository Ent callers`.

T009 then timed out after 900 seconds. The timeout stop boundary worked: no
same-scope debug task was launched, task-local changes were rolled back, and
`phase_repair_008.md` was written. The remaining issue is task granularity:
repository caller alignment is still too broad for one real Codex worker window.

T008's inventory evidence identified the actual repository groups:

- `account_repo.go` and related identity/account callers still reference
  removed Proxy edges.
- Proxy, channel monitor, error passthrough, TLS fingerprint, and user platform
  quota repositories still call generated Ent clients that no longer exist.
- Repository provider wiring still registers retired constructors.

## Fix

Focused schema/build repairs that identify failed T009 now split repository
caller alignment into:

- `Align account repository Ent callers`
- `Remove retired generated-client repositories`
- `Align remaining repository compile contracts`

These tasks keep service/server cleanup in later tasks and use lightweight
repository compile checks (`go test ./internal/repository -run '^$'`) instead
of the previous repository-wide test execution boundary.

The schema/build cumulative repair-context floor is also raised to ten ordinary
repair briefs so the T002/T003/T006/T008/T009 chain remains available for later
phase_011 resumes.

## Verification

- Focused planner regression for T009 repository caller timeout split.
- Focused full-roadmap regression for a nine-brief schema/build repair chain.
- Real phase_011 graph probe should preserve T008 completed and replace T009
  with the three repository caller split tasks.
