# V2.148 Codex Connectivity Blocker Classification

## Problem

Billing Core `final_verification/run_attempt_022` exposed a new controller issue while running the V2.147 file-only
refund dialog task.

T026 first failed because the local Codex CLI connection failed before a structured worker result was returned:

- repeated `stream disconnected` retries
- websocket connection failures
- `turn.failed`
- `idle timeout waiting for SSE`
- no parseable `codex_worker_result_v1` JSON

Alchemy treated that as an ordinary product task failure, created `T026-DEBUG-1`, and then retried T026. The retry later
hit the 900 second worker timeout and stopped correctly. The stop boundary was healthy, but the earlier debug/retry was
not useful because the root cause was local Codex connectivity, not CRM product code.

## Change

- `runtime/codex_worker.py` now detects unparseable real Codex output caused by connectivity failures and returns a
  `blocked` worker result instead of a normal `failed` result.
- The detector is scoped to real Codex event/output markers such as `turn.failed`, `stream disconnected`,
  `idle timeout waiting for SSE`, websocket connection failures, and request-send failures.
- `runtime/orchestrator.py` now classifies Codex connectivity failures as environment blockers, alongside local usage
  limits and unavailable tooling.
- Ordinary unparseable output without connectivity markers still remains a normal failed worker result, preserving the
  existing response-format repair path.

## Verification

- Focused Codex worker parser regressions:
  - generic unparseable output still returns `failed`
  - unparseable connectivity failure returns `blocked`
- Focused orchestrator regressions:
  - connectivity failure blocks without creating debug work
  - usage-limit blocker behavior is preserved
  - historical product text mentioning usage limits is still not an environment blocker
- Full `tests/test_runtime.py`.
- Full `tests/test_full_roadmap_execution.py`.
- `python -B -m compileall runtime tests -q`.
- `git diff --check`.
- Temporary graph probe against copied `run_attempt_022` artifacts confirmed the next resume is still clean: it preserves
  T001-T025 and starts at T026 `Repair final frontend admin payment refund dialog file`.

## Operational Note

A generic read-only Codex smoke wrote `OK` to `.codex-longrun/logs/codex_network_smoke_last.md`, but the CLI process did
not exit before the outer timeout and had to be cleaned up. A later worker-like smoke using Alchemy's real worker mode
(`--disable plugins --json`) exited cleanly and returned an `OK` agent message. Billing Core relaunches should use the
worker-like path and V2.148 should stop future stream failures as environment blockers instead of product debug loops.
