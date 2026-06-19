# V2.32 Feedback Recovery Comparison

## Purpose

V2.32 closes a reviewability gap in the feedback repair loop.

The system already supports:

- initial document-driven delivery
- manual or acceptance feedback intake
- feedback-derived Debug Agent tasks
- reopening a delivered run with feedback files
- final delivery evidence review

The missing contract was a clear before/after report. A repair run should not
only say that it finished. It should explain whether it improved the prior run,
which must-requirement gaps were resolved, whether any new gaps appeared, and
which probe or CI evidence changed.

## Scope

This phase adds a derived `recovery_comparison` report for feedback and recovery
runs.

It compares:

- source run id and current run id
- run status
- final gate score
- requirement coverage score
- missing and partial must-requirement ids
- newly introduced feedback must-requirement ids and whether they are covered
- blocker count
- static, browser, semantic, scenario, gameplay, native UI, and CI statuses

It does not change execution, task scheduling, evaluator scoring, worker
behavior, or agent roles.

## Report Contract

`recovery_comparison` is a displayable and machine-readable object:

```json
{
  "status": "improved|mixed|regressed|same_passed|unchanged",
  "summary": "",
  "source_run_id": "run_001",
  "current_run_id": "run_002",
  "source": {},
  "current": {},
  "score_delta": 0.0,
  "coverage_delta": 0.0,
  "blocker_delta": 0,
  "resolved_missing_must_requirement_ids": [],
  "new_missing_must_requirement_ids": [],
  "resolved_partial_must_requirement_ids": [],
  "new_partial_must_requirement_ids": [],
  "new_must_requirement_ids": [],
  "covered_new_must_requirement_ids": [],
  "uncovered_new_must_requirement_ids": [],
  "probe_changes": []
}
```

Comparison status meanings:

- `improved`: the repair run improved score, coverage, status, blockers, must
  gaps, newly covered feedback requirements, or probe evidence without a
  detected regression.
- `mixed`: the repair run improved some evidence but introduced a regression.
- `regressed`: the repair run only moved backward.
- `same_passed`: source and current runs both satisfy the delivery gate with no
  material delta.
- `unchanged`: no material evidence change was detected.

## API And UI Contract

`POST /projects/{project_id}/feedback/reopen` persists
`recovery_comparison` on the repair run.

`GET /projects/{project_id}/delivery` returns:

- top-level `recovery_comparison`
- `delivery_evidence.recovery_comparison`
- a display card labeled `Repair Comparison`

The browser console renders a `Repair Comparison` detail section with source and
current run ids, score delta, coverage delta, blocker delta, resolved/new must
gaps, and probe status changes.

## Acceptance Criteria

V2.32 is complete when:

- feedback reopen runs persist `recovery_comparison`
- delivery lookup can derive comparison evidence for recovery runs that cite a
  source run
- delivery evidence includes a `Repair Comparison` card when comparison data is
  available
- the browser console renders repair comparison details
- local repository acceptance checks verify that feedback reopen includes a
  comparison report
- focused tests, full unit suite, acceptance harness, JSON parsing, diff
  hygiene, state validation, and remote CI pass

## Non-Goals

This phase does not:

- introduce new agents
- change the final gate formula
- automatically choose the next repair action from the comparison report
- add screenshot preview serving
- run generated native UI tests inside target repositories
