# V2.62 Central Auto-Iteration Controller

## Objective

Turn the V2.61 central review result from a human-readable checkpoint into an executable
auto-iteration contract.

The original product goal stays unchanged:

```text
user goal or development package
  -> agent cluster understands the work
  -> code is written
  -> tests and probes run
  -> review identifies gaps
  -> the system iterates until delivery quality or a real blocker
```

V2.61 answers: "What should happen next?"

V2.62 must answer: "If the answer is iterate, what exact repair run should the system start next?"

## Why This Phase Exists

The current runtime can intake one-line ideas, uploaded development documents, local repositories,
and GitHub repositories. It can plan, execute, test, score, reopen with feedback, and show central
review evidence.

The remaining gap is that central review is advisory. A human operator still has to translate:

```text
central_review.decision = iterate
```

into a concrete repair document, reopened run, or next task package.

V2.62 closes that gap by defining a central auto-iteration controller. The controller does not add a
new product feature for the target application. It turns existing evidence into the next development
cycle when the system is not yet good enough to hand off.

## Scope

V2.62 covers:

- repair plan generation from central review and delivery evidence;
- automatic repair-run creation when iteration is safe;
- iteration history linking source run and repair run;
- beginner UI copy for "continue optimizing";
- advanced UI evidence for repair plan and loop guardrails;
- API contracts for starting or previewing the next iteration;
- deterministic tests for advisory, blocked, and repairable states.

V2.62 does not cover:

- a new model provider;
- automatic merge to protected branches;
- unbounded looping;
- destructive cleanup of user repositories;
- replacing existing feedback reopen behavior;
- changing source-intake modes.

## Central Auto-Iteration State Machine

```text
run evidence available
        |
        v
central_review
        |
        +-- decision=handoff ------> show delivery actions
        |
        +-- decision=blocked ------> stop and surface blocker
        |
        +-- decision=continue -----> keep polling current run
        |
        +-- decision=wait_for_input -> keep configuration/source locked
        |
        +-- decision=iterate ------> build repair_plan
                                      |
                                      v
                              guardrail evaluation
                                      |
                   +------------------+------------------+
                   |                                     |
                   v                                     v
            safe_to_iterate                         unsafe/duplicate
                   |                                     |
                   v                                     v
        create reopened repair run                 ask human or block
                   |
                   v
          execute existing run loop
                   |
                   v
         compare source and repair run
```

## Inputs

The controller must read only existing machine evidence plus the V2.61 central review payload:

- project id and run id;
- `central_review`;
- delivery report;
- final gate score and dimension scores;
- requirement coverage;
- artifact report and browser probes;
- development-cycle report;
- recovery comparison when this is already a repair run;
- task graph status;
- blockers and required changes;
- source mode and delivery mode;
- previous auto-iteration reports for the project.

It must not infer hidden facts from chat history.

## Output: Repair Plan

When `central_review.decision=iterate`, the controller produces a `repair_plan_v1` document.

The repair plan must include:

- source project id;
- source run id;
- reason for iteration;
- evidence gaps;
- requirements to repair;
- tasks to reopen or create;
- agent assignment;
- verification commands or probes to run;
- stop conditions;
- confidence;
- whether automatic execution is allowed.

The plan is written into the source run folder before any repair run starts:

```text
runs/<run_id>/repair_plan.json
runs/<run_id>/repair_plan.md
```

The Markdown file exists for human audit. The JSON file is the executable contract.

## Output: Auto-Iteration Report

When the controller starts, blocks, or skips an iteration, it writes:

```text
runs/<run_id>/auto_iteration_report.json
```

The report records:

- status: `started`, `skipped`, `blocked`, or `handoff`;
- source run id;
- repair run id if created;
- central review decision;
- repair plan path;
- guardrail decisions;
- reason;
- next actions.

## Guardrails

The controller may start a repair run only when all conditions are true:

- central review decision is `iterate`;
- no hard external blocker exists;
- a repair plan contains at least one concrete task or requirement gap;
- the same repair signature has not already failed repeatedly;
- project iteration count is below the configured limit;
- the source mode permits local or repository edits;
- the user has not stopped the project;
- no mutating GitHub action is required without explicit user approval.

Default limits:

```json
{
  "max_auto_iterations_per_project": 3,
  "max_duplicate_repair_signature_count": 1,
  "require_score_or_evidence_progress": true
}
```

