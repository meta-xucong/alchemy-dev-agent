# Long-Running Progress

## 2026-06-17

- Initialized long-running state for runtime v0.1 implementation.
- Confirmed existing repository contains specification docs and schemas only.
- Confirmed no `execution_kernel.md` exists; implementation follows current execution loop, task graph, worker, and evaluation docs.
- Implemented deterministic runtime v0.1 with orchestrator, graph engine, router, worker adapter, evaluator, state manager, and CLI loop.
- Added standard-library unit tests and CLI smoke coverage.
- Updated README with runtime usage and verification commands.
- Upgraded runtime to a usable autonomous development prototype with a real Codex subprocess adapter behind `--real-codex`, structured worker result parsing, deterministic dry-run mode, retry/debug task generation, weighted final evaluation gate, and GitHub execution flow behind `--real-github`.
- Added `runtime/github_flow.py`, expanded persistent runtime state toward schema v2, and added release/GitHub evidence as a required final gate input.
- Expanded tests to cover subprocess worker parsing failures, retry/debug scheduling, GitHub dry-run evidence, final gate behavior, and CLI smoke completion.
- Updated README, worker docs, execution-loop docs, and roadmap for the new runtime behavior.
## 2026-06-17 Contract Alignment Fix

- Audited docs, specs, runtime modules, tests, and README for contract drift.
- Found schema/runtime drift: runtime persisted `done`, `created_at`, `evaluation_result`, `iteration_history`, repository/GitHub execution fields, string task ID lists, and task node `relevant_files`, `commands_to_run`, and `retry_count` fields not fully represented in schemas.
- Updated `specs/state_schema_v2.json` and `specs/task_graph_schema.json` to recognize intentional runtime fields.
- Updated stale runtime/README version wording.
- Added regression tests that assert runtime state and task node keys are declared in schemas.
- Verified unit tests, CLI smoke, and JSON parsing.
## 2026-06-18 Self-Check Bug Fixes

- Found and fixed real GitHub flow bug where a clean worktree caused `git commit` to be treated as a fatal failure.
- Found and fixed state-loading bug where schema-style task reference objects could remain as dictionaries in runtime task ID lists.
- Found and fixed real Codex worker parsing brittleness for JSONL/event-stream outputs containing nested worker JSON.
- Added regression tests for all three bugs.
- Verified 18 tests, CLI smoke, JSON parsing, and long-running state validation.
## 2026-06-18 V2 Document-Driven Plan

- Reframed v2 around the user's primary scenario: detailed development documents, supporting files, and optional GitHub repository context.
- Added `docs/07_v2_development_plan.md` with lifecycle, module boundaries, milestones, risks, and implementation readiness criteria.
- Added `docs/08_intake_and_context.md` for ProjectBrief, ContextBundle, document parsing, repository retrieval, GitHub CLI authentication, requirement mapping, and blocker handling.
- Added `docs/09_ui_and_api_requirements.md` for multi-file upload, GitHub inspection, intake review, task graph preview, execution monitoring, and delivery review.
- Added `docs/10_v2_alignment_audit.md` to record scenario, contract, runtime boundary, gap, logic, and risk audits.
- Added `specs/project_brief_schema.json` and `specs/context_bundle_schema.json`.
- Added `examples/document_driven_project_example.md`.
- Updated README to describe the document-driven primary workflow and current implementation boundary.
## 2026-06-18 V2.1 Intake Runtime

- Added the `intake/` package for local ProjectBrief generation.
- Implemented `DocumentLoader` for local file cataloging, deterministic file IDs, SHA-256 hashes, media type detection, summaries, parse status, and role inference.
- Implemented GitHub URL parsing for HTTPS, SSH shorthand, and SSH URL forms without network access.
- Implemented `ProjectBriefBuilder` for document-driven and one-line fallback modes.
- Added explicit blockers for missing objectives, missing primary documents, unreadable files, unsupported required files, and invalid GitHub URLs.
- Added local ProjectBrief schema contract validation.
- Added CLI support via `python -m intake.project_brief`.
- Added intake tests and updated README/v2 docs to reflect V2.1 implemented scope.
## 2026-06-18 One-Line App Generation Demo

- Evaluated the current system honestly: V2.1 did not yet satisfy arbitrary "user input objective -> finished program" delivery.
- Added a narrow local demo pipeline from one-line objective to ProjectBrief, ContextBundle, TaskGraph, deterministic local agent events, generated artifact, static verification, and reviewer evidence.
- Added ContextBundle data structures and builder.
- Added TaskGraphBuilder for generated-app demos.
- Added `autodev.demo_run` CLI.
- Added an original HTML5 canvas retro platformer generator that avoids protected game names, characters, layouts, and external assets.
- Added tests for the one-line platformer generation path and CLI.
- Ran the user's requested game prompt through the pipeline and generated `.alchemy/generated/retro_platformer_test/index.html`.
- Browser-verified the generated game page through local HTTP: visible HUD, canvas, sky, platforms, coins, player, gaps, and controls.
- Updated README, audit docs, and example material with the demo command and boundaries.
## 2026-06-18 V2.2 Repository Context Runtime

- Added `context/repository_indexer.py` for deterministic local repository indexing.
- Added file kind classification for source, test, docs, config, CI, assets, migrations, and unknown files.
- Added language detection, package file detection, CI workflow detection, package manager detection, and test/build/lint command inference.
- Integrated repository indexing into `ContextBundleBuilder` when `ProjectBrief.repository.local_path` is available.
- Added blockers for missing and invalid local repository paths.
- Added `docs/11_v2_repository_context_runtime.md`.
- Updated README, v2 development plan, and alignment audit for V2.2 status.
- Added repository context tests using a synthetic local TypeScript repository.
## 2026-06-18 V2.3 Public GitHub Source Runtime

