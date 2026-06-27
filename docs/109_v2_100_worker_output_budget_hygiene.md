# V2.100 Worker Output Budget Hygiene

## Problem

The V2.99 Billing Core relaunch proved that the T010 timeout split worked:
`run_attempt_040` preserved T001-T009, completed
`Complete remaining frontend API service closure`, and advanced to T011.

However, the completed T010 worker evidence exposed a new efficiency problem.
The worker solved the task, but its Codex turn included very large command
output and raw event evidence from broad searches and a dirty large worktree.
That kind of output costs tokens before Alchemy can truncate the final
`raw_output` stored on disk.

This means the recent high token use has two distinct sources:

- controller recovery bugs that caused unnecessary relaunches or same-scope
  replay;
- worker command-output discipline gaps that can make a successful narrow task
  far more expensive than a human-supervised Codex chapter.

The first category has been reduced by V2.88-V2.99. The second category needs
its own guardrails.

## Fix

The real Codex worker prompt now includes explicit output-budget hygiene:

- prefer path-scoped searches, `rg -l`, `rg --count`, or output capped with
  `Select-Object -First 80`;
- avoid broad `rg -n` searches for common terms across large directories unless
  output is capped;
- avoid full `git diff`, full `git status --short` on very dirty trees,
  generated files, dependency directories, build artifacts, and long test logs;
- summarize large outputs in the final JSON instead of pasting them into
  `commands_run`, `evidence`, or `raw_output`.

The worker result parser also truncates structured text fields returned by the
worker:

- command summaries and general text fields are capped;
- command stdout/stderr fields are capped more aggressively;
- worker-provided `raw_output` is capped with the existing raw-output limit.

This second layer does not reduce tokens already consumed inside the Codex
worker turn, but it prevents large structured evidence from polluting later
repair prompts and resume context.

## Billing Core Status

As of `run_attempt_040`:

- T001-T009 are completed or preserved.
- T010 `Complete remaining frontend API service closure` completed.
- T011 `Complete remaining frontend store and composable closure` was running
  when the supervisor wrote a stop marker so no further tasks are dispatched
  before V2.100 is verified.

The run is not looping at T001. The repeated T001 labels belong to different
attempts and are normal planning nodes. The waste that was abnormal came from
controller replay bugs and now from unbounded worker command output.

## Remaining Optimization

Alchemy still needs progress-aware worker telemetry. A hard timeout is safer
than silent runaway, but it cannot distinguish a worker that is actively
making progress from one that is stuck. The next controller-level improvement
should add heartbeat/checkpoint evidence and a bounded grace policy rather than
simply increasing `max_worker_seconds`.

## Verification

- `python -B -m pytest tests/test_runtime.py::CodexWorkerTests::test_worker_prompt_includes_output_budget_hygiene tests/test_runtime.py::CodexWorkerTests::test_worker_result_truncates_large_structured_text_fields tests/test_runtime.py::CodexWorkerTests::test_real_worker_truncates_large_raw_output_after_parsing -q` => `3 passed`
- `python -B -m py_compile runtime\codex_worker.py tests\test_runtime.py`
- `python -B -m pytest tests/test_runtime.py -q` => `129 passed`
