# alchemy-dev-agent

`alchemy-dev-agent` is a specification repository and prototype runtime for an autonomous software development agent system.

Its purpose is to define the architecture, protocols, state model, task graph model, worker contract, GitHub execution flow, retry loop, and evaluation gates required to build a multi-agent autonomous development system. The included `runtime/` package is a usable CLI runtime with deterministic dry-run defaults and opt-in real Codex/GitHub adapters.

## Goal

The system is designed primarily for workflows where a user provides a complete project package:

- A development objective, such as a feature, product, system, or migration.
- A detailed development document, requirements brief, or acceptance specification.
- Supporting files such as API specs, database schemas, design notes, test plans, logs, or reference material.
- An optional public GitHub repository link, with private repositories treated as an explicit future/authenticated path.

The autonomous development system should then:

- Normalize the uploaded material into a project brief and context bundle.
- Decompose the objective into a dependency-aware task graph.
- Assign tasks to specialized agents.
- Use Codex CLI as an execution worker.
- Write code, run tests, fix failures, and report artifacts.
- Evaluate completion against explicit delivery criteria.
- Stop only after the system reaches delivery quality.

## Foundation

The design assumes three major implementation foundations:

- **OpenAI Agent SDK** for orchestration, agent roles, tool routing, and structured reasoning.
- **Codex CLI worker model** for isolated code execution, test execution, debugging, and patch generation.
- **GitHub-based execution loop** for repository synchronization, branch management, pull requests, CI checks, and review history.

## Core Model

The system is centered on:

- **Multi-agent planning and execution**: architecture, implementation, testing, debugging, and review are separate responsibilities.
- **Task graph execution**: work is represented as nodes with dependencies, status, ownership, and completion criteria.
- **Evaluation gate**: test success alone is insufficient; completion requires spec alignment, reviewer approval, and a final gate score of at least `0.85`.

## Repository Map

```text
docs/
  00_overview.md             System motivation and operating context.
  01_architecture.md         Layered architecture and component contracts.
  02_agent_design.md         Agent roles, inputs, outputs, and boundaries.
  03_task_graph.md           Task graph model and execution rules.
  04_codex_worker.md         Codex CLI worker contract.
  05_evaluation_system.md    Completion criteria and scoring.
  06_execution_loop.md       End-to-end execution loop.
  07_v2_development_plan.md  Document-driven v2 development plan.
  08_intake_and_context.md   Project intake and context bundle contract.
  09_ui_and_api_requirements.md
                              Planned v2 UI/API workflow and endpoints.
  10_v2_alignment_audit.md   V2 readiness and gap audit.
  11_v2_repository_context_runtime.md
                              V2.2 local repository context runtime.
  12_v2_public_github_source_runtime.md
                              V2.3 public GitHub clone/fetch runtime.
  13_v2_document_to_plan_runtime.md
                              V2.4 requirement extraction and task planning runtime.
  14_v2_plan_to_execution_handoff.md
                              V2.5 runtime handoff and worker package bridge.
  15_v2_document_run_cli.md
                              V2.6 document-driven dry-run CLI.
  16_v2_real_execution_preflight.md
                              V2.7 real execution flags and preflight checks.
  17_v2_local_api_runtime.md  V2.8 local JSON API and project service runtime.

specs/
  project_brief_schema.json  Document-driven intake schema.
  context_bundle_schema.json Planner-ready context bundle schema.
  state_schema_v2.json       Persistent project state schema.
  task_graph_schema.json     Task graph schema.

examples/
  full_autodev_example.md    Example autonomous development run.
  document_driven_project_example.md
                              Example with documents, attachments, and GitHub repository input.

runtime/
  orchestrator.py            Runtime entry point and control loop coordinator.
  task_graph_engine.py       Dependency resolution and graph status updates.
  agent_router.py            Task-to-agent mapping.
  codex_worker.py            Dry-run and real Codex subprocess worker adapter.
  evaluator.py               DONE gate scoring.
  github_flow.py             Dry-run and real git/gh execution flow adapter.
  handoff.py                 ProjectBrief/ContextBundle/TaskGraph to RuntimeState bridge.
  state_manager.py           JSON state persistence.
  run_loop.py                CLI loop entry point.

intake/
  project_brief.py           V2.1 ProjectBrief builder and CLI.
  document_loader.py         Local file cataloging, hashing, summaries, and role inference.
  github_source.py           GitHub URL parsing and source normalization.
  github_runtime.py          Public GitHub clone/fetch/checkout source runtime.
  schema_validation.py       Local contract validation for intake payloads.

context/
  builder.py                 ContextBundle builder.
  repository_indexer.py      Local repository indexing and test profile detection.
  requirement_extractor.py   Deterministic requirement extraction and traceability.

planner/
  task_graph_builder.py      ContextBundle-to-task-graph planning.

autodev/
  document_run.py            Document-driven end-to-end dry-run CLI.
  preflight.py               Real execution environment preflight checks.
  demo_run.py                One-line local app generation demo.
  agents.py                  Deterministic local agent cluster for demo delivery.
  game_generator.py          Original retro platformer artifact generator.

server/
  project_service.py         Persistent project service for intake, planning, runs, and delivery reports.
  api.py                     Standard-library local JSON API server.

tests/
  test_runtime.py            Unit and smoke tests for the runtime contract.
  test_intake.py             Unit and CLI tests for v2.1 intake.
  test_autodev_pipeline.py   End-to-end local demo generation tests.
  test_repository_context.py Repository context runtime tests.
  test_document_to_plan.py   Requirement extraction and task graph planning tests.
  test_runtime_handoff.py    Plan-to-execution handoff tests.
  test_document_run_pipeline.py
                              Document-driven dry-run CLI tests.
  test_execution_preflight.py
                              Real execution preflight tests.
  test_api_server.py         Local API and project service tests.
```

