# V2.65 Full Roadmap Execution Mode

## Objective

V2.65 closes the gap exposed by the Alchemy Creative Agent 3.0 Foundation probe:

```text
The system correctly completed the current scoped phase,
but it stopped after V3.0 because the immediate prompt said "Foundation only".
```

The product goal is broader:

```text
User objective or development package
  -> system understands all required work
  -> system builds a full roadmap
  -> system executes every required phase
  -> central brain audits, tests, repairs, and optimizes after each phase
  -> system automatically advances to the next phase
  -> system stops only when the whole objective is complete or a real blocker exists
```

V2.65 introduces **Full Roadmap Execution Mode**.

It turns Alchemy Dev Agent from a single-phase executor into a full-document autonomous developer.

## Core Principle

The user-level objective is the root contract.

When the user says:

```text
Develop everything in this document.
```

or:

```text
Build the whole project from this idea.
```

the system must not stop merely because one phase, milestone, task prompt, or local gate is complete.

Phase completion is an internal checkpoint.
It is not final delivery.

## Required Behavior

### Document-Driven Mode

When the user provides development documents, supporting files, or a GitHub repository:

1. Read all relevant documents.
2. Extract the full roadmap, including phases marked as later, next, phase 2, phase 3, v3.1, v3.2, future, or subsequent.
3. Classify constraints as either:
   - global constraints that must always be obeyed;
   - phase-local constraints that apply only to the current phase;
   - external blockers that require user action or infrastructure.
4. Build a `RoadmapExecutionPlan`.
5. Execute every phase in dependency order.
6. Run central review, tests, repair, and optimization after each phase.
7. Automatically promote the next phase when the current phase gate passes.
8. Stop only when the root roadmap is complete or a real blocker prevents safe progress.

### One-Sentence Mode

When the user provides only a short natural-language request:

1. Treat the text as the root objective.
2. Generate a development document package from the objective.
3. Self-audit the generated documents for completeness.
4. Convert the generated documents into a `RoadmapExecutionPlan`.
5. Execute the generated roadmap to completion using the same full-roadmap loop.

One-sentence mode may be lower confidence than document-driven mode, but it must still produce a
complete development plan before coding.

## Non-Negotiable Rule: No Phase-Boundary Stop

The system must not hand off to the user at ordinary phase boundaries.

These events are not stop conditions:

- one task graph completes;
- one phase reaches final gate score >= 0.85;
- one PR branch is ready;
- one implementation prompt says "phase complete";
- current phase docs say "phase 2 later";
- central review says the current phase is acceptable.

Those events should trigger:

```text
phase audit -> repair if needed -> promote next phase -> continue execution
```

The final handoff happens only when the root objective is complete.

V2.70 hardens this rule for real runs: if a phase finishes without real blockers
but its promotion score is below the required gate, the roadmap executor writes
a phase-local auto-repair document and retries the same phase before blocking.
See `docs/78_v2_70_phase_gate_auto_repair.md`.

V2.71 hardens the final handoff rule: after every roadmap phase completes, the
executor runs a final audit/test convergence gate. Real Codex full-roadmap runs
add a final worker pass named `Final Full-System Audit And Testing`. This worker
must challenge the result from multiple angles, run broad simulation/real tests,
repair defects if found, and return explicit `FINAL_AUDIT_STATUS`,
`SIMULATION_TEST_STATUS`, and `REAL_TEST_STATUS` PASS markers before final
handoff. A generic high score or "done" result is not enough in strict real
full-roadmap mode. See
`docs/79_v2_71_final_audit_test_convergence.md`.

## Valid Stop Conditions

The system may stop before full completion only when at least one condition is true:

- credentials are missing and cannot be safely inferred from local configuration;
- required paid services, API keys, GPU services, or accounts are unavailable;
- a destructive action is required and no policy authorizes it;
- user product judgment is required and cannot be reasonably inferred from the documents;
- repository permissions prevent required delivery;
- repeated identical repair signatures show no progress;
- scope rules conflict and cannot be resolved safely;
- the target requirement is impossible under the provided constraints.

Stopping must produce:

- exact blocker;
- completed phases;
- remaining phases;
- evidence already produced;
- required user or external action;
- resume instructions.

## Roadmap Extraction

Add a `RoadmapExtractor` layer before task graph creation.

Inputs:

- objective;
- primary documents;
- supporting files;
- repository map;
- existing task prompts;
- README and roadmap files;
- previous run state, if any.

Outputs:

```json
{
  "schema_version": "roadmap_execution_plan_v1",
  "root_objective": "",
  "source_mode": "one_sentence|uploaded_docs|local_repo|github_repo",
  "completion_policy": "full_roadmap",
  "global_constraints": [],
  "external_blockers": [],
  "phases": [],
  "final_acceptance": {},
  "delivery_policy": {},
  "confidence": 0.0
}
```

