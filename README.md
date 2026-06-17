# alchemy-dev-agent

`alchemy-dev-agent` is a specification repository and prototype runtime for an autonomous software development agent system.

Its purpose is to define the architecture, protocols, state model, task graph model, worker contract, GitHub execution flow, retry loop, and evaluation gates required to build a multi-agent autonomous development system. The included `runtime/` package is a usable CLI runtime with deterministic dry-run defaults and opt-in real Codex/GitHub adapters.

## Goal

The system is designed primarily for workflows where a user provides a complete project package:

- A development objective, such as a feature, product, system, or migration.
- A detailed development document, requirements brief, or acceptance specification.
- Supporting files such as API specs, database schemas, design notes, test plans, logs, or reference material.
- An optional GitHub repository link, including private repositories available through local `gh` authentication.

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
  state_manager.py           JSON state persistence.
  run_loop.py                CLI loop entry point.

intake/
  project_brief.py           V2.1 ProjectBrief builder and CLI.
  document_loader.py         Local file cataloging, hashing, summaries, and role inference.
  github_source.py           GitHub URL parsing and source normalization.
  schema_validation.py       Local contract validation for intake payloads.

tests/
  test_runtime.py            Unit and smoke tests for the runtime contract.
  test_intake.py             Unit and CLI tests for v2.1 intake.
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
- Private repository metadata flagging through `visibility=private` and `gh_auth_required=true`.
- ProjectBrief contract validation against `specs/project_brief_schema.json`.

Build a ProjectBrief:

```bash
python -m intake.project_brief \
  --objective "Add workspace support" \
  --document docs/workspace_feature_spec.md \
  --attachment docs/api_contract.yaml \
  --repository https://github.com/example/private-saas-dashboard \
  --repository-visibility private \
  --validate
```

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

- Multi-file upload or document parser pipeline.
- ContextBundle runtime generation.
- Real GitHub clone/fetch or `gh auth status` checks during intake.
- Repository indexing before planning.
- Agent SDK runtime code.
- GitHub App integration.
- GitHub Actions log ingestion.
- UI, API server, database, or worker daemon.

Those systems should be implemented against the protocols defined here.
