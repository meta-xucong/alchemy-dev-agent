# V2.124 Iteration-Limit Resume Context

## Problem

V2.123 raised the schema/build iteration budget, but a real Billing Core resume
exposed a second iteration-limit recovery issue.

`run_attempt_023` completed the V2.122 split verification chain:

- T022 `Verify backend tests`
- T023 `Verify frontend tests`
- T024 `Verify backend build`
- T025 `Verify frontend build and lint`

The old four-iteration run then stopped before T026 review and T027 delivery
evidence. A later relaunch created `run_attempt_024`, but because the clean
iteration-limit completion evidence was not converted into resume context, the
task graph collapsed back to T001. Codex Desktop stopped that bad attempt before
it could spend another worker window.

## Fix

Full-roadmap bootstrap now scans phase attempts for clean iteration-limit stops:

- no blockers
- no active tasks
- no failed tasks
- `execution_history` contains an iteration-limit event
- completed tasks exist
- pending tasks remain

When found, Alchemy writes a `phase_repair_resume_NNN.md` context document that
preserves completed task IDs and names the pending task IDs as the next focused
scope. This keeps older ordinary repair briefs active while carrying the latest
completed verification evidence forward.

The final verification split builder also now reconstructs the whole fixed
T022-T25 split chain whenever the original final-verification timeout context is
present. Preserved split tasks are marked completed instead of being skipped,
which keeps T026 as `Review delivery readiness` rather than drifting into a new
generic verification node.

## Verification

- Focused planner regression: when T022-T25 are preserved completed, the graph
  still contains the completed split verification nodes and T026 remains the
  pending review task.
- Focused full-roadmap bootstrap regression: a clean iteration-limit attempt
  writes iteration-limit resume context preserving completed tasks and pending
  review/evidence IDs.
- Real phase_011 graph probe with synthetic iteration-limit context: T022-T25
  are completed and T026 is pending review.
- Full `tests/test_document_to_plan.py`.
- Full `tests/test_full_roadmap_execution.py`.
