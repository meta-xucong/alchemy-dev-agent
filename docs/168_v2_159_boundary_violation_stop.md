# V2.159 Boundary Violation Stop

## Problem

Billing Core final verification `run_attempt_033` resumed correctly after V2.158 and completed T041 inside its timeout grace window. T042 (`Repair final frontend legacy admin view cleanup`) then returned with a boundary failure:

- the worker modified files outside `allowed_files`
- Alchemy rolled the offending changes back
- the orchestrator still created `T042-DEBUG-1`

That debug task was same-scope work after a deterministic boundary violation. It could not safely expand the task boundary or preserve the rolled-back out-of-scope edits, so it risked spending another worker window without changing the recovery graph.

## Change

The orchestrator now treats worker results that report an out-of-scope file boundary violation as a non-partial technical blocker, similar to timeout handling.

When a task returns a boundary-violation result, Alchemy now:

- records a `worker_boundary_blocker` history event
- records a non-partial blocker on the original task
- avoids creating a same-scope debug task
- leaves the next supervised resume to split the task or expand the task boundary from structured evidence

## Verification

- `python -B -m pytest tests/test_runtime.py::OrchestratorTests::test_boundary_violation_records_blocker_without_debug_task tests/test_runtime.py::OrchestratorTests::test_worker_timeout_records_blocker_without_debug_task tests/test_runtime.py::OrchestratorTests::test_partial_result_raw_timeout_instruction_does_not_record_timeout_blocker -q`
- `python -B -m compileall runtime tests -q`
- `python -B -m pytest tests/test_full_roadmap_execution.py -q`
- `python -B -m pytest tests/test_runtime.py::CodexWorkerTests::test_real_worker_allows_filename_glob_scope -q`
- `python -B -m pytest tests/test_runtime.py -q`

## Billing Core Resume Note

`run_attempt_033` should be treated as operator-stopped after the legacy-admin boundary violation path was observed. The next relaunch should preserve completed T036-T041 evidence and rebuild T042 as a boundary-aware repair path instead of replaying same-scope debug.
