# Long-Running Roadmap

Objective: Continue autonomous development until the document-driven agent system is ready for acceptance or blocked by an external requirement.

## Completed Phases

### V2.7 Real Execution Preflight

- Added real Codex/GitHub execution flags to the document-run CLI.
- Added deterministic repository path, git, Codex, and gh preflight checks.
- Added optional public repository preparation.
- Persisted preflight evidence and blocked-state runtime state.

### V2.8 Local API And Project Service Runtime

- Implemented local project creation and persistence.
- Supported multi-file project input through local file paths and UI-oriented file metadata.
- Built intake, context, task graph, runs, run events, and delivery summaries through API/service calls.

### V2.9 Browser UI And Async Run Control

- Added the browser console for project create, upload, GitHub source, plan preview, execution monitor, and delivery review.
- Added multipart upload handling into per-project storage.
- Added asynchronous run jobs with pause, resume, stop, and live event retrieval.

### V2.10 Task-Boundary Controls And Private GitHub Preflight

- Made pause and stop requests visible to the execution loop before dispatching the next task.
- Recorded blocked delivery state when a run is stopped before completion.
- Added optional private GitHub `gh auth status` preflight without storing tokens.

### V2.11 Private GitHub Source Adapter

- Implemented optional private repository clone/fetch using local `gh` when auth preflight passes.
- Kept public clone/fetch as default and token-free.
- Integrated private preparation into document-run and API source inspection.

### V2.12 Controlled End-To-End Acceptance Harness

- Added a local acceptance harness for document intake, file upload/source paths, planning, async execution, event retrieval, and delivery report generation.
- Produced a machine-readable acceptance report used as a local delivery gate.

### V2.13 Real Environment Validation

- Added real environment reporting for `git`, `gh`, `gh auth`, and Codex CLI.
- Found the WindowsApps Codex CLI access-denied blocker and recorded exact evidence.

### V2.14 Standalone Codex CLI API Integration

- Installed and validated a standalone Codex CLI at `D:\AI\Tools\CodexCLI\bin\codex.exe`.
- Added explicit Codex executable support to CLI, API, environment checks, and worker adapter.
- Verified a bounded API-to-real-Codex smoke.

### V2.15 Real Codex Worker File-Boundary Hardening

- Added `allowed_files` worker boundaries and persisted worker package payloads.
- Added git diff auditing before and after real `codex exec`.
- Rolled back out-of-scope changes and task-local timeout changes.
- Verified a real Codex out-of-scope boundary smoke.

### V2.16 Real-Run Worktree Lifecycle

- Added isolated git worktree lifecycle for real Codex document-runs.
- Rebuilt context, graph, state, and worker packages against the worktree path.
- Added browser controls for real Codex, real GitHub, worktree isolation, and keep-worktree behavior.
- Verified a real Codex isolated worktree smoke.

### V2.17 Resumable Worker Execution

- Added runtime recovery from stopped, paused, failed, and active task state.
- Added document-run CLI resume flags and API/UI resume wiring.
- Verified focused recovery tests, acceptance, and a bounded real Codex recovery smoke.

### V2.18 Real GitHub Delivery Validation

- Added a GitHub Actions CI workflow for tests and JSON spec validation.
- Added controlled real delivery validation for branch, commit, push, draft PR, and CI collection.
- Created draft PR #2 against the public repository.
- Fixed a real CI-discovered async job-state race with atomic job writes and tolerant load retries.
- Rebasing the validation PR onto the fix produced GitHub Actions `CI / tests` success.
- Added configurable CI wait polling to avoid early `unknown` check state.

### V2.19 Representative Real Document-Driven Delivery Run

- Proved the document-driven pipeline can drive a controlled real Codex worker run against the current repository.
- Real Codex created `docs/28_representative_delivery_probe.md` inside an isolated worktree.
- Source checkout stayed clean while task-local edits remained in the worktree.
- Added deterministic static document verification and deterministic review so read-only tasks do not drift into unrelated Codex debugging.
- The representative run reached `DONE condition met` with final gate score `0.88`.

## Current Phase: V2.20 Delivery Stabilization And Acceptance Closure

Goal: close the current long-running objective if the repository is now acceptance-ready, or record the exact remaining gap as a blocker or next targeted phase.

Planned actions:

- Run final local acceptance and full unit suites.
- Validate JSON specs, diff hygiene, and long-running state.
- Confirm GitHub push status and inspect relevant CI/PR evidence.
- Decide whether the current objective can be marked `done` or requires one more targeted stabilization phase.
