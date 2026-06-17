# Full Autodev Example: Todo App With Login

## Input

```text
build a todo app with login
```

## Interpreted Objective

Build a web application where users can register, log in, and manage their own todo items. Authenticated users can create, read, update, complete, and delete todos. Users must not see other users' todos.

## Done Criteria

- Users can register with email and password.
- Users can log in and log out.
- Authenticated users can create, edit, complete, and delete todos.
- Todo data is scoped to the authenticated user.
- Backend tests cover auth and todo ownership.
- Frontend tests or browser checks cover login and todo workflows.
- CI passes.
- Reviewer Agent approves.
- Final gate score is at least `0.85`.

## Task Graph

```json
{
  "graph_id": "todo-login-v1",
  "version": 1,
  "nodes": [
    {
      "id": "T001",
      "title": "Define application architecture",
      "description": "Define frontend, backend, auth, persistence, and testing architecture.",
      "type": "architecture",
      "assigned_agent": "architect",
      "status": "pending",
      "dependencies": [],
      "completion_criteria": [
        "Architecture identifies app layers, auth model, todo ownership model, and required tests."
      ],
      "evidence": []
    },
    {
      "id": "T002",
      "title": "Implement auth data model",
      "description": "Create user model, password storage approach, and session or token persistence.",
      "type": "backend",
      "assigned_agent": "backend",
      "status": "pending",
      "dependencies": ["T001"],
      "completion_criteria": [
        "User records can be persisted.",
        "Passwords are not stored in plaintext.",
        "Auth model is covered by backend tests."
      ],
      "evidence": []
    },
    {
      "id": "T003",
      "title": "Implement auth API",
      "description": "Implement register, login, logout, and current-user endpoints.",
      "type": "backend",
      "assigned_agent": "backend",
      "status": "pending",
      "dependencies": ["T002"],
      "completion_criteria": [
        "Register endpoint creates users.",
        "Login endpoint authenticates valid credentials.",
        "Invalid credentials fail safely.",
        "Logout clears authentication state."
      ],
      "evidence": []
    },
    {
      "id": "T004",
      "title": "Implement todo data model and API",
      "description": "Create todo persistence and CRUD endpoints scoped to authenticated users.",
      "type": "backend",
      "assigned_agent": "backend",
      "status": "pending",
      "dependencies": ["T003"],
      "completion_criteria": [
        "Todos belong to users.",
        "Users cannot access todos owned by other users.",
        "CRUD endpoints are tested."
      ],
      "evidence": []
    },
    {
      "id": "T005",
      "title": "Implement frontend auth flow",
      "description": "Create registration, login, logout, and authenticated session UI.",
      "type": "frontend",
      "assigned_agent": "frontend",
      "status": "pending",
      "dependencies": ["T003"],
      "completion_criteria": [
        "Users can register from the UI.",
        "Users can log in and log out from the UI.",
        "Unauthenticated users are prompted to log in."
      ],
      "evidence": []
    },
    {
      "id": "T006",
      "title": "Implement frontend todo workflow",
      "description": "Create UI for listing, adding, editing, completing, and deleting todos.",
      "type": "frontend",
      "assigned_agent": "frontend",
      "status": "pending",
      "dependencies": ["T004", "T005"],
      "completion_criteria": [
        "Authenticated users can manage todos from the UI.",
        "Todo state updates are reflected without full-page reload.",
        "Empty, loading, and error states are handled."
      ],
      "evidence": []
    },
    {
      "id": "T007",
      "title": "Add verification coverage",
      "description": "Add or update tests for auth, todo ownership, and primary frontend workflows.",
      "type": "test",
      "assigned_agent": "test",
      "status": "pending",
      "dependencies": ["T004", "T006"],
      "completion_criteria": [
        "Required backend tests pass.",
        "Required frontend workflow checks pass.",
        "Test Agent confirms coverage matches done criteria."
      ],
      "evidence": []
    },
    {
      "id": "T008",
      "title": "Final review",
      "description": "Review implementation, evidence, and spec alignment.",
      "type": "review",
      "assigned_agent": "reviewer",
      "status": "pending",
      "dependencies": ["T007"],
      "completion_criteria": [
        "Reviewer Agent approves.",
        "No required task remains failed or blocked.",
        "Final gate score is at least 0.85."
      ],
      "evidence": []
    }
  ],
  "dependencies": [
    { "from": "T001", "to": "T002", "type": "blocks" },
    { "from": "T002", "to": "T003", "type": "blocks" },
    { "from": "T003", "to": "T004", "type": "blocks" },
    { "from": "T003", "to": "T005", "type": "blocks" },
    { "from": "T004", "to": "T006", "type": "blocks" },
    { "from": "T005", "to": "T006", "type": "blocks" },
    { "from": "T004", "to": "T007", "type": "requires_test_pass" },
    { "from": "T006", "to": "T007", "type": "requires_test_pass" },
    { "from": "T007", "to": "T008", "type": "requires_review" }
  ]
}
```

