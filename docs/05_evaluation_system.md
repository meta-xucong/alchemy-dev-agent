# Evaluation System

## Purpose

The evaluation system determines whether the autonomous development run is complete enough to stop.

It prevents the system from confusing local task completion or passing tests with delivery readiness.

## Core Principle

Test pass does not equal done.

Passing tests is necessary for most software tasks, but final completion also requires:

- Alignment with the user objective.
- Coverage of acceptance criteria.
- Reviewer approval.
- No unresolved required blockers.
- A final gate score of at least `0.85`.

## Evaluation Inputs

The final evaluation consumes:

- User objective.
- Requirements document.
- Done criteria.
- Final task graph state.
- Worker evidence.
- Test Agent assessment.
- Reviewer Agent assessment.
- CI check results.
- Known issues.
- Blockers and skipped task rationales.

## Evaluation Dimensions

### 1. Test Health

Checks whether required test commands, CI checks, and verification steps passed.

Signals:

- Unit tests pass.
- Integration tests pass.
- End-to-end tests pass when required.
- Lint/static checks pass.
- No known failing required checks.

Passing test health alone cannot approve completion.

### 2. Spec Alignment

Checks whether the implementation satisfies the stated objective and requirements.

Signals:

- Each acceptance criterion maps to completed evidence.
- User-facing behavior matches the requested behavior.
- Architecture constraints were followed.
- No required feature was skipped silently.
- Edge cases specified by the requirements are handled.

### 3. Graph Completion

Checks whether task graph execution is complete.

Signals:

- Required nodes are completed.
- Skipped nodes have accepted rationale.
- Failed nodes are non-required or resolved by replacement tasks.
- No required active or blocked tasks remain.
- Dependency closure is satisfied.

### 4. Reviewer Approval

Checks whether the Reviewer Agent approves the work.

Reviewer decision values:

- `approved`
- `changes_requested`
- `rejected`

Final completion requires `approved`.

### 5. Risk And Quality

Checks whether known risks are acceptable.

Signals:

- No high-severity unresolved issue.
- Security-sensitive areas received appropriate validation.
- No broad unrelated rewrites.
- No weakened tests or acceptance criteria.
- Implementation is maintainable within project conventions.

## Scoring Model

The orchestrator computes a final gate score from weighted dimensions.

Recommended weights:

```text
test_health        0.25
spec_alignment     0.30
graph_completion   0.20
reviewer_approval  0.15
risk_quality       0.10
```

Each dimension receives a score from `0.0` to `1.0`.

Final score:

```text
final_gate_score =
  test_health * 0.25 +
  spec_alignment * 0.30 +
  graph_completion * 0.20 +
  reviewer_approval * 0.15 +
  risk_quality * 0.10
```

Completion requires:

```text
final_gate_score >= 0.85
```

## Hard Fail Conditions

The final gate must fail regardless of numeric score if any condition is true:

- Reviewer Agent decision is not `approved`.
- Any required task is `failed`, `blocked`, `pending`, `ready`, or `active`.
- Required tests are failing.
- The implementation violates a critical requirement.
- Security or data loss risk is unresolved.
- The system cannot produce evidence for key acceptance criteria.

## Evaluation Output

The evaluation result should be structured.

```json
{
  "status": "passed",
  "final_gate_score": 0.89,
  "dimension_scores": {
    "test_health": 0.95,
    "spec_alignment": 0.88,
    "graph_completion": 1.0,
    "reviewer_approval": 1.0,
    "risk_quality": 0.78
  },
  "reviewer_decision": "approved",
  "hard_failures": [],
  "required_changes": [],
  "evidence_summary": [
    "All required graph nodes completed.",
    "CI checks passed.",
    "Reviewer approved after final changes."
  ]
}
```

## Central Review Projection

The evaluation result is still the numeric and rule-based gate. Central review projects that gate
into a product decision that the UI and auto-iteration controller can act on.

Decision mapping:

| Condition | Central decision |
| --- | --- |
| Run is queued, running, or paused | `continue` |
| Required input or setup is missing | `wait_for_input` |
| Hard blockers exist | `blocked` |
| Gate passes and delivery evidence is reviewable | `handoff` |
| Gate fails or evidence is incomplete but repairable | `iterate` |

A result can be shippable without being perfect. A score such as `0.87` may pass the final gate, but
central review should still explain what evidence kept the result from scoring higher.

## Retry Decision

If evaluation fails, the orchestrator must classify the failure:

- `missing_implementation`
- `test_failure`
- `spec_mismatch`
- `review_rejection`
- `quality_risk`
- `blocked_external`

The failure classification determines next action:

- Missing implementation creates new implementation tasks.
- Test failure routes to Debug Agent.
- Spec mismatch routes to Architect Agent or relevant implementation agent.
- Review rejection creates required-change tasks.
- Quality risk creates refactor, security, or test tasks.
- External blocker pauses or escalates.

In V2.62, repairable classifications can also feed a `repair_plan` for the central auto-iteration
controller. The repair plan must preserve the failure classification and required evidence so the
next run is specific rather than a vague retry.

## Termination Rule

The system may stop only when:

- Final gate score is at least `0.85`.
- Reviewer Agent approval is present.
- Hard fail conditions are absent.
- Persistent state records the final evaluation.
- GitHub sync layer records final branch, PR, commit, or release evidence.
- Central review has produced a handoff decision or equivalent final delivery summary.
