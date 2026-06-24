# V2.62 Repair Plan Contract

## Purpose

The repair plan is the machine-readable bridge between central review and the next autonomous
development run.

It is not a new requirements document from the user. It is a system-authored delta that says:

```text
The current result is not ready enough. Repair these specific gaps, then retest and review.
```

## File Locations

For a source run:

```text
.alchemy/.../projects/<project_id>/runs/<run_id>/repair_plan.json
.alchemy/.../projects/<project_id>/runs/<run_id>/repair_plan.md
.alchemy/.../projects/<project_id>/runs/<run_id>/auto_feedback.md
```

For a repair run:

```text
.alchemy/.../projects/<project_id>/runs/<repair_run_id>/repair_source.json
```

## JSON Shape

The canonical JSON shape is defined by `specs/repair_plan_schema.json`.

Required top-level fields:

- `schema_version`;
- `repair_plan_id`;
- `project_id`;
- `source_run_id`;
- `trigger`;
- `status`;
- `summary`;
- `items`;
- `guardrails`;
- `auto_execution`;
- `created_at`.

## Status Values

| Status | Meaning |
| --- | --- |
| `draft` | Plan was generated but not yet checked. |
| `ready` | Plan can start a repair run. |
| `blocked` | Plan cannot execute without human or external action. |
| `started` | A repair run has been created from this plan. |
| `superseded` | A newer plan replaced this one. |

## Trigger Values

| Trigger | Meaning |
| --- | --- |
| `central_review_iterate` | V2.61 central review returned `decision=iterate`. |
| `delivery_gate_failed` | Final delivery evidence failed hard. |
| `feedback_reopen` | User or system feedback reopened a delivered run. |
| `manual_operator` | Advanced operator requested a repair pass. |

## Repair Items

Each repair item must be concrete enough to become a task graph delta.

Required fields:

- `id`;
- `priority`;
- `source`;
- `summary`;
- `target_agent`;
- `target_files`;
- `required_evidence`;
- `acceptance_check`.

Allowed target agents:

- `architect`;
- `backend`;
- `frontend`;
- `test`;
- `debug`;
- `reviewer`.

Priority meanings:

| Priority | Meaning |
| --- | --- |
| `must` | Blocks handoff. |
| `should` | Should be repaired when safe, but may not block handoff by itself. |
| `could` | Low-risk polish or optional improvement. |

## Source Values

Repair items should preserve traceability to the evidence that created them.

Allowed source values:

- `hard_blocker`;
- `test_failure`;
- `browser_probe`;
- `scenario_probe`;
- `gameplay_probe`;
- `requirement_coverage`;
- `reviewer_change`;
- `central_review_missing_step`;
- `score_dimension`;
- `github_ci`;
- `manual_feedback`.

## Guardrails

The `guardrails` object explains why automatic execution is or is not allowed.

Required fields:

- `safe_to_execute`;
- `max_iterations`;
- `current_iteration`;
- `duplicate_signature_count`;
- `requires_user_approval`;
- `blockers`.

Automatic execution is allowed only when:

```text
safe_to_execute = true
requires_user_approval = false
blockers = []
```

## Repair Signature

Every repair plan must include a deterministic `repair_signature`.

The signature is derived from:

- source run id;
- sorted repair item sources;
- sorted repair item summaries;
- target agents;
- required evidence.

The controller uses this signature to prevent endless duplicate loops.

## Auto Feedback Document

The Markdown feedback document should be concise and worker-ready:

```markdown
# Auto Feedback

Source run: run_001
Reason: central review requested another iteration.

## Required Repairs

1. Fix failed browser probe: ...
2. Add evidence for must requirement: ...

## Acceptance Evidence Required

- Browser probe passes.
- Requirement REQ-3 is covered.
- Final gate score is at least 0.85.
```

The feedback file must not include broad vague instructions such as "make it better" unless paired
with concrete evidence gaps.

When target files are known, the feedback document must include a `Target files:` line. The runtime
uses those files to activate the V2.64 repair convergence gate, allowing a repair pass to stop after
the target files and checks have passed instead of dispatching duplicate same-file repair tasks.

## Relationship To Task Graph

The repair plan may be translated into:

- new debug tasks for failed behavior;
- new implementation tasks for missing requirements;
- new test tasks for missing verification;
- a reviewer task when prior approval was absent;
- an architect task when the original graph was wrong.

The task graph remains the execution source of truth after the repair run starts. The repair plan is
the intake artifact for that run.

## Validation Rules

An implementation should reject a repair plan when:

- no repair items exist;
- all items are optional and the run is already ready for handoff;
- target agents are invalid;
- required evidence is empty for `must` items;
- guardrails require user approval but a start operation tries to auto-execute;
- the repair signature has already failed beyond policy limits.
