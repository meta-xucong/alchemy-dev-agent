# Architecture

## System Layers

The system is organized into five layers:

- **Orchestrator layer**: owns global state, task scheduling, agent routing, retry policy, and termination.
- **Agent layer**: performs specialized planning, implementation guidance, testing strategy, debugging, and review.
- **Codex worker runtime**: executes concrete repository work through Codex CLI.
- **GitHub sync layer**: synchronizes branches, commits, pull requests, CI status, and review metadata.
- **State persistence layer**: stores project state, task graph state, evidence, scores, and blockers.

## Architecture Diagram

```text
                          User Objective + Spec
                                   |
                                   v
                         +--------------------+
                         |    Orchestrator    |
                         |--------------------|
                         | state manager      |
                         | task scheduler     |
                         | retry controller   |
                         | evaluation gate    |
                         +---------+----------+
                                   |
                +------------------+------------------+
                |                  |                  |
                v                  v                  v
        +---------------+  +---------------+  +---------------+
        | Architect     |  | Implementation|  | Verification  |
        | Agent         |  | Agents        |  | Agents        |
        |---------------|  |---------------|  |---------------|
        | task graph    |  | backend       |  | test          |
        | architecture  |  | frontend      |  | reviewer      |
        | constraints   |  | debug         |  | final gate    |
        +-------+-------+  +-------+-------+  +-------+-------+
                |                  |                  |
                +------------------+------------------+
                                   |
                                   v
                         +--------------------+
                         | Codex CLI Worker   |
                         |--------------------|
                         | edit files         |
                         | run tests          |
                         | fix bugs           |
                         | return evidence    |
                         +---------+----------+
                                   |
                 +-----------------+-----------------+
                 |                                   |
                 v                                   v
        +------------------+               +-------------------+
        | GitHub Sync      |               | State Persistence |
        |------------------|               |-------------------|
        | branches         |               | state schema      |
        | commits          |               | task graph        |
        | pull requests    |               | run history       |
        | CI checks        |               | evaluation record |
        +------------------+               +-------------------+
```

## Orchestrator Layer

The orchestrator is the control plane. It is responsible for deciding what should happen next, not for directly editing code.

Responsibilities:

- Load the objective, requirements, repository metadata, and current state.
- Ask the Architect Agent to create or update the task graph.
- Select executable tasks whose dependencies are complete.
- Assign each task to the correct agent.
- Invoke Codex worker runs for executable implementation or debugging tasks.
- Collect outputs, patches, test results, CI status, and review evidence.
- Update persistent state after every meaningful event.
- Trigger evaluation after task completion.
- Continue retry loops until done criteria pass or a blocker requires escalation.

The orchestrator must not silently mark work complete without evaluation evidence.

## Agent Layer

The agent layer is made of specialized roles.

Required agents:

- **Architect Agent**: decomposes objectives and owns graph structure.
- **Backend Agent**: scopes and validates backend implementation tasks.
- **Frontend Agent**: scopes and validates frontend implementation tasks.
- **Test Agent**: defines test strategy and evaluates test evidence.
- **Debug Agent**: diagnoses failures and proposes repair tasks.
- **Reviewer Agent**: checks specification alignment and final quality.

Agents return structured outputs. They do not mutate global state directly; the orchestrator applies accepted outputs to state.

## Codex Worker Runtime

Codex CLI is the execution runtime for repository changes.

It receives:

- A single task or tightly scoped task bundle.
- Relevant requirements.
- Repository state.
- Constraints and forbidden actions.
- Expected outputs.

It returns:

- Summary of changes.
- Files changed.
- Commands run.
- Test results.
- Known issues.
- Completion evidence.
- Suggested follow-up tasks if needed.

Codex worker output must be treated as evidence, not as final authority.

## GitHub Sync Layer

The GitHub sync layer connects the autonomous system to real development workflow.

Responsibilities:

- Create or select branches for task execution.
- Commit worker changes with traceable task IDs.
- Push branches.
- Open or update pull requests.
- Read CI check results.
- Read review comments and requested changes.
- Attach task and evaluation metadata to PR descriptions or comments.

GitHub is the shared execution ledger for code changes.

## State Persistence Layer

The persistence layer stores machine-readable state.

It must include:

- Objective.
- Task graph.
- Active tasks.
- Completed tasks.
- Failed tasks.
- Evaluation score.
- Blockers.
- Done criteria.
- Execution history.
- Evidence records.

State must be recoverable after process interruption. The system should be able to resume from persisted state without reconstructing progress from chat logs.

## Control Boundaries

The orchestrator controls:

- Scheduling.
- State transitions.
- Agent calls.
- Worker calls.
- Retry limits.
- Final termination.

Agents control:

- Analysis inside their domain.
- Structured recommendations.
- Task-specific judgments.

Codex workers control:

- Local repository edits.
- Local command execution.
- Bug fixing within task scope.

Review and evaluation control:

- Whether the work is complete enough to ship.
