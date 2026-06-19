# V2.31 Delivery Evidence Console

## Purpose

V2.31 turns machine-generated delivery evidence into a human-reviewable console.

The long-term goal remains unchanged:

```text
development documents + repository source
  -> agent task graph
  -> Codex implementation
  -> tests and browser probes
  -> audit and repair loop
  -> final deliverable
```

The missing product step is reviewability. A run may already contain enough
machine evidence to pass the delivery gate, but the operator still needs to see
why it passed, what failed, and what should be fixed next.

V2.31 makes that evidence visible without changing the execution model.

## Scope

This phase productizes evidence already produced by earlier phases:

- `delivery_report`
- `artifact_report`
- `requirement_coverage`
- `development_cycle`
- `browser_verification`
- `native_ui_tests`
- GitHub PR, CI, and merge evidence
- blockers and next actions

The console should answer:

```text
Is the run ready for review?
Which requirements are missing or partial?
Which browser probes passed or failed?
Were native UI test drafts generated?
What GitHub/CI/merge evidence exists?
What should happen next?
```

## Evidence Contract

The API exposes a derived `delivery_evidence` object in `GET /projects/{id}/delivery`.

Shape:

```json
{
  "status": "ready|blocked|in_progress|unknown",
  "ready_for_review": true,
  "score": 0.0,
  "summary": "",
  "cards": [],
  "requirements": {},
  "probes": {},
  "native_ui_tests": {},
  "github": {},
  "development_cycle": {},
  "blockers": [],
  "next_actions": []
}
```

Each `cards[]` item is concise and display-ready:

```json
{
  "label": "Final Gate",
  "status": "passed|failed|partial|skipped|unknown",
  "value": "0.96",
  "detail": "DONE condition met."
}
```

## Console Requirements

The browser console must add a delivery evidence section with:

- top evidence cards for final gate, requirements, artifact, browser, native UI
  tests, CI, and development cycle
- requirement coverage detail counts for covered, partial, missing, and must gaps
- probe detail rows for semantic, scenario, gameplay, and browser status
- native UI test status, framework, write mode, target path, and generated files
- GitHub branch, PR, CI, merge, and commit evidence
- development-cycle checklist summary
- blockers and next actions

The existing raw JSON output remains available for audit.

## Non-Goals

This phase does not:

- redesign the full console
- add new agent roles
- change task execution
- change evaluator scoring
- run generated native UI tests
- add repository-write mode for generated UI tests
- implement recovery-run diffing

## Acceptance Criteria

V2.31 is complete when:

- `GET /projects/{id}/delivery` includes `delivery_evidence`
- `delivery_evidence` summarizes final gate, requirements, probes, native UI
  tests, GitHub, development-cycle, blockers, and next actions
- the browser console renders the evidence summary without relying only on raw
  JSON
- static asset tests protect the new UI contract
- project-service tests protect the new API evidence contract
- local focused tests, full unit suite, acceptance harness, JSON parsing, diff
  hygiene, state validation, and remote CI pass
