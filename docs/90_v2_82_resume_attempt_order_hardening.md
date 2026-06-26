# V2.82 Resume Attempt Ordering Hardening

## Objective

V2.82 hardens full-roadmap resume selection so a phase does not fall back from a
newer stopped attempt to an older stale active attempt.

This protects recovery chains where a current controller has already reached a
clean stop boundary, but an older attempt still contains obsolete
`active_tasks` state.

## Problem Evidence

Billing Core `phase_010` had this shape:

- `run_attempt_014` still contained stale `active_tasks=["T005-DEBUG-1"]`;
- its worker evidence showed the task had already completed;
- `run_attempt_015` was the newer authoritative boundary and had
  `active_tasks=[]` plus T004 non-partial blockers.

Before V2.82, `interrupted_phase_resume_source()` scanned attempts in reverse
order, skipped the newer no-active state, and could fall back into the older
stale active attempt. That risked resuming the wrong source again.

## Design

When the newest run attempt has a readable `state.json` and no active tasks,
the resume scan now stops there and returns no `resume_from` source. The parent
full-roadmap executor can then create a fresh phase attempt, including a repair
attempt when V2.81 classifies the blockers as autonomous technical blockers.

The scan still resumes a latest attempt that truly has active tasks and no live
worker process, preserving interrupted-worker recovery.

## Compatibility Contract

V2.82 does not change:

- live worker detection;
- recovery blockers for active live processes;
- phase repair document generation;
- runtime non-partial blocker semantics.

The only change is that a newer terminal/stopped attempt supersedes older stale
active evidence.

## Acceptance Criteria

- the latest interrupted active attempt is still resumable when it is the
  current boundary;
- a newer no-active state prevents fallback to older stale active states;
- full-roadmap regression tests pass when run serially.

## Verification

Focused tests:

```powershell
python -B -m pytest tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_interrupted_resume_does_not_fall_back_past_newer_terminal_attempt tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_executor_resumes_latest_interrupted_phase_attempt -q
```

Broader checkpoint:

```powershell
python -B -m pytest tests/test_full_roadmap_execution.py -q
python -B -m py_compile autodev\full_roadmap_executor.py tests\test_full_roadmap_execution.py
git diff --check -- autodev/full_roadmap_executor.py tests/test_full_roadmap_execution.py README.md docs/90_v2_82_resume_attempt_order_hardening.md
```
