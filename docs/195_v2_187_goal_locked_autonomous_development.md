# V2.187 Goal-Locked Autonomous Development Loop

## Status

This document defines the next architecture revision required before Alchemy is
trusted with another product-scale, document-driven autonomous development run.

It is the parent design for:

- `docs/194_v2_186_hard_prune_governance.md`, which defines the specialized
  absence rules for copy-and-cut and hard-prune projects;
- the existing full-roadmap executor, repair controller, evaluator, repository
  indexer, worker runtime, and final-verification pipeline;
- future project classes where a detailed development document is expected to
  be sufficient input for a long-running autonomous implementation loop.

V2.186 remains valid. V2.187 expands the solution from one failure class into a
general objective-convergence architecture.

## Executive Decision

Alchemy must stop treating a development document as context for a sequence of
LLM tasks. It must compile that document into an immutable, machine-verifiable
objective contract and operate a closed loop against that contract.

The required loop is:

```text
source documents and explicit reference repositories
  -> objective contract
  -> product-boundary and repository inventory
  -> transformation manifest
  -> requirement-locked task graph
  -> bounded implementation waves
  -> independent evidence refresh
  -> convergence diagnosis
  -> replan, continue, or deliver
```

The loop is complete only when all required product states are proven. A high
task-completion ratio, a passing subset of tests, a hidden route, a renamed
legacy concept, or a worker's claim of completion cannot substitute for that
proof.

## Why This Revision Is Necessary

Billing Core demonstrated that Alchemy can become operationally stable while
remaining directionally wrong.

The controller eventually handled Windows worker paths, Go cache permissions,
workspace isolation, timeout boundaries, resume ordering, and non-partial
blocker dispatch correctly. Those fixes matter. They prevented uncontrolled
damage and made runs recoverable.

However, the development outcome still diverged from the source objective:

- route allowlisting was treated as stronger evidence than source deletion;
- legacy gateway domains remained in Ent schema, services, repositories,
  generated code, frontend APIs, components, tests, and copy;
- forbidden RPM, platform-capacity, account-pool, subscription, and relay
  concepts were reframed as contracts to repair;
- repeated timeout recovery split those wrong tasks into smaller wrong tasks;
- completion estimates reached about 99.9 percent while the core product
  boundary was still violated;
- workers did not have an enforced rule to compare damaged local code against
  the original Sub2API source before attempting medium or large repairs.

The manually completed Billing Core pass used a different strategy. It added a
repository-level operating rule that required the original Sub2API source to
be used as a read-only structural reference, explicitly decided between
transplant, repair, redesign, and deletion, and then performed a real cross-layer
hard prune. The resulting working tree deleted hundreds of files and more than
one hundred thousand lines instead of continuing to rename or quarantine the
legacy system.

This difference identifies a system defect, not merely a weak prompt or one bad
worker.

## Failure Analysis

### 1. The objective was not compiled

The source document contained positive features, negative boundaries,
architecture constraints, reference-source expectations, and release criteria.
Alchemy flattened much of this into generic `Requirement.text`, acceptance
criteria, task titles, and path hints.

That representation does not preserve enough meaning to answer:

- must this artifact exist, disappear, remain unchanged, or be rebuilt;
- is a legacy name permitted, temporarily waived, or categorically forbidden;
- what source is authoritative when local code is damaged;
- what proof is required at source, runtime, schema, API, UI, and delivery
  levels;
- whether two requirements contradict each other;
- whether a completed task actually moved the repository toward the requested
  final state.

### 2. Planning optimized for executable work, not final-state truth

The planner successfully emitted runnable tasks and repeatedly narrowed scopes
after timeouts. It did not consistently ask whether the task itself represented
the correct product state.

This allowed titles such as `Repair final backend admin RPM capacity contracts`
to exist in a project whose source document prohibited RPM capacity as a
product concept.

### 3. Verification trusted local behavior more than global absence

Route tests and package tests can pass while forbidden code remains dormant.
Existing test suites inherited from a source product may actively defend the
behavior that the new product must remove. Test health is therefore not an
independent specification oracle.

### 4. Recovery preserved direction as well as progress

Resume preservation correctly avoided replaying completed work, but it also
made a mistaken graph increasingly sticky. Each timeout generated a narrower
descendant without forcing a fresh comparison against the source objective.

### 5. Workers lacked a governed reference baseline

The worker saw the current target repository and task context. It was not
required to consult a separately declared, read-only original repository before
repairing structurally damaged code. Local damage therefore became the basis
for further invention.

### 6. Progress was derived from activity

Task completion, phase promotion, passing tests, and preserved evidence raised
the reported percentage. None of those signals proved that forbidden domains
were gone or that all final product contracts were satisfied.

### 7. Delivery state was not authoritative enough

Long-lived work existed across isolated worktrees, run artifacts, repair
documents, and a dirty target tree. A system cannot claim full delivery unless
it can identify the exact baseline, accepted changes, target worktree, final
commit or patch set, and verification evidence that belong together.