Long-running tasks may have no wall-clock timeout, but they must still have loop guardrails. A stuck
worker should be reported as a blocker instead of silently waiting forever.

## Repair Plan Generation Rules

The controller must prioritize gaps in this order:

1. hard blockers;
2. failed required tests, CI, or browser probes;
3. missing `must` requirement coverage;
4. reviewer changes requested;
5. central review missing loop steps;
6. low final gate dimensions;
7. local-only evidence where the user requested real GitHub/CI delivery.

Each gap becomes a repair item with:

- `id`;
- `priority`;
- `source`;
- `summary`;
- `target_agent`;
- `required_evidence`;
- `acceptance_check`.

The repair plan should prefer existing feedback reopen and Debug Agent repair mechanics instead of
inventing a parallel execution path.

## Integration With Existing Feedback Reopen

V2.62 should reuse the feedback reopen path by generating a machine-authored feedback file:

```text
runs/<run_id>/auto_feedback.md
```

This file is attached to the next run as feedback input. It must state:

- what was delivered;
- why central review requested iteration;
- exact requirements and probes to repair;
- what evidence must be produced before handoff.

The next run should be visibly linked to the source run:

```json
{
  "source_run_id": "run_001",
  "reopen_reason": "central_auto_iteration",
  "repair_plan_id": "repair_plan_v1:..."
}
```

## API Contract

V2.62 should expose two operations.

### Preview

```http
GET /projects/{project_id}/runs/{run_id}/auto-iteration
```

Returns the current auto-iteration report if present. If no report exists, it may compute a
non-mutating preview.

### Start

```http
POST /projects/{project_id}/runs/{run_id}/auto-iteration
```

Starts a repair run only when guardrails pass.

Required response fields:

```json
{
  "status": "started",
  "source_run_id": "run_001",
  "repair_run_id": "run_002",
  "repair_plan": {},
  "auto_iteration_report_url": "/projects/proj_x/runs/run_001/files/auto_iteration_report.json"
}
```

Blocked response example:

```json
{
  "status": "blocked",
  "source_run_id": "run_001",
  "repair_run_id": null,
  "reason": "Hard external blocker requires human action.",
  "next_actions": ["Fix GitHub authentication in Configuration."]
}
```

## Beginner UX Contract

Beginner UI should show at most one next-step action:

| Central decision | Beginner action |
| --- | --- |
| `handoff` | `Open result` |
| `iterate` | `Continue optimizing` |
| `blocked` | `Fix required setup` or `View issue` |
| `continue` | progress remains active |
| `wait_for_input` | return to configuration/source input |

The UI must not show raw repair terms by default. Suggested copy:

- "The first version works, but I found a few things to improve."
- "Continue optimizing"
- "I need your help before continuing."
- "Ready to review"

Advanced details may show:

- repair plan JSON;
- missing loop steps;
- score dimensions;
- task graph gaps;
- probe failures;
- previous iteration comparison.

## Acceptance Criteria

- A ready run with `central_review.decision=handoff` does not create a repair run.
- A blocked run with hard blockers returns a blocked auto-iteration report.
- A run with `central_review.decision=iterate` produces `repair_plan.json`, `repair_plan.md`, and `auto_feedback.md`.
- Safe iteration starts a new run through the existing feedback reopen mechanism.
- The new run records the source run id, repair plan id, and reopen reason.
- Repair runs with explicit `target_files` may stop through the V2.64 repair convergence gate once
  the target files and required checks pass.
- Duplicate repair plans do not loop forever.
- The UI shows a beginner-safe `Continue optimizing` action only when automatic iteration is available.
- Advanced UI exposes repair plan and report evidence.
- Tests cover service, API, static UI contract, and at least one end-to-end dry-run repair cycle.

## Implementation Order

1. Add schemas for central review, repair plan, and auto-iteration report.
2. Add repair plan generation from existing evidence.
3. Add a non-mutating auto-iteration preview service.
4. Add mutating start operation that reuses feedback reopen.
5. Add project/run history links for source and repair runs.
6. Add beginner UI action and advanced evidence panel.
7. Add regression tests and local dry-run acceptance.

## Done Definition

V2.62 is complete when a delivered-but-imperfect run can be automatically converted into a repair
run, the repair run executes through the existing development loop, and the project history clearly
shows the chain:

```text
run_001 -> central review says iterate -> repair_plan -> run_002 -> comparison -> handoff or iterate
```

No user should need to understand task graphs, JSON evidence, or Codex worker internals to continue
optimizing a project.
