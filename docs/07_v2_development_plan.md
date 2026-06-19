# V2 Development Plan

## Purpose

Alchemy Dev Agent v2 is a document-driven autonomous development system.

The primary workflow is not a one-line prompt. The primary workflow is:

1. The user provides a detailed development document.
2. The user uploads supporting files such as API specs, database schemas, design notes, test plans, or reference code.
3. The user optionally provides a public GitHub repository URL; private repositories remain an explicit authenticated extension path.
4. The system builds a structured project brief and context bundle.
5. The multi-agent runtime converts that context into a task graph, executes tasks, tests changes, reviews evidence, and stops only when the delivery gate passes.

One-line objective expansion remains supported as a fallback path, but it is secondary. Its output must be converted into the same `ProjectBrief` contract before planning begins.

## Current Baseline

The repository currently contains:

- A complete v1 specification layer for agents, task graphs, Codex worker execution, evaluation, and execution loop.
- A CLI runtime prototype with deterministic dry-run defaults.
- Runtime modules for orchestration, task graph scheduling, agent routing, Codex worker execution, evaluation, state persistence, and GitHub execution evidence.
- A v2.1 intake runtime for local ProjectBrief generation from documents, attachments, and GitHub URL metadata.
- A v2.2 repository context runtime for local repository indexing and test profile detection.
- A v2.3 public GitHub source runtime for clone, fetch, and deterministic branch checkout.
- A v2.4 document-to-plan runtime for deterministic requirement extraction, traceability, and task graph generation.
- A v2.5 plan-to-execution handoff runtime for RuntimeState creation, worker package generation, and orchestrator dry-run execution.
- A v2.6 document-driven dry-run CLI that emits a complete integration report.
- A v2.7 real execution preflight layer and configurable document-run adapters.
- A v2.8 local API/project service runtime for project intake, planning, execution runs, event retrieval, and delivery summaries.
- A v2.9 browser console, multipart upload path, async run job records, and persisted run controls/events.
- A v2.10 task-boundary pause/stop hook and optional private GitHub CLI auth preflight.
- A v2.11 private GitHub source adapter using local `gh` authentication.
- A v2.12 local acceptance harness for document intake, planning, async execution, events, and delivery reports.
- A v2.13 real environment validation report for local tool readiness.
- A v2.14 standalone Codex CLI integration path for real worker execution.
- A v2.15 real Codex worker hardening layer with allowed-file enforcement.
- A v2.16 isolated real-run worktree lifecycle.
- A v2.17 recovery controller for resumable worker execution.
- A v2.18 controlled real GitHub delivery validation harness and CI workflow.
- A v2.19 representative real worker probe for bounded document-driven execution.
- V2.20 and V2.21 acceptance closure and post-acceptance quality gate hardening.
- A V2.22 supplemental plan for external docs-only repository delivery closure.
- Tests that protect the runtime contract.

V2 must continue extending this baseline with deeper document parsing, richer UI/API observability, representative real GitHub delivery validation, external docs-only delivery closure, and safer live execution controls. It must not bypass the existing task graph, worker, state, and evaluation contracts.

## V2 Objective

Build a system that can accept a complete project package and drive implementation through an agent cluster.

The system must be able to:

- Ingest a development document and multiple supporting files.
- Inspect a linked public GitHub repository.
- Treat private repository access as an optional path that requires local `gh` authentication.
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
  - clone or fetch public repository
  - check local gh authentication only when private repository mode is explicitly selected
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

These are current and planned implementation module boundaries. Most modules below now have a deterministic local implementation; production-grade UI, streaming, hard worker cancellation, and representative external delivery validation remain future work.

