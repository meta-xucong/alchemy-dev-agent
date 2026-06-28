# V2.128 Final Verification Skip Planning Worker

## Problem

After V2.127 changed final verification to an audit/test task graph, the next
Billing Core relaunch correctly created `run_attempt_002` with T002/T003/T004
audit and test tasks. However, the generic T001 architecture planning worker
still ran first and made no visible progress for more than eight minutes.

That worker was unnecessary: the final verification graph is deterministic and
already encodes the audit/test order. Spending a real Codex worker window on
planning at this point can waste time and tokens before the actual final audit
begins.

## Fix

V2.128 pre-completes T001 only for final verification audit contexts:

- T001 is renamed to `Use deterministic final verification graph`.
- T001 is persisted with `status=completed`.
- T001 records deterministic graph-builder evidence.
- T002 remains dependent on T001 and becomes the first ready runtime task.

Normal roadmap phases still use the ordinary T001 planning worker.

## Verification

- Focused final verification graph test passed.
- Real Billing Core final-verification graph probe shows T001 completed and
  T002/T003/T004 pending audit/test tasks.
- Runtime handoff probe selects T002 `Audit final requirements and phase
  evidence` as the first ready task.
- Full `tests/test_document_to_plan.py` passed.
- Full `tests/test_full_roadmap_execution.py` passed.
- `compileall` passed for `planner`, `autodev`, and `tests`.
