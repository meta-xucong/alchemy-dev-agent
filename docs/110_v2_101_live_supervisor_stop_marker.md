# V2.101 Live Supervisor Stop Marker

## Problem

During `run_attempt_040`, the supervisor wrote `supervisor_stop.json` after T010
completed so Alchemy would pause before dispatching more pre-V2.100 workers.
T011 completed, but the running parent still dispatched T012.

The reason was that `supervisor_stop.json` and `operator_stop.json` were only
used by full-roadmap resume selection. They told future launches to skip a
marked attempt, but the currently running document-run parent did not read
those marker files between task dispatches.

That distinction matters for long-running supervision: a human supervisor needs
a disk stop marker to be live control, not just stale-attempt metadata.

## Fix

Alchemy now has a `MarkerFileExecutionController` that watches a run output
directory for:

- `supervisor_stop.json`
- `operator_stop.json`

The controller checks markers before each task dispatch and through
`should_stop_worker()` while a worker is running. `DocumentRunPipeline` wraps
any existing controller with this marker controller by default, so full-roadmap
phase attempts get live stop behavior without needing a custom caller.

## Billing Core Status

After the missed live stop, the supervisor terminated the clearly scoped
`run_attempt_040` process tree. The static attempt state currently has:

- T010 completed.
- T011 completed.
- T012 active in state, but its process was stopped by the supervisor.
- `supervisor_stop.json` exists, so future resume selection must not reuse this
  active T012 state as a live resume source.

The next Billing Core relaunch should start a new attempt, carry the existing
repair context, and preserve the completed T010/T011 evidence if the planner
can safely map it. If that preservation is not carried, Alchemy should be fixed
before running more product work.

## Verification

- `python -B -m pytest tests/test_runtime.py::OrchestratorTests::test_marker_file_controller_blocks_before_dispatching_worker tests/test_runtime.py::OrchestratorTests::test_marker_file_controller_requests_running_worker_stop tests/test_document_run_pipeline.py::DocumentRunPipelineTests::test_pipeline_honors_supervisor_stop_marker_by_default -q` => `3 passed`
- `python -B -m py_compile runtime\control.py autodev\document_run.py tests\test_runtime.py tests\test_document_run_pipeline.py`