- Added `intake/github_runtime.py` for public GitHub source preparation.
- Implemented public repository clone into `RepositorySource.local_path`.
- Implemented fetch plus deterministic `checkout -B <branch> origin/<branch>` for existing git checkouts.
- Added explicit blockers for private repository requests, non-empty non-git target paths, clone failures, fetch failures, checkout failures, and invalid GitHub URLs.
- Added `python -m intake.github_runtime` CLI for source preparation smoke runs.
- Changed ProjectBrief and CLI default repository visibility from `unknown` to `public`.
- Kept private repository metadata as an explicit optional path with `gh_auth_required=true`.
- Added `docs/12_v2_public_github_source_runtime.md`.
- Updated README, architecture, V2 plan, intake/context contract, UI/API requirements, V2 audit, V2.2 context notes, and examples to reflect public repositories as the primary path.
- Updated tests to cover public-first defaults, public clone/fetch, and private optional blocker behavior.
## 2026-06-18 V2.4 Document-To-Plan Runtime

- Added `context/requirement_extractor.py` for deterministic requirement extraction from structured development documents.
- Extracted requirement priority, acceptance criteria, source document IDs, and related repository files.
- Integrated requirement extraction into `ContextBundleBuilder` while preserving the one-line generated-game safety path.
- Rebuilt `planner/task_graph_builder.py` to create document-driven architecture, implementation, verification, and review tasks.
- Added traceability from each requirement to implementation, verification, and review task IDs.
- Added `docs/13_v2_document_to_plan_runtime.md`.
- Updated README, V2 plan, intake/context contract, V2 audit, and document-driven example for V2.4 status.
- Added `tests/test_document_to_plan.py` covering document requirements, related-file mapping, task graph generation, and legacy one-line demo graph preservation.
## 2026-06-18 V2.5 Plan-To-Execution Handoff Runtime

- Added `runtime/handoff.py` to convert ProjectBrief, ContextBundle, and TaskGraph into executable RuntimeState.
- Added worker package generation from document-driven task nodes into `CodexWorkerInput`.
- Preserved repository metadata, blockers, objective, generated graph, and document-aware done criteria during handoff.
- Extended `Orchestrator.initialize` and `Orchestrator.run` to accept an external initial RuntimeState or TaskGraph.
- Added release task insertion during handoff so generated document-driven graphs satisfy the existing GitHub evidence DONE gate.
- Added `docs/14_v2_plan_to_execution_handoff.md`.
- Updated README, V2 plan, and V2 audit for V2.5 status.
- Added `tests/test_runtime_handoff.py` covering state handoff, worker packages, and dry-run orchestrator execution to DONE.
## 2026-06-18 V2.6 Document-Driven Dry-Run CLI

- Added `autodev/document_run.py` for a single-command document-driven dry-run pipeline.
- The CLI now builds ProjectBrief, ContextBundle, TaskGraph, RuntimeState, worker packages, orchestrator dry-run state, and final report.
- Added `document_run_report.json` output with all major contract payloads.
- Added lazy autodev exports so `python -m autodev.document_run` runs without module preload warnings.
- Fixed requirement path extraction so `.tsx` and `.jsx` paths are not truncated by `.ts` or `.js` alternatives.
- Added `docs/15_v2_document_run_cli.md`.
- Updated README, V2 plan, and V2 audit for V2.6 status.
- Added `tests/test_document_run_pipeline.py` and expanded document-to-plan path matching coverage.
## Supervisor Run 20260617-215941-iter-001

- returncode: 0
- timed_out: False
- stdout: `D:\AI\Alchemy Dev Agent System\alchemy-dev-agent\.codex-longrun\logs\20260617-215941-iter-001.jsonl`
- stderr: `D:\AI\Alchemy Dev Agent System\alchemy-dev-agent\.codex-longrun\logs\20260617-215941-iter-001.stderr.txt`
- last_message: `D:\AI\Alchemy Dev Agent System\alchemy-dev-agent\.codex-longrun\logs\20260617-215941-iter-001.last-message.md`
- event_summary: `D:\AI\Alchemy Dev Agent System\alchemy-dev-agent\.codex-longrun\logs\20260617-215941-iter-001.summary.json`

### Event Summary

- total_events: 274
- malformed_lines: 1
- thread_id: 019ed5e1-70d3-7593-89b6-a64e881b4a96
- agent_messages: 64
- command_executions: 73
- command_failures: 9
- file_changes: 29
- file_change_failures: 0
- last_event_type: turn.completed