## Product Goal For Alchemy

Given:

- one or more detailed development documents;
- a target repository or an empty target workspace;
- optional read-only reference repositories;
- credentials and external dependencies that are actually available;

Alchemy must be able to:

1. derive the requested final product state;
2. identify contradictions, ambiguities, and external decisions before costly
   implementation;
3. inventory the target against that final state;
4. create a transformation plan whose tasks are traceable to requirements;
5. implement in bounded, verifiable waves;
6. diagnose whether failures require repair, replanning, reference recovery,
   environment correction, or user input;
7. repeat until all required evidence passes;
8. produce one coherent, reviewable delivery state.

The intended user contract is:

> A complete development document defines the product. Alchemy owns the
> implementation loop until that product is delivered or a real external
> decision prevents further progress.

## Non-Goals

V2.187 does not promise that arbitrary vague prompts can produce arbitrary
production systems without review. It does not remove the need for secrets,
legal decisions, payment accounts, inaccessible external systems, or unresolved
product choices.

It also does not require workers to delete code blindly. It requires every
preserve, delete, transplant, repair, redesign, and waive decision to be tied to
the objective contract and verified independently.

## Core Invariants

The following invariants are mandatory.

### Objective immutability

The normalized objective contract is versioned. A worker, repair brief, or
runtime evaluator cannot silently weaken it. Any change creates a new objective
contract revision with a reason and source reference.

### Requirement traceability

Every required task must identify the requirement IDs it advances. Every must
requirement must identify its proof obligations and current evidence.

### Final-state planning

Tasks describe state transitions, not vague effort. `Delete forbidden upstream
account services` is a state transition. `Repair legacy contracts` is not unless
the exact desired final state is defined.

### Independent verification

The final verifier rebuilds evidence from the objective contract and current
repository. It does not infer correctness from task status or worker summaries.

### Reference-source safety

Reference repositories are read-only and explicitly declared. They can guide
transplants and structural repair but can never become accidental writable
targets.

### No implicit waiver

Compatibility, quarantine, disabled routes, archived code, and renamed legacy
semantics require an explicit requirement rule or waiver. Silence means the
original requirement remains active.

### Evidence freshness

Evidence is bound to a repository fingerprint. Changes that can invalidate an
evidence item mark it stale. Preserved completion never preserves stale proof.

### Strategy-level recovery

Repeated failure cannot be handled indefinitely by smaller task scopes. The
controller must eventually revisit the strategy, objective mapping, reference
source, or architecture.

### Delivery identity

Every accepted change and proof item belongs to one target worktree and one
delivery ledger. Completion cannot be assembled from unrelated workspaces.

## Architecture Overview

V2.187 introduces seven logical layers.

```text
1. Objective Compiler
   development docs -> objective_contract.json

2. Reference And Target Analyzer
   reference repos + target repo -> reference_baseline.json
                                  -> repository_inventory.json

3. Transformation Planner
   objective + inventory -> transformation_manifest.json
                         -> requirement-locked task graph

4. Bounded Worker Runtime
   task packet -> edits + decision record + narrow evidence + inventory delta

5. Independent Verifier
   objective + current repo -> verification_matrix.json

6. Convergence Controller
   verification gaps + failures -> continue, replan, backtrack, or block

7. Delivery Controller
   accepted task states + fresh evidence -> delivery_ledger.json + handoff
```

These layers may initially reuse current modules, but their data contracts must
be explicit. The implementation should not add more Billing Core-specific title
matching to `planner/task_graph_builder.py` as the primary solution.

## Required Run Artifacts

Every V2.187 run must maintain:

```text
.alchemy/<run>/objective_contract.json
.alchemy/<run>/reference_baseline.json
.alchemy/<run>/repository_inventory.json
.alchemy/<run>/transformation_manifest.json
.alchemy/<run>/requirement_coverage.json
.alchemy/<run>/verification_matrix.json
.alchemy/<run>/convergence_history.jsonl
.alchemy/<run>/decision_records/
.alchemy/<run>/task_packets/
.alchemy/<run>/evidence/
.alchemy/<run>/delivery_ledger.json
```

Hard-prune runs additionally retain all V2.186 artifacts:

```text
negative_requirements.json
forbidden_inventory.json
prune_manifest.json
absence_evidence.json
waivers.json
```

The specialized artifacts may be projections of the generic contracts, but the
files must remain separately inspectable for audits.

## Objective Contract

### Requirement classes

The objective compiler must support at least:

