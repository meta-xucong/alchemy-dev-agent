# V2.91 Usage-Limit False Positive Guard

## Objective

V2.91 prevents historical quota text in successful Codex JSONL output from
being treated as a current local Codex CLI usage-limit blocker.

## Problem Evidence

After V2.90, the post-reset Codex OK smoke passed and Billing Core was relaunched
through Alchemy. `phase_010/run_attempt_028` correctly used a fresh attempt and
the inherited isolated worktree, but T001 stopped as an environment blocker.

The Codex subprocess itself exited successfully. The false blocker came from
Alchemy scanning the entire raw JSONL stream. T001 had read repair evidence that
mentioned the previous local Codex usage limit, so the broad substring detector
matched historical text inside command output and returned:

```text
Codex CLI usage limit reached: <entire JSONL stream>
```

That was not a live account-quota failure.

## Design

V2.91 tightens the boundary:

- `CodexWorkerAdapter` only treats usage-limit text inside structured Codex
  `type=error`, `turn.failed`, or `response.failed` events as a JSONL quota
  blocker.
- Plain text usage-limit lines are still recognized for non-JSON CLI failures.
- Successful JSONL command output can mention prior usage limits without
  blocking normal result parsing.
- `Orchestrator` no longer scans raw JSONL stdout for broad usage-limit
  substrings. It still accepts explicit result summaries, known issues, stderr,
  or structured Codex error events as environment evidence.

`run_attempt_028` was marked with `supervisor_stop.json` so later resumes skip
that false state.

## Verification

Focused checks:

```powershell
python -B -m pytest tests/test_runtime.py::CodexWorkerTests::test_real_worker_usage_limit_jsonl_blocks_without_parse_retry tests/test_runtime.py::CodexWorkerTests::test_real_worker_ignores_usage_limit_text_inside_successful_jsonl_output tests/test_runtime.py::OrchestratorTests::test_worker_usage_limit_blocks_without_debug_retry tests/test_runtime.py::OrchestratorTests::test_worker_raw_usage_limit_context_does_not_become_environment_blocker -q
```

Regression:

```powershell
python -B -m pytest tests/test_runtime.py -q
python -B -m py_compile runtime\codex_worker.py runtime\orchestrator.py tests\test_runtime.py
```

## Next Action

Relaunch Billing Core through Alchemy only. The next attempt should skip
`run_attempt_028`, start with normal planning, and avoid treating historical
usage-limit text as a live environment blocker.
