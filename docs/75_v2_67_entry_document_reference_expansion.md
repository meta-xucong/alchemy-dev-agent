# V2.67 Entry Document Reference Expansion

## Goal

Alchemy Dev Agent must behave like a human Codex operator during project analysis:

1. read the entry task document;
2. discover every referenced development document;
3. build the roadmap from the complete document package;
4. start workers only after the central analysis gate understands the real full scope.

This closes the gap found during the `alchemy-media-agent` V3 validation: when only
`06_CODEX_TASK_PROMPT.md` was supplied, the system initially read only that entry prompt,
collapsed the work into one low-confidence phase, and stopped before development. A human
operator would have followed the "Read These Documents First" list before judging the task.

## Product Principle

The user may provide only a GitHub repository plus one obvious task prompt. The system must
not require the user to manually upload every referenced file when those files already live
inside the repository.

## Contract

Before `RoadmapExtractor` and `ProjectAnalysisGate` run, full-roadmap mode expands the
primary document list:

```text
entry documents
  -> parse referenced .md/.txt/.json/.yaml/.yml paths
  -> resolve paths relative to repository root and document directory
  -> recursively include readable referenced documents
  -> write expanded_document_index.json evidence
```

The expanded document set remains read-only input. It does not authorize broader code edits.
Scope controls still define the writable area for Codex workers.

## Acceptance Criteria

- Entry prompts that list repository documents produce an expanded document index.
- Project analysis uses the expanded document set.
- A V3-style entry prompt can produce a multi-phase roadmap from referenced roadmap docs.
- Scope controls from the full expanded package still protect V1/V2 and other legacy areas.
- The behavior works in dry-run before real Codex workers are launched.

## Non-Goals

- Do not guess remote URLs or fetch third-party documents.
- Do not add unsupported binary files to the roadmap analysis package.
- Do not expand references into writable scope.
- Do not override explicit hard blockers from the analysis gate.