| Class | Meaning |
| --- | --- |
| `must_implement` | Required behavior or artifact must exist and work. |
| `must_preserve` | Existing behavior, data, API, or file boundary must remain valid. |
| `must_absent_runtime` | Route, page, process, or command must not be reachable. |
| `must_absent_source` | Source module, schema, generated client, or production asset must not remain. |
| `must_absent_fresh_schema` | Fresh installation must not create the named data contract. |
| `must_absent_public_contract` | Public API, UI, SDK, docs, and product copy must not expose the concept. |
| `must_reference` | A declared source must be inspected before a class of changes. |
| `must_verify` | A named test, scenario, migration, or operational probe must pass. |
| `must_decide` | A design choice must be resolved before dependent implementation. |
| `may_reframe` | A legacy artifact may remain only under explicitly changed semantics. |
| `may_waive` | A reviewed temporary exception is permitted under stated conditions. |

### Requirement record

Each requirement must carry structured meaning. A representative record is:

```json
{
  "id": "REQ-DATA-014",
  "source": {
    "document": "BILLING_CORE_DEV_PLAN.md",
    "section": "6. Fresh migration",
    "line_start": 274,
    "quote_hash": "sha256:..."
  },
  "statement": "Fresh Billing Core migrations must not create subscription plans.",
  "strength": "must",
  "class": "must_absent_fresh_schema",
  "domain": "subscription",
  "subjects": ["subscription_plans", "SubscriptionPlan"],
  "scope": ["backend/migrations/**", "backend/ent/**"],
  "allowed_exceptions": ["backend/migrations/legacy_relay/**"],
  "depends_on": [],
  "conflicts_with": [],
  "proof_obligations": [
    "fresh_schema_inventory_zero",
    "ent_schema_inventory_zero",
    "fresh_migration_smoke"
  ],
  "status": "unproven"
}
```

### Compilation checks

Before implementation, the compiler must reject or flag:

- must requirements without proof obligations;
- negative requirements without scope or subject seeds;
- reference-dependent requirements without a valid reference root;
- contradictory keep/remove requirements for the same domain;
- acceptance language that is not mapped to any requirement;
- undefined terms that materially change architecture;
- source documents that appear truncated, unreadable, or superseded.

The compiler may use model-assisted extraction, but deterministic validation of
the resulting schema is mandatory.

## Reference Baseline Governance

### Declared repository roles

Every repository path must have one role:

- `target`: the only product repository workers may modify;
- `reference`: read-only source used for comparison or transplantation;
- `orchestrator`: Alchemy's own repository, writable only during an explicit
  Alchemy framework-development task;
- `artifact`: run output, not product source;
- `external`: unavailable or remote source represented by metadata only.

Workers must never infer these roles from the current working directory.

### Reference manifest

`reference_baseline.json` records:

```json
{
  "target": {
    "path": "D:/AI/billing core",
    "head": "...",
    "writable": true
  },
  "references": [
    {
      "id": "original-sub2api",
      "path": "D:/AI/SSH/sub2api",
      "head": "...",
      "writable": false,
      "purpose": ["structural_repair", "transplant_source"]
    }
  ],
  "orchestrator": {
    "path": "D:/AI/Alchemy Dev Agent System/alchemy-dev-agent",
    "writable_for_product_tasks": false
  }
}
```

The runtime must verify path containment and read-only policy before each
worker starts.

### Change-strategy decision

Before any medium or large code slice, the worker must produce a decision
record choosing one of:

- `preserve`: current target code is correct and remains unchanged;
- `transplant`: copy original structure with minimal target adaptation;
- `repair_from_reference`: restore damaged target structure using reference
  comparison, then apply required target changes;
- `redesign`: requirements demand behavior not present in the reference;
- `delete`: the slice only supports a forbidden target domain;
- `waive`: a permitted temporary exception is requested.

A decision record includes inspected target files, inspected reference files,
reason, requirement IDs, risks, expected inventory delta, and verification
commands. Medium or large edits cannot begin without this record.

### Reference-aware prompts

Worker packets must include:

- target root and writable boundaries;
- relevant reference root and immutable boundaries;
- requirement IDs and source excerpts;
- current target inventory hits;
- reference files likely to contain the undamaged structure;
- the required strategy decision;
- explicit prohibition against inventing a replacement when direct transplant
  or deletion satisfies the contract.

This turns the successful manual `AGENTS.md` discipline into a framework
contract instead of a project-specific reminder.

## Repository Inventory And Product Boundary Model

The current repository index is useful for files, languages, packages, test
commands, and representative paths. V2.187 must add a semantic boundary index.

### Inventory dimensions

The index must identify:

- source files and generated files;
- symbols and import edges;
- backend routes and route registrars;
- handlers, services, repositories, jobs, and command entry points;
- database schemas, tables, columns, indexes, seeds, and migration families;
- frontend routes, navigation entries, views, components, stores, composables,
  API modules, public barrels, types, and i18n keys;
- configuration keys, environment variables, deployment services, sidecars,
  and startup dependencies;
- tests that defend required behavior and tests that defend forbidden legacy
  behavior;
- archived, generated, vendored, fixture, reference, and production surfaces.

### Product-boundary graph

The inventory should project a graph:

```text
domain -> files -> symbols -> imports/callers -> routes/contracts -> tests
       -> schemas/migrations -> config/deploy -> user-visible copy
```

