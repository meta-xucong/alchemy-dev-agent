# Long-Running Roadmap

Objective: Continue autonomous development until the document-driven agent system is ready for acceptance or blocked by an external requirement.

## Completed Phase: V2.7 Real Execution Preflight

- Added real Codex/GitHub execution flags to the document-run CLI.
- Added deterministic repository path, git, Codex, and gh preflight checks.
- Added optional public repository preparation.
- Persisted preflight evidence and blocked-state runtime state.
- Verified focused tests, full suite, JSON specs, and state validation.
- Committed and pushed as `3cba763`.

## Current Phase: V2.8 Local API And Project Service Runtime

- Implement local project creation and persistence.
- Support multi-file project input through local file paths and UI-oriented file metadata.
- Build intake, context, task graph, runs, run events, and delivery summaries through API/service calls.
- Keep synchronous dry-run execution as the default.
- Update docs and tests for implemented API boundaries.

## Next Phase: V2.9 Browser UI And Async Run Control

- Add a small operational UI for project create, file intake, GitHub source, plan preview, execution monitor, and delivery review.
- Add real browser upload handling into per-project storage.
- Add asynchronous run jobs with pause/resume/stop state and live event retrieval.
- Verify the UI through browser smoke tests.

## Later Phase: V2.10 Controlled Real Repository Validation

- Run the system against a representative public repository and detailed development document.
- Validate real Codex worker preflight and, when environment permits, real worker execution.
- Validate real GitHub PR/CI flow or record exact environment blockers.
- Produce final acceptance report.