```text
intake/
  project_brief.py          Normalize user objective, documents, attachments, and repository references.
  document_loader.py        Load and classify uploaded files.
  attachment_indexer.py     Hash, catalog, and summarize supporting files.
  github_source.py          Normalize GitHub repository metadata.
  github_runtime.py         Clone, fetch, and checkout public GitHub repositories.
  gh_auth.py                Check local GitHub CLI authentication and account state for optional private repositories.
  private_github_runtime.py Clone, fetch, and checkout private GitHub repositories through local `gh` authentication.

context/
  repository_indexer.py     Build file tree, language, package, test, and CI metadata.
  builder.py                Create the ContextBundle contract.
  requirement_extractor.py  Extract requirements, acceptance criteria, and traceability links.

planner/
  task_graph_builder.py     Build task graph nodes using the existing task graph schema.

runtime/
  control.py                Task-boundary execution controls.
  handoff.py                Convert ProjectBrief, ContextBundle, and TaskGraph into RuntimeState and worker packages.
  orchestrator.py           Execute task graphs through worker, retry, evaluation, and delivery gates.
  recovery.py               Resume paused, stopped, failed, or blocked runs from persisted state.

autodev/
  acceptance_run.py         Run local end-to-end acceptance checks and write an acceptance report.
  document_run.py           Run document-driven intake, context, planning, handoff, and dry-run execution.
  preflight.py              Check local readiness for real Codex and GitHub execution.
  real_delivery_validation.py
                            Validate real GitHub branch, PR, and CI evidence collection.

server/
  api.py                    Project, file upload, GitHub inspect, plan, run, and state endpoints.
  project_service.py        Project metadata, context bundles, task graphs, run records, and delivery summaries.
  jobs.py                   Async run job status, persisted controls, and event records.
  static/                   Browser console for project creation, upload, planning, execution, and delivery review.

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

- Public GitHub repository inspection as the default path.
- Public repository clone, fetch, and branch checkout without requiring `gh` authentication.
- Private GitHub repository inspection as an optional authenticated extension through local GitHub CLI authentication.
- Branch selection.
- Commit, branch, pull request, and CI evidence collection.
- Clear blocker reporting when public clone/fetch fails or when optional private access is requested but `gh` is missing, unauthenticated, or lacks access.

The system must not store GitHub tokens. Authentication is delegated to the local `gh` installation and its credential store.

## UI Requirements Summary

The v2 product surface must support:

- Multi-file upload.
- Primary development document selection.
- File role classification.
- GitHub repository URL input.
- Branch or tag input.
- Public repository source status.
- Optional `gh auth status` visibility when private repository mode is enabled.
- Repository inspection results.
- Parsed requirement review before execution.
- Task graph preview before execution.
- Live execution event stream.
- Final delivery evidence review.

The current browser console covers the document-driven workflow at an operational level. Richer graph visualization, delivery evidence screens, and true live streaming remain product-hardening work.

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

- Implement project creation. Status: partial, available as local ProjectBrief generation.
- Implement multi-file cataloging. Status: done for local files.
- Implement document role classification. Status: done with deterministic filename and extension rules.
- Implement `ProjectBrief` generation. Status: done.
- Add schema validation tests. Status: done.

### V2.2: GitHub Context Runtime

- Implement GitHub URL parsing. Status: done in V2.1.
- Implement local repository indexing. Status: done in V2.2.
- Implement test profile detection. Status: done in V2.2.
- Implement blockers for missing local repository paths. Status: done in V2.2.
- Implement `gh auth status` checks. Status: done in V2.10.
- Implement public/private clone or fetch. Status: public path done in V2.3; private path done in V2.11.
- Add blocker handling for missing remote access. Status: done.

### V2.3: Public GitHub Source Runtime

- Implement public GitHub clone. Status: done.
- Implement public GitHub fetch for existing checkouts. Status: done.
- Implement deterministic branch checkout. Status: done.
- Make public repository visibility the default ProjectBrief and CLI behavior. Status: done.
- Return explicit blockers for private repository requests. Status: done.
- Add tests for clone, fetch, and private optional blocker behavior. Status: done.

### V2.4: Context And Planning Runtime

- Implement `ContextBundle` generation. Status: done for deterministic local documents and repository evidence.
- Implement requirement extraction and traceability. Status: done.
- Implement task graph generation from context bundle. Status: done.
- Add tests for requirement-to-task mapping. Status: done.

### V2.5: Plan-To-Execution Handoff Runtime

- Convert generated task graphs into `RuntimeState`. Status: done.
- Build `CodexWorkerInput` packages from document-driven task nodes. Status: done.
- Append release evidence task when needed for the existing DONE gate. Status: done.
- Run generated document-driven graphs through orchestrator dry-run execution. Status: done.
- Add tests for state handoff, worker package generation, and dry-run DONE. Status: done.

### V2.6: Document-Driven Dry-Run CLI

- Implement one local command for document-driven dry-run execution. Status: done.
- Emit ProjectBrief, ContextBundle, TaskGraph, worker packages, RuntimeState, and final status. Status: done.
- Persist `document_run_report.json` and runtime `state.json`. Status: done.
- Add CLI and pipeline tests. Status: done.

### V2.7: Real Execution Preflight And Adapter Configuration

- Add document-run flags for real Codex and real GitHub execution. Status: done.
- Add preflight checks for repository path, git, Codex executable, and gh. Status: done.
- Block real execution before worker tasks when required local tools are missing. Status: done.
- Add optional public repository preparation from GitHub URL. Status: done.
- Add preflight and document-run report tests. Status: done.

### V2.8: UI And API Runtime

- Implement project intake API. Status: done for local JSON API.
- Implement upload and repository inspection API. Status: done for local JSON API, multipart browser upload, public source preparation, and optional private source preparation through local `gh`.
- Implement task graph preview API. Status: done.
- Implement execution event stream. Status: partial; persisted async events are available, live SSE/WebSocket streaming is pending.
- Implement UI screens for the document-driven flow. Status: partial; one operational browser console covers the flow, richer graph and delivery views remain pending.

### V2.9: Browser UI And Async Execution Runtime

- Implement browser screens for project create, file intake, GitHub source, intake review, task graph preview, execution monitor, and delivery review. Status: partial; one local operational console covers the full flow, richer graph visualization remains pending.
- Implement real multipart upload into per-project storage. Status: done.
- Implement asynchronous run control with pause, resume, stop, and live events. Status: partial; background run jobs, persisted controls, and event retrieval are done; hard worker cancellation and true live streaming remain pending.
- Keep the current local API contract as the backend interface. Status: done.

### V2.10: Task-Boundary Cancellation And Private GitHub Runtime

- Implement safe task-boundary pause before dispatching each worker task. Status: done.
- Implement stop behavior that prevents further task dispatch and records a blocked delivery state. Status: done.
- Implement safe cancellation for real Codex subprocesses where possible. Status: pending.
- Implement optional private GitHub source retrieval through local `gh` authentication. Status: done for source preparation; end-to-end private delivery remains pending.

### V2.11: Private GitHub Source Adapter

- Implement private repository clone through `gh repo clone`. Status: done.
- Implement private repository fetch/checkout for existing checkouts. Status: done.
- Integrate private preparation into document-run and API inspect. Status: done.
- Add deterministic fake-runner tests. Status: done.

### V2.12: Local Acceptance Harness

- Exercise local fixture project creation, intake, planning, async execution, event retrieval, and delivery report generation. Status: done.
- Persist `acceptance_report.json`. Status: done.
- Use deterministic dry-run mode as the final local gate before external validation. Status: done.

### V2.13: Real Environment Validation

- Check local `git`, `gh`, `gh auth status`, and Codex CLI readiness. Status: done.
- Emit a machine-readable real environment readiness report. Status: done.
- Identify WindowsApps Codex launch failure and explicit standalone CLI workaround. Status: done.

### V2.14: Standalone Codex CLI API Integration

- Install and verify a standalone Codex CLI path outside the WindowsApps desktop package. Status: done.
- Add configurable `codex_executable` support to CLI/API real runs. Status: done.
- Verify a real Codex worker smoke through the runtime adapter. Status: done.

### V2.15: Real Codex Worker Hardening

- Persist allowed-file boundaries in worker packages. Status: done.
- Enforce dirty-diff auditing before and after real worker execution. Status: done.
- Roll back out-of-scope changes and timeout-local changes. Status: done.
- Verify a real Codex boundary smoke. Status: done.

### V2.16: Isolated Real-Run Worktree Lifecycle

- Create isolated git worktrees for real Codex document runs by default. Status: done.
- Rebuild context, graph, state, and worker packages against the worktree. Status: done.
- Expose API/UI controls for real Codex, real GitHub, worktree isolation, and retained worktrees. Status: done.
- Verify a real Codex isolated worktree smoke. Status: done.

### V2.17: Resumable Worker Execution

- Resume from persisted `run.json`, `document_run_report.json`, or `state.json`. Status: done.
- Reset active, retryable failed, and retryable blocked tasks. Status: done.
- Clear operator stop blockers and record recovery checkpoints. Status: done.
- Add CLI/API/UI resume wiring. Status: done.
- Verify dry-run recovery and bounded real Codex recovery. Status: done.

### V2.18: Real Delivery Validation

- Add a minimal GitHub Actions CI workflow. Status: done.
- Make `GitHubFlow` create or reuse PRs idempotently. Status: done.
- Collect PR check evidence and normalize CI state. Status: done.
- Add a controlled real delivery validation harness. Status: done.
- Run the harness against the public repository and record results. Status: done.

### V2.19: End-To-End Autonomous Delivery Runtime

- Run against a representative real repository with a detailed development document. Status: partially done through a bounded representative documentation probe.
- Execute real Codex worker tasks through document-driven graph execution. Status: done for bounded representative tasks.
- Run tests and collect CI evidence. Status: done for repository CI validation; still pending for arbitrary external docs-only product repositories.
- Open or update a GitHub pull request. Status: done in validation harness; external docs-only product delivery exposed V2.22 gaps.
- Produce a final delivery report. Status: done for internal representative runs; external docs-only product reports need richer evidence.

### V2.20: Delivery Stabilization And Acceptance Closure

- Run final local acceptance, unit tests, JSON parsing, diff hygiene, state validation, and GitHub Actions checks. Status: done.
- Mark the previous long-running objective acceptance-ready. Status: done.

### V2.21: Post-Acceptance Quality Gate Hardening

- Block real GitHub delivery when CI is failed, pending, or unknown and CI collection is enabled. Status: done.
- Add explicit CI collection controls and no-CI opt-out behavior. Status: done.
- Harden static verification and async job persistence. Status: done.

### V2.22: External Docs-Only Repository Delivery Closure

- Prevent parsed document-driven briefs from being downgraded to generated one-line fallback. Status: done.
- Improve Chinese and outline-style technical requirement extraction. Status: done.
- Preserve product scaffold and module structure for empty docs-only repositories. Status: done.
- Group complete docs-only web game scaffold delivery into one implementation task to avoid slow serial worker chains. Status: done.
- Add deterministic static artifact verification for HTML/canvas outputs. Status: done.
- Make real GitHub delivery create the final branch, commit, and PR with explicit no-CI waiver evidence when selected. Status: done.
- Add a representative external docs-only acceptance scenario. Status: done in `examples/external_docs_only_delivery_acceptance.md` and `autodev.external_docs_only_acceptance`.
- Run a real public target delivery against `meta-xucong/-super-mario-test`. Status: done via PR `https://github.com/meta-xucong/-super-mario-test/pull/2`.

