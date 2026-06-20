# V2.41 Unified Acceptance Harness

V2.41 keeps the original goal unchanged: the system should accept a user goal,
development documents, supporting files, and optional local/GitHub repository
context, then drive autonomous planning, implementation, testing, repair,
review, and delivery evidence.

V2.40 made individual unified run requests safe to start. V2.41 turns that into
a repeatable local acceptance harness.

## Problem

The repository already has strong focused tests and several specialized
acceptance harnesses. After V2.39 and V2.40, the product-facing path is the
unified request contract, but there is not yet one acceptance harness that proves
the following user-facing modes together:

- one-line fallback;
- document-only generated repository;
- document plus local repository;
- document plus GitHub URL metadata in dry-run mode.

Without one harness, regressions can slip between CLI, API, UI, preflight,
project creation, run execution, and evidence retrieval.

## Scope

V2.41 adds a deterministic local harness that exercises the unified API/service
contract only. It does not create external GitHub repositories and does not run
real Codex workers.

The harness must:

1. create local fixture documents and repositories;
2. call request-level preflight for each scenario;
3. start the unified request through `ProjectService.run_unified_request`;
4. wait for async runs when needed;
5. retrieve events, delivery, and artifact manifest evidence;
6. write one machine-readable acceptance report.

## Scenarios

### One-Line Fallback

Input:

- objective only;
- dry-run/report-only modes.

Expected:

- route is `one_line_fallback`;
- preflight passes;
- generated artifact report exists;
- status is `done`.

### Document-Only Generated Repository

Input:

- objective;
- primary development document;
- no repository URL or path.

Expected:

- route is `document_run`;
- preflight reports a planned generated repository;
- run status is `done`;
- generated repository artifacts exist;
- delivery is ready for review.

### Local Repository Package

Input:

- objective;
- primary development document;
- local repository path.

Expected:

- source mode is `local`;
- preflight validates repository path;
- async run finishes;
- events are recorded;
- delivery evidence is retrievable.

### GitHub URL Dry-Run Metadata

Input:

- objective;
- primary development document;
- public GitHub URL;
- no `prepare_repository`;
- dry-run/report-only modes.

Expected:

- preflight passes with a warning that the GitHub source is not prepared;
- run can record repository metadata without mutating a remote;
- no real GitHub commands are required.

## Report

The harness writes:

```text
output_dir/
  unified_acceptance_report.json
```

The report contains:

- overall `status`;
- scenario checks;
- route/source/execution/delivery summaries;
- preflight status and warnings;
- project/run identifiers where applicable;
- delivery and artifact evidence availability.

## Acceptance Criteria

V2.41 is accepted when:

- `python -m autodev.unified_acceptance` returns `passed`;
- unit tests verify every scenario and the CLI report;
- full regression tests pass;
- README references the unified acceptance harness.

## Non-Goals

V2.41 is not a real Codex/GitHub online probe. Real execution remains opt-in and
should be tested separately after request-level preflight proves local
readiness.
