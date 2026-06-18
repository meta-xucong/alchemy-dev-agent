# Long-Running Roadmap

Objective: Implement V2.5 plan-to-execution handoff runtime for document-driven task graphs.

## Phase 1: Runtime Handoff Contract

- Convert `ProjectBrief`, `ContextBundle`, and generated `TaskGraph` into a `RuntimeState`.
- Preserve repository metadata, blockers, objective, task graph, and done criteria.
- Avoid creating a second runtime state model.

## Phase 2: Worker Package Preparation

- Build `CodexWorkerInput` packages from generated task nodes.
- Include objective, task description, acceptance criteria, repository path, agent context, relevant files, commands, and constraints.
- Support deterministic inspection before task execution.

## Phase 3: Dry-Run Execution Bridge

- Run document-driven generated graphs through the existing `Orchestrator` in dry-run mode.
- Persist state to `.alchemy/state.json`.
- Verify DONE gate behavior with generated graph tasks and GitHub dry-run evidence.

## Phase 4: Documentation And Verification

- Add V2.5 handoff documentation.
- Update README, V2 plan, and audit docs.
- Add tests for handoff state, worker packages, and dry-run execution.
- Run full verification, commit, push, and notify.