### V2.23: Perfect Delivery Optimization

- Convert manual browser smoke verification into a first-class runtime artifact verifier. Status: partial but executable; `artifact_report` can import screenshots or run `--auto-browser-verify` through the browser artifact runner when Playwright is available.
- Add artifact profiles for `canvas_game`, `static_web_app`, `node_project`, `python_project`, and `documentation_only`. Status: done.
- Add managed worker process lifecycle with PID tracking, timeout cleanup, and stale-worker recovery. Status: core runtime implemented; UI surfacing and real-environment preflight polish remain.
- Add a requirement coverage matrix that maps each requirement to files, tests, browser evidence, and PR evidence. Status: done for runtime report and evaluator hard-gate integration.
- Add optional generated CI workflows for docs-only static app repositories. Status: implemented for static web/canvas artifacts; the release task now generates the workflow before GitHub commit/PR execution when real GitHub CI collection is enabled and no workflow exists.
- Productize final delivery reports with screenshots, PR, commit, CI/no-CI status, blockers, and retry guidance. Status: `delivery_report` summary implemented and exposed through document-run output and API delivery output.
- Polish the browser console for multi-file upload, GitHub link intake, graph preview, live execution, and final evidence review. Status: partial; delivery evidence summary, auto browser verification toggle, and generated static CI toggle are exposed, broader graph/coverage UX remains.