- failed_command: `"C:\\Program Files\\WindowsApps\\Microsoft.PowerShell_7.6.2.0_x64__8wekyb3d8bbwe\\pwsh.exe" -Command 'codex --help'`
  exit_code: 1
  status: failed
  output_tail: [0m[36;1m[31;1m[31;1m[36;1m | [31;1mProgram 'codex.exe' failed to run: An error occurred trying to start process 'C:\Program Files\WindowsApps\OpenAI.Codex_26.609.4994.0_x64__2p2nqsd0c76g0\app\resources\codex.exe' with working directory 'D:\AI\Alchemy Dev Agent System\alchemy-dev-agent'. 拒绝访问。At line:2 char:1[0m [31;1m[36;1m[36;1m[0m[36;1m[0m[36;1m[31;1m[31;1m[36;1m[31;1m+ codex --help[0m [31;1m[36;1m[36;1m[0m[36;1m[0m[36;1m[31;1m[31;1m[36;1m[31;1m+ ~~~~~~~~~~~~.[0m

- failed_command: `"C:\\Program Files\\WindowsApps\\Microsoft.PowerShell_7.6.2.0_x64__8wekyb3d8bbwe\\pwsh.exe" -Command 'python -m compileall runtime'`
  exit_code: 1
  status: failed
  output_tail: 312.pyc.1574408265360' -> 'runtime\\__pycache__\\run_loop.cpython-312.pyc' Compiling 'runtime\\state_manager.py'... *** PermissionError: [WinError 5] 拒绝访问。: 'runtime\\__pycache__\\state_manager.cpython-312.pyc.1574408265360' -> 'runtime\\__pycache__\\state_manager.cpython-312.pyc' Compiling 'runtime\\task_graph_engine.py'... *** PermissionError: [WinError 5] 拒绝访问。: 'runtime\\__pycache__\\task_graph_engine.cpython-312.pyc.1574408265360' -> 'runtime\\__pycache__\\task_graph_engine.cpython-312.pyc'

- failed_command: `"C:\\Program Files\\WindowsApps\\Microsoft.PowerShell_7.6.2.0_x64__8wekyb3d8bbwe\\pwsh.exe" -Command '$env:PYTHONDONTWRITEBYTECODE='"'1'; python -B -m unittest discover -s tests"`
  exit_code: 1
  status: failed
  output_tail:  _resetperms(path) File "C:\Users\T14S\AppData\Local\Programs\Python\Python312\Lib\tempfile.py", line 286, in _resetperms _dont_follow_symlinks(_os.chmod, path, 0o700) File "C:\Users\T14S\AppData\Local\Programs\Python\Python312\Lib\tempfile.py", line 277, in _dont_follow_symlinks func(path, *args) PermissionError: [WinError 5] 拒绝访问。: 'C:\\Users\\T14S\\AppData\\Local\\Temp\\tmpuwi_o1my' ---------------------------------------------------------------------- Ran 13 tests in 0.204s FAILED (errors=5)

- failed_command: `"C:\\Program Files\\WindowsApps\\Microsoft.PowerShell_7.6.2.0_x64__8wekyb3d8bbwe\\pwsh.exe" -Command '$env:PYTHONDONTWRITEBYTECODE='"'1'; python -B -m unittest discover -s tests"`
  exit_code: 1
  status: failed
  output_tail: C:\Users\T14S\AppData\Local\Programs\Python\Python312\Lib\tempfile.py", line 286, in _resetperms _dont_follow_symlinks(_os.chmod, path, 0o700) File "C:\Users\T14S\AppData\Local\Programs\Python\Python312\Lib\tempfile.py", line 277, in _dont_follow_symlinks func(path, *args) PermissionError: [WinError 5] 拒绝访问。: 'D:\\AI\\Alchemy Dev Agent System\\alchemy-dev-agent\\.test-tmp\\tmpq2_9gnfh' ---------------------------------------------------------------------- Ran 13 tests in 0.211s FAILED (errors=5)

- failed_command: `"C:\\Program Files\\WindowsApps\\Microsoft.PowerShell_7.6.2.0_x64__8wekyb3d8bbwe\\pwsh.exe" -Command '$env:PYTHONDONTWRITEBYTECODE='"'1'; python -B - <<'PY'
from pathlib import Path
import tempfile
root=Path('.test-tmp')
root.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=root) as d:
    p=Path(d)
    print('dir', p)
    print('exists', p.exists())
    (p/'x.txt').write_text('ok', encoding='utf-8')
    print((p/'x.txt').read_text(encoding='utf-8'))
PY"`
  exit_code: 1
  status: failed
  output_tail: [31;1mParserError: [0m [31;1m[36;1mLine |[0m [31;1m[36;1m[36;1m 2 | [0m $env:PYTHONDONTWRITEBYTECODE='1'; python -B - <[36;1m<[0m'PY'[0m [31;1m[36;1m[36;1m[0m[36;1m[0m[36;1m | [31;1m ~[0m [31;1m[36;1m[36;1m[0m[36;1m[0m[36;1m[31;1m[31;1m[36;1m | [31;1mMissing file specification after redirection operator.[0m

## 2026-06-18 V2.7 Real Execution Preflight

- Added `autodev/preflight.py` for deterministic repository path, git, Codex CLI, and GitHub CLI checks.
- Added document-run flags for `--prepare-repository`, `--real-codex`, `--real-github`, `--codex-executable`, and `--max-worker-seconds`.
- Kept dry-run execution as the default safe path and block real execution before workers run when required tools are unavailable.
- Integrated optional public repository source preparation into `DocumentRunPipeline`.
- Added `preflight` evidence to `document_run_report.json`.
- Ensured blocked preflight runs still persist `state.json` for audit and recovery.
- Added `docs/16_v2_real_execution_preflight.md`.
- Updated README, V2 plan, and V2 alignment audit for V2.7 status and remaining real-environment validation boundary.
- Added preflight and document-run regression tests.

## 2026-06-18 V2.8 Local API Runtime

- Added `server/project_service.py` with persistent project creation, file references, intake rebuild, planning, execution runs, event retrieval, and delivery summaries.
- Added `server/api.py` with a standard-library local JSON API server.
- Implemented API-compatible project creation from `documents`/`attachments` arrays or a UI-oriented `files` list.
- Persisted project metadata, ProjectBrief, ContextBundle, TaskGraph, run state, document-run report, and run summary under `.alchemy/server/projects/{project_id}`.
- Added synchronous run execution through the existing `DocumentRunPipeline` with dry-run defaults and real-execution flags passed through.
- Added completed-run event retrieval for the execution monitor path.
- Added `docs/17_v2_local_api_runtime.md`.
- Updated README, UI/API requirements, V2 plan, and V2 alignment audit for the implemented local API boundary.
- Added service-level and HTTP smoke tests.

## 2026-06-18 V2.9 Browser UI And Async Runtime

- Added `server/jobs.py` for async run job records, persisted controls, and append-only event logs.
- Extended the local API with async run start using `{ "async": true }`.
- Added run job, pause, resume, stop, and events endpoints.
- Added multipart upload support for `POST /projects/{project_id}/files`.
- Stored browser uploads under each project's `uploads/` directory and fed them back into ProjectBrief intake.
- Added `server/static/` browser console assets for project creation, upload, planning, async run start, controls, events, and delivery review.
- Added `docs/18_v2_browser_ui_async_runtime.md`.
- Updated README, UI/API requirements, V2 plan, V2.8 local API notes, and V2 alignment audit.
- Browser DOM-verified the console on a free local port after finding port `8765` was occupied by another local service.
- Added service-level, HTTP, multipart upload, async run, control endpoint, and static asset tests.

## 2026-06-18 V2.10 Task-Boundary Controls And Private GitHub Preflight

- Added `runtime/control.py` with `ExecutionController`, `ControlDecision`, and no-op default control behavior.
- Wired Orchestrator to check pause/stop decisions before dispatching each ready task.
- Stop decisions now record blocker `B-RUN-STOPPED` and prevent further task dispatch.
- Pause decisions now record `run_paused` and return before worker dispatch.
- Added `JobExecutionController` to translate persisted async job controls into task-boundary runtime decisions.
- Added `intake/gh_auth.py` for optional `gh --version` and `gh auth status` checks without reading or storing tokens.
- Integrated private repository visibility into document-run preflight with `--repository-visibility`.
- Updated README and V2 docs for task-boundary controls and private GitHub auth preflight.
- Added tests for runtime stop/pause controls, server job boundary stop, GitHub auth preflight, and private repository preflight.

## 2026-06-18 V2.11 Private GitHub Source Adapter

- Added `intake/private_github_runtime.py` for optional private GitHub source preparation through local `gh` authentication.
- Implemented private clone with `gh repo clone OWNER/REPO <local_path> -- --branch <branch> --single-branch`.
- Implemented fetch and deterministic checkout for existing private git checkouts.
- Preserved public repository clone/fetch as the default token-free path.
- Integrated private preparation into `autodev.document_run --prepare-repository --repository-visibility private`.
- Added API `github/inspect` prepare behavior that chooses public or private source runtime based on repository visibility.
- Updated README, V2 plan, private GitHub docs, and V2 audit.
- Added deterministic fake-runner tests for private clone, fetch, and auth-blocked behavior.

## 2026-06-18 V2.12 Local Acceptance Harness

- Added `autodev/acceptance_run.py` for a local end-to-end acceptance harness.
- The harness creates a fixture repository, development document, supporting API contract, ProjectService project, task graph, async run, event retrieval, and delivery summary.
- Added `acceptance_report.json` with machine-readable pass/fail checks.
- Added `docs/21_v2_acceptance_harness.md`.
- Updated README, V2 plan, and V2 audit for the acceptance gate.
- Added direct harness and CLI tests.
- Ran the acceptance CLI manually and generated `.alchemy/acceptance/acceptance_report.json` with status `passed`.

## 2026-06-18 V2.13 Real Environment Validation

- Added `autodev/real_env_check.py` to produce a machine-readable real-execution readiness report.
- Added `docs/22_real_environment_validation.md`.
- Verified `git` is available.
- Verified `gh` is available and authenticated as `meta-xucong`.
- Verified `codex --version` fails from PowerShell with Windows access denied.
- Wrote `.alchemy/real_env_check/real_environment_report.json` with status `blocked`.
- Added tests for report payload helpers and token redaction.
- Marked the long-running task blocked on external Codex CLI launchability, because real worker validation cannot proceed safely without a working CLI executable.

## 2026-06-18 V2.14 Standalone Codex CLI API Integration

- Installed standalone Codex CLI 0.141.0 to `D:\AI\Tools\CodexCLI\bin\codex.exe` using the official install script and an explicit `CODEX_INSTALL_DIR`.
- Verified the standalone CLI launches without relying on the WindowsApps desktop package path.
- Added `--codex-executable` support to `autodev.real_env_check` and made environment checks accept absolute executable paths.
- Added `POST /environment/check` to the local API and wired the browser console to pass a Codex CLI executable path.
- Updated real worker invocation to use `codex exec --json --sandbox workspace-write` for implementation-capable real runs.
- Added `docs/23_codex_cli_api_integration.md` and updated README/V2.13 docs.
- Verified API-to-real-Codex-worker smoke with `max_iterations=1`; the run completed one real task and intentionally remained `in_progress` because the smoke was bounded to one iteration.

## 2026-06-18 V2.15 Real Codex Worker File-Boundary Hardening

- Added `allowed_files` to `CodexWorkerInput` and persisted worker package payloads.
- Updated real worker prompts to require edits only inside `allowed_files`.
- Added machine-enforced git diff auditing before and after real `codex exec`.
- Out-of-scope changed files are rolled back and the task is marked failed with boundary evidence.
- Timeout cleanup rolls back task-local changes after a real worker timeout.
- Architecture, review, and test tasks are read-only by default; implementation-style tasks may edit only task `relevant_files`.
- Added `docs/24_real_codex_worker_hardening.md` and README coverage.
- Verified a real Codex boundary smoke in a temporary git repository: the worker returned `blocked` for an out-of-scope requested file and left git status clean.


## 2026-06-18 V2.16 Real-Run Worktree Lifecycle

- Added first-class isolated git worktree lifecycle for `real_codex` document-runs.
- Real Codex runs now require a clean git repository root and default to a run-local worktree under the output directory.
- Rebuilt ContextBundle, TaskGraph, RuntimeState, and worker packages against the worktree path after creation so planning and execution share one repository target.
- Added API run payload support for `isolate_real_run`, `keep_worktree`, and `worktree_branch_prefix`.
- Persisted `workspace` evidence in document-run reports.
- Hardened real worker result parsing for string/list/non-dict fields observed during a real Codex smoke.
- Tightened dirty-source checks with `git status --porcelain -uall` and exact output-directory exclusion.
- Added V2.16 documentation and README coverage.
- Verified focused tests, full tests, acceptance harness, and a real Codex isolated worktree smoke.

- Browser console now exposes real Codex, real GitHub, isolated worktree, and keep-worktree run controls so UI/API/CLI real-run contracts are aligned.

## 2026-06-19 V2.17 Resumable Worker Execution

- Added `runtime/recovery.py` for explicit resume/retry preparation from `run.json`, `document_run_report.json`, or `state.json`.
- Recovery now resets active tasks, retryable failed tasks, and retryable blocked tasks, clears recoverable blockers including `B-RUN-STOPPED`, and records a persisted recovery checkpoint.
- Extended RuntimeState and `specs/state_schema_v2.json` with the `recovery` contract.
- Added document-run CLI resume flags `--resume-from` and `--resume-task`.
- Added API/UI resume wiring so a paused run starts a new recovery run and the browser switches to `resumed_run_id`.
- Updated README and V2 docs/audits so current capabilities match runtime behavior.
- Verified focused recovery tests, full suite, JSON specs, acceptance harness, and a bounded real Codex recovery smoke.
- Advanced the long-running phase to V2.18 controlled real GitHub PR and CI delivery validation.

## 2026-06-19 V2.18 Real GitHub Delivery Validation

- Added `.github/workflows/ci.yml` so pull requests produce concrete CI evidence.
- Added `autodev.real_delivery_validation` for controlled real branch, commit, push, draft PR, and CI collection.
- Ran the harness against the public repository and created draft PR #2.
- Initial CI failed and exposed a real async job-state race where `JobStore.load()` could read an incomplete `job.json`.
- Fixed job persistence with atomic temp-file replacement and short load retries for transient incomplete reads.
- Rebasing the validation PR branch onto the fix produced GitHub Actions `CI / tests` success.
- Added configurable CI wait polling so future validation reports can wait for terminal PR check status.
- Advanced the long-running phase to V2.19 representative real document-driven delivery run.

## 2026-06-19 V2.19 Representative Real Document-Driven Delivery

- Ran a representative document-driven real Codex delivery probe against the current repository.
- The first attempts exposed three real issues: Windows Codex output decoding, planner file-boundary drift for document requirements, and read-only verification tasks drifting into full unittest/debug work.
- Fixed real Codex output capture to use bytes plus UTF-8 replacement decoding.
- Fixed document planning so acceptance-target files guide same-document requirements, same-file requirements are grouped, documentation target classification wins before verification keywords, and documentation-only plans use static checks.
- Added deterministic runtime execution for static document verification and review tasks so verification evidence is bounded and does not ask Codex to improvise unrelated test commands.
- Re-ran the representative real document-run successfully: real Codex created `docs/28_representative_delivery_probe.md` in an isolated worktree, deterministic verification and review passed, dry-run release evidence was recorded, final gate score was 0.88, and the source checkout stayed clean.
- Advanced the long-running phase to V2.20 delivery stabilization and acceptance closure.

## 2026-06-19 V2.20 Delivery Stabilization And Acceptance Closure

- Ran final local acceptance harness: 8/8 checks passed.
- Ran full unit suite: 92 tests passed.
- Validated JSON specs, whitespace diff hygiene, and long-running state schema.
- Checked GitHub Actions on `master`: the latest five runs are successful, including commit `705af9b`.
- Added `docs/28_representative_delivery_probe.md` as the formalized artifact from the successful V2.19 representative real worker run.
- Marked the long-running objective as acceptance ready / done.


## 2026-06-19 V2.21 Post-Acceptance Quality Gate Hardening

- Audited the recent real delivery, worker decoding, document planning, deterministic verification, and async job persistence changes.
- Fixed release execution so `failed`, `pending`, or `unknown` CI status blocks real GitHub release completion instead of counting as delivery evidence.
- Fixed the controlled real delivery validation harness so unhealthy or missing CI status records `B-REAL-DELIVERY-CI`; explicit `--no-ci` remains available for PR-plumbing-only validation.
- Wired configurable CI wait/poll settings through runtime CLI, document-run CLI, ProjectService/API payloads, and the browser console.
- Hardened static document verification so missing target files fail instead of passing with empty evidence.
- Hardened async `JobStore.save()` with unique temp files and retry-on-transient Windows `PermissionError` during atomic replacement.
- Updated README and V2.18 docs to reflect the stricter CI quality gate.

- Finalized V2.21 with explicit GitHub CI collection controls so repositories without PR checks can opt out while normal real GitHub delivery still treats failed, pending, or missing CI as a quality gate blocker.
- Re-ran full unit suite, acceptance harness, JSON spec parsing, diff hygiene, and state validation after the final CI collection control pass.

## 2026-06-19 V2.22 External Docs-Only Delivery Plan Supplement

- Ran a real external docs-only repository test against `https://github.com/meta-xucong/-super-mario-test`.
- Confirmed the pipeline can clone the source, create an isolated worktree, invoke real Codex, generate a playable original retro platformer artifact, browser-smoke the artifact, and produce a real PR after manual GitHub delivery.
- Identified the central gap: the ProjectBrief was correctly document-driven, but the context builder routed a game-like objective into the generated one-line artifact path, reducing the document to one generated fallback requirement.
- Recorded required follow-up work for document-dominant planning, richer Chinese/outline-style requirement extraction, empty-repository scaffold planning, built-in browser artifact verification, productized real GitHub document-run delivery, no-CI evidence handling, and an external docs-only acceptance harness.
- Added `docs/29_v2_22_external_docs_only_delivery.md` as the updated supplemental development document.
- Added `examples/external_docs_only_delivery_acceptance.md` as the representative external docs-only acceptance material.
- Updated README and `docs/07_v2_development_plan.md` so V2.22 complements the earlier versions without replacing their goals.


## 2026-06-19 V2.22 External Docs-Only Implementation And Real Game Delivery

- Implemented document-dominant planning so parsed primary documents no longer fall through to generated one-line fallback.
- Improved Chinese and outline-style requirement extraction for docs with guidance lines such as `本次提交包含：`, `该文档用于指导实现：`, and `建议下一阶段实现：`.
- Added protected-term rewriting for planning contracts and hardened Codex worker prompts so generated files do not include protected commercial game terms, even in safety notes.
- Added docs-only web game scaffold planning and grouped full scaffold delivery into one implementation task to avoid long serial worker chains.
- Added deterministic static web artifact verification, explicit no-CI waiver evidence, local git commit identity fallback, and release-branch binding to the isolated worktree branch.
- Ran a real external target delivery against `https://github.com/meta-xucong/-super-mario-test`.
- Recovered and completed the generated original retro platformer worktree after the first real run exceeded the outer timeout.
- Verified the generated game with `node tests/static_checks.js`, `StaticWebArtifactVerifier`, browser screenshots, keyboard interaction, and screenshot pixel diff.
- Created target PR https://github.com/meta-xucong/-super-mario-test/pull/2 on branch `agent/super-mario-v2-22b-20260619033500199673` with commit `72f2b6e27e972c43e135f3eec3ff0c5bc80b3bb8`.
- Final main-repository test suite passed with 114 tests.


## 2026-06-19 V2.23 Perfect Delivery Optimization Planning

- Added `docs/30_v2_23_perfect_delivery_optimization.md`.
- Kept the original autonomous development objective unchanged: detailed docs plus supporting files and GitHub repository should drive agent planning, execution, testing, debugging, evaluation, and PR delivery.
- Captured practical gaps from the real external game delivery: browser evidence not first-class, worker timeout process supervision, artifact profiles, generated CI, requirement coverage, UI polish, and domain-specific worker guardrails.
- Defined V2.23 implementation phases: browser artifact verifier, artifact profiles, managed worker lifecycle, requirement coverage matrix, generated CI, delivery report productization, and UI intake/evidence polish.
- Updated README and `docs/07_v2_development_plan.md` to reference V2.23 as the next optimization phase.

## 2026-06-19 V2.23 Perfect Delivery Optimization Implementation

- Implemented artifact profile detection for `canvas_game`, `static_web_app`, `node_project`, `python_project`, `documentation_only`, and `unknown`.
- Added `artifact_report` to document-run outputs with static artifact verification and optional browser evidence.
- Added browser evidence import plus automatic local-server/browser-runner verification with screenshot, console-error, blank-screen, and pixel-diff checks.
- Added managed real-worker lifecycle records with PID, process group, timeout, cleanup, and termination evidence.
- Added requirement coverage reports and wired missing/partial must-requirement coverage into evaluator scoring and DONE gating.
- Added generated static web CI support and moved generation into the release task before GitHub commit/PR execution.
- Added stable `delivery_report` output and API delivery summary exposure.
- Added browser console controls for automatic browser verification and generated static CI.
- Re-ran full unit suite, external docs-only acceptance, main acceptance, JSON parsing, diff hygiene, and long-running state validation successfully.

## 2026-06-19 V2.24 Development-Cycle Brain And One-Click External Delivery Rerun

- Reviewed the user's manual engineering SOP and found the missing layer: the runtime had project-level mechanics, but not one machine-checkable top-level development-cycle contract.
- Added `development_cycle` reports covering long-task state, document reading, central-brain refinement, phase planning, execution, audit, testing, iteration, full review, simulated acceptance, real delivery, and merge.
- Added explicit auto-merge support and UI/API payload wiring.
- Created a fresh public docs-only test repository: https://github.com/meta-xucong/super-mario-agent-v2-24-test-20260619163034.
- Ran a real document-driven delivery with real Codex and real GitHub against the fresh repository; the run reached `done`, generated a playable original retro canvas platformer, generated static CI, and created PR #1.
- GitHub Actions `Alchemy Static Checks / static-web` passed on the generated PR.
- Merged PR #1 and updated the local delivery report so `github.merge.status = merged` and `development_cycle.score = 1.0`.
- Found and fixed a real GitHub merge edge case where `gh pr merge` could merge remotely but return a local worktree cleanup error; runtime now verifies the remote PR state after merge command failures.
- Added browser automation readiness to `real_env_check` and UI preflight payloads.
- Installed Playwright in the local Python environment and confirmed `--require-browser` passes on this machine.
- Found and fixed an automatic browser verification path bug: relative output directories caused screenshots to be generated but not found by the verifier. The runner now resolves output paths before invoking Playwright.
- Re-ran automatic browser verification against the generated game; screenshots were captured, initial screenshot was non-uniform, interaction changed pixels, and console errors were empty.
- Full suite now passes with 143 tests.

## 2026-06-19 CI Follow-Up Fix

- The pushed master CI run exposed two environment/contract issues that local verification had not caught.
- Fixed CI dependency setup by adding `python -m pip install -e .` to `.github/workflows/ci.yml` and declaring `pillow` as a runtime dependency because image diff helpers require it.
- Fixed async pause/resume recovery handoff by restoring project status to `planned` before starting the recovery run.
- Narrowed the HTTP pause/resume control test so it verifies the HTTP handoff contract without racing a full recovery run to completion; service-level tests still cover completed recovery execution.
- Re-ran the full local suite: 143 tests passed.

## 2026-06-19 CI Package Discovery Follow-Up

- GitHub Actions showed that `python -m pip install -e .` failed in CI because setuptools refused automatic package discovery in the repository's flat layout.
- Added explicit setuptools package discovery includes for `autodev`, `context`, `intake`, `planner`, `runtime`, and `server`.
- Verified `python -m pip install -e .` locally and reran the full unit suite: 143 tests passed.

## 2026-06-19 Final Remote CI Closure

- Pushed follow-up commit `a02ee8f` to master.
- GitHub Actions CI run https://github.com/meta-xucong/alchemy-dev-agent/actions/runs/27819574114 completed successfully.

## 2026-06-19 V2.25 Playability Feedback Loop

- Converted the user's manual feedback that the generated game still had bugs into a semantic canvas-game acceptance contract.
- Added `docs/32_v2_25_playability_feedback_loop.md` and linked it from README and the V2 development plan.
- Required generated canvas games to expose `window.__ALCHEMY_GAME_TEST__` with `snapshot()`, `step(dt)`, `advanceToVictory()`, and `restart()`.
- Added browser gameplay probing for numeric player position, right movement, jump behavior, victory reachability, and restart state.
- Surfaced gameplay probe evidence in artifact reports, delivery reports, requirement coverage, development-cycle testing, and the browser console delivery summary.
- Hardened generated static CI fallback and Codex worker prompts so new generated canvas games include the hook.
- Updated the built-in retro platformer generator to expose the same deterministic gameplay hook.
- Re-audited the previous V2.24 generated game under the new gate; V2.25 correctly rejects it because it lacks semantic gameplay evidence.
- Fixed a related acceptance issue where non-web Node projects were incorrectly marked partial by static web artifact checks; non-web profiles now skip the web-specific verifier.
- Verified focused tests, full suite, browser gameplay probe, acceptance harness, JSON specs, diff hygiene, and long-running state validation.

## 2026-06-19 V2.25 Remote CI Closure

- Pushed commit `e5e653d` to `master`.
- GitHub Actions CI run `27822953044` completed successfully for `Add semantic gameplay verification gate`.

## 2026-06-19 V2.26 Semantic Web And Feedback Loop

- Added `docs/33_v2_26_semantic_web_and_feedback.md` and linked it from README and the V2 development plan.
- Split ordinary `static_web_app` verification from canvas-game-only rules so forms, dashboards, and static product pages are not evaluated as games.
- Added browser `semantic_probe` evidence for static web apps: visible controls, deterministic input filling, safe button clicks, and DOM/state-change summaries.
- Preserved `gameplay_probe` compatibility while surfacing unified `semantic_probe` evidence in browser verification results.
- Surfaced semantic probe status in delivery reports, requirement coverage, development-cycle testing, and the browser console summary.
- Added `feedback` as a first-class intake role for bug reports, playtest notes, and acceptance feedback files.
- Updated requirement extraction so feedback items become must-priority requirement deltas and feed the normal task graph.
- Verified a real Playwright semantic probe on a static todo form fixture: it filled an input, clicked Add Todo, and detected visible DOM state change.
- Verified focused tests, full suite, acceptance harness, JSON specs, diff hygiene, and long-running state validation.

## 2026-06-19 V2.26 Remote CI Closure

- Pushed commit `7757d08` to `master`.
- GitHub Actions CI run `27825199118` completed successfully for `Add semantic web probes and feedback intake`.


## 2026-06-19 V2.27 Acceptance Scenario Browser Probes

- Added `docs/34_v2_27_acceptance_scenario_browser_probes.md` and linked it from README and the V2 development plan.
- Added deterministic acceptance scenario planning for CRUD, auth, file upload, and dashboard requirements.
- Wired generated scenarios into automatic static-web browser verification as `scenario_probe` evidence.
- Surfaced scenario status in delivery reports, requirement coverage, development-cycle testing, and the browser console summary.
- Updated Codex worker guidance so generated static web apps expose visible semantic controls for document-specific flows.
- Verified real Playwright scenario probing against a static fixture containing auth, CRUD, upload, and dashboard controls.
- Verified focused tests, full suite, acceptance harness, JSON specs, diff hygiene, and long-running state validation.


## 2026-06-19 V2.27 Remote CI Closure

- Pushed commit `a9fb340` to `master`.
- GitHub Actions CI run `27826225218` completed successfully for `Add acceptance scenario browser probes`.


## 2026-06-19 V2.28 Feedback Reopen Loop

- Added `docs/35_v2_28_feedback_reopen_loop.md` and linked it from README and the V2 development plan.
- Preserved `source_role` on extracted requirements and updated the ContextBundle schema.
- Routed feedback-derived requirements to Debug Agent tasks instead of ordinary feature tasks.
- Added `POST /projects/{project_id}/feedback/reopen` to reopen a delivered run with feedback files and start a repair run using `agent/feedback-recovery` by default.
- Added browser-console `Feedback Reopen` control that uploads selected files as feedback and starts the repair run.
- Verified focused tests, full suite, acceptance harness, JSON specs, diff hygiene, and long-running state validation.


## 2026-06-19 V2.28 Remote CI Closure

- Pushed commit `cab4518` to `master`.
- GitHub Actions CI run `27827029904` completed successfully for `Add feedback reopen repair loop`.

## 2026-06-19 V2.29 Local And GitHub Source Modes

- Added `docs/36_v2_29_local_and_github_source_modes.md` and linked it from README and the V2 development plan.
- Promoted local repository import to a first-class `ProjectBrief.repository` provider with `provider = local`.
- Wired `repository_path` through intake, API project service, and document-run ProjectBrief generation so local-only projects are indexed like GitHub-derived checkouts.
- Added `autodev.local_repository_acceptance`, a local-only harness that verifies project creation, context indexing, initial delivery, feedback reopen, Debug Agent routing, dry-run GitHub evidence, and delivery readiness without creating a GitHub repository.
- Fixed dry-run worker false-positive blocking when a natural-language goal contains the word `blocked`; only explicit dry-run blocker constraints now block.
- Kept feedback-derived requirements as must-priority even when the feedback sentence contains `should`.
- Classified `.html` and `.css` as source files during repository indexing so static web local repositories are represented correctly.
- Verified focused tests, full suite, local-only acceptance with browser verification, main acceptance harness, JSON specs, diff hygiene, and long-running state validation.

## 2026-06-19 V2.29 Remote CI Closure

- Pushed commit `0c97999` to `master`.
- GitHub Actions CI run `27829089780` completed successfully for `Add local repository source acceptance`.


## 2026-06-19 V2.30 Native UI Acceptance Tests

- Added `docs/37_v2_30_native_ui_acceptance_tests.md` and linked V2.30 from README and the V2 development plan.
- Added `runtime/native_ui_tests.py` to convert generated CRUD/auth/upload/dashboard acceptance scenarios into Playwright or Cypress test drafts.
- Detects Playwright/Cypress from config files, package metadata, scripts, or Cypress directories.
- Generates report-only Playwright drafts for static browser artifacts without mutating arbitrary repositories.
- Wired `native_ui_tests` into document-run output, artifact reports, delivery reports, runtime repository evidence, and requirement coverage evidence.
- Hardened generated Playwright output with explicit TypeScript types and script-value framework detection.
- Verified focused tests before final full-suite and acceptance checks.


## 2026-06-19 V2.30 Remote CI Closure

- Pushed commit `9ec419b` to `master`.
- GitHub Actions CI run `27831272738` completed successfully for `Add native UI acceptance test generation`.


## 2026-06-19 V2.31 Delivery Evidence Console

- Added `docs/38_v2_31_delivery_evidence_console.md` to align the evidence console with the autonomous development delivery goal.
- Added `autodev.delivery_evidence` to build display-ready summaries for final gate, requirements, probes, native UI tests, GitHub/CI, blockers, next actions, and development-cycle evidence.
- Added `delivery_evidence` to API delivery responses.
- Updated the browser console with evidence cards and detailed evidence sections while preserving raw JSON output.
- Verified focused API, static UI, and evidence-summary tests before full verification.


## 2026-06-19 V2.31 Remote CI Closure

- Pushed commit `1db8afb` to `master`.
- GitHub Actions CI run `27832406533` completed successfully for `Add delivery evidence console`.


## 2026-06-19 V2.32 Feedback Recovery Comparison

- Added `docs/39_v2_32_feedback_recovery_comparison.md` and linked V2.32 from README and the V2 development plan.
- Added `autodev.recovery_comparison` to compare feedback/recovery runs with their source run.
- Comparison evidence covers run status, final gate score, requirement coverage, missing/partial must gaps, newly covered feedback must requirements, blocker deltas, browser probe deltas, native UI test status, and CI status.
- Persisted `recovery_comparison` on feedback reopen runs and derived it during delivery lookup when a run references a source run.
- Added `Repair Comparison` cards/details to delivery evidence and the browser console.
- Hardened comparison logic so a feedback run that adds and covers new must requirements is classified as improved rather than unchanged.
- Verified focused tests, full suite, local feedback acceptance with browser verification, main acceptance harness, UI smoke, JSON specs, diff hygiene, and long-running state validation.

## 2026-06-19 V2.32 Remote CI Closure

- Pushed commit `00258fc` to `master`.
- GitHub Actions CI run `27834632529` completed successfully for `Add feedback recovery comparison evidence`.
