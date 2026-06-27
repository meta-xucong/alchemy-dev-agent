# V2.90 Codex Usage-Limit Blocker

## Objective

V2.90 prevents local Codex CLI quota errors from being treated as CRM product
failures. When the real worker hits an account usage limit, Alchemy must stop
as an environment blocker instead of creating debug tasks or phase repair
attempts.

## Problem Evidence

After V2.89, Billing Core `phase_010/run_attempt_026` proved the repaired task
graph was healthy:

- T001 completed planning.
- T002 completed router/menu/direct page closure.
- T003 completed frontend API service cleanup.
- T004 completed wallet/recharge/payment/order surface work.

T005 then failed quickly. The stored raw Codex JSONL showed the real cause:

```text
You've hit your usage limit ... try again at 5:39 PM.
```

Alchemy previously summarized this as:

```text
Codex worker did not return parseable codex_worker_result_v1 JSON.
```

That generic summary caused the scheduler to create `T005-DEBUG-1`, retry T005,
and then generate `phase_repair_004.md`. This was not a CRM product repair. It
was a local model availability blocker.

## Design

V2.90 changes three boundaries:

- `CodexWorkerAdapter` reads Codex CLI JSONL `error` and `turn.failed` events.
  Usage-limit messages become `status=blocked` with a clear summary and retained
  raw output.
- `Orchestrator` records worker availability and usage-limit blockers as
  `type=environment`, so no debug task or same-scope retry is created.
- `FullRoadmapExecutor` treats usage-limit wording as non-repairable even if an
  older attempt already stored it under `technical_limit`.

The raw output remains in runtime state so a supervisor can see the exact reset
time and distinguish local account quota from product or test failures.

## Billing Core Impact

The current Billing Core state is not a loop:

- `run_attempt_026` advanced from T001 through T004.
- The run stopped at T005 only because local Codex usage was unavailable.
- `run_attempt_027` was supervisor-stopped before another product worker could
  be launched.

The correct next action is to wait for the local Codex quota window to reset,
then relaunch through Alchemy. Do not widen CRM product scope or edit Billing
Core directly to fix a model-account blocker.

## Verification

Focused checks:

```powershell
python -B -m pytest tests/test_runtime.py::CodexWorkerTests::test_real_worker_usage_limit_jsonl_blocks_without_parse_retry tests/test_runtime.py::OrchestratorTests::test_worker_usage_limit_blocks_without_debug_retry tests/test_runtime.py::OrchestratorTests::test_debug_environment_blocker_blocks_parent_without_retry -q
python -B -m pytest tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_phase_repair_distinguishes_technical_and_environment_blockers -q
```

Regression:

```powershell
python -B -m pytest tests/test_runtime.py -q
python -B -m pytest tests/test_full_roadmap_execution.py -q
python -B -m py_compile runtime\codex_worker.py runtime\orchestrator.py autodev\full_roadmap_executor.py tests\test_runtime.py tests\test_full_roadmap_execution.py
```
