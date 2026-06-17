# V2 Development Plan

## Purpose

Alchemy Dev Agent v2 is a document-driven autonomous development system.

The primary workflow is not a one-line prompt. The primary workflow is:

1. The user provides a detailed development document.
2. The user uploads supporting files such as API specs, database schemas, design notes, test plans, or reference code.
3. The user optionally provides a GitHub repository URL, including private repositories accessible through local `gh` authentication.
4. The system builds a structured project brief and context bundle.
5. The multi-agent runtime converts that context into a task graph, executes tasks, tests changes, reviews evidence, and stops only when the delivery gate passes.

One-line objective expansion remains supported as a fallback path, but it is secondary. Its output must be converted into the same `ProjectBrief` contract before planning begins.

## Current Baseline

The repository currently contains:

- A complete v1 specification layer for agents, task graphs, Codex worker execution, evaluation, and execution loop.
- A CLI runtime prototype with deterministic dry-run defaults.
- Runtime modules for orchestration, task graph scheduling, agent routing, Codex worker execution, evaluation, state persistence, and GitHub execution evidence.
- Tests that protect the runtime contract.

V2 must extend this baseline with a formal intake and context layer. It must not bypass the existing task graph, worker, state, and evaluation contracts.

## V2 Objective

Build a system that can accept a complete project package and drive implementation through an agent cluster.

The system must be able to:

- Ingest a development document and multiple supporting files.
- Inspect a linked GitHub repository.
- Use `gh` login status for private repository access.
- Build a normalized project brief.
- Build a context bundle from documents and repository evidence.
- Map requirements to task graph nodes.
- Dispatch task nodes to specialized agents.
- Execute implementation through Codex worker sessions.
- Run tests and CI checks where available.
- Review completion against acceptance criteria.
- Produce a final delivery artifact such as a branch, pull request, report, or blocked-state explanation.

## Non-Goals For V2 Planning

This document does not implement the runtime code.

V2 planning must not introduce:

- A new agent taxonomy.
- A second task graph model.
- A second evaluator.
- A second worker protocol.
- A second state schema for active execution.

V2 adds intake, context construction, and product interface requirements around the existing execution contract.

## System Lifecycle

```text
User Inputs
  |
  v
Project Intake
  - objective
  - primary development document
  - supporting files
  - GitHub repository link
  - branch / issue / PR references
  |
  v
Source Retrieval
  - validate uploaded files
  - check local gh authentication
  - clone or fetch repository
  - record source metadata
  |
  v
Context Bundle Builder
  - parse documents
  - index repository
  - detect stack and test commands
  - extract requirements and acceptance criteria
  |
  v
Requirement Mapper
  - normalize requirements
  - link requirements to files and tests
  - identify blockers and assumptions
  |
  v
Task Graph Planning
  - create dependency-aware nodes
  - assign completion criteria
  - assign task types
  |
  v
Agent Dispatch
  - architect
  - backend
  - frontend
  - test
  - debug
  - reviewer
  |
  v
Codex Worker Execution
  - write code
  - run checks
  - fix failures
  - return structured worker results
  |
  v
Evaluation Gate
  - tests
  - spec alignment
  - reviewer approval
  - risk checks
  - GitHub evidence
  |
  v
Delivery
  - completed state
  - branch / PR / patch
  - execution report
  - remaining blockers if any
```

## Planned Module Boundaries

These are planned implementation modules for the next phase. They are contracts, not current files.

```text
intake/
  project_brief.py          Normalize user objective, documents, attachments, and repository references.
  document_loader.py        Load and classify uploaded files.
  attachment_indexer.py     Hash, catalog, and summarize supporting files.
  github_source.py          Clone, fetch, and inspect GitHub repositories.
  gh_auth.py                Check local GitHub CLI authentication and account state.

context/
  repository_indexer.py     Build file tree, language, package, test, and CI metadata.
  context_builder.py        Create the ContextBundle contract.
  requirement_mapper.py     Extract requirements, acceptance criteria, and traceability links.
  test_profile.py           Detect test commands, CI workflows, and verification gaps.

planner/
  document_planner.py       Convert ProjectBrief and ContextBundle into planning inputs.
  task_graph_builder.py     Build task graph nodes using the existing task graph schema.
  acceptance_mapper.py      Attach acceptance criteria to task completion criteria.

server/
  api.py                    Project, file upload, GitHub inspect, plan, run, and state endpoints.
  storage.py                Project files, metadata, context bundles, and run records.
  events.py                 Execution event stream for UI monitoring.

ui/
  project_create            Objective, document upload, GitHub URL, branch, and auth status.
  intake_review             Parsed requirements, assumptions, repository map, and blockers.
  task_graph                Graph view, task status, agent assignment, and retry state.
  execution_monitor         Logs, tests, worker outputs, and evaluation score.
  delivery_review           Final evidence, PR link, artifacts, and unresolved risks.
```

## Required Contracts

V2 introduces two new pre-execution contracts:

- `ProjectBrief`: normalized user intent, documents, attachments, repository source, constraints, and acceptance criteria.
- `ContextBundle`: parsed document evidence, repository index, requirement map, test profile, risk profile, and blockers.

The execution runtime remains based on:

