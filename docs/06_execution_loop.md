# Execution Loop

## Purpose

The execution loop defines how the autonomous development system progresses from objective intake to delivery termination.

The loop is state-driven. Every iteration reads persistent state, performs a bounded action, records evidence, and re-evaluates next steps.

## High-Level Loop

```text
1. Load objective, documents, supporting files, repository context, and persisted state.
2. Build or load ProjectBrief and ContextBundle when v2 intake is enabled.
3. Create or update task graph.
4. Select ready tasks.
5. Assign tasks to agents.
6. Invoke Codex workers for executable tasks.
7. Run tests and collect evidence.
8. Update task state.
9. Evaluate graph progress.
10. Retry, debug, replan, or review.
11. Run final evaluation gate.
12. Run central review over all available evidence.
13. If repairable gaps remain, generate a repair plan and re-enter the loop.
14. For full-roadmap runs, run final audit/test convergence across the whole system.
15. Terminate only when done criteria pass, central review reaches handoff, and final audit/test convergence passes.
```

## Step 1: Intake

Inputs:

- User objective.
- Requirements or development document.
- Supporting files.
- Target repository.
- Constraints.
- Done criteria.

The orchestrator initializes state using `state_schema_v2.json`.

In v2, raw intake material is normalized before graph planning:

```text
Objective + Documents + Attachments + GitHub Source
  -> ProjectBrief
  -> ContextBundle
  -> TaskGraph
```

If the user provides only one sentence, the system may expand it into a generated `ProjectBrief`, but that path is lower confidence than document-driven intake.

## Step 2: Task Graph Creation

The orchestrator asks the Architect Agent to create the task graph.

The graph must include:

- Required implementation tasks.
- Verification tasks.
- Review tasks.
- Dependencies.
- Agent assignment recommendations.
- Completion criteria.

The orchestrator validates the graph against `task_graph_schema.json`.

## Step 3: Task Selection

The orchestrator selects ready tasks.

A task is ready when:

- Its dependencies are complete.
- It has no unresolved blocker.
- It has clear completion criteria.
- It has an assigned agent type.
- It has not exceeded retry limits.

Ready tasks may be grouped for parallel execution when conflict policy allows it.

## Step 4: Agent Assignment

The orchestrator sends each selected task to the appropriate agent.

Assignment examples:

- `architecture` to Architect Agent.
- `backend` to Backend Agent.
- `frontend` to Frontend Agent.
- `test` to Test Agent.
- `debug` to Debug Agent.
- `review` to Reviewer Agent.

Agents return worker instructions, validation criteria, or review decisions depending on task type.

## Step 5: Codex Worker Execution

For executable tasks, the orchestrator invokes Codex CLI with a bounded task package.

Codex worker performs:

- Repository inspection.
- File edits.
- Test execution.
- Bug fixing within task scope.
- Result reporting.

The worker result is attached to the task node as evidence.

The current runtime exposes this through `python -m runtime.run_loop`.
Dry-run worker execution is the default for deterministic local runs. Pass `--real-codex` to invoke a real Codex subprocess.

## Step 6: Testing

Testing can happen inside a worker run, as a separate Test Agent task, through CI, or all three.

The Test Agent evaluates:

- Whether the correct tests were run.
- Whether failures are relevant.
- Whether coverage is sufficient for the task.
- Whether additional tests are required.

## Step 7: State Update

After every task run, the orchestrator updates persistent state.

State updates include:

- Active task changes.
- Completed task records.
- Failed task records.
- Evidence records.
- Blockers.
- Retry counts.
- Evaluation scores.
- GitHub references.

State must be written before starting another major action.

## Step 8: Evaluation

The orchestrator evaluates the current graph state.

Possible outcomes:

- Continue with more ready tasks.
- Route failed tasks to Debug Agent.
- Ask Architect Agent to replan.
- Ask Test Agent for missing verification.
- Ask Reviewer Agent for final review.
- Run central review to decide continue, iterate, blocked, wait-for-input, or handoff.
- Generate a repair plan when the result is incomplete but repairable.
- Stop because final gate passed.
- Stop or pause because of an external blocker.

## Retry Loop

When a task fails:

```text
worker failure
      |
      v
Debug Agent diagnosis
      |
      v
repair task or retry prompt
      |
      v
Codex worker execution
      |
      v
test and evidence evaluation
```

Retry rules:

- A retry must include new diagnosis or changed instructions.
- Retry count is tracked per task.
- The orchestrator must stop retrying after policy limits.
- Repeated failure creates a blocker or graph revision request.

## Replanning Loop

The Architect Agent is re-entered when:

- A requirement was misunderstood.
- A dependency was missing.
- A task is too broad.
- Integration reveals new work.
- A blocker changes the feasible plan.

Replanning should preserve completed valid work and update only affected graph regions.

## Review Loop

After required tasks are complete, the Reviewer Agent evaluates the result.

If changes are requested:

- The orchestrator creates required-change tasks.
- Relevant implementation agents scope the fixes.
- Codex worker executes fixes.
- Tests run again.
- Reviewer Agent reviews again.

After reviewer and evaluation evidence exists, the Central Review Agent summarizes whether the
system should hand off, continue, iterate, block, or wait for input. This central review step is the
product-facing equivalent of a human Codex operator asking whether the phase is truly done.

## Central Auto-Iteration Loop

When central review returns `decision=iterate`, the orchestrator must not blindly rerun the same
work. It must create a repair plan.

```text
central_review.decision = iterate
      |
      v
repair_plan generation
      |
      v
guardrail check
      |
      +-- blocked/duplicate/unsafe -> surface blocker or ask human
      |
      v
feedback reopen or graph delta
      |
      v
Codex worker execution
      |
      v
tests, probes, review, recovery comparison
```

Rules:

- Every repair iteration must have a concrete evidence gap.
- Duplicate repair signatures must be guarded to prevent endless loops.
- Auto-iteration must reuse the same intake, task graph, worker, test, evaluation, and delivery
  evidence contracts.
- Mutating GitHub actions still require the configured GitHub delivery policy.
- If no safe automatic repair exists, the run becomes blocked or waits for human input.

## Termination Condition

The system terminates successfully only when:

- Required graph nodes are complete.
- Required tests and CI checks pass.
- Reviewer Agent approves.
- Final gate score is at least `0.85`.
- Central review returns a handoff decision.
- Full-roadmap final audit/test convergence passes when a roadmap exists.
- No hard fail condition exists.
- Final state is persisted.
- GitHub sync evidence is recorded.

The current runtime records GitHub evidence with `runtime/github_flow.py`.
Dry-run evidence is recorded by default. Pass `--real-github` to run local `git` and `gh` commands for branch, commit, push, and pull request creation.

## Failed Termination

The system may terminate unsuccessfully when:

- External blockers prevent progress.
- Retry policy is exhausted.
- Requirements are impossible under constraints.
- Repository permissions prevent required actions.
- Critical ambiguity cannot be resolved without user input.

Failed termination must include:

- Current graph state.
- Completed work.
- Failed work.
- Blockers.
- Required user or external action.
