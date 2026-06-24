# V2.62 Acceptance And Test Plan

## Purpose

This document defines how to prove the central auto-iteration controller is ready for implementation
and later delivery.

The tests must show that the system behaves like the intended human Codex loop:

```text
develop -> audit -> test -> decide -> repair -> repeat -> handoff
```

## Test Categories

### 1. Schema Validation

Validate:

- `specs/central_review_schema.json`;
- `specs/repair_plan_schema.json`;
- `specs/auto_iteration_report_schema.json`.

Expected result:

- all files parse as JSON;
- example payloads conform to required fields;
- invalid target agents and status values are rejected by local validation helpers or tests.

### 2. Repair Plan Unit Tests

Required cases:

- ready delivery produces no repair items;
- failed browser probe creates a `must` item targeting `debug`;
- missing must requirement creates a `must` item targeting the owning implementation agent;
- reviewer change request creates a `must` item with reviewer traceability;
- low score dimension creates a `should` item when no hard failure exists;
- hard blocker creates a blocked plan and disables automatic execution;
- duplicate repair signature blocks repeated auto-execution.

### 3. Service/API Tests

Required cases:

- `GET /projects/{project_id}/runs/{run_id}/auto-iteration` returns a non-mutating preview.
- `POST /projects/{project_id}/runs/{run_id}/auto-iteration` starts a repair run when guardrails pass.
- `POST` returns blocked when guardrails fail.
- Repair run metadata links to source run id and repair plan id.
- Existing feedback reopen API continues to work unchanged.

### 4. UI Static Contract Tests

Required cases:

- beginner view shows `Continue optimizing` only for auto-iteration-ready runs;
- beginner view hides repair JSON by default;
- advanced view exposes repair plan and auto-iteration report;
- handoff runs show result actions, not repair controls;
- blocked runs show setup/help copy, not retry spam.

### 5. Dry-Run Acceptance Harness

Create a deterministic local scenario:

```text
run_001:
  delivery exists
  central_review.decision = iterate
  missing requirement coverage = one must gap

auto-iteration:
  writes repair_plan.json
  writes repair_plan.md
  writes auto_feedback.md
  starts run_002 through feedback reopen

run_002:
  completes
  recovery comparison shows improvement or accepted handoff
```

Expected result:

- no real GitHub mutation;
- no real model call required;
- project history shows both runs;
- final report explains whether the repair improved score/evidence.

### 6. Real-Environment Optional Probe

When the user approves runtime/API cost, run one real Codex local repository probe.

Required evidence:

- Codex CLI executable is detected;
- source repository is isolated in a project workspace;
- repair feedback file is passed to the real worker;
- worker lifecycle evidence is recorded;
- target-file convergence evidence is recorded when the repair worker fixes all target files and
  required checks pass;
- browser/static/CI gates run according to project type.

This optional probe is not required for deterministic unit acceptance.

## Manual Review Checklist

Before declaring V2.62 done:

- The beginner console has one obvious next action.
- A non-technical user can continue optimization without reading JSON.
- Advanced evidence is still available for debugging.
- No loop can repeat indefinitely without a new signal.
- Auto-iteration never performs mutating GitHub actions without the configured delivery policy.
- Ready runs do not keep asking users to optimize.
- Blocked runs ask for specific help.

## Success Criteria

V2.62 is implementation-complete when:

- all relevant unit tests pass;
- schema parse checks pass;
- API/static tests pass;
- a dry-run acceptance scenario produces a linked `run_001 -> run_002` repair chain;
- central review, repair plan, auto feedback, and recovery comparison are all visible in delivery evidence.

## Regression Risks

Watch for:

- starting a new repair run when the user only opened a historical project;
- creating duplicate repair runs on page refresh;
- showing technical controls in beginner mode;
- lowering final gate standards to reach handoff;
- losing uploaded documents or repository links during repair reopen;
- confusing local-only delivery with GitHub PR delivery.
