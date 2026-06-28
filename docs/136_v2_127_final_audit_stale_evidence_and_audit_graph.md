# V2.127 Final Audit Stale Evidence And Audit Graph

## Problem

After V2.126 fixed final verification worktree inheritance, the Billing Core
final verification worker reached the inherited worktree but generated a broad
`Implement large refactor integration` task. That was wasteful and risky at the
handoff gate because the run was already past all roadmap phases.

The trigger was a stale-evidence mismatch in final audit aggregation:

- phase records for promoted phases had `promotion.can_promote=true` and passing
  scores;
- old nested `delivery_report.final_gate.hard_failures` and
  `runtime_state.evaluation.hard_failures` still contained historical
  `Required tests are failing.` strings;
- final audit treated those stale nested values as current blockers and told the
  final worker to repair them.

The same run also showed that a supervisor-stopped final verification attempt
could poison the next relaunch if `run_attempt_001` were reused.

## Fix

V2.127 changes three controller paths:

1. `FinalVerificationLoop` ignores stale nested gate/evaluation failures when a
   phase record is cleanly promoted: done/completed status, `can_promote=true`,
   passing score, and no promotion reasons.
2. `TaskGraphBuilder` recognizes final verification documents from the final
   audit title/path/context and builds audit/test tasks instead of the generic
   large-refactor integration task.
3. `FullRoadmapExecutor` starts final verification from the next unused
   `run_attempt_NNN` directory, so an operator-stopped final attempt is preserved
   as evidence without causing the next attempt to stop immediately.

Boundary warning detection was also narrowed so repair instructions mentioning
`out-of-scope full-suite failures` are not treated as scope violations.

## Verification

- Focused final verification task-graph test passed.
- Focused stale hard-failure audit tests passed.
- Focused final verification attempt-directory test passed.
- Real Billing Core final-verification document graph probe now produces:
  - `T002 Audit final requirements and phase evidence`
  - `T003 Run final simulation probes`
  - `T004 Run final real repository checks`
  - no integration task
- Full `tests/test_document_to_plan.py` passed.
- Full `tests/test_full_roadmap_execution.py` passed.
- `compileall` passed for `planner`, `autodev`, and `tests`.