## Agent Assignment

| Task | Agent | Reason |
| --- | --- | --- |
| T001 | Architect Agent | Converts objective into system plan and graph. |
| T002 | Backend Agent | Owns user persistence and password storage design. |
| T003 | Backend Agent | Owns auth endpoint implementation. |
| T004 | Backend Agent | Owns todo persistence, API, and ownership rules. |
| T005 | Frontend Agent | Owns login, registration, logout, and session UI. |
| T006 | Frontend Agent | Owns todo management UI. |
| T007 | Test Agent | Validates coverage and test evidence. |
| T008 | Reviewer Agent | Approves or rejects final delivery. |

## Execution Flow

### 1. Architecture

The orchestrator sends the objective to Architect Agent.

Architect Agent returns:

- App boundaries.
- Auth model recommendation.
- Todo ownership rule.
- Required backend and frontend tasks.
- Verification strategy.
- Initial task graph.

The orchestrator persists the graph and marks `T001` ready.

### 2. Backend Foundation

The orchestrator selects `T002` after `T001` completes.

Backend Agent prepares a Codex worker package:

```json
{
  "task_id": "T002",
  "task_description": "Implement user persistence and secure password storage.",
  "acceptance_criteria": [
    "User records can be persisted.",
    "Passwords are hashed.",
    "Tests cover user creation and password verification."
  ],
  "constraints": [
    "Do not implement frontend UI.",
    "Do not store plaintext passwords."
  ]
}
```

Codex worker edits repository files, runs backend tests, and returns evidence.

### 3. Auth API

After `T002`, `T003` becomes ready.

Backend Agent scopes register, login, logout, and current-user endpoints. Codex worker implements them and runs tests.

If tests fail, the orchestrator routes logs to Debug Agent. Debug Agent creates a repair prompt, and Codex worker retries within policy.

### 4. Parallelizable Work

After `T003`, the graph allows:

- `T004` backend todo API.
- `T005` frontend auth flow.

These may run in parallel if branch and file conflict policy permits.

### 5. Todo UI

`T006` waits for both `T004` and `T005`.

Frontend Agent prepares task instructions for:

- Todo list.
- Add todo.
- Edit todo.
- Complete todo.
- Delete todo.
- Empty, loading, and error states.

Codex worker implements the UI and runs frontend checks.

### 6. Verification

`T007` starts after backend and frontend workflow tasks complete.

Test Agent verifies:

- Auth tests exist and pass.
- Todo ownership is tested.
- UI workflow is tested or browser-verified.
- CI is passing or local equivalent evidence exists.

If coverage is missing, Test Agent returns required test tasks instead of approval.

### 7. Final Review

Reviewer Agent receives:

- Objective.
- Done criteria.
- Final graph state.
- Worker summaries.
- Test results.
- CI status.
- Known issues.

Reviewer Agent checks:

- Users can register, log in, log out.
- Todos are user-scoped.
- CRUD workflow works.
- Tests cover critical behavior.
- No required tasks remain unresolved.

### 8. Final Gate

Example final evaluation:

```json
{
  "status": "passed",
  "final_gate_score": 0.9,
  "dimension_scores": {
    "test_health": 0.95,
    "spec_alignment": 0.9,
    "graph_completion": 1.0,
    "reviewer_approval": 1.0,
    "risk_quality": 0.8
  },
  "reviewer_decision": "approved",
  "hard_failures": [],
  "required_changes": []
}
```

The orchestrator terminates successfully only after this result is persisted.
