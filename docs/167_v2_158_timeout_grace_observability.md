# V2.158 Timeout Grace Observability

## Problem

Billing Core final verification `run_attempt_032` reached T041 (`Repair final frontend admin operations view contracts`) after T036-T040 completed in the inherited worktree. The T041 worker crossed the base 900 second timeout while frontend verification child processes were still active.

Alchemy correctly granted one bounded progress grace window, but the live worker status was easy to misread because the latest grace deadline was not exposed as a first-class lifecycle field. Codex Desktop wrote a `supervisor_stop.json` marker and cancelled the worker before the full timeout-plus-grace window elapsed.

## Change

`WorkerLifecycleRecord` now persists `timeout_grace_deadline_at` whenever `ManagedSubprocessRunner` grants progress-based timeout grace.

Each timeout grace snapshot also records the same `deadline_at`, and the lifecycle error message includes the deadline. Supervisors can now distinguish:

- base timeout exceeded but worker is still inside a bounded progress grace window
- timeout plus grace exceeded and the worker should be treated as overdue
- operator stop cancellation

## Verification

- `python -B -m pytest tests/test_runtime.py::CodexWorkerTests::test_managed_subprocess_runner_extends_timeout_when_progress_is_detected tests/test_runtime.py::CodexWorkerTests::test_managed_subprocess_runner_terminates_on_timeout -q`
- `python -B -m compileall runtime tests -q`
- `python -B -m pytest tests/test_runtime.py -q`
- `python -B -m pytest tests/test_full_roadmap_execution.py -q`

## Billing Core Resume Note

`run_attempt_032` should be treated as an operator-stopped attempt at T041, not as a product failure. The next supervised relaunch should preserve completed T036-T040 evidence and resume from T041 through the correct final-verification repair path.
