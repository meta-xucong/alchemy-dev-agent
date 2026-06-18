# V2.4 Document-To-Plan Runtime

## Purpose

V2.4 turns a document-driven intake package into a planner-ready task graph.

The implemented flow is:

```text
ProjectBrief
  -> ContextBundleBuilder
  -> RequirementExtractor
  -> ContextBundle.requirement_map
  -> TaskGraphBuilder
  -> TaskGraph
```

This stage is deterministic and standard-library only. It does not call external models. Its goal is to create a stable execution contract from well-structured development documents.

## Requirement Extraction

The requirement extractor reads parsed Markdown, text, JSON, YAML, and YML files already cataloged by ProjectBrief.

It extracts:

- Requirement lines from requirement sections.
- Lines containing priority markers such as `must`, `should`, `could`, `required`, `必须`, `需要`, `应该`, and `可选`.
- Acceptance criteria from acceptance sections.
- Requirement priority.
- Source document ID.
- Related repository files from explicit paths and filename/stem matches.

When the document content is unavailable, extraction falls back to the file summary. When no requirement candidates exist, it falls back to the objective.

## Traceability

Every extracted requirement preserves:

- `id`
- `source_document_id`
- `text`
- `priority`
- `acceptance_criteria`
- `related_files`
- `planned_task_ids`

The planner fills `planned_task_ids` after task graph generation. This lets reviewer checks trace from requirement to implementation task, verification task, and review task.

## Task Graph Generation

For document-driven projects, the task graph contains:

- One architecture planning task.
- One implementation task per requirement.
- One verification task.
- One final review task.

Implementation task type and agent are inferred from requirement text and related file signals:

- Backend: API, database, migration, auth, server, service.
- Frontend: UI, dashboard, page, screen, component, TSX/JSX/CSS/HTML files.
- Test: tests, QA, verification, coverage, CI, test files.
- Documentation: README, docs, Markdown files.
- Integration: multiple related files without a more specific match.

Detected test, build, and lint commands are attached to verification tasks.

## Safety Boundaries

V2.4 does not execute code changes. It only prepares the structured graph that downstream agents and Codex workers will execute.

It also preserves the existing one-line game demo path. Generated one-line artifact contexts still use the narrow four-node generated-app graph.

## Implemented Files

```text
context/
  requirement_extractor.py
  builder.py

planner/
  task_graph_builder.py

tests/
  test_document_to_plan.py
```

## Current Limitations

- Extraction is rule-based and works best with structured Markdown or plain text.
- PDF and DOCX deep parsing are still future parser work.
- Requirement contradiction detection is not implemented yet.
- Semantic code summarization is not implemented yet.
- Generated task graphs are deterministic starting points, not final expert plans.