This graph enables a planner to remove a domain by dependency closure rather
than by keyword or one file at a time.

### Inventory classification

Every hit receives:

- requirement ID;
- domain;
- surface class;
- production relevance;
- generated or handwritten status;
- active, dormant, archived, test-only, or ambiguous status;
- proposed action;
- permitted exception or waiver ID;
- evidence fingerprint.

Keyword matching can seed inventory. It cannot be the sole final decision
because terms such as `channel`, `token`, `account`, and `provider` have valid
meanings in retained authentication and payment domains.

## Transformation Manifest

Planning begins only after objective and inventory validation.

The transformation manifest is the authoritative list of intended state
changes. Each item records:

```json
{
  "id": "TRANS-SUBSCRIPTION-003",
  "requirements": ["REQ-DATA-014", "REQ-UI-021"],
  "domain": "subscription",
  "action": "delete",
  "targets": [
    "backend/ent/schema/subscription_plan.go",
    "backend/internal/service/subscription_service.go",
    "frontend/src/api/subscriptions.ts"
  ],
  "dependency_closure": [
    "generated Ent clients",
    "wire providers",
    "router imports",
    "subscription tests"
  ],
  "expected_final_state": {
    "inventory_hits": 0,
    "runtime_routes": 0,
    "fresh_tables": 0
  },
  "verification": [
    "static_inventory",
    "ent_generation",
    "backend_compile",
    "frontend_typecheck"
  ]
}
```

Manifest actions are:

- `add`;
- `modify`;
- `delete`;
- `transplant`;
- `regenerate`;
- `rename_with_semantic_change`;
- `archive`;
- `waive`.

The manifest must distinguish `delete` from `hide`, `unregister`, `archive`, and
`rename_with_semantic_change`.

## Requirement-Locked Planning

### Task contract

Every implementation task must contain:

- requirement IDs;
- transformation IDs;
- expected starting inventory;
- expected final state;
- target and reference paths;
- allowed write paths;
- required strategy decision;
- narrow verification commands;
- evidence outputs;
- downstream invalidation rules;
- explicit non-goals.

### Task ordering

Default ordering is:

1. objective and reference validation;
2. read-only target inventory;
3. architecture and transformation decisions;
4. domain-level delete/transplant/add waves;
5. generated-code regeneration;
6. compile and caller repair;
7. feature and behavior tests;
8. cross-domain integration;
9. independent objective verification;
10. deployment smoke and delivery.

For copy-and-cut projects, forbidden-domain deletion must precede repair of
callers that only exist because the forbidden domain remains.

### Task granularity

Tasks should be large enough to complete a semantic state transition and small
enough to verify within one worker budget.

Correct split dimensions are:

- domain;
- architectural layer;
- dependency closure;
- generated versus handwritten code;
- implementation versus verification.

Incorrect split dimensions are repeated fragments of an invalid task title,
such as turning a forbidden RPM-capacity domain into backend RPM, frontend RPM,
settings RPM, and handler RPM leaves.

### Planning hard failures

The planner must reject a graph when:

- a task advances a forbidden product concept without an allowed reframe;
- a must requirement has no task or verifier;
- a delete requirement is represented only by hide/unregister/rename work;
- a task writes to a reference or orchestrator repository during product work;
- final verification depends only on inherited source-product tests;
- broad verification is scheduled before high-priority inventory gaps close;
- a generic repair task has no expected inventory delta.

## Worker Execution Protocol

Each worker follows:

```text
inspect objective slice
  -> inspect target slice
  -> inspect declared reference when required
  -> record strategy decision
  -> apply one transformation wave
  -> run narrow checks
  -> report repository and inventory delta
  -> checkpoint accepted state
```

Worker output must separately report:

- files added, modified, deleted, regenerated, or transplanted;
- requirement IDs advanced;
- transformation items completed;
- inventory hits removed, introduced, or left ambiguous;
- tests added, rewritten, or deleted and why;
- narrow checks and exact results;
- unexpected scope discoveries;
- evidence invalidated by the change;
- recommended next action.

A worker cannot mark a transformation complete merely because its command
returned successfully. The controller refreshes the relevant inventory and
proof obligations first.

## Independent Verification Matrix

`verification_matrix.json` is generated from the objective contract, not from
the task graph.

Each proof obligation records:

- requirement ID;
- verifier type;
- command or probe implementation;
- repository fingerprint;
- status: `unrun`, `pass`, `fail`, `blocked`, or `stale`;
- produced evidence paths;
- failure summary;
- affected domains;
- last verified time.

### Verification levels

V2.187 separates:

1. `source`: files, symbols, imports, and generated code;
2. `schema`: fresh migrations and retained-data migrations;
3. `contract`: routes, DTOs, SDK types, frontend APIs, and public exports;
4. `behavior`: unit, integration, scenario, and browser tests;
5. `operational`: build, startup, health, dependency, and deployment probes;
6. `delivery`: clean target identity, accepted patch/commit, and handoff
   artifacts.

