# Long-Running Roadmap

Objective: Implement V2.1 intake runtime for document-driven ProjectBrief generation.

## Phase 1: Intake Runtime

- Add an `intake/` package.
- Implement local file cataloging, hashing, summaries, and role inference.
- Implement GitHub URL parsing and source normalization without network access.
- Implement ProjectBrief generation from documents, attachments, constraints, acceptance criteria, and repository metadata.
- Implement local ProjectBrief contract validation.

## Phase 2: Tests

- Add unit tests for document-driven intake.
- Add blocker tests for missing primary documents, unsupported required files, and invalid GitHub URLs.
- Add one-line fallback tests.
- Add CLI smoke coverage for `python -m intake.project_brief`.

## Phase 3: Documentation

- Update README with V2.1 intake usage.
- Update v2 plan and audit docs to distinguish implemented ProjectBrief generation from remaining ContextBundle and GitHub retrieval work.

## Phase 4: Verification And Delivery

- Run intake tests.
- Run full runtime test suite.
- Validate long-running state.
- Commit and push V2.1 intake runtime.