### V2.24: Development Cycle Brain

- Convert the manual long-running engineering SOP into a machine-checkable `development_cycle` report. Status: implemented for document-run reports and API delivery output.
- Track evidence for document reading, central-brain refinement, phase planning, implementation, audit, testing, iteration, full review, simulated acceptance, real delivery, and merge/waiver. Status: implemented.
- Add explicit auto-merge support for trusted real GitHub runs after passing CI. Status: implemented and off by default.
- Run a new external docs-only repository test to compare against the earlier `meta-xucong/-super-mario-test` run. Status: pending.

### V2.25: Playability Feedback Loop

- Convert manual game-play feedback into a semantic browser probe for generated canvas games. Status: implemented for movement, jump, victory, restart, and missing-hook failure.
- Require generated canvas games to expose `window.__ALCHEMY_GAME_TEST__` with `snapshot()`, `step(dt)`, `advanceToVictory()`, and `restart()`. Status: implemented in worker prompt, static artifact verifier, and generated static CI fallback.
- Surface gameplay probe evidence in `artifact_report`, `delivery_report`, `requirement_coverage`, `development_cycle`, and the browser console delivery summary. Status: implemented.
- Treat canvas-game delivery as incomplete when gameplay probe evidence is missing or failed. Status: implemented in browser verification and development-cycle testing.
- Generalize semantic probes to non-game apps and turn structured user feedback into requirement deltas/debug tasks. Status: planned.

