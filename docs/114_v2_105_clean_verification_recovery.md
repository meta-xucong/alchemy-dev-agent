# V2.105 Clean Verification Recovery

## Problem

V2.103 intentionally recovered concrete verification failures from older phase
attempts, and V2.104 preserved original requirement coverage while dispatching a
focused verification repair. After the Billing Core `run_attempt_044` repair,
T018 completed successfully: frontend install, tests, build, and lint all
passed. Its worker result still recorded non-fatal `known_issues` such as dirty
worktree context and warning noise.

The recovery code treated any `known_issues` or `follow_up_tasks` as repairable
failure evidence, even when the worker status was `completed` and every command
exited with code 0. If left unchanged, a clean verification with warnings could
become a new repair context. Worse, if the warning was ignored but the scanner
kept walking backward, stale older failures such as the already-fixed T014 build
error could be revived after a newer clean test verification had superseded
them.

## Fix

Verification repair detection is now stricter:

- `tests_failed` still always triggers repair evidence.
- Any command with a non-zero exit code still triggers repair evidence.
- explicit failed/partial/blocked/timed-out worker statuses still trigger
  repair evidence.
- `known_issues` and `follow_up_tasks` only trigger repair evidence when the
  worker status is not a successful status such as `completed`, `done`, or
  `passed`.

Historical verification recovery now stops when it encounters a newer clean
test verification worker. That preserves V2.103's ability to recover older
failures from degraded preserve-only attempts, but prevents stale fixed build
errors from resurfacing after a newer successful verification pass.

## Billing Core Impact

The immediate Billing Core stop was not a final delivery stop. It was a safe
supervisor pause before relaunching after V2.104. The latest attempt had no live
worker process, and T018's verification result was successful with only
non-fatal warnings. V2.105 prevents that state from creating another false
repair loop.

The next controlled Billing Core launch should resume through Alchemy only and
should not recover the old T014 admin compliance Markdown build failure after
the newer successful T018 verification.

## Verification

- focused full-roadmap recovery regressions => `3 passed`
- `python -m pytest tests/test_full_roadmap_execution.py -q` => `63 passed`
- `python -m pytest tests/test_document_to_plan.py -q` => `25 passed`
- `python -m compileall autodev planner tests -q` => passed
