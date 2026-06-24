# V2.72 One-Shot Document Readiness Hardening

## Objective

V2.72 hardens the document-readiness layer used before a one-shot Dev Lab run starts.

The goal is to ensure a target repository's development documents are not merely present, but executable as one consistent roadmap.

This closes the gaps found while preparing the Alchemy Creative Agent V3 document package for a full autonomous run.

## Problems Found

### 1. Important Documents Existed Outside The Target Repository

Two V3 frontend/product documents existed only in the local Downloads folder.

That meant a Dev Lab run starting from the target repository would not see:

- Scenario Pack platform and V3 home UI rules;
- General Creative product/workspace rules.

Resolution:

- copy those documents into the target V3 docs folder;
- add repository README index entries;
- add a one-shot integration document that tells the executor to read the complete package.

### 2. A Phase Worker Prompt Could Be Mistaken For The Whole Product Scope

`06_CODEX_TASK_PROMPT.md` is a valid Foundation-phase worker prompt, but it says later phases are not part of that task.

In a full-roadmap run, this must not stop the system after Foundation.

Resolution:

- Foundation prompts must declare their local scope;
- full-product objectives must read a one-shot execution spec before planning;
- phase-local "not yet" constraints must not become global "never" constraints.

### 3. Product Phase Titles Were Too Narrowly Parsed

The roadmap extractor missed phase titles such as:

```text
V3.7 General Creative Workspace and Runtime Flow
```

because the title used product words such as `workspace`, `runtime`, and `flow`.

Resolution:

- treat scenario, workspace, runtime, and flow as valid phase-title hints.

### 4. Safety Policies Were Misclassified As External Blockers

The classifier treated a line like:

```text
CandidateView.metadata must not expose secrets, raw provider credentials, or hidden reasoning.
```

as if credentials were missing.

This is a safety policy, not an external blocker.

Resolution:

- classify "must not expose/leak secrets" as a policy constraint;
- do not block development for redaction/safety requirements.

### 5. Future Optional Phases Were Executed As Required Work

Future vertical packs are useful roadmap context, but they are not part of the current V3 General Creative acceptance target.

Resolution:

- mark future/optional expansion phases optional;
- skip optional phases in automatic `next_ready_phase` selection;
- keep optional phases visible in the roadmap for traceability.

## Required Behavior

Before one-shot development starts, Dev Lab must verify:

1. target documents live in the target repository or supplied upload package;
2. entry prompts recursively reference the full document package;
3. phase-local prompts are not treated as final product scope;
4. every required product phase is extracted;
5. future optional phases are marked optional;
6. safety/redaction policies are not misclassified as credential blockers;
7. project analysis returns `start` only when blockers are real;
8. the final plan can continue from first phase to final required phase without manual continue clicks.

## Acceptance Criteria

- A V3 document package with Foundation, Brand, Generation Loop, Product API, Scenario Hub, and General Creative documents extracts all required phases.
- `V3.7 General Creative Workspace and Runtime Flow` is retained as a required phase.
- `V3.8 Future Vertical Agent Specialization` is recorded as optional unless explicitly requested.
- Secret-redaction policies produce constraints, not blockers.
- The project analysis gate returns `start` for a clean V3 package.
- `next_ready_phase` returns `None` after all required phases complete even if optional future phases remain pending.

## Tests

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -m unittest tests.test_full_roadmap_execution -v
```

The suite includes regressions for:

- General Creative workspace phase extraction;
- secret redaction policy classification;
- optional future phase skipping;
- full-roadmap non-stop execution.
