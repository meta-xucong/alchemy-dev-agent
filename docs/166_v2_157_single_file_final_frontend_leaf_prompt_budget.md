# V2.157 Single-File Final Frontend Leaf Prompt Budget

## Problem

After V2.156, `final_verification/run_attempt_031` proved the announcement/backup/promo split was correct:

- T034 `Repair final frontend admin announcements view file` completed.
- T035 `Repair final frontend admin backup view file` completed.
- T036 `Repair final frontend admin promo codes view file` ran as a single-file task.

T036 still timed out at the 900 second worker boundary. At that point, the problem is no longer file count. The likely
failure mode is that real Codex workers still choose broad frontend verification such as typecheck/build/test inside
single-file final repair tasks.

## Change

- `runtime/codex_worker.py` now tells workers that single-file final frontend repair tasks must keep verification
  file-local.
- For task titles containing `final frontend` and `view file`, `leaf file`, or `component file`, the worker prompt now
  says not to run broad frontend commands such as `pnpm typecheck`, `pnpm build`, `pnpm test`, or `vitest run` unless
  explicitly requested by the task package.
- The prompt directs workers to inspect the named file, make the smallest scoped edit, use path-scoped checks, and leave
  broad verification to final real repository checks.

## Verification

- Focused worker prompt regression.
- Full `tests/test_runtime.py`.
- Full `tests/test_document_to_plan.py`.
- Full `tests/test_full_roadmap_execution.py`.

## Follow-Up

The next relaunch should resume at T036 and use the tighter prompt. If a single-file task still times out after this,
Alchemy likely needs structured checkpoints or partial-result handoff rather than further file splitting.