- `TaskGraph`
- `WorkerTask`
- `WorkerResult`
- `State`
- `EvaluationResult`

V2 must follow this conversion path:

```text
ProjectBrief -> ContextBundle -> TaskGraph -> Runtime State -> EvaluationResult
```

No agent may consume raw uploaded files as its only source of truth after intake. Agents receive structured task packages that cite the relevant documents, repository files, and acceptance criteria.

## Agent Cluster Responsibilities

V2 keeps the existing agent roles:

- Architect Agent: converts requirements and repository evidence into technical plan and graph structure.
- Backend Agent: implements backend, data, API, service, and integration tasks.
- Frontend Agent: implements UI, client state, routes, accessibility, and interaction tasks.
- Test Agent: defines and runs verification commands.
- Debug Agent: fixes failed tasks and failed tests.
- Reviewer Agent: validates spec alignment, quality, risks, and delivery readiness.

The intake and context layers are system services, not new autonomous agent roles.

## GitHub Repository Support

The system must support:

- Public GitHub repository inspection.
- Private GitHub repository inspection through local GitHub CLI authentication.
- Branch selection.
- Commit, branch, pull request, and CI evidence collection.
- Clear blocker reporting when `gh` is missing, unauthenticated, lacks access, or cannot fetch the requested repository.

The system must not store GitHub tokens. Authentication is delegated to the local `gh` installation and its credential store.

## UI Requirements Summary

The v2 product surface must support:

- Multi-file upload.
- Primary development document selection.
- File role classification.
- GitHub repository URL input.
- Branch or tag input.
- `gh auth status` visibility.
- Repository inspection results.
- Parsed requirement review before execution.
- Task graph preview before execution.
- Live execution event stream.
- Final delivery evidence review.

The UI is a planned v2 implementation target. It is not part of the current v1 CLI runtime.

## One-Line Fallback

When the user provides only a sentence, the system may use a central reasoning model such as Claude or Codex to expand it into:

- Objective.
- Assumptions.
- Functional requirements.
- Non-functional requirements.
- Acceptance criteria.
- Suggested project structure.
- Initial task graph candidates.

The expanded result must be marked as `generated_from_one_liner=true` in the `ProjectBrief`. The planner must treat those requirements as lower-confidence than user-provided documents.

## Delivery Gate

V2 completion still uses the existing evaluation principle:

```text
test pass != done
```

DONE requires:

- Required task graph nodes are completed.
- Required tests or checks pass.
- Acceptance criteria from the development document are mapped and satisfied.
- Reviewer approval is present.
- Final gate score is at least `0.85`.
- GitHub execution evidence is recorded when a repository is linked.
- No unresolved hard blocker remains.

## V2 Milestones

### V2.0: Development Contract

- Add document-driven development plan.
- Add ProjectBrief and ContextBundle schemas.
- Add intake, UI/API, and GitHub retrieval requirements.
- Add document-driven example.
- Audit spec/runtime boundary.

### V2.1: Intake Runtime

- Implement project creation.
- Implement multi-file cataloging.
- Implement document role classification.
- Implement `ProjectBrief` generation.
- Add schema validation tests.

### V2.2: GitHub Context Runtime

- Implement GitHub URL parsing.
- Implement `gh auth status` checks.
- Implement public/private clone or fetch.
- Implement repository indexing.
- Add blocker handling for missing access.

### V2.3: Context And Planning Runtime

- Implement `ContextBundle` generation.
- Implement requirement extraction and traceability.
- Implement task graph generation from context bundle.
- Add tests for requirement-to-task mapping.

### V2.4: UI And API Runtime

- Implement project intake API.
- Implement upload and repository inspection API.
- Implement task graph preview API.
- Implement execution event stream.
- Implement UI screens for the document-driven flow.

### V2.5: End-To-End Delivery Runtime

- Run against a real repository with a real development document.
- Execute Codex worker tasks.
- Run tests and collect CI evidence.
- Open or update a GitHub pull request.
- Produce a final delivery report.

## Risks And Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Development documents are long or contradictory. | Planner may create wrong tasks. | Build requirement traceability and reviewer gate before execution. |
| Supporting files use mixed formats. | Context bundle may miss important constraints. | Keep file role metadata and parse confidence in the context bundle. |
| Private repository access fails. | Execution cannot inspect source. | Use local `gh auth status` and report an explicit blocker. |
| One-line fallback creates weak specs. | The system may over-assume. | Mark generated requirements as low-confidence and require acceptance review. |
| Runtime drifts from documents. | Agents follow stale contracts. | Keep schemas and tests as contract checks. |
| UI starts execution before review. | Wrong plan may mutate code. | Require intake review and task graph preview before live execution. |

## Implementation Readiness Criteria

The v2 plan is ready for implementation when:

- `ProjectBrief` schema exists and covers objective, documents, attachments, repository, constraints, and acceptance criteria.
- `ContextBundle` schema exists and covers document index, repository map, requirement map, test profile, risks, and blockers.
- UI/API requirements define the project intake flow.
- GitHub private repository behavior is specified through local `gh` authentication.
- The document-driven example shows how inputs become task graph execution.
- The plan clearly separates current runtime capabilities from planned v2 implementation.
