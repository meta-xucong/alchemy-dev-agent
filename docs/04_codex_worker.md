# Codex Worker

## Role

Codex CLI is an execution worker in this system.

It is not the main brain, not the global planner, and not the final delivery authority. It performs concrete repository work assigned by the orchestrator through agent-generated task instructions.

## Responsibilities

Codex worker is responsible for:

- Inspecting relevant repository files.
- Editing code within task scope.
- Running tests and verification commands.
- Fixing bugs discovered during task execution.
- Producing a structured execution report.
- Returning evidence for the orchestrator and agents.

Codex worker may propose follow-up tasks, but the orchestrator decides whether to add them to the graph.

## Non-Responsibilities

Codex worker must not:

- Redefine the full system architecture.
- Change global objective or done criteria.
- Mark the whole project complete.
- Bypass review or evaluation gates.
- Silently ignore failing tests.
- Expand task scope without reporting it.
- Rewrite unrelated parts of the repository.

## Invocation Model

The orchestrator invokes Codex worker with a bounded task package.

Required invocation fields:

- `task_id`
- `objective`
- `task_description`
- `acceptance_criteria`
- `repository_path`
- `branch`
- `agent_context`
- `relevant_files`
- `constraints`
- `commands_to_run`
- `expected_output_format`

Example invocation package:

```json
{
  "task_id": "T014",
  "objective": "Build a todo app with login",
  "task_description": "Implement password-based login API endpoints.",
  "acceptance_criteria": [
    "Users can register with email and password.",
    "Users can log in and receive an authenticated session.",
    "Invalid credentials return a safe error.",
    "Backend auth tests pass."
  ],
  "repository_path": "/workspace/todo-app",
  "branch": "agent/T014-login-api",
  "agent_context": {
    "assigned_agent": "backend",
    "upstream_tasks": ["T001", "T006"]
  },
  "relevant_files": [
    "src/server",
    "src/db",
    "tests/backend"
  ],
  "constraints": [
    "Do not change frontend routes.",
    "Do not weaken existing tests.",
    "Keep changes limited to auth API and related tests."
  ],
  "commands_to_run": [
    "npm test -- --runInBand",
    "npm run lint"
  ],
  "expected_output_format": "codex_worker_result_v1"
}
```

## Task Passing Rules

Each worker task must be:

- Specific enough to complete in one isolated run.
- Bound to a graph node.
- Supplied with acceptance criteria.
- Supplied with relevant repository context.
- Supplied with allowed and forbidden changes.
- Supplied with verification commands.

The orchestrator should avoid sending broad instructions such as "build the whole app" unless the repository is trivial and the graph explicitly permits a bundled task.

## Result Contract

Codex worker returns a structured result.

Required fields:

- `task_id`
- `status`
- `summary`
- `files_changed`
- `commands_run`
- `tests_passed`
- `tests_failed`
- `evidence`
- `known_issues`
- `follow_up_tasks`
- `confidence`

Example:

```json
{
  "task_id": "T014",
  "status": "completed",
  "summary": "Implemented registration and login endpoints with session creation.",
  "files_changed": [
    "src/server/auth.ts",
    "src/server/routes/auth.ts",
    "tests/backend/auth.test.ts"
  ],
  "commands_run": [
    {
      "command": "npm test -- --runInBand",
      "exit_code": 0,
      "summary": "All backend tests passed."
    },
    {
      "command": "npm run lint",
      "exit_code": 0,
      "summary": "Lint passed."
    }
  ],
  "tests_passed": ["backend auth test suite"],
  "tests_failed": [],
  "evidence": [
    "Registration rejects duplicate email.",
    "Login creates authenticated session.",
    "Invalid password returns 401."
  ],
  "known_issues": [],
  "follow_up_tasks": [],
  "confidence": 0.91
}
```

## Status Values

Allowed worker statuses:

- `completed`
- `partial`
- `failed`
- `blocked`

Status meanings:

- `completed`: task criteria appear satisfied and verification ran successfully.
- `partial`: some work completed, but criteria or verification remain incomplete.
- `failed`: worker attempted the task but could not complete it.
- `blocked`: worker could not proceed because of missing external input, permissions, dependency failure, or ambiguity.

## Evidence Requirements

Worker evidence should include:

- Commands run and exit codes.
- Test names or suites passed.
- Files changed.
- Summary of behavior implemented.
- Any manual verification performed.
- Known limitations.

Evidence must be specific enough for Test Agent and Reviewer Agent to evaluate.

## Retry Handling

When a worker returns `failed` or `partial`, the orchestrator should:

- Attach result evidence to the task node.
- Route failure data to the Debug Agent.
- Generate a repair task or retry package.
- Avoid repeating the same prompt without new diagnosis.

Retry limits should be defined per task type and risk level.
