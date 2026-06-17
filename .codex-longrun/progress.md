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

