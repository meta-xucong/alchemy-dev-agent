# V2.66 Project Analysis Gate

## Objective

V2.66 adds a mandatory project-analysis gate before autonomous development starts.

The purpose is to move the human operator's pre-development reasoning into the system:

```text
read all supplied material
-> understand the root objective
-> decide whether this is a full-roadmap task or a bounded phase task
-> extract valid development phases
-> ignore pseudo-phases, section labels, and repeated prompts
-> classify global and phase-local constraints
-> decide whether Codex workers may start editing code
```

This prevents the product UI from launching Codex workers with an unsafe or misunderstood plan.

## Problem

V2.65 introduced full-roadmap execution, but the first real document probe exposed an upstream risk:

```text
The executor could continue beyond V3.0,
but the extractor initially treated ordinary V3 constraint sentences as development phases.
```

Examples that must not start as phases:

```text
V3 code must not import from V1 or V2 runtime modules.
V3 may use V1/V2 only as historical reference.
V2 concept: PromptTransformResult.
V3.1 Acceptance Criteria.
V3.2 Out of Scope.
Phase 2 Prompt: V3.1 Brand Consistency Foundation, when V3.1 is already present.
```

Without a project-analysis gate, this kind of mistake can still reach the frontend one-click flow.

## Required Behavior

Before development starts, the system must produce:

```text
project_analysis_report.json
```

The report must include:

- root objective;
- completion scope;
- start decision;
- confidence;
- valid phases;
- ignored phase candidates;
- duplicate phase candidates;
- global constraints;
- phase-local constraints;
- external blockers;
- warnings;
- required human actions, if any.

The executor may start workers only when:

- `start_decision = start`;
- confidence is at least `0.75`;
- at least one valid phase exists;
- no hard blocker exists;
- no suspicious roadmap explosion exists;
- no unresolved duplicate or pseudo-phase issue remains.

## Start Decisions

| Decision | Meaning |
| --- | --- |
| `start` | The system can begin development. |
| `repair_roadmap` | The system should repair or narrow the roadmap before editing code. |
| `blocked` | Human input or missing external capability is required. |

## Analysis Rules

### Valid Phase

A phase is valid when it is a real development milestone, such as:

```text
V3.0 Foundation
V3.1 Brand Consistency Foundation
V3.2 Generation Loop MVP
Phase 1 - License Gate Foundation
Milestone 2 API Integration
```

### Ignored Candidate

The analysis gate must ignore candidates that are only:

- constraints;
- section labels;
- acceptance criteria sections;
- out-of-scope sections;
- conceptual reference lists;
- repeated phase prompts;
- generic statements beginning with a version number.

### Duplicate Candidate

When multiple documents describe the same version or phase, the gate must keep one canonical phase.

Priority order:

1. step-by-step delivery plan;
2. development roadmap;
3. Codex task prompt;
4. README;
5. other supporting docs.

### Suspicious Roadmap Explosion

If the number of valid phases is much larger than expected, the gate should not silently continue.

Default rule:

```text
if phase_count > 20:
    start_decision = repair_roadmap
```

The report must explain that pseudo-phase detection or source document selection should be reviewed.

## Integration

### Full-Roadmap Executor

`FullRoadmapExecutor` must run `ProjectAnalysisGate` immediately after roadmap extraction and before phase execution.

If the gate returns `blocked` or `repair_roadmap`, the executor stops before calling any Codex worker.

### CLI

`python -m autodev.run --full-roadmap ...` must write:

```text
project_analysis_report.json
```

next to:

```text
roadmap_execution_plan.json
full_roadmap_report.json
```

### API / Frontend

The API run result must expose:

```json
{
  "project_analysis": {
    "start_decision": "start",
    "confidence": 0.91,
    "valid_phase_count": 8
  }
}
```

The beginner UI can show this as:

```text
I read your documents.
I found 8 real development stages.
I ignored 5 repeated or non-development headings.
The project is ready to start.
```

## Acceptance Tests

Unit tests:

- valid V3.0/V3.1/V3.2 phases pass;
- V3 constraint sentences are ignored;
- `V3.1 Acceptance Criteria` and `V3.2 Out of Scope` are ignored;
- `Phase 2 Prompt: V3.1...` is deduplicated against V3.1;
- suspicious phase explosion blocks start;
- external blockers block start.

Integration tests:

- full-roadmap execution writes `project_analysis_report.json`;
- blocked analysis prevents phase execution;
- alchemy-media-agent style documents produce a clean multi-phase plan and `start_decision=start`;
- CLI full-roadmap output includes project analysis.

## Done Criteria

V2.66 is complete when:

- project analysis is a mandatory pre-development gate;
- the report is persisted and surfaced in execution output;
- unsafe analysis stops before code editing;
- tests prove pseudo-phases and duplicate prompt phases do not start workers;
- real-document dry-run shows a clean, startable roadmap.

