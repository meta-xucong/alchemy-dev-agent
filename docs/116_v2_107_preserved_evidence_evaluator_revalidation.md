# V2.107 Preserved Evidence Evaluator Revalidation

## Problem

After V2.106, Billing Core phase_010 resumed with the correct narrow graph. It
did not replay the broad frontend implementation tasks:

- T001-T008 were preserved as completed.
- T021/T024 verification completed successfully.
- T022/T025 review approved the evidence.
- T023/T026 delivery evidence was recorded.

However, `run_attempt_046` and `run_attempt_047` still scored only `0.6945`.
The final gate had no hard failures and the requirement coverage score was above
the threshold, but the runtime evaluator only counted completed nodes with
`worker_result` evidence toward `spec_alignment`. The preserved implementation
nodes carried `focused_repair_preserved_task` evidence, so they were marked
completed but did not contribute alignment score.

The same attempts also carried non-fatal verification warnings such as dirty
worktree context, Vite chunking warnings, vue-i18n warnings, and task-branch
notes. Those warnings were useful audit notes, not delivery risks, but they
lowered `risk_quality`.

The parent then launched another verification-only attempt, `run_attempt_048`,
which timed out after 900 seconds. This timeout was a side effect of the scoring
bug, not a new CRM product failure.

## Fix

The evaluator now treats these evidence types as valid spec-alignment evidence:

- `worker_result`
- `focused_repair_preserved_task`
- `focused_repair_preserved_coverage`
- `ci_result`

It also classifies common successful-verification warning notes as benign for
risk scoring, including pre-existing dirty worktree notes, non-fatal frontend
tool warnings, temporary-copy verification, task-branch naming differences, and
`eslint --fix` script notes.

Full-roadmap resume now revalidates existing attempt reports with the current
evaluator before launching a new phase attempt. If an older `document_run_report`
now promotes under the repaired evaluator, the phase record is updated to
`done` and no additional Codex worker is launched.

## Billing Core Probe

Revalidating the real `run_attempt_047/state.json` after V2.107 produces:

- final gate score `0.9607`
- `spec_alignment=0.8689`
- `test_health=1.0`
- `graph_completion=1.0`
- `reviewer_approval=1.0`
- `risk_quality=1.0`
- no hard failures

`revalidated_promotable_phase_record()` selects
`phase_010/run_attempt_047` as a promotable record even though the current
`phase_record.json` points at the later timed-out `run_attempt_048`.

## Verification

- focused full-roadmap/evaluator regressions => `2 passed`
- evaluator regression group => `4 passed`
- `python -m pytest tests/test_runtime.py -q` => `132 passed`
- `python -m pytest tests/test_full_roadmap_execution.py -q` => `68 passed`
- `python -m pytest tests/test_document_to_plan.py -q` => `25 passed`
- `python -m compileall autodev runtime planner tests -q` => passed
