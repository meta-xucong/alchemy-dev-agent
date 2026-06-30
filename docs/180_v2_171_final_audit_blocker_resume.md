# V2.171 Final Audit Blocker And Resume Preservation

## Problem

Billing Core `final_verification/run_attempt_044` consumed the V2.170 split correctly:

- T056 `Repair final frontend API and integration test contracts` completed.
- T057 `Repair final frontend component and composable test contracts` completed.
- T058 `Repair final frontend view router i18n utility test contracts` completed.
- T059 `Repair final frontend test config and fixture contracts` completed.

T060 `Audit final requirements and phase evidence` then completed its read-only audit worker with return code 0, but reported `FINAL_AUDIT_STATUS=FAIL` with real remaining product defects:

- `frontend/src/components/admin/usage/__tests__/UsageTable.spec.ts` still had five failing image usage tooltip assertions.
- Frontend `/admin/ops` API/router/sidebar surfaces still exposed forbidden ops/upstream/token-log behavior.
- Residual retired schema, migration, and source-boundary references still required cleanup before final PASS.

Two Alchemy controller issues appeared at this boundary:

1. The environment blocker detector treated raw Codex retry warnings such as `stream disconnected` inside a successful worker log as authoritative, so the real audit failure was incorrectly classified as an `environment` blocker.
2. The final-verification resume builder inferred a blocked partial audit as completed partial downstream handoff, causing the first T060 repair resume to preserve T060 even though it had failed.

## Change

`runtime/orchestrator.py` now only treats raw Codex environment patterns as authoritative when the structured worker result itself is `blocked`. Successful or partial workers can still mention retry warnings in raw logs without becoming environment blockers.

Boundary-violation detection now also requires actual `files_changed` evidence. A read-only audit saying that repairs require files outside the current `allowed_files` is not the same thing as a worker modifying files outside the boundary.

`autodev/full_roadmap_executor.py` now excludes nodes whose current status is `failed`, `blocked`, `timed_out`, or `cancelled` from inferred partial downstream handoff preservation. Real partial handoff remains supported for non-terminal nodes with scoped progress and downstream target scope.

## Verification

- `tests/test_runtime.py::OrchestratorTests::test_boundary_violation_records_blocker_without_debug_task`
- `tests/test_runtime.py::OrchestratorTests::test_worker_connectivity_failure_blocks_without_debug_retry`
- `tests/test_runtime.py::OrchestratorTests::test_partial_audit_raw_stream_warning_does_not_become_environment_blocker`
- `tests/test_runtime.py::OrchestratorTests::test_worker_raw_usage_limit_context_does_not_become_environment_blocker`
- `tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_final_verification_resume_preserves_partial_downstream_handoff`
- `tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_blocked_partial_final_audit_is_not_preserved_as_completed`
- `tests/test_runtime.py`
- `tests/test_full_roadmap_execution.py`
- `python -B -m compileall runtime autodev tests -q`
- `python C:\Users\T14S\.codex\skills\long-running-task\scripts\validate_state.py --project .`

## Real Billing Core Probe

The real helper first generated `final_verification_repair_resume_040.md` from `run_attempt_044`, which exposed the preserve bug by listing T060 as completed.

After the fix, the helper generated `final_verification_repair_resume_041.md` with:

- `Repair attempt: run_attempt_044`
- `Primary failed task IDs: T060`
- completed tasks preserved only through T059

The next controlled Billing Core relaunch should consume `_041`, preserve T001-T059, reopen the T060 final-audit findings as editable repair work, and avoid replaying the completed T056-T059 test leaf tasks.
