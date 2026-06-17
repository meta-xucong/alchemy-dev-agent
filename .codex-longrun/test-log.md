# Test Log

## 2026-06-17

- Command: `python -m unittest discover -s tests`
- Result: passed
- Summary: 8 runtime tests passed.
- Next verification command: CLI smoke run.

## 2026-06-17

- Command: `python -m runtime.run_loop --project <temp> --objective "build a todo app with login" --reset`
- Result: passed
- Summary: Runtime reached `done=true` with `final_score=1.0`.
- Next verification command: long-running state validation.

## 2026-06-17

- Command: `python %USERPROFILE%\.codex\skills\long-running-task\scripts\validate_state.py --project .`
- Result: passed
- Summary: Long-running task state schema validated.
- Next verification command: none.

## 2026-06-17

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m runtime.run_loop --project .test-tmp/final-smoke --objective "build a todo app with login" --reset`
- Result: passed
- Summary: Final CLI smoke reached `done=true`, `status=passed`, `final_gate_score=0.94`.
- Next verification command: none.

## 2026-06-17

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests`
- Result: passed
- Summary: 13 runtime tests passed, covering graph readiness, worker dry-run, real worker subprocess parsing, evaluator gates, retry/debug loop, GitHub dry-run evidence, persistence, and CLI smoke.
- Next verification command: CLI smoke run.

## 2026-06-17

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m runtime.run_loop --project .test-tmp/<unique-smoke-dir> --objective "build a todo app with login" --reset`
- Result: passed
- Summary: CLI smoke reached `done=true`, `status=passed`, and `final_gate_score=0.94`.
- Next verification command: long-running state validation.

## 2026-06-17

- Command: `python %USERPROFILE%\.codex\skills\long-running-task\scripts\validate_state.py --project .`
- Result: passed
- Summary: Long-running task state schema validated after implementation updates.
- Next verification command: none.

## 2026-06-17

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests`
- Result: failed, then passed
- Summary: Initial contract test caught missing `retry_count` in `task_graph_schema.json`; after adding it, 15 tests passed.
- Next verification command: CLI smoke and JSON parsing.

## 2026-06-17

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m runtime.run_loop --project .test-tmp/alignment-smoke --objective "build a todo app with login" --reset`
- Result: passed
- Summary: CLI smoke reached `done=true`, `evaluation_score=0.94`.
- Next verification command: long-running state validation.

## 2026-06-17

- Command: `Get-Content specs/*.json -Raw | ConvertFrom-Json`
- Result: passed
- Summary: State and task graph schemas parse as valid JSON.
- Next verification command: long-running state validation.

## 2026-06-18

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests`
- Result: passed
- Summary: 17 tests passed, including regressions for clean real GitHub flow and schema-style task reference loading.
- Next verification command: CLI smoke and JSON parsing.

## 2026-06-18

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m runtime.run_loop --project .test-tmp/selfcheck-smoke --objective "build a todo app with login" --reset`
- Result: passed
- Summary: CLI smoke reached `done=true`, `evaluation_score=0.94`.
- Next verification command: JSON parsing and long-running state validation.

## 2026-06-18

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests`
- Result: passed
- Summary: 18 tests passed after adding JSONL/event-stream Codex worker parsing coverage.
- Next verification command: CLI smoke, JSON parsing, and state validation.

## 2026-06-18

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m runtime.run_loop --project .test-tmp/selfcheck-smoke-2 --objective "build a todo app with login" --reset`
- Result: passed
- Summary: CLI smoke reached `done=true`, `evaluation_score=0.94`.
- Next verification command: none.

## 2026-06-18

- Command: `Get-Content specs\*.json -Raw | ConvertFrom-Json`
- Result: passed
- Summary: Existing and new v2 JSON schemas parse successfully, including ProjectBrief and ContextBundle.
- Next verification command: runtime unit tests.

## 2026-06-18

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests`
- Result: passed
- Summary: 19 tests passed, including the new v2 intake/context schema contract test.
- Next verification command: long-running state validation.

## 2026-06-18

- Command: `python %USERPROFILE%\.codex\skills\long-running-task\scripts\validate_state.py --project .`
- Result: passed
- Summary: Long-running state schema validated during v2 documentation work.
- Next verification command: final git diff and smoke checks.

## 2026-06-18

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m runtime.run_loop --project .test-tmp\v2-docs-smoke --objective "build a todo app with login" --reset`
- Result: passed
- Summary: CLI smoke reached `done=true`, `status=passed`, and `final_gate_score=0.94`.
- Next verification command: final diff check.

## 2026-06-18

- Command: `git diff --check`
- Result: passed
- Summary: No whitespace errors were reported. Git reported existing CRLF normalization warnings for long-running markdown/state files.
- Next verification command: final long-running state validation.

## 2026-06-18

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m unittest tests.test_intake`
- Result: passed
- Summary: 7 V2.1 intake tests passed.
- Next verification command: full test suite.

## 2026-06-18

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests`
- Result: passed
- Summary: 26 tests passed across runtime and intake modules.
- Next verification command: ProjectBrief CLI smoke.

## 2026-06-18

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m intake.project_brief --objective "Add workspace support" --document .test-tmp\manual-intake-2\feature.md --attachment .test-tmp\manual-intake-2\api.yaml --repository https://github.com/example/repo --validate`
- Result: passed
- Summary: CLI emitted schema-compatible ProjectBrief JSON without warnings after lazy-loading package exports.
- Next verification command: long-running state validation.

## 2026-06-18

- Command: `Get-Content specs\*.json -Raw | ConvertFrom-Json`
- Result: passed
- Summary: All JSON specs parse after V2.1 intake changes.
- Next verification command: final state validation.

## 2026-06-18

- Command: `python %USERPROFILE%\.codex\skills\long-running-task\scripts\validate_state.py --project .`
- Result: passed
- Summary: Long-running state schema validated for V2.1 intake runtime.
- Next verification command: none.

## 2026-06-18

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m unittest tests.test_autodev_pipeline`
- Result: passed
- Summary: 2 one-line app generation demo tests passed.
- Next verification command: full test suite.

## 2026-06-18

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests`
- Result: passed
- Summary: 28 tests passed across runtime, intake, and autodev demo modules.
- Next verification command: user's one-line game prompt.

## 2026-06-18

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m autodev.demo_run --objective "我要生成一个超级玛丽第一关的游戏。关卡设计、人物和场景形象均完全模仿经典原始版的超级玛丽" --output .alchemy/generated/retro_platformer_test`
- Result: passed
- Summary: Demo returned `status=done`, generated `index.html` and `autodev_report.json`, and recorded architect/frontend/test/reviewer events. The request was converted into an original retro platformer for copyright safety.
- Next verification command: browser rendering check.

## 2026-06-18

- Command: Browser verification through local HTTP server for `.alchemy/generated/retro_platformer_test/index.html`
- Result: passed
- Summary: Screenshot showed HUD, canvas, sky, platforms, coins, player, gaps, and control hint. DOM reported title `Original Retro Platformer`, canvas `960x540`, score/coins/time/state HUD, and controls.
- Next verification command: final suite and schema checks.

## 2026-06-18

- Command: `Get-Content specs\*.json -Raw | ConvertFrom-Json`
- Result: passed
- Summary: All JSON specs parse after one-line demo pipeline changes.
- Next verification command: long-running state validation.
