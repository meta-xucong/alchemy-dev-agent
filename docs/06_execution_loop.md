# Execution Loop

## Purpose

The execution loop defines how the autonomous development system progresses from objective intake to delivery termination.

The loop is state-driven. Every iteration reads persistent state, performs a bounded action, records evidence, and re-evaluates next steps.

## High-Level Loop

```text
1. Load objective, requirements, repository context, and persisted state.
2. Create or update task graph.
3. Select ready tasks.
4. Assign tasks to agents.
5. Invoke Codex workers for executable tasks.
6. Run tests and collect evidence.
7. Update task state.
8. Evaluate graph progress.
9. Retry, debug, replan, or review.
10. Run final evaluation gate.
11. Terminate only when done criteria pass.
```

## Step 1: Intake

Inputs:

- User objective.
- Requirements or development document.
- Target repository.
- Constraints.
- Done criteria.

The orchestrator initializes state using `state_schema_v2.json`.

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

## Termination Condition

The system terminates successfully only when:

- Required graph nodes are complete.
- Required tests and CI checks pass.
- Reviewer Agent approves.
- Final gate score is at least `0.85`.
- No hard fail condition exists.
- Final state is persisted.
- GitHub sync evidence is recorded.

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
