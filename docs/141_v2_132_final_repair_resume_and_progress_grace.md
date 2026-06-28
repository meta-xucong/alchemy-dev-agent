# V2.132 Final Repair Resume And Progress Grace

## Context

Billing Core final verification `run_attempt_006` proved that V2.131 fixed the
first backend migration repair scope: T002 completed and changed only the named
migration/database-contract files in the inherited worktree.

The next task, T003 `Repair final backend schema and domain contracts`, still
bundled Ent schema/generated code, domain, repository, service, handler, server,
and command wiring. It reached heavy Go verification work, but the fixed 900
second worker timeout terminated the Codex process tree while `go.exe`/`link.exe`
children were still active. The timeout stop boundary behaved safely, but it was
not progress-aware and the final verification resume document still pointed at
older attempt_003 evidence.

## Changes

- Split final backend schema/domain repair into smaller serial tasks:
  - `Repair final backend Ent schema contracts`
  - `Repair final backend domain and repository contracts`
  - `Repair final backend service handler server contracts`
- Added explicit task instructions that implementation repair workers should use
  narrow static/package checks and leave broad Go/frontend verification to the
  final real repository checks.
- Final verification resume now writes a fresh
  `final_verification_repair_resume_NNN.md` when the latest failed attempt is not
  already represented, even when an older resume document exists.
- The fresh final resume records focused repair context, including primary failed
  task IDs and completed task IDs to preserve.
- Real worker lifecycle now supports one bounded progress grace window when the
  timeout boundary sees verification/build child processes such as `go.exe`,
  `link.exe`, `node.exe`, `pnpm.exe`, or related toolchain processes.
- Lifecycle evidence records grace count, seconds, and a small process snapshot.
  Workers without clear progress still stop at the original timeout boundary.

## Expected Billing Core Resume

The generated real graph from the current Billing Core final verification state
now preserves T001/T002 and starts at T003:

- T002 completed: `Repair final backend migration contracts`
- T003 pending: `Repair final backend Ent schema contracts`
- T004 pending: `Repair final backend domain and repository contracts`
- T005 pending: `Repair final backend service handler server contracts`
- T006 pending: `Repair final frontend API and i18n contracts`
- T007 pending: `Repair final frontend routes views and tests`
- T008-T011 pending: final audit, simulation probes, real checks, and review

## Verification

- `python -B -m pytest tests/test_document_to_plan.py -q`
- `python -B -m pytest tests/test_full_roadmap_execution.py -q`
- `python -B -m pytest tests/test_runtime.py -q`
- `python -B -m compileall planner runtime autodev tests -q`
- `git diff --check`
- Real Billing Core final-verification graph probe against
  `.alchemy/billing_core_v274_20260624_012/final_verification`
