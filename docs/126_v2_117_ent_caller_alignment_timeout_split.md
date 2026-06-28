# V2.117 Ent Caller Alignment Timeout Split

## Problem

After V2.116, Billing Core `run_attempt_017` completed:

- `T006 Inventory Ent regeneration inputs`
- `T007 Regenerate Ent generated clients`

The next task, `T008 Align repository callers after Ent regeneration`, timed out
after 900 seconds without structured worker evidence. The timeout boundary
worked correctly: Alchemy stopped the phase attempt, wrote
`phase_repair_007.md`, and did not launch a same-scope debug task.

However, the planner did not yet know how to translate that T008 timeout repair
brief into smaller executable caller-alignment tasks. A direct resume would risk
replaying the same broad repository/service/server worker.

## Fix

- Focused schema/build repairs that identify failed `T008` now split caller
  alignment into:
  - `Inventory Ent caller alignment failures`
  - `Align repository Ent callers`
  - `Align service Ent caller contracts`
  - `Align server and handler Ent wiring`
- The inventory task has no verification command, so the runtime packages it as
  a read-only checkpoint task.
- The editable follow-up tasks use narrower relevant files and scoped Go
  commands instead of the previous full backend verification boundary.
- Schema/build phase repair bootstrap now retains at least eight ordinary
  repair briefs, keeping the full T002/T003/T006/T008 split chain available
  when phase_011 is resumed.

This is a throughput fix, not a product-code patch: Billing Core changes still
must be made by Alchemy workers in the inherited isolated worktree.

## Verification

- Focused planner regression for T008 caller-alignment timeout split.
- Focused full-roadmap regression for schema/build cumulative repair context.
- Real phase_011 graph probe should show T006/T007 preserved completed and
  T008 replaced by the caller-alignment inventory task before editable
  repository/service/server tasks.