Each phase must include:

```json
{
  "phase_id": "phase_001",
  "title": "",
  "source_references": [],
  "status": "pending",
  "phase_type": "foundation|feature|integration|ui|generation|delivery|hardening",
  "prerequisites": [],
  "requirements": [],
  "scope_controls": {},
  "phase_local_constraints": [],
  "verification": {
    "commands": [],
    "probes": [],
    "review_checks": []
  },
  "promotion_gate": {
    "required_score": 0.85,
    "required_tests_pass": true,
    "central_review_decision": "handoff_for_phase"
  }
}
```

## Constraint Classification

The system must distinguish local phase prompts from global project constraints.

Example:

```text
Do not implement real image generation in V3.0 Foundation.
```

In single-phase mode, this means:

```text
Do not implement real image generation.
```

In full-roadmap mode, this means:

```text
Do not implement real image generation during V3.0.
Create or preserve a later phase for real generation if the roadmap requires it.
```

Example:

```text
Do not import V1/V2 runtime modules.
```

This is a global constraint.
It remains true for every phase.

## Full Roadmap State Machine

```text
intake
  |
  v
roadmap_extraction
  |
  v
roadmap_audit
  |
  +-- incomplete_docs -> synthesize_missing_plan -> audit_again
  |
  v
phase_planning
  |
  v
phase_execution
  |
  v
phase_tests
  |
  v
central_phase_review
  |
  +-- iterate -> repair_plan -> repair_run -> phase_tests
  |
  +-- blocked -> stop_with_resume_contract
  |
  +-- phase_passed -> roadmap_progression_gate
                          |
                          +-- more_phases -> next_phase_planning
                          |
                          +-- no_more_phases -> final_full_system_audit
                                                    |
                                                    +-- iterate -> repair_plan
                                                    +-- blocked -> stop
                                                    +-- complete -> final_handoff
```

## Execution Loop

Pseudo-code:

```text
roadmap = extract_or_generate_roadmap(input)
roadmap = audit_and_repair_roadmap(roadmap)

while not roadmap.complete:
    phase = select_next_ready_phase(roadmap)

    if no phase:
        stop blocked with missing dependency report

    task_graph = build_task_graph_for_phase(phase, roadmap.global_constraints)
    execute_task_graph(task_graph)
    run_phase_tests(phase)
    central_review = review_phase(phase, task_graph, evidence)

    while central_review.requires_iteration:
        repair_plan = generate_repair_plan(central_review)
        execute_repair_plan(repair_plan)
        run_phase_tests(phase)
        central_review = review_phase(phase, task_graph, evidence)

    if central_review.blocked:
        stop blocked with resume contract

    mark_phase_complete(phase)
    persist_roadmap_state()

run_final_full_system_audit()

while final_audit.requires_iteration:
    repair_plan = generate_final_repair_plan(final_audit)
    execute_repair_plan(repair_plan)
    run_final_full_system_audit()

run_final_simulation_and_real_tests()

while final_tests.require_iteration:
    repair_plan = generate_final_test_repair_plan(final_tests)
    execute_repair_plan(repair_plan)
    run_final_full_system_audit()
    run_final_simulation_and_real_tests()

deliver_final_result()
```

## Central Brain Responsibilities

The Central Brain replaces the human operator between phases.

It must:

- decide whether the current phase satisfies its local requirements;
- identify missing requirements;
- generate repair plans;
- compare repair runs against source runs;
- decide whether the next phase is ready to start;
- reject premature final handoff when roadmap phases remain;
- detect repeated non-progress loops;
- preserve the root objective across every phase.

It must not:

- silently drop roadmap phases;
- treat "later" as "out of scope forever" in full-roadmap mode;
- stop after one successful task graph if phases remain;
- auto-merge or perform destructive delivery without delivery policy.

## Generated Development Document Package

For one-sentence mode, the system must create a machine-auditable document package before coding.

Required files in the run workspace:

```text
generated_development_package/
  00_objective.md
  01_product_requirements.md
  02_architecture.md
  03_roadmap.md
  04_acceptance_criteria.md
  05_test_plan.md
  06_delivery_policy.md
  roadmap_execution_plan.json
```

The package is not merely explanatory.
It becomes the execution contract.

## Delivery Policy

Full completion does not always mean automatic merge.

The roadmap execution plan must classify delivery mode:

```json
{
  "mode": "local_only|branch_only|pull_request|auto_merge",
  "requires_user_approval_for_merge": true,
  "allow_public_repository": true,
  "allow_destructive_actions": false
}
```

Default policy:

- local workspace generation is allowed;
- branch creation is allowed when repository mode is configured;
- PR creation is allowed when GitHub auth is available and user requested GitHub delivery;
- auto-merge is disabled unless explicitly authorized;
- protected branches are never mutated directly.