## Runtime

The runtime is intentionally standard-library only. By default it runs in deterministic dry-run mode so local tests and smoke runs do not require credentials or mutate remotes.

Implemented runtime capabilities:

- Dependency-aware task graph scheduling.
- Task-to-agent routing.
- Bounded Codex worker task packages.
- Real Codex subprocess adapter with structured JSON parsing.
- Deterministic dry-run worker for tests and demos.
- Retry/debug loop with generated debug tasks.
- Weighted evaluation gate across test health, spec alignment, graph completion, reviewer approval, and risk quality.
- GitHub execution evidence through dry-run records or real `git`/`gh` commands.
- Persistent JSON runtime state under `.alchemy/state.json`.

DONE requires final gate score `>= 0.85`, completed required graph nodes, passing verification evidence, reviewer approval, no hard failures, and GitHub execution evidence.

## V2.1 Intake

The v2.1 intake runtime can generate a schema-compatible `ProjectBrief` from local development documents, supporting files, and optional GitHub repository metadata.

Implemented intake capabilities:

- Document-driven and one-line fallback modes.
- Local file cataloging with deterministic file IDs and SHA-256 content hashes.
- File role inference for primary requirements, API specs, database schemas, design notes, test plans, reference code, data samples, and supplemental files.
- Explicit blockers for missing primary documents, unreadable files, unsupported required files, missing objectives, and invalid GitHub URLs.
- GitHub URL parsing for HTTPS and SSH repository URLs without network access.
- Public repository metadata by default, with optional private metadata flagging through `visibility=private` and `gh_auth_required=true`.
- ProjectBrief contract validation against `specs/project_brief_schema.json`.

Build a ProjectBrief:

```bash
python -m intake.project_brief \
  --objective "Add workspace support" \
  --document docs/workspace_feature_spec.md \
  --attachment docs/api_contract.yaml \
  --repository https://github.com/example/saas-dashboard \
  --validate
```

## Local One-Line Demo

The repository now includes a narrow local demo pipeline that exercises the v2 contracts end to end:

```text
one-line objective
  -> ProjectBrief
  -> ContextBundle
  -> TaskGraph
  -> deterministic local agent cluster
  -> generated local artifact
  -> static verification
  -> reviewer evidence
```

Generate an original retro platform game:

```bash
python -m autodev.demo_run \
  --objective "Build a small retro platform game" \
  --output .alchemy/generated/retro_platformer
```

The demo writes:

- `index.html`
- `autodev_report.json`

Important boundary: this is a deterministic local demo, not the full production autonomous development system. It proves the contract path and generated-artifact loop, but it does not yet use the Agent SDK, real Codex worker sessions, CI, or UI/API intake.

## V2.2 Repository Context

The repository context runtime can enrich a `ContextBundle` from a local repository checkout path.

Implemented repository context capabilities:

- File discovery with ignored directory filtering.
- File kind classification for source, test, docs, config, CI, assets, migrations, and unknown files.
- Language detection by file suffix.
- Package file detection.
- GitHub Actions and CI file detection.
- Package manager detection.
- Test, build, and lint command inference.
- ContextBundle population with repository map and test profile.
- Hard blockers for missing or invalid repository paths.

## V2.3 Public GitHub Source Runtime

The GitHub source runtime can prepare public repositories for intake without requiring `gh` login or stored tokens.

Implemented public source capabilities:

- Public GitHub repository clone into `RepositorySource.local_path`.
- Fetch and deterministic checkout for an existing local git checkout.
- Default repository visibility of `public` for ProjectBrief and CLI intake.
- Structured blockers for invalid repository paths, clone failures, fetch failures, and explicit private repository requests.
- CLI entry point for source preparation:

```bash
python -m intake.github_runtime \
  --repository https://github.com/example/saas-dashboard \
  --project-id proj_workspace_support \
  --target-branch main
```

