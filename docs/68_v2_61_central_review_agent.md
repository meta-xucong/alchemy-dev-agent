# V2.61 Central Review Agent

## Objective

Add a deterministic central review layer that mirrors the human Codex long-task loop:

```text
read context -> refine plan -> implement -> audit -> test -> iterate -> review -> handoff
```

The central review agent does not replace task execution, evaluation, or delivery gates. It summarizes their evidence into one operator-facing decision that can later drive automated iteration.

## Why This Phase Exists

The runtime already has:

- source intake for idea, uploaded documents, and GitHub repositories;
- task graph planning;
- Codex worker execution;
- requirement coverage;
- artifact/browser verification;
- reviewer/final gate scoring;
- feedback reopen;
- project history and local artifact delivery.

What is still weak compared with a human Codex engineering session is the explicit "thinking checkpoint" between phases. A human operator repeatedly asks:

- Did we understand the documents?
- Did we implement the right thing?
- Did tests and browser/manual checks actually prove it?
- Should we continue, repair, ask for help, or hand off?

V2.61 makes that checkpoint machine-readable.

## Contract

Every completed or running project run should expose:

```json
{
  "central_review": {
    "status": "running|ready|needs_iteration|blocked|waiting",
    "decision": "continue|handoff|iterate|blocked|wait_for_input",
    "confidence": 0.0,
    "summary": "",
    "completed_loop_steps": [],
    "missing_loop_steps": [],
    "next_actions": [],
    "human_help_needed": false
  }
}
```

### Status Semantics

| Status | Meaning |
| --- | --- |
| `waiting` | No run evidence exists yet. |
| `running` | Work is queued, running, or paused. |
| `ready` | Delivery evidence says the result is ready to review. |
| `needs_iteration` | A result exists but key evidence or quality gates are incomplete. |
| `blocked` | The run failed, stalled, or contains unresolved hard blockers. |

### Decision Semantics

| Decision | Meaning |
| --- | --- |
| `continue` | Keep running or polling the current run. |
| `handoff` | Show result actions and let the user inspect/accept. |
| `iterate` | Start a feedback/reopen or repair cycle before handoff. |
| `blocked` | Stop automatic work and surface the blocker. |
| `wait_for_input` | User must choose a source, provide files, or fix environment/configuration. |

## Evidence Inputs

The central review agent reads only existing runtime evidence:

- run/job status;
- runtime state and task graph;
- delivery report and final gate;
- development cycle report;
- requirement coverage;
- artifact/browser verification;
- delivery actions and artifact manifest;
- unresolved blockers and next actions.

No new model call is required in this phase.

## Manual-Loop Mapping

| Human Codex Step | Existing Evidence | Central Review Output |
| --- | --- | --- |
| Read docs | project brief and context bundle | completed/missing `read_documents` |
| Refine plan | requirement map and task graph | completed/missing `brain_refinement` |
| Execute phase | completed task nodes | completed/missing `execution` |
| Audit | reviewer node and requirement coverage | completed/missing `audit` |
| Test | test health, static/browser checks, CI | completed/missing `testing` |
| Iterate | retry/debug/feedback evidence | completed/missing `iteration` |
| Full review | final gate and ready_for_review | `handoff` or `iterate` |

## UX Requirements

Beginner UI should show one short central message:

- "Still building..."
- "Ready to review."
- "Needs another iteration."
- "Blocked: human help needed."

Advanced UI may show missing loop steps and next actions.

## Implementation Plan

1. Add `autodev.central_review`.
2. Add `central_review` to `get_run_status`.
3. Add `central_review` to `get_delivery_for_run`.
4. Render central review in the progress panel and delivery overview.
5. Add API/static tests.

## Acceptance Criteria

- Running jobs return `central_review.status=running` and `decision=continue`.
- Done runs with ready delivery return `status=ready` and `decision=handoff`.
- Failed or blocked runs return `decision=blocked`.
- Done runs with missing delivery evidence return `decision=iterate`.
- Beginner UI displays the central review summary without requiring raw JSON.
