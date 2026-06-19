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

## Completed Follow-Up Phases

### V2.21 Post-Acceptance Quality Gate Hardening

- Tightened real GitHub release behavior so failed, pending, or unknown CI blocks delivery when CI collection is enabled.
- Added explicit CI collection controls and no-CI opt-out behavior.
- Hardened static document verification and async job persistence.
- Verified full unit suite, acceptance harness, JSON specs, diff hygiene, and state validation.

### V2.22 External Docs-Only Delivery Plan Supplement

- Converted the `meta-xucong/-super-mario-test` external docs-only repository test findings into a supplemental development document.
- Added `docs/29_v2_22_external_docs_only_delivery.md`.
- Added `examples/external_docs_only_delivery_acceptance.md`.
- Updated README and V2 development plan to keep the new requirements aligned with the existing v2 objective.

## Next Recommended Development Phase: V2.22.1 And V2.22.2

Goal: close the largest external docs-only delivery planning gap.

Planned actions:

- Enforce the document dominance rule so parsed primary documents cannot be routed through generated one-line fallback.
- Improve Chinese and outline-style requirement extraction for technical specs.
- Add regression tests using the external platformer spec shape.
- Keep the existing one-line generated-game demo working as an explicit fallback path only.


## Completed Follow-Up Phase: V2.22 Implementation And Real External Game Delivery

- Document dominance, richer Chinese extraction, scaffold planning, static artifact gates, no-CI waiver evidence, worker safety prompt, local git identity fallback, and release branch binding are implemented and tested.
- The external docs-only target repository was delivered through a real public PR: https://github.com/meta-xucong/-super-mario-test/pull/2.
- The generated artifact is an original retro platformer Level 1 with canvas rendering, player movement/jump controls, enemies, coins, scoring, timer, lives, level completion, modular files, and static checks.
- Browser smoke evidence is recorded in `.alchemy/super_mario_v2_22_real_run_retry/browser_smoke_initial.png` and `.alchemy/super_mario_v2_22_real_run_retry/browser_smoke_after_input.png`.

## Optional Next Phase

- Productize browser playability verification as a first-class automated document-run acceptance command instead of retaining it as manual audit evidence.


## Next Planned Phase: V2.23 Perfect Delivery Optimization

Goal: move from successful external proof to stable product-grade one-click delivery while preserving the original document-driven autonomous development objective.

Planned order:

1. V2.23.1 Browser Artifact Verifier.
2. V2.23.2 Artifact Profiles.
3. V2.23.3 Managed Worker Process Lifecycle.
4. V2.23.4 Requirement Coverage Matrix.
5. V2.23.5 Generated CI For Docs-Only Static Apps.
6. V2.23.6 Delivery Report Productization.
7. V2.23.7 UI Intake And Evidence Polish.

## Completed Follow-Up Phase: V2.23 Perfect Delivery Optimization Implementation

- Artifact profiles, artifact reports, browser evidence import, automatic browser runner contract, worker lifecycle records, requirement coverage, evaluator coverage gates, generated static CI, delivery reports, and UI evidence controls are implemented.
- Static CI generation is now part of the release task before GitHub commit/PR execution, so generated workflows can be included in the delivery branch.
- Full unit suite, external docs-only acceptance, main acceptance, JSON parsing, diff hygiene, and long-running state validation passed.

## Next Recommended Phase

- Run a real external docs-only target delivery with generated static CI and GitHub CI collection enabled.
- Add Playwright/browser-binary readiness to real environment checks and UI preflight.
- Add richer visual previews for task graph and requirement coverage before execution.

## Completed Follow-Up Phase: V2.24 Development-Cycle Brain And One-Click External Delivery Rerun

- The manual engineering SOP is now represented as `development_cycle` in document-run and API delivery reports.
- Explicit auto-merge is implemented and merge evidence is included in runtime state, delivery reports, and development-cycle scoring.
- A fresh external docs-only repository was delivered end-to-end: https://github.com/meta-xucong/super-mario-agent-v2-24-test-20260619163034.
- The generated PR passed generated static GitHub Actions CI and was merged.
- Browser automation readiness is part of real environment checks and UI preflight when auto browser verification is requested.
- Automatic browser verification was validated with Playwright screenshots, nonblank rendering, pixel-change evidence, and no console errors.
- Remaining optimization work is now product polish rather than core feasibility: richer UI checklist/graph/coverage views and reducing internal retry frequency for complex game tasks.