Private repositories are still represented in the schema, but they are not the primary path. When `visibility=private` is selected, the current public source runtime returns an explicit blocker instead of attempting to collect tokens or silently falling back to unauthenticated clone.

## V2.4 Document-To-Plan Runtime

The document-to-plan runtime can turn parsed development documents and repository evidence into requirements and a task graph.

Implemented document-to-plan capabilities:

- Deterministic requirement extraction from structured Markdown, text, JSON, YAML, and YML inputs.
- Priority inference for `must`, `should`, and `could` requirements.
- Acceptance criteria extraction from document sections and explicit ProjectBrief criteria.
- Traceability from requirement to source document, related repository files, implementation task, verification task, and review task.
- Task graph generation with architecture, implementation, verification, and review nodes.
- Implementation task assignment to backend, frontend, test, documentation, or integration work based on requirement and repository-file signals.
- Preservation of the existing one-line generated-app demo graph.

## V2.5 Plan-To-Execution Handoff

The handoff runtime connects document-driven planning to the existing orchestrator loop.

Implemented handoff capabilities:

- Convert `ProjectBrief`, `ContextBundle`, and generated `TaskGraph` into `RuntimeState`.
- Preserve repository metadata, blockers, objective, task graph, and document-aware done criteria.
- Build `CodexWorkerInput` packages from generated task nodes.
- Include objective, assigned agent, upstream task IDs, acceptance criteria, related files, and verification commands in worker packages.
- Append a release task when needed so the existing DONE gate can record GitHub or dry-run delivery evidence.
- Run generated document-driven graphs through the `Orchestrator` dry-run loop to DONE.

## V2.6 Document-Driven Dry-Run CLI

The document-run CLI provides a single local command for the document-driven pipeline:

```bash
python -m autodev.document_run \
  --objective "Add workspace support" \
  --document workspace_feature_spec.md \
  --repository https://github.com/example/saas-dashboard \
  --repository-path .alchemy/projects/proj_workspace_support/repo \
  --output .alchemy/document_run
```

The command emits a JSON report containing ProjectBrief, ContextBundle, TaskGraph, worker packages, RuntimeState, and final dry-run status. It proves the contract path can execute end to end without requiring credentials or mutating a remote repository.

V2.7 adds controlled real-execution switches:

```bash
python -m autodev.document_run \
  --objective "Add workspace support" \
  --document workspace_feature_spec.md \
  --repository https://github.com/example/saas-dashboard \
  --repository-path .alchemy/projects/proj_workspace_support/repo \
  --real-codex \
  --real-github
```

The CLI records preflight checks for repository path, `git`, Codex, and `gh`. Missing required tools block real execution before worker tasks start.

## V2.8 Local API Runtime

The local API wraps the document-driven runtime with project persistence and HTTP endpoints:

```bash
python -m server.api --host 127.0.0.1 --port 8765 --storage-root .alchemy/server
```

Core implemented endpoints include:

```text
POST /projects
GET  /projects/{project_id}
POST /projects/{project_id}/files
GET  /projects/{project_id}/files
POST /projects/{project_id}/intake/build
GET  /projects/{project_id}/brief
GET  /projects/{project_id}/context
POST /projects/{project_id}/plan
GET  /projects/{project_id}/task-graph
POST /projects/{project_id}/runs
GET  /projects/{project_id}/runs/{run_id}
GET  /projects/{project_id}/runs/{run_id}/events
GET  /projects/{project_id}/delivery
```

The API accepts local file paths through `documents`, `attachments`, or a UI-oriented `files` list. Real browser upload, asynchronous run control, and UI screens remain planned next steps.

Run a smoke execution:

```bash
python -m runtime.run_loop --objective "build a todo app with login" --reset
```

Run with a real Codex worker:

```bash
python -m runtime.run_loop \
  --objective "implement the requested feature" \
  --project /path/to/repo \
  --real-codex
```

Run with real GitHub branch/commit/push/PR flow:

```bash
python -m runtime.run_loop \
  --objective "implement the requested feature" \
  --project /path/to/repo \
  --real-codex \
  --real-github
```

`--real-github` expects local `git` and `gh` authentication to be available. Without it, the runtime records dry-run branch, commit, PR, and CI evidence instead.

Run tests:

```bash
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests
```

## Non-Goals

This repository does not yet implement:

- Browser-based multi-file upload or full document parser pipeline.
- Private GitHub retrieval through `gh auth status`.
- Deep code summarization and semantic requirement-to-file mapping beyond deterministic file/path signals.
- Agent SDK runtime code.
- GitHub App integration.
- GitHub Actions log ingestion.
- Browser UI, production database, asynchronous worker daemon, or multi-user access control.

Those systems should be implemented against the protocols defined here.
