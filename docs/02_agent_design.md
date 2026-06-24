# Agent Design

## Agent Contract

Every agent receives structured input and returns structured output. Agents do not directly mutate persistent state. The orchestrator validates agent output, records it, and decides the next action.

Common input fields:

- `objective`
- `requirements`
- `repository_context`
- `current_state`
- `task_graph`
- `assigned_task`
- `constraints`
- `evidence`

Common output fields:

- `status`
- `summary`
- `recommendations`
- `task_updates`
- `evidence`
- `blockers`
- `confidence`

## Architect Agent

### Responsibilities

- Convert the user objective and requirements into an executable task graph.
- Define task dependencies.
- Identify system boundaries and major components.
- Split work into tasks that can be assigned to specialized agents.
- Update the graph when requirements change or blockers appear.
- Define done criteria for the overall objective and for major task groups.

### Input

- User objective.
- Requirements document.
- Repository structure.
- Existing state.
- Known constraints.
- Prior execution evidence.

### Output

- Task graph.
- Dependency model.
- Task type classification.
- Agent assignment recommendation.
- System-level risks.
- Done criteria.

### Forbidden Behavior

- Must not directly write application code.
- Must not mark tasks complete.
- Must not ignore existing repository constraints.
- Must not create vague tasks without completion criteria.

## Backend Agent

### Responsibilities

- Interpret backend tasks from the task graph.
- Define backend implementation scope.
- Specify data models, API contracts, service boundaries, migrations, and server-side tests.
- Prepare precise worker instructions for backend implementation.
- Review backend worker output for task-level correctness.

### Input

- Assigned backend task.
- API requirements.
- Database requirements.
- Backend repository context.
- Relevant task dependencies.
- Existing test evidence.

### Output

- Backend implementation plan.
- Codex worker task prompt.
- Expected files or modules to inspect.
- Test commands to run.
- Backend completion evidence.
- Follow-up tasks if scope gaps remain.

### Forbidden Behavior

- Must not modify frontend scope unless explicitly assigned.
- Must not approve work without test or inspection evidence.
- Must not introduce architecture that conflicts with Architect Agent constraints.
- Must not broaden the task beyond its graph node without orchestrator approval.

## Frontend Agent

### Responsibilities

- Interpret frontend tasks from the task graph.
- Define UI, client-state, routing, accessibility, and interaction requirements.
- Prepare precise worker instructions for frontend implementation.
- Validate frontend output against user-facing acceptance criteria.
- Request visual or browser verification when needed.

### Input

- Assigned frontend task.
- Product requirements.
- Design constraints.
- Frontend repository context.
- API contracts.
- Relevant task dependencies.

### Output

- Frontend implementation plan.
- Codex worker task prompt.
- UI acceptance criteria.
- Test or verification commands.
- Browser verification requirements.
- Follow-up tasks if UX gaps remain.

### Forbidden Behavior

- Must not invent product requirements not supported by the objective.
- Must not accept UI work without checking responsive and interaction requirements when applicable.
- Must not change backend contracts without coordination.
- Must not mark visual quality complete from code inspection alone when runtime verification is required.

## Test Agent

### Responsibilities

- Define the verification strategy for the task graph.
- Map requirements to test cases.
- Identify required unit, integration, end-to-end, static analysis, and manual checks.
- Evaluate test results from Codex workers and CI.
- Identify missing test coverage.

### Input

- Objective.
- Requirements.
- Task graph.
- Repository test tooling.
- Worker command output.
- CI results.
- Known risks.

### Output

- Test plan.
- Required commands.
- Coverage expectations.
- Test result assessment.
- Missing verification items.
- Recommended retry or repair tasks.

### Forbidden Behavior

- Must not treat passing existing tests as sufficient by default.
- Must not waive required verification without an explicit reason.
- Must not modify implementation scope.
- Must not approve final delivery alone.

## Debug Agent

### Responsibilities

- Diagnose failed tasks, failed tests, CI errors, runtime errors, and review failures.
- Classify failure cause.
- Propose minimal repair actions.
- Generate debugging instructions for Codex workers.
- Recommend graph updates when the failure reveals missing tasks.

### Input

- Failed task.
- Error logs.
- Test output.
- CI output.
- Recent changes.
- Repository context.
- Retry history.

### Output

- Failure diagnosis.
- Repair plan.
- Codex worker debugging prompt.
- Risk assessment.
- Retry recommendation.
- Blocker classification if repair is not possible.

### Forbidden Behavior

- Must not repeatedly retry the same repair without new evidence.
- Must not hide failures by reducing tests or weakening acceptance criteria.
- Must not mark a task complete after a partial fix.
- Must not bypass reviewer or evaluation gates.

## Reviewer Agent

### Responsibilities

- Evaluate completed work against the objective, requirements, and done criteria.
- Inspect task evidence, code changes, test results, and CI status.
- Identify requirement gaps, quality risks, and integration issues.
- Produce approval, rejection, or conditional approval.
- Contribute to the final gate score.

### Input

- Objective.
- Requirements.
- Final task graph state.
- Completed task evidence.
- Git diff or PR summary.
- Test and CI results.
- Known issues and blockers.

### Output

- Review decision.
- Spec alignment assessment.
- Quality risks.
- Required changes.
- Final gate score contribution.
- Approval evidence.

### Forbidden Behavior

- Must not approve based only on implementation summaries.
- Must not ignore unresolved failed tasks.
- Must not approve if done criteria are unmet.
- Must not lower standards to terminate a long-running loop.

## Central Review Agent

The Central Review Agent is an orchestrator-level decision agent. It is not one of the normal
task-graph implementation workers.

### Responsibilities

- Read project status, task graph state, delivery evidence, requirement coverage, artifact reports,
  development-cycle evidence, reviewer output, and blockers.
- Map the run to the human development loop: read documents, refine plan, execute, audit, test,
  iterate, full review, and handoff.
- Produce one next decision: `continue`, `handoff`, `iterate`, `blocked`, or `wait_for_input`.
- Produce beginner-readable summary text.
- When iteration is needed, provide evidence gaps that can become a repair plan.

### Input

- Objective and source mode.
- Central runtime state.
- Delivery report.
- Evaluation result.
- Requirement coverage.
- Artifact and browser probe evidence.
- Development-cycle report.
- Blockers, known issues, and next actions.

### Output

- Central review status.
- Next decision.
- Confidence.
- Completed and missing loop steps.
- Human-readable summary.
- Next actions.
- Human-help flag.

### Forbidden Behavior

- Must not edit code or run shell commands.
- Must not replace the Reviewer Agent's quality judgment.
- Must not mark a run delivered when hard fail conditions exist.
- Must not create an auto-iteration repair plan without traceable evidence gaps.
- Must not trigger mutating GitHub operations without the configured delivery policy.

## Agent Handoff Rules

- Architect Agent creates or revises the graph.
- Implementation agents produce worker-ready task instructions.
- Codex worker executes implementation tasks.
- Test Agent evaluates verification evidence.
- Debug Agent handles failures and creates repair prompts.
- Reviewer Agent performs final approval.
- Central Review Agent turns all run evidence into a handoff, iterate, continue, blocked, or wait-for-input decision.
- Orchestrator owns state updates and final termination.
