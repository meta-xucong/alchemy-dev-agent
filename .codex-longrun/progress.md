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

