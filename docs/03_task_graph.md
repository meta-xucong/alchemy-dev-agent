# Task Graph

## Purpose

The task graph is the executable representation of the development objective. It defines what must be done, in what order, by which type of agent, and how completion is proven.

The graph is not a project plan in prose. It is a machine-readable scheduling and evaluation contract.

## Core Concepts

### Node

A node represents one task with a clear outcome.

Required node properties:

- Stable task ID.
- Title.
- Description.
- Task type.
- Assigned agent type.
- Dependencies.
- Execution status.
- Completion criteria.
- Evidence records.

### Dependency

A dependency defines that one task cannot start until another task reaches an acceptable terminal state.

Supported dependency types:

- `blocks`: target task cannot start until source task is complete.
- `requires_artifact`: target task needs an output artifact from source task.
- `requires_review`: target task needs approval evidence from source task.
- `requires_test_pass`: target task needs successful test evidence from source task.

### Task Type

Recommended task types:

- `architecture`
- `backend`
- `frontend`
- `test`
- `debug`
- `review`
- `documentation`
- `integration`
- `release`

### Execution Status

Required statuses:

- `pending`
- `ready`
- `active`
- `blocked`
- `completed`
- `failed`
- `skipped`

## Task Graph Schema

The normative JSON schema is defined in:

```text
specs/task_graph_schema.json
```

Minimum shape:

```json
{
  "graph_id": "todo-app-login-v1",
  "version": 1,
  "nodes": [
    {
      "id": "T001",
      "title": "Define architecture",
      "type": "architecture",
      "assigned_agent": "architect",
      "status": "pending",
      "dependencies": [],
      "completion_criteria": [
        "Architecture covers frontend, backend, auth, persistence, and testing."
      ],
      "evidence": []
    }
  ],
  "dependencies": [
    {
      "from": "T001",
      "to": "T002",
      "type": "blocks"
    }
  ]
}
```

## Dependency Model

A task is eligible to run when:

- Its status is `pending` or `ready`.
- All required dependency source nodes are in `completed` state.
- Required artifact evidence is present.
- No blocking issue is attached to the task.
- The orchestrator has selected an agent capable of handling the task type.

A task is not eligible when:

- Any dependency is `pending`, `active`, `failed`, or `blocked`.
- It requires a missing artifact.
- It depends on a review that has not been approved.
- It exceeds retry policy without Debug Agent intervention.

## Parallel Execution Rule

The orchestrator may run tasks in parallel when all conditions are true:

- Each task is eligible.
- The tasks do not write to overlapping high-risk files or modules unless conflict policy allows it.
- The tasks do not depend on each other.
- The tasks have compatible branch strategy.
- The system can merge or reconcile outputs safely.

Recommended parallel groups:

- Independent backend endpoints after architecture is complete.
- Frontend components that depend on stable API contracts.
- Test creation for already defined modules.
- Documentation updates that do not depend on final implementation details.

Parallel execution must preserve task-specific branches, commits, and evidence.

## Completion Rule

A task can move to `completed` only when:

- Worker output or agent output satisfies task completion criteria.
- Required tests or checks have passed or have documented acceptance.
- Evidence is attached to the node.
- The responsible agent confirms task-level completion.
- The orchestrator accepts the state transition.

The full graph is complete only when:

- All required nodes are `completed` or explicitly `skipped` with accepted rationale.
- No active, failed, or blocked required nodes remain.
- Final evaluation score is at least `0.85`.
- Reviewer Agent approval is present.
- Done criteria are satisfied.

## Failure Rule

A task moves to `failed` when:

- Codex worker cannot complete the task within retry policy.
- Required tests fail and the Debug Agent cannot repair them within retry policy.
- The implementation conflicts with architecture constraints.
- Required evidence is missing after execution.

Failure does not automatically fail the whole objective. The orchestrator should route failed tasks to the Debug Agent or Architect Agent depending on the cause.

## Blocker Rule

A blocker is used when progress requires external input or a state change the system cannot perform.

Examples:

- Missing credentials.
- Ambiguous requirement that affects architecture.
- Unavailable dependency or service.
- Repository permission issue.
- CI infrastructure outage.

Blocked tasks must include:

- Blocker type.
- Description.
- Required resolution.
- Impacted task IDs.
- Whether the objective can continue partially.