A requirement may need evidence from multiple levels. Route absence does not
prove source absence. Unit tests do not prove fresh migration correctness.

### Test provenance

Every test is classified as:

- inherited and still authoritative;
- inherited but requiring adaptation;
- inherited and defending forbidden behavior;
- newly generated from the objective contract;
- independent static or operational probe.

Deleting a legacy test is valid when its behavior is forbidden. Weakening a
required test is a hard failure.

## Convergence Controller

The convergence controller replaces blind task continuation with evidence-based
iteration.

After each wave it computes:

- which requirements moved from unproven to proven;
- which inventory counts decreased, increased, or stayed unchanged;
- which evidence became stale;
- which failures are product, code, test, environment, reference, boundary, or
  external failures;
- whether the current strategy is converging.

### Convergence decision

The controller chooses exactly one:

- `continue`: current strategy is reducing objective gaps;
- `repair`: implementation is correct in direction but locally broken;
- `replan`: task graph does not cover the observed repository state;
- `backtrack`: strategy decision was wrong; revisit transplant/repair/delete or
  architecture;
- `fix_environment`: failure is outside product code and has a known local
  remedy;
- `wait_for_input`: a real product or external decision is required;
- `deliver`: every hard gate has fresh passing evidence.

### Failure fingerprint

Each failure fingerprint includes:

```text
requirement IDs
transformation IDs
domain and surface class
target file set
command or probe
normalized error signature
inventory before and after
strategy decision
reference baseline revision
```

This is stronger than matching task titles or free-form repair text.

## Anti-Loop Policy

Alchemy must detect both execution loops and semantic loops.

### Execution loop

The same command, error signature, files, and strategy repeat without evidence
movement.

### Semantic loop

Task names or file scopes change, but the same requirements remain unproven and
the same forbidden or missing inventory remains.

### Escalation ladder

For one failure fingerprint:

1. first failure: perform a focused local repair;
2. second failure: re-index the affected domain and rebuild its task slice;
3. third failure: invalidate the strategy decision and compare against the
   declared reference or architecture contract again;
4. fourth failure: run an independent objective audit and choose a different
   transformation strategy;
5. only then mark blocked, and only if the blocker is external, contradictory,
   destructive without authorization, or genuinely undecidable.

Repeatedly splitting a task after step two without inventory reduction is
prohibited.

### Convergence budget

Token and time budgets are attached to requirements and transformation waves,
not only workers. A controller may spend more worker attempts on a high-risk
payment or migration requirement, but it must stop spending on a strategy that
does not move its proof obligations.

## Progress Model

Progress must represent proven final state.

The user-facing report includes:

- requirements proven / total;
- hard requirements unproven;
- transformation items complete / total;
- forbidden inventory remaining by category;
- required evidence passing, failing, blocked, and stale;
- current strategy and last measurable delta;
- exact blockers;
- delivery readiness.

### Milestone gates

Suggested milestone ceilings are:

| Gate | Maximum progress before gate passes |
| --- | ---: |
| Objective contract validated | 10% |
| Reference and target inventory complete | 20% |
| Transformation manifest approved by internal validation | 30% |
| Required implementation state reached | 70% |
| Source/schema/contract proof complete | 85% |
| Behavior and operational verification complete | 95% |
| Delivery ledger coherent and final review approved | 100% |

These ceilings do not mean progress rises automatically when a gate passes.
Within a gate, progress is based on weighted requirement proof, not task count.
V2.186 applies stricter caps when forbidden inventory remains.

### One hundred percent rule

Alchemy may report 100 percent only when:

- every must requirement has fresh passing proof;
- no unwaived negative requirement has a remaining hit;
- no required evidence is stale, failing, blocked, or unrun;
- reviewer decision is approved;
- target workspace and delivery ledger identify one coherent final state;
- required tests, build, startup, and delivery checks pass;
- no objective-linked next action remains.

## Workspace And Delivery Discipline

### Workspace roles

The runtime must resolve absolute paths before launching workers and record:

- target product worktree;
- reference repositories;
- Alchemy orchestrator root;
- run artifact root;
- external cache roots.

Each path is validated for role and write policy. This prevents workers launched
from the Alchemy root from accidentally reasoning about or modifying the wrong
repository.

### Accepted checkpoints

After each verified transformation wave, Alchemy records an accepted checkpoint
containing:

- target HEAD or patch fingerprint;
- changed files;
- requirement and transformation IDs;
- evidence generated;
- evidence invalidated;
- rollback information;
- worktree identity.

Unverified worker edits remain provisional and do not count toward progress.

### Delivery ledger

`delivery_ledger.json` records:

- original baseline;
- ordered accepted checkpoints;
- final target fingerprint;
- final branch, commit, patch, or PR;
- verification matrix revision;
- waivers;
- unresolved non-required issues;
- handoff decision.

Final delivery cannot reference a stale phase record or a different worktree.

