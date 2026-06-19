# V2.36 Comparison-Driven Repair Suggestions

## Goal

V2.36 turns feedback recovery comparison evidence into machine-readable Debug Agent repair suggestions.

Earlier phases can reopen a delivered run with feedback and compare the repair run against its source run. That comparison is useful for review, but it does not directly tell the next automated iteration what to fix. This phase closes that gap.

## Scope

The system derives `repair_suggestions` from existing `recovery_comparison` evidence.

Suggestions are not a new execution model. They are task seeds for the existing Debug Agent loop.

## Suggestion Contract

Each suggestion uses this shape:

```json
{
  "id": "RS-001",
  "agent": "debug",
  "task_type": "debug",
  "priority": "must",
  "title": "Repair scenario probe regression",
  "reason": "scenario probe changed from passed to failed.",
  "requirement_ids": [],
  "probe": "scenario",
  "blocker_ids": [],
  "worker_goal": "Reproduce the scenario probe regression, patch the app or tests, and rerun the probe until it passes."
}
```

## Inputs

Suggestions are built from:

- `new_missing_must_requirement_ids`
- `new_partial_must_requirement_ids`
- `uncovered_new_must_requirement_ids`
- negative `coverage_delta`
- negative `score_delta`
- positive `blocker_delta`
- regressed `probe_changes`
- not-ready repair runs with no more specific bucket

## Output Locations

`repair_suggestions` appears in:

- `recovery_comparison.repair_suggestions`
- `delivery_evidence.repair_suggestions`
- `delivery_evidence.next_actions`
- browser console `Repair Comparison` details

## Evidence Review Deep Link

The browser console supports direct review of a known project/run:

```text
/?project_id=<project_id>&run_id=<run_id>
```

When `run_id` is present, the console loads:

```text
GET /projects/{project_id}/runs/{run_id}/delivery
```

This keeps evidence review scoped to the requested run instead of silently showing the latest delivery.

## Rules

- Suggestions always target `agent = debug`.
- Suggestions never mutate the task graph by themselves.
- Suggestions must be deterministic from persisted evidence.
- Suggestions must not add new product scope.
- If no actionable regression or remaining gap exists, the list is empty.

## Acceptance Criteria

- Mixed or regressed repair comparisons produce Debug Agent suggestions.
- New missing, partial, or uncovered must requirements produce requirement-linked suggestions.
- Probe regressions produce probe-linked suggestions.
- New blockers produce blocker-linked suggestions.
- Fully improved or same-passed comparisons can produce no suggestions.
- Browser evidence shows suggestions in the repair comparison section.
- Run-scoped delivery evidence can be opened from a project/run deep link.
