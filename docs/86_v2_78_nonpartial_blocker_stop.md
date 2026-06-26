# V2.78 Non-Partial Blocker Dispatch Stop

## Objective

V2.78 hardens the orchestrator so it stops dispatching adjacent ready tasks as
soon as the current task records a new blocker with
`can_continue_partially=false`.

The live Billing Core `run_attempt_014` on 2026-06-26 exposed a controller
correctness gap after the earlier Windows prompt hardening landed:

- `T004` exhausted its retry policy and recorded `B-T004-3` with
  `can_continue_partially=false`;
- four seconds later, the same ready-task batch still started `T005`;
- this burned more live Codex time even though the run had already concluded
  that manual inspection was required.

This is not a network-only issue. It is a scheduler stop-condition issue.

## Compatibility Contract

V2.78 does not change:

- retryable task behavior that creates a debug task instead of a blocker;
- debug-first scheduling once pending debug work exists;
- worker JSON result parsing;
- recovery/migration logic for paused or resumed runs;
- release evidence semantics.

The only behavior change is that a newly recorded non-partial blocker now stops
the current dispatch loop immediately.

## Design

### Per-Task Blocker Snapshot

Before dispatching a ready task, the orchestrator snapshots the current set of
blocker IDs whose `can_continue_partially` value is false.

### Post-Task Blocker Diff

After the task completes and normal debug-pruning housekeeping runs, the
orchestrator compares the current non-partial blocker set against the snapshot.

If any new blocker ID appeared during that task:

- record a `run_blocked` history event;
- save state;
- return immediately instead of dispatching the next ready sibling task.

### Why This Is Narrow

Retryable failures still behave exactly as before:

- the task fails;
- a debug task is created;
- no blocker is recorded yet;
- the loop breaks only because pending debug work now exists.

So V2.78 only changes the exhausted-retry / explicit-blocker path, which is
the path that should already be asking for human or controller intervention.

## Acceptance Criteria

- a task that records a new non-partial blocker prevents the same ready batch
  from dispatching sibling work;
- retryable failures that create debug tasks still interrupt the batch without
  recording a non-partial blocker;
- runtime history records a `run_blocked` event when the new stop condition
  triggers;
- runtime and full-roadmap regression suites continue to pass.

## Verification

Focused tests:

```powershell
python -B -m pytest tests/test_runtime.py::OrchestratorTests::test_non_partial_blocker_stops_current_ready_batch tests/test_runtime.py::OrchestratorTests::test_failed_task_interrupts_current_ready_batch_for_debug -q
```

Broader checkpoint:

```powershell
python -B -m pytest tests/test_runtime.py -q
python -B -m pytest tests/test_full_roadmap_execution.py -q
python -B -m py_compile runtime/orchestrator.py tests/test_runtime.py
git diff --check -- runtime/orchestrator.py tests/test_runtime.py README.md docs/86_v2_78_nonpartial_blocker_stop.md
```
