# alchemy-dev-agent

`alchemy-dev-agent` is a specification repository and v0.1 prototype runtime for an autonomous software development agent system.

Its purpose is to define the architecture, protocols, state model, task graph model, worker contract, and evaluation gates required to build a multi-agent autonomous development system. The included `runtime/` package is a deterministic CLI prototype that exercises those contracts without requiring external services.

## Goal

The system is designed for workflows where a user provides:

- A development objective, such as a feature, product, system, or migration.
- A detailed development document, requirements brief, or acceptance specification.

The autonomous development system should then:

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

specs/
  state_schema_v2.json       Persistent project state schema.
  task_graph_schema.json     Task graph schema.

examples/
  full_autodev_example.md    Example autonomous development run.

runtime/
  orchestrator.py            Runtime entry point and control loop coordinator.
  task_graph_engine.py       Dependency resolution and graph status updates.
  agent_router.py            Task-to-agent mapping.
  codex_worker.py            Deterministic Codex worker adapter contract.
  evaluator.py               DONE gate scoring.
  state_manager.py           JSON state persistence.
  run_loop.py                CLI loop entry point.

tests/
  test_runtime.py            Unit and smoke tests for runtime v0.1.
```

## Runtime v0.1

The first executable prototype is intentionally narrow:

- CLI-only.
- Standard-library Python.
- Deterministic worker stub.
- Persistent JSON state.
- Sequential task execution.
- DONE gate using:

```text
final_score =
  test_pass_rate * 0.5 +
  spec_alignment * 0.3 +
  reviewer_score * 0.2
```

DONE requires `final_score >= 0.85` and all graph nodes completed.

Run a smoke execution:

```bash
python -m runtime.run_loop --objective "build a todo app with login" --reset
```

Run tests:

```bash
python -m unittest discover -s tests
```

## Non-Goals

This repository does not yet implement:

- Agent SDK runtime code.
- Real Codex CLI subprocess invocation.
- GitHub App or GitHub Actions integrations.
- UI, API server, database, or worker daemon.

Those systems should be implemented against the protocols defined here.
