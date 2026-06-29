# V2.167 Final Test Boundary Glob And Stop Boundary

## Problem

Billing Core final verification `run_attempt_039` advanced through the split frontend composable tail and reached `T056 Repair final frontend test and fixture contracts`. The real worker returned successfully, but the boundary audit marked allowed frontend test files as out of scope.

The task allowed patterns such as:

- `frontend/src/**/__tests__/**`
- `frontend/src/**/*.spec.ts`
- `frontend/src/**/*.spec.tsx`

Python's `PurePosixPath.match` does not provide the intended repository-boundary semantics for these patterns. It missed nested files such as `frontend/src/components/Guide/__tests__/steps.spec.ts` and deep `*.spec.ts` files, causing a false non-partial boundary blocker.

The same failed attempt also exposed a final-verification supervisor issue: after a non-partial blocker, the parent loop could immediately launch another final-verification attempt. That is unsafe because non-partial blockers are stop boundaries and should be handed to a controlled relaunch.

## Change

- Replaced wildcard allowed-file matching in `runtime/codex_worker.py` with segment-aware repository glob matching.
- Preserved fast paths for directory and single-segment patterns.
- Added support for `**` as zero or more path segments.
- Kept `*`, `?`, and bracket matching segment-local via `fnmatch.fnmatchcase`.
- Hardened `_run_final_verification_worker` so any runtime blocker with `can_continue_partially=false` stops the current final-verification parent loop.
- Marked such final-verification attempt records with `stop_boundary=non_partial_blocker`.

## Verification

- `tests/test_runtime.py::CodexWorkerTests::test_allowed_file_globs_match_nested_frontend_tests`
- `tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_final_verification_worker_stops_after_non_partial_blocker`

## Expected Billing Core Impact

The next controlled Billing Core final-verification relaunch should not treat nested frontend test/spec files under the T056 allowlist as out-of-scope. If T056 still fails, it should fail on real product/test evidence rather than a false boundary audit.

The parent final-verification loop should also stop cleanly at future non-partial blockers instead of silently opening a new attempt from the same parent process.
