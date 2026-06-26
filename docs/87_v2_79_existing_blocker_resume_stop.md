# V2.79 Existing Blocker Resume Stop

## Objective

V2.79 hardens resumed runs so an already-present blocker with
`can_continue_partially=false` stops scheduling before any ready task is
dispatched.

The Billing Core `phase_010/run_attempt_014` recovery boundary exposed this
resume-specific gap. V2.78 stopped the current ready batch when a task created a
new non-partial blocker, but a stale interrupted run can already contain the
blocker before the fresh controller starts. In that case, the controller must
honor the blocker immediately instead of continuing adjacent or debug work.

## Compatibility Contract

V2.79 does not change:

- retry reset behavior for tasks whose recoverable blockers are cleared by
  `RuntimeRecovery`;
- operator-stop blockers that are explicitly marked `can_continue_partially`;
- debug-first scheduling for retryable failures that have not produced a
  non-partial blocker;
- the V2.78 post-task new-blocker stop behavior.

The only behavior change is that a non-partial blocker already present at the
start of an orchestrator iteration is treated as a hard stop.

## Design

After each evaluation pass, before computing ready tasks, the orchestrator now
checks the current set of non-partial blocker IDs.

If any are present:

- first attempt the existing completed-debug repair promotion path, because a
  successful nested debug repair can legitimately clear an old retry-exhausted
  blocker without dispatching another worker;
- record a `run_blocked` history event;
- save state;
- return without dispatching another worker.

This keeps resumed stale states from using old blocker evidence as permission
to continue.

## Acceptance Criteria

- a state that already contains a non-partial blocker does not dispatch a ready
  task;
- a state with successful completed-debug repair evidence can still promote and
  clear the old blocker;
- a `run_blocked` history event is recorded;
- V2.78 behavior for newly recorded non-partial blockers still passes;
- runtime and full-roadmap regression suites continue to pass.

## Verification

Focused tests:

```powershell
python -B -m pytest tests/test_runtime.py::OrchestratorTests::test_existing_non_partial_blocker_stops_before_dispatch tests/test_runtime.py::OrchestratorTests::test_non_partial_blocker_stops_current_ready_batch -q
```

Broader checkpoint:

```powershell
python -B -m pytest tests/test_runtime.py -q
python -B -m pytest tests/test_full_roadmap_execution.py -q
python -B -m py_compile runtime/orchestrator.py tests/test_runtime.py
git diff --check -- runtime/orchestrator.py tests/test_runtime.py README.md docs/87_v2_79_existing_blocker_resume_stop.md
```
