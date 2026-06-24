# Central Auto-Iteration Example

## Input

User source mode: uploaded development document.

Objective:

```text
Build a small browser game with movement, scoring, restart, and level completion.
```

## First Run Result

The first run produces a playable artifact, but the evidence is incomplete:

```json
{
  "run_id": "run_001",
  "delivery_status": "needs_iteration",
  "final_gate_score": 0.82,
  "central_review": {
    "status": "needs_iteration",
    "decision": "iterate",
    "summary": "The game runs, but one required gameplay probe failed.",
    "missing_loop_steps": ["testing", "iteration"],
    "next_actions": ["Repair failed gameplay probe and rerun browser verification."]
  }
}
```

## Generated Repair Plan

```json
{
  "schema_version": "1.0",
  "repair_plan_id": "rp_run_001_gameplay_probe",
  "project_id": "proj_game",
  "source_run_id": "run_001",
  "trigger": "central_review_iterate",
  "status": "ready",
  "summary": "Repair failed gameplay probe before handoff.",
  "repair_signature": "sha256:example",
  "items": [
    {
      "id": "repair_001",
      "priority": "must",
      "source": "gameplay_probe",
      "summary": "Victory condition probe failed after reaching the level end.",
      "target_agent": "debug",
      "required_evidence": [
        "Gameplay probe passes for movement, jump, scoring, restart, and victory."
      ],
      "acceptance_check": "browser_gameplay_probe.status == passed"
    }
  ],
  "guardrails": {
    "safe_to_execute": true,
    "max_iterations": 3,
    "current_iteration": 1,
    "duplicate_signature_count": 0,
    "requires_user_approval": false,
    "blockers": []
  },
  "auto_execution": {
    "allowed": true,
    "mode": "feedback_reopen"
  },
  "created_at": "2026-06-21T00:00:00Z"
}
```

## Auto Feedback

```markdown
# Auto Feedback

Source run: run_001
Reason: central review requested another iteration.

## Required Repairs

1. Fix the failed gameplay victory probe.

## Acceptance Evidence Required

- Browser gameplay probe passes.
- Final gate score is at least 0.85.
- Central review decision becomes handoff.
```

## Repair Run

The controller starts a new run:

```json
{
  "run_id": "run_002",
  "source_run_id": "run_001",
  "reopen_reason": "central_auto_iteration",
  "repair_plan_id": "rp_run_001_gameplay_probe"
}
```

## Expected Handoff

After the repair run:

```json
{
  "run_id": "run_002",
  "delivery_status": "ready_for_review",
  "final_gate_score": 0.89,
  "central_review": {
    "status": "ready",
    "decision": "handoff",
    "summary": "Ready to review."
  }
}
```

Beginner UI shows:

```text
Ready to review
Open result
Open result folder
```