## Token And Time Efficiency

Goal locking should reduce, not increase, waste.

### Context selection

Workers receive only:

- objective slice for their requirement IDs;
- target inventory slice;
- relevant reference files;
- dependency and caller slice;
- previous failure fingerprint when repairing;
- narrow verification commands.

They do not receive the entire historical repair chain unless a strategy audit
requires it.

### Incremental indexing

The inventory refreshes changed files and dependency neighbors after each wave.
A full repository index runs at initial analysis, after architecture-level
changes, and before final verification.

### Verification scheduling

Use:

- static inventory after every transformation wave;
- narrow package or component checks during implementation;
- impacted integration checks at domain boundaries;
- broad repository suites only at planned convergence gates;
- final broad checks once evidence indicates the repository is ready.

### History compaction

Convergence history stores structured deltas. Repair prompts receive the latest
objective gap and failure fingerprint, not concatenated free-form repair briefs.

### Search hygiene

Repository inventory tools return structured counts and bounded examples. Raw
unbounded `rg`, `git diff`, test, or status output is stored as an artifact and
summarized for the model.

## Detailed Implementation Plan

### Phase 0: Freeze special-case expansion

Before adding more product-specific recovery branches:

- classify current `planner/task_graph_builder.py` title-matching branches as
  compatibility behavior;
- prevent new Billing Core-specific title predicates unless they fix an active
  safety defect;
- record baseline tests for current behavior;
- introduce a feature flag such as `goal_locked_convergence`.

Exit criteria:

- existing flows remain testable;
- new V2.187 code has a separate activation path;
- no new project-specific repair vocabulary is required for the Billing Core
  fixture.

### Phase 1: Objective compiler

Add:

```text
context/objective_compiler.py
context/objective_models.py
specs/objective_contract_schema.json
```

Responsibilities:

- compile document summaries and source spans into structured requirements;
- preserve source locations and quote hashes;
- classify positive, negative, preserve, reference, verification, and decision
  requirements;
- derive proof obligations;
- detect conflicts and missing semantics;
- write `objective_contract.json`.

Integrate with `specs/context_bundle_schema.json` by referencing an objective
contract revision instead of relying only on flattened requirement text.

Tests:

- source-span preservation;
- negative requirement extraction;
- reference requirement extraction;
- contradiction detection;
- missing-proof rejection;
- deterministic serialization and revision hashing.

### Phase 2: Reference and semantic inventory

Add:

```text
context/reference_baseline.py
context/semantic_inventory.py
context/product_boundary_graph.py
specs/reference_baseline_schema.json
specs/repository_inventory_schema.json
```

Extend `context/repository_indexer.py` rather than replacing its package and
command detection.

Responsibilities:

- enforce target/reference/orchestrator path roles;
- fingerprint repositories;
- index route, schema, migration, backend layer, frontend surface, config,
  deployment, generated, archived, and test contracts;
- build domain dependency closure;
- classify inventory hits against requirements;
- support incremental refresh.

Tests:

- reference roots are never writable;
- target path containment works on Windows spaced paths;
- archived legacy migrations are distinguished from fresh migrations;
- payment providers are not confused with model upstream providers;
- authentication channels are not confused with gateway channels;
- generated Ent clients are linked to their source schemas.

### Phase 3: Transformation and convergence planner

Add:

```text
planner/transformation_manifest.py
planner/convergence_graph_builder.py
planner/task_contract_validator.py
specs/transformation_manifest_schema.json
```

Keep `planner/task_graph_builder.py` as the compatibility planner during
migration. New goal-locked runs use the convergence builder.

Responsibilities:

- derive add/delete/transplant/repair/regenerate actions from objective and
  inventory;
- order tasks by domain and dependency closure;
- attach requirement and transformation IDs to every task;
- reject semantically invalid graphs;
- generate decision-record and evidence obligations;
- split timeouts by inventory category and dependency closure.

Tests:

- a forbidden RPM domain creates delete tasks, never RPM repair tasks;
- route unregistration cannot satisfy source deletion;
- schema deletion schedules generation and caller repair downstream;
- required reference comparison precedes large edits;
- all must requirements have tasks and verifiers;
- task splitting preserves expected final state.

### Phase 4: Independent verifier and evaluator hard gates

Add:

```text
runtime/independent_verifier.py
runtime/verification_matrix.py
runtime/progress_model.py
specs/verification_matrix_schema.json
```

Update `runtime/evaluator.py` to consume the verification matrix and objective
contract.

Responsibilities:

- generate verifiers from proof obligations;
- refresh evidence from the current repository;
- fingerprint evidence and mark invalidated items stale;
- enforce positive and negative hard gates;
- compute proof-based progress;
- prevent numeric score from overriding hard failures.

Tests:

- passing route tests cannot pass while forbidden schema files remain;
- stale evidence cannot be preserved after relevant changes;
- inherited tests for forbidden behavior do not count as required proof;
- 100 percent is impossible with any unproven must requirement;
- an explicit valid exception is reported separately from zero inventory.

