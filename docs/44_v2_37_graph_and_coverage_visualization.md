# V2.37 Graph And Coverage Visualization

## Goal

V2.37 improves the browser console review workflow by turning raw task graph and requirement coverage JSON into compact visual summaries.

The goal is not to add a new scheduler. The goal is to make the existing autonomous-development evidence easier to inspect before and after execution.

## Task Graph Visualization

The console renders `task_graph.nodes` into:

- total task count,
- distinct agent count,
- number of dependency-bound tasks,
- status distribution,
- agent distribution,
- a compact task rail with task id, agent, title, dependencies, and completion criteria count.

This supports fast checks for:

- whether Architect, Backend, Frontend, Test, Debug, Reviewer, and Release work are separated correctly;
- whether dependencies are present;
- whether task status is moving as expected.

## Requirement Coverage Visualization

The console renders `requirement_coverage.entries` into:

- requirement count,
- coverage score,
- must-gap count,
- coverage status distribution,
- a compact coverage matrix with requirement id, status, requirement text, files, and planned tasks.

This supports fast checks for:

- missing must requirements,
- partial must requirements,
- requirement-to-file traceability,
- requirement-to-task traceability.

## Deep-Link Integration

When a project/run deep link is opened:

```text
/?project_id=<project_id>&run_id=<run_id>
```

the console loads:

- project metadata,
- persisted task graph,
- run-scoped delivery evidence,
- artifact previews,
- repair suggestions,
- requirement coverage visualization.

## Rules

- Visualization is read-only.
- Visualization must not mutate task graph, coverage, delivery, or runtime state.
- Raw JSON output remains available for audit.
- Long text must wrap instead of breaking layout.
- The console must remain usable on narrow screens.

## Acceptance Criteria

- Plan preview renders graph statistics and task cards.
- Delivery review renders requirement coverage statistics and coverage rows.
- Project/run deep links render graph and coverage evidence without requiring manual clicks.
- Static console tests lock the required DOM ids and rendering functions.
- Browser smoke verifies graph and coverage content on a local API run.
