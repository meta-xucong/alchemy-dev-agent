# Long-Running Roadmap

Objective: Implement V2.4 document-to-plan runtime for requirement extraction, traceability, and task graph generation.

## Phase 1: Requirement Extraction Runtime

- Extract deterministic requirements from parsed development documents and supporting files.
- Preserve document source IDs for traceability.
- Attach acceptance criteria from explicit user criteria and document sections.
- Infer requirement priority from must/should/could wording.
- Link requirements to repository files when document text or filename signals match indexed files.

## Phase 2: Task Graph Planning Runtime

- Generate architecture, implementation, verification, and review tasks from ContextBundle requirements.
- Assign implementation tasks to backend/frontend/documentation/integration agents using requirement and repository-file signals.
- Attach requirement acceptance criteria, related files, and detected verification commands to tasks.
- Preserve the existing generated-game demo behavior.

## Phase 3: Documentation And Examples

- Add V2.4 document-to-plan runtime documentation.
- Update README, V2 plan, alignment audit, and document-driven example.
- Keep public GitHub repositories as the primary source path.

## Phase 4: Verification And Delivery

- Add tests for requirement extraction, traceability, and task graph generation.
- Run focused and full test suites.
- Validate JSON specs and long-running state.
- Commit, push, notify, and stop only when the phase is ready for review.
