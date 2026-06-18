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

## 2026-06-18

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m unittest tests.test_repository_context`
- Result: passed
- Summary: 3 V2.2 repository context tests passed after fixing a brittle exact file-size assertion.
- Next verification command: full test suite.

## 2026-06-18

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests`
- Result: passed
- Summary: 31 tests passed across runtime, intake, context, planner, and autodev modules.
- Next verification command: JSON spec parsing and long-running state validation.

## 2026-06-18

- Command: `Get-Content specs\*.json -Raw | ConvertFrom-Json`
- Result: passed
- Summary: All JSON specs parse after V2.2 repository context changes.
- Next verification command: final long-running state validation.
## 2026-06-18

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m unittest tests.test_github_runtime`
- Result: failed, then passed after fixes.
- Summary: Initial local git fixture failed because the temporary source repository was created under an ignored workspace path and existing checkout used a brittle plain `git checkout main`. Fixed the fixture to use the system temp directory and changed runtime checkout to `git checkout -B main origin/main`.
- Next verification command: full test suite.

## 2026-06-18

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m unittest tests.test_intake`
- Result: passed.
- Summary: ProjectBrief builder and CLI tests pass after changing repository visibility defaults to `public` and adding explicit private metadata coverage.
- Next verification command: public source CLI smoke.

## 2026-06-18

- Command: `python -B -m intake.github_runtime --repository https://github.com/example/private-repo --project-id proj_test --visibility private`
- Result: expected blocked exit.
- Summary: CLI returns `private_repository_not_supported_in_public_runtime` with `access_status=auth_required` and no runtime warning.
- Next verification command: invalid GitHub URL smoke.

## 2026-06-18

- Command: `python -B -m intake.github_runtime --repository https://gitlab.com/example/repo --project-id proj_test`
- Result: expected failed exit.
- Summary: CLI returns `invalid_github_url` for unsupported non-GitHub input and no runtime warning.
- Next verification command: full test suite.

## 2026-06-18

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests`
- Result: passed.
- Summary: 35 tests passed across runtime, intake, context, planner, autodev demo, repository context, and public GitHub source runtime modules.
- Next verification command: JSON spec parsing and long-running state validation.

## 2026-06-18

- Command: `python -c "import json, pathlib; [print('OK ' + str(p)) for p in pathlib.Path('specs').glob('*.json') if json.loads(p.read_text(encoding='utf-8')) is not None]"`
- Result: passed.
- Summary: All JSON specs parse after V2.3 public source changes.
- Next verification command: long-running state validation.
## 2026-06-18

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m unittest tests.test_document_to_plan`
- Result: failed, then passed after fixes.
- Summary: Initial task classification treated a test requirement as backend because filename stem matching pulled in source files first. Fixed planner classification to prioritize test and CI signals. The test also now serializes ContextBundle after graph generation so `planned_task_ids` reflects planner traceability updates.
- Next verification command: focused V2.4 regression group.

## 2026-06-18

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m unittest tests.test_document_to_plan tests.test_repository_context tests.test_autodev_pipeline`
- Result: passed.
- Summary: 7 tests passed across document-to-plan, repository context, and one-line demo compatibility.
- Next verification command: full test suite.

## 2026-06-18

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests`
- Result: passed.
- Summary: 37 tests passed across runtime, intake, GitHub source, repository context, document-to-plan, planner, and autodev modules.
- Next verification command: JSON spec parsing.

## 2026-06-18

- Command: `python -c "import json, pathlib; [print('OK ' + str(p)) for p in pathlib.Path('specs').glob('*.json') if json.loads(p.read_text(encoding='utf-8')) is not None]"`
- Result: passed.
- Summary: All JSON specs parse after V2.4 changes.
- Next verification command: long-running state validation.
## 2026-06-18

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m unittest tests.test_runtime_handoff`
- Result: failed, then passed after fixes.
- Summary: Initial dry-run handoff did not reach DONE because V2.4 generated graphs ended at review and lacked release/GitHub evidence required by the existing evaluator. Fixed `RuntimeHandoff` to append a release task when needed.
- Next verification command: full test suite.

## 2026-06-18

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m unittest tests.test_runtime_handoff`
- Result: passed.
- Summary: 2 V2.5 handoff tests passed, covering RuntimeState creation, CodexWorkerInput packages, and orchestrator dry-run DONE.
- Next verification command: full test suite.

## 2026-06-18

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests`
- Result: passed.
- Summary: 39 tests passed across runtime, intake, GitHub source, repository context, document-to-plan, planner, handoff, and autodev modules.
- Next verification command: JSON spec parsing and state validation.

## 2026-06-18

- Command: `python -c "import json, pathlib; [print('OK ' + str(p)) for p in pathlib.Path('specs').glob('*.json') if json.loads(p.read_text(encoding='utf-8')) is not None]"`
- Result: passed.
- Summary: All JSON specs parse after V2.5 handoff changes.
- Next verification command: long-running state validation.
## 2026-06-18

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m unittest tests.test_document_run_pipeline`
- Result: failed, then passed after fixes.
- Summary: Initial assertions checked output after temporary cleanup and CLI had a module preload warning from eager package exports. Fixed test lifecycle and changed autodev exports to lazy loading.
- Next verification command: focused document pipeline and planner tests.

## 2026-06-18

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m unittest tests.test_document_to_plan tests.test_document_run_pipeline`
- Result: passed.
- Summary: 4 tests passed, including document path extraction, document-run pipeline, and CLI report generation.
- Next verification command: full test suite.

## 2026-06-18

- Command: `PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests`
- Result: passed.
- Summary: 41 tests passed across runtime, intake, GitHub source, repository context, document-to-plan, handoff, document-run CLI, planner, and autodev modules.
- Next verification command: JSON spec parsing and long-running state validation.

## 2026-06-18

- Command: `python -c "import json, pathlib; [print('OK ' + str(p)) for p in pathlib.Path('specs').glob('*.json') if json.loads(p.read_text(encoding='utf-8')) is not None]"`
- Result: passed.
- Summary: All JSON specs parse after V2.6 document-run CLI changes.
- Next verification command: long-running state validation.