### Phase 5: Strategy-aware recovery

Update:

```text
runtime/recovery.py
runtime/orchestrator.py
autodev/full_roadmap_executor.py
```

Add:

```text
runtime/convergence_controller.py
runtime/failure_fingerprint.py
specs/convergence_decision_schema.json
```

Responsibilities:

- classify objective movement after each worker;
- fingerprint repeated failures;
- detect semantic loops;
- escalate from repair to re-index, replan, reference backtrack, and independent
  audit;
- preserve accepted checkpoints without preserving stale evidence;
- stop dispatch on non-partial blockers as already required.

Tests:

- repeated timeout with unchanged inventory cannot create infinite leaf splits;
- changed titles with unchanged requirement gaps count as a semantic loop;
- environment failures route to environment repair without product edits;
- reference backtrack can replace a failed freestyle repair strategy;
- downstream tasks never dispatch after a non-partial blocker.

### Phase 6: Worker packets and checkpoints

Update `runtime/codex_worker.py` and task serialization.

Add:

```text
runtime/task_packet.py
runtime/decision_record.py
runtime/accepted_checkpoint.py
```

Responsibilities:

- deliver bounded objective, inventory, reference, and failure context;
- require strategy decisions for medium and large changes;
- capture structured file and inventory deltas;
- validate worker output before acceptance;
- record provisional versus accepted edits.

Tests:

- worker packet contains target and reference roles;
- worker cannot report a reference file as changed;
- deletion tasks require deleted-file and inventory-delta evidence;
- medium/large edits without a strategy record are rejected;
- oversized output is artifacted and summarized.

### Phase 7: Delivery ledger and handoff

Update `runtime/handoff.py` and GitHub/dry-run delivery integration.

Add:

```text
runtime/delivery_ledger.py
specs/delivery_ledger_schema.json
```

Responsibilities:

- bind accepted checkpoints to one target worktree;
- record final branch/commit/patch/PR state;
- require a clean or explicitly enumerated delivery diff;
- bind verification evidence to the final fingerprint;
- produce a concise user-facing proof report.

Tests:

- evidence from another worktree cannot approve delivery;
- untracked required files appear in the ledger;
- dirty unrelated files are reported and excluded explicitly;
- final handoff cannot use a stale verification matrix;
- final branch and commit identity are consistent.

### Phase 8: Default activation

Run goal-locked mode against a benchmark matrix before making it the default:

- additive feature in an existing repository;
- copy-and-cut hard prune;
- damaged fork repaired from a reference repository;
- schema migration with preserved production data;
- frontend redesign with unchanged backend API;
- new project generated from documents only;
- external blocker requiring user input.

Default activation requires all regression fixtures and current safety tests to
pass. Compatibility planner fallback remains explicit and cannot report the
same confidence as goal-locked mode.

## Billing Core Regression Fixture

Billing Core is the mandatory end-to-end fixture for V2.187.

### Fixture inputs

- original detailed Billing Core development document;
- copied Sub2API target containing gateway-era domains;
- original Sub2API repository as a read-only reference;
- route allowlist tests that already pass;
- forbidden Ent schema, services, frontend APIs, router entries, and fresh
  migration surfaces still present.

### Required compiled objective

The compiler must produce requirements proving:

- identity, wallet, recharge, redeem, metering, usage, admin, payment, and audit
  capabilities exist;
- gateway, upstream account, proxy, model routing, channel scheduling,
  subscription plan, platform quota, and RPM capacity product domains are
  absent at all applicable levels;
- original Sub2API is a read-only structural reference for repair;
- payment and redeem fulfillment only affect wallet balance;
- fresh installation contains only allowed Billing Core tables;
- final backend, frontend, migration, build, startup, and smoke evidence passes.

### Required initial result

The route allowlist pass must not approve the project. The inventory must report
the remaining forbidden schema, service, migration, frontend API, component,
test, and copy surfaces.

### Required plan shape

Expected high-level tasks include:

- inventory forbidden domains;
- decide delete/transplant/repair strategies using original Sub2API;
- delete upstream account and gateway dependency closures;
- delete subscription, platform quota, and RPM capacity closures;
- rebuild fresh schema and regenerate Ent;
- repair retained Billing Core callers;
- delete frontend relay APIs, routes, components, stores, and tests;
- verify wallet/payment/metering retained behavior;
- prove forbidden inventory is zero;
- run full backend/frontend/fresh-install/startup verification;
- record one coherent delivery.

The graph must never create `Repair final backend admin RPM capacity contracts`
because that concept is forbidden by the objective.

### Required recovery behavior

If a deletion wave times out:

- refresh its domain inventory;
- preserve files and inventory categories already removed;
- split by dependency closure;
- compare damaged retained files against the reference source;
- replan if inventory does not decrease;
- never convert the forbidden domain into a compatibility contract.

### Required final result

Final approval requires:

