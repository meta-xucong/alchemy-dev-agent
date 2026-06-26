# V2.81 Technical Blocker Phase Repair

## Objective

V2.81 allows Alchemy to continue product development through its own repair
mechanism after a phase records implementation-level technical blockers.

This is different from continuing inside the same runtime state. The
orchestrator must still stop at non-partial blockers. The parent full-roadmap
executor can then create a new repair attempt with a machine-actionable repair
brief, preserving the rule that product code changes are made by Alchemy
workers rather than by the monitoring Codex thread.

## Problem Evidence

Billing Core `phase_010/run_attempt_015` stopped correctly at existing T004
non-partial blockers after V2.79. That fixed wasteful dispatch, but it also
exposed a next-layer gap: `FullRoadmapExecutor.should_auto_repair_phase()`
refused to auto-repair any phase result that contained blockers.

For implementation blockers such as `technical_limit`, this stopped the parent
roadmap before Alchemy could write a repair brief and launch a new phase
attempt.

## Design

The full-roadmap executor now distinguishes repairable technical blockers from
external stop conditions.

Repairable blockers include implementation and verification gaps such as:

- `technical_limit`;
- `quality_gate`;
- `test_failure`;
- `implementation`.

Non-repairable blockers still stop immediately, including:

- environment and preflight failures;
- missing credentials or authentication;
- operator stop requests;
- recovery/source-state blockers;
- live worker processes;
- external dependencies or approvals.

When a phase contains only repairable blockers and the phase result is
`blocked`, the executor writes `phase_repair_NNN.md` and starts a new phase
attempt instead of resuming the blocked runtime state.

The repair document now includes a `Repairable Blockers` section so the next
Alchemy worker can target the blocker IDs and task IDs directly.

## Compatibility Contract

V2.81 does not change:

- runtime non-partial blocker stop semantics;
- worker JSON result schema;
- file boundary auditing;
- interrupted live-worker detection;
- preflight/environment blocker handling.

The change only affects the parent full-roadmap decision about whether a new
phase repair attempt is safe.

## Acceptance Criteria

- a blocked phase with only technical implementation blockers creates a repair
  document and retries the phase;
- the repair document includes blocker IDs and required changes;
- existing low-score phase repair behavior is preserved;
- interrupted active worker resume behavior is preserved;
- external stop conditions remain non-repairable.

## Verification

Focused tests:

```powershell
python -B -m pytest tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_executor_auto_repairs_technical_blocker_phase_before_blocking tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_executor_auto_repairs_low_scoring_phase_before_blocking tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_executor_resumes_latest_interrupted_phase_attempt -q
```

Broader checkpoint:

```powershell
python -B -m pytest tests/test_full_roadmap_execution.py -q
python -B -m py_compile autodev\full_roadmap_executor.py tests\test_full_roadmap_execution.py
git diff --check -- autodev/full_roadmap_executor.py tests/test_full_roadmap_execution.py README.md docs/89_v2_81_technical_blocker_phase_repair.md
```
