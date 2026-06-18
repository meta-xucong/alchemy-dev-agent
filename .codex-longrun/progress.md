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
