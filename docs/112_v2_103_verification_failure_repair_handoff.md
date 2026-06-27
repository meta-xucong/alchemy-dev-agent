# V2.103 Verification Failure Repair Handoff

## Problem

Billing Core phase_010 reached a strong implementation boundary: T001 through
T016 completed in `run_attempt_041`. The verification task recorded concrete
failure evidence:

- `pnpm --dir frontend test` passed.
- backend `go test ./...` passed.
- backend `go build ./...` passed.
- frontend lint passed.
- `pnpm --dir frontend run build` failed because
  `frontend/src/components/admin/AdminComplianceDialog.vue` imported missing
  raw Markdown files under `docs/legal/`.

The parent repair document did not carry that concrete evidence forward because
T014 had status `completed`, even though its worker result contained
`tests_failed`, `known_issues`, and a failed command. Later repair attempts
therefore preserved T001-T016 but had no actionable repair task, exhausting the
repair limit at score 0.70.

## Fix

`write_phase_repair_document()` now emits a `Failing Verification Issues`
section for completed test/review tasks whose worker result still contains
repairable failure evidence. It includes:

- failed command summaries;
- `tests_failed`;
- `known_issues`;
- `follow_up_tasks`;
- target file paths extracted from worker evidence and failed command output.

Blocked-phase bootstrap now scans prior run attempt `state.json` files for the
latest concrete verification issue. This recovers useful evidence from an older
attempt when newer attempts only preserved completed tasks and lost the original
failure details.

The planner now treats those verification issue lines as focused frontend repair
requirements. When a repair brief also lists `Completed tasks to preserve:
T001...T016`, the new repair task is assigned an unpreserved task id such as
T017, and downstream verification/review ids are also placed beyond the
preserved range.

Repair metadata lines such as `Target files`, `Completed tasks to preserve`,
`Tests failed`, and `Known issues` are no longer converted into generic
remaining frontend closure tasks.

## Billing Core Impact

The next phase_010 relaunch should not replay T001-T016 and should not stop at
the stale low-score repair loop. Bootstrap should recover the old T014 build
failure from `run_attempt_041` and create a focused repair task for:

- `docs/legal/admin-compliance.zh.md`
- `docs/legal/admin-compliance.en.md`
- `frontend/src/components/admin/AdminComplianceDialog.vue`

The CRM product files must still be changed by Alchemy workers only.

A real graph probe against the current `.alchemy/billing_core_v274_20260624_012`
artifact set now rebuilds phase_010 with only these pending nodes:

- T017 `Repair failing frontend verification assets`
- T018 `Verify implementation against project checks`
- T019 `Review delivery readiness`

The prior broad `Complete remaining frontend closure requirements` fallback is
suppressed for this verification-repair resume.

## Verification

- focused repair document test => `1 passed`
- focused planner repair task test => `1 passed`
- focused historical verification-context bootstrap test => `1 passed`
- `python -m pytest tests/test_document_to_plan.py -q` => `25 passed`
- `python -m pytest tests/test_full_roadmap_execution.py -q` => `61 passed`
- `python -m compileall autodev planner tests -q` => passed
- real phase_010 graph probe => T017 repair, T018 verify, T019 review pending