## No Wall-Clock Timeout

Full-roadmap mode must not impose a fixed development time limit.

It must still detect stuck work through:

- heartbeat files;
- worker lifecycle state;
- no-output duration;
- unchanged evidence;
- repeated identical failures;
- stalled process diagnostics.

A stuck worker becomes a blocker or repairable infrastructure issue.
It is not silently killed as ordinary completion.

## UI Requirements

Beginner UI must show the whole roadmap in simple language.

Default view:

```text
Project goal
Current phase
Overall progress
What I am doing now
What I already finished
What remains
Open result
```

Advanced view may show:

- phase graph;
- raw roadmap JSON;
- task graph;
- repair plans;
- test logs;
- worker lifecycle;
- GitHub delivery details.

The UI must not ask the user to manually click "continue" after every successful phase.

Manual actions are allowed only for:

- blocker resolution;
- destructive approval;
- final review;
- optional publish or merge.

## Required Implementation Modules

Add or extend:

```text
autodev/roadmap_extractor.py
autodev/roadmap_auditor.py
autodev/generated_development_package.py
autodev/full_roadmap_executor.py
autodev/phase_promotion.py
autodev/final_system_audit.py
specs/roadmap_execution_plan_schema.json
server/project_service.py
server/api.py
server/static/app.js
runtime/orchestrator.py
planner/task_graph_builder.py
```

Existing V2.62 central auto-iteration and V2.64 repair convergence must be reused.
V2.65 must not create a parallel repair runtime.

## Acceptance Tests

### Unit Tests

- Roadmap extractor identifies phases from documents.
- Constraint classifier separates phase-local and global constraints.
- One-sentence mode generates a complete document package.
- Roadmap auditor rejects missing acceptance criteria.
- Phase promotion refuses final handoff when later phases remain.
- Final audit rejects completion when any required phase is incomplete.

### Integration Tests

- Uploaded docs with V3.0, V3.1, and V3.2 produce a multi-phase roadmap.
- A successful V3.0 phase automatically promotes V3.1.
- A failed phase creates a repair plan and retries before promotion.
- A blocked phase stops with a resume contract.
- GitHub delivery policy prevents auto-merge by default.
- UI shows whole-roadmap progress instead of a single completed run.

### Real Probe

Use a copied or disposable repository based on the Alchemy Creative Agent documents.

Expected result:

```text
V3.0 Foundation completes
-> central phase review passes
-> executor does not stop
-> V3.1 starts automatically
-> later phases continue until complete or a real blocker is reached
```

The test must fail if the run stops after only V3.0 while roadmap phases remain.

## Done Definition

V2.65 is complete when:

- document-driven input can produce a full roadmap execution plan;
- one-sentence input can synthesize a development package and full roadmap;
- the executor does not stop at phase boundaries;
- central review, repair, test, and optimization happen after each phase;
- the next phase starts automatically after phase gate pass;
- final handoff is impossible while required phases remain;
- final handoff is impossible before final audit/test convergence passes;
- all state is resumable;
- beginner UI shows whole-roadmap progress;
- tests and at least one real probe prove the system does not repeat the V3.0-only stopping problem.

## Self-Audit

### Alignment With Original Product Goal

Status: PASS.

This document restores the original goal:

```text
input objective or development package -> autonomous multi-agent development -> complete deliverable
```

It removes the single-phase stopping behavior as a valid final handoff condition.

### Compatibility With Existing Architecture

Status: PASS.

The design reuses:

- intake and context bundle;
- task graph builder;
- Codex worker;
- evaluator;
- central review;
- auto-iteration repair plans;
- repair convergence;
- delivery evidence.

It adds a roadmap layer above existing phase execution rather than replacing the runtime.

### Handling Of Document-Driven Work

Status: PASS.

Development documents remain the highest-confidence input source.
The full roadmap is extracted from all docs instead of only the current implementation prompt.

### Handling Of One-Sentence Work

Status: PASS.

One-sentence mode first generates a development package, audits it, and then executes it.
It does not start coding from a vague prompt without a contract.

### No Midway Stop Requirement

Status: PASS with explicit safety exceptions.

The document forbids ordinary phase-boundary stops.
It still allows stopping for credentials, destructive actions, impossible constraints, and repeated non-progress.

### V3 Probe Regression Coverage

Status: PASS.

The acceptance tests include a regression where Alchemy Creative Agent V3.0 completion must promote later phases instead of handing off.

### Remaining Risk

The largest risk is over-expanding documents that intentionally describe future possibilities rather than required work.
The mitigation is the constraint classifier plus roadmap auditor:

```text
required roadmap item -> execute
future optional idea -> classify as optional, not required
phase-local "later" -> schedule as later only when the root objective asks for full completion
global "never" or safety rule -> always obey
```
