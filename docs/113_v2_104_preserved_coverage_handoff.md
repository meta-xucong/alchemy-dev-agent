# V2.104 Preserved Coverage Handoff

## Problem

V2.103 correctly recovered the historical T014 build failure and generated a
focused T017 repair task. The real Billing Core `run_attempt_044` proved the
product fix worked: Alchemy added the missing admin compliance Markdown files,
and frontend tests, build, and lint passed.

However, phase_010 still did not promote. By suppressing the broad
`Complete remaining frontend closure requirements` fallback, the regenerated
graph no longer carried nodes for some previously completed frontend closure
requirements. The final gate then reported missing coverage for requirements
such as REQ-009, REQ-022, REQ-023, REQ-024, REQ-030, and REQ-032 even though the
repair brief explicitly said T001 through T016 should be preserved.

## Fix

When a focused verification repair has a substantial completed-task preserve
list and still has unmatched original frontend requirements, the planner now
creates a completed coverage node:

- `Preserve completed frontend closure coverage`
- status `completed`
- evidence type `focused_repair_preserved_coverage`

That node maps the unmatched original requirements to preserved completion
evidence without dispatching a broad `frontend/**` worker. The new focused
repair task remains pending and unpreserved, while verification/review are
assigned later task IDs.

## Billing Core Probe

A real graph rebuild against the current phase_010 artifacts now produces:

- T017 `Repair failing frontend verification assets` pending
- T018 `Preserve completed frontend closure coverage` completed
- T019 `Verify implementation against project checks` pending
- T020 `Review delivery readiness` pending

No broad `Complete remaining frontend closure requirements` task is generated.

## Verification

- focused planner regression => `1 passed`
- `python -m pytest tests/test_document_to_plan.py -q` => `25 passed`
- `python -m pytest tests/test_full_roadmap_execution.py -q` => `61 passed`
- `python -m compileall planner tests -q` => passed
- real phase_010 graph probe => T018 completed coverage node present