- forbidden source, route, fresh-schema, public-contract, and UI inventory at
  zero except documented permitted archives;
- retained Billing Core behavior passing its proof matrix;
- no required test, build, startup, or smoke evidence stale;
- one target worktree and delivery ledger;
- 100 percent reported only at that point.

## Test Strategy

### Unit tests

- objective classification and conflict detection;
- source reference and quote hashing;
- semantic inventory classifiers;
- transformation action selection;
- task contract validation;
- evidence invalidation;
- failure fingerprint and semantic-loop detection;
- proof-based progress calculation.

### Integration tests

- document -> objective contract -> inventory -> task graph;
- worker result -> incremental inventory -> verification refresh;
- timeout -> convergence diagnosis -> strategy-aware recovery;
- reference transplant -> target-only write validation;
- accepted checkpoint -> final delivery ledger;
- resume from disk without task-ID or evidence drift.

### End-to-end tests

- Billing Core hard-prune fixture;
- a small reference-repair fixture with intentionally corrupted source;
- a project with valid compatibility waivers;
- a project with contradictory requirements that must stop before coding;
- a project with a simulated Windows cache failure that must not trigger product
  repair;
- a project where task names change but objective evidence does not, proving
  semantic-loop detection.

### Adversarial evaluator tests

The evaluator must reject:

- all tests pass but a forbidden schema remains;
- route is hidden but handler/service/source remains;
- file is renamed but forbidden behavior remains;
- worker claims completion with no inventory delta;
- old evidence belongs to a different repository fingerprint;
- a passing score coexists with one hard failure;
- 99 percent is derived from completed tasks while core requirements are
  unproven.

## Observability

The runtime report must answer, without reading worker logs:

- What exact final product state is requested?
- Which requirements remain unproven?
- What changed in the last iteration?
- Did inventory or proof coverage improve?
- Why was the current strategy selected?
- Which reference files were consulted?
- Is the run repeating an execution or semantic loop?
- What is the next task and which proof gap will it close?
- What prevents delivery right now?

The report should show evidence counts and paths, not a narrative percentage
alone.

## Compatibility And Migration

Existing run artifacts remain readable. When a run lacks an objective contract:

- it is marked `legacy_unlocked`;
- its progress percentage is advisory;
- it cannot be resumed in goal-locked mode until a bootstrap compiler creates
  and validates the missing contract and inventory;
- preserved task completion may seed history but not proof;
- final delivery requires fresh V2.187 verification.

Current project-specific repair predicates may remain temporarily for old runs.
New goal-locked runs must not depend on them.

## Security And Safety

- Reference repositories are opened read-only.
- Target and orchestrator write permissions are role-scoped.
- Destructive database or production operations remain approval-gated.
- Delete manifests are reviewable and limited to the target worktree.
- Generated commands use structured argument execution where possible.
- Secrets are never copied into task packets or evidence artifacts.
- Waivers require explicit user or policy authority and expiry.
- Recovery cannot weaken tests, requirements, or write boundaries silently.

## Acceptance Criteria For V2.187

V2.187 is implemented only when all of the following are true:

- detailed documents compile into a validated objective contract with source
  traceability;
- reference and target repository roles are explicit and enforced;
- medium/large repairs require transplant/repair/redesign/delete decisions;
- semantic repository inventory covers source, schema, contract, UI, config,
  deploy, generated, archived, and test surfaces;
- the transformation manifest distinguishes deletion from hiding and renaming;
- every task maps to requirements, transformations, and expected final state;
- independent verification is generated from the objective rather than task
  completion;
- stale evidence cannot approve a changed repository;
- repeated failures trigger re-index, replan, and strategy backtracking instead
  of endless leaf splitting;
- progress is based on proven requirements and hard gates;
- 100 percent requires one coherent final delivery state;
- Billing Core fails while any unwaived forbidden domain remains;
- Billing Core planning uses the original Sub2API reference and never repairs
  forbidden RPM capacity as a retained product contract;
- targeted, regression, and end-to-end test suites pass;
- the user-facing report explains current gaps and convergence without reading
  raw logs.

## Recommended Delivery Order

The minimum useful implementation is:

1. objective compiler and schemas;
2. reference roles and semantic inventory;
3. convergence graph builder and task validation;
4. independent verifier and hard-gate progress;
5. strategy-aware recovery and worker decision records;
6. delivery ledger and default activation.

Alchemy should not start another unattended Billing Core-scale project after
only step 1 or 2. The minimum trustworthy pilot requires steps 1 through 4 so
the system can both plan the right target and refuse a false completion.

## Final Design Principle

The autonomous loop must optimize for convergence on the requested product,
not for keeping workers busy, completing graph nodes, passing inherited tests,
or reducing task size.

The development document defines truth. The reference repositories define
trusted starting structure. The target repository defines current reality. The
verification matrix proves the distance between them. Alchemy's job is to make
that distance reach zero and to know, from fresh evidence, when it has done so.