## Risks And Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Development documents are long or contradictory. | Planner may create wrong tasks. | Build requirement traceability and reviewer gate before execution. |
| Supporting files use mixed formats. | Context bundle may miss important constraints. | Keep file role metadata and parse confidence in the context bundle. |
| Public repository clone or fetch fails. | Execution cannot inspect source. | Record git command output as a hard source blocker before planning. |
| Private repository access is requested. | Execution cannot inspect source through the public path. | Use local `gh auth status` in a later optional adapter and report an explicit blocker until implemented. |
| One-line fallback creates weak specs. | The system may over-assume. | Mark generated requirements as low-confidence and require acceptance review. |
| Runtime drifts from documents. | Agents follow stale contracts. | Keep schemas and tests as contract checks. |
| UI starts execution before review. | Wrong plan may mutate code. | Require intake review and task graph preview before live execution. |

## Implementation Readiness Criteria

The v2 plan is ready for implementation when:

- `ProjectBrief` schema exists and covers objective, documents, attachments, repository, constraints, and acceptance criteria.
- `ContextBundle` schema exists and covers document index, repository map, requirement map, test profile, risks, and blockers.
- UI/API requirements define the project intake flow.
- Public GitHub repository behavior is implemented and covered by tests.
- Private GitHub repository behavior is specified as an optional local `gh` authentication path.
- The document-driven example shows how inputs become task graph execution.
- The plan clearly separates current runtime capabilities from planned v2 implementation.
