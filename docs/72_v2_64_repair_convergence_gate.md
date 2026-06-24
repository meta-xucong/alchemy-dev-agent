# V2.64 Repair Convergence Gate

## Purpose

Real Codex repair runs can finish the requested fix and pass tests before every queued repair,
verification, review, and local-delivery node has been dispatched.

The repair convergence gate prevents wasteful duplicate worker loops by letting a repair run stop
as soon as the repair contract is satisfied.

## Scope

This gate applies only to repair runs created from:

- `feedback_reopen`;
- `central_auto_iteration`.

It must not affect ordinary first-pass development runs.

## Required Input Contract

The runtime state may include:

```json
{
  "repository": {
    "repair_convergence": {
      "enabled": true,
      "status": "pending",
      "source_run_id": "run_001",
      "repair_plan_id": "rp_run_001_example",
      "feedback_files": ["auto_feedback.md"],
      "target_files": ["app.py"],
      "required_tests": ["python -m unittest discover -s tests"]
    }
  }
}
```

`enabled` must be false unless `target_files` is non-empty. Vague feedback without target files
continues through the full graph.

## Completion Rule

After each worker task, the orchestrator may apply the gate when all conditions are true:

- the run has `repository.repair_convergence.enabled = true`;
- the latest worker result is `completed`;
- no tests failed and no known issues were reported;
- the worker result or task scope covers every `target_files` entry;
- `tests_passed` is non-empty, or every recorded command exited with code `0`;
- the run is local/dry-run delivery mode, not real GitHub delivery mode.

When the gate applies, the orchestrator:

- marks remaining graph nodes as `completed`;
- attaches `source=repair_convergence_gate` evidence to each completed node;
- records dry-run local delivery evidence if no delivery evidence exists;
- writes `repository.repair_convergence.status = completed`;
- records a `repair_convergence_gate` history event;
- re-runs the normal evaluator.

## Non-Goals

- It does not lower the final gate threshold.
- It does not hide failed tests.
- It does not skip real GitHub PR/CI evidence when `real_github=true`.
- It does not run when feedback lacks target files.

## Acceptance Criteria

- A repair run with duplicate same-file tasks calls the worker once, then stops.
- The runtime state explains which task triggered convergence.
- Generated cache files such as `__pycache__/*.pyc` do not count as out-of-scope worker edits.
- Final delivery remains blocked if requirement coverage, artifact probes, or evaluator hard failures
  still fail after convergence.
- A real GitHub repair run still executes the normal release flow.
