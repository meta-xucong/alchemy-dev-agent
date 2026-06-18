# Long-Running Roadmap

Objective: Implement V2.6 document-driven end-to-end dry-run CLI.

## Phase 1: Document Run Pipeline

- Add a CLI that accepts objective, primary document, attachments, repository URL, and optional local repository path.
- Build ProjectBrief, ContextBundle, TaskGraph, RuntimeState, worker packages, and orchestrator dry-run result.
- Emit a deterministic JSON report with every major contract payload.

## Phase 2: CLI Verification

- Add tests for document-driven CLI execution against a synthetic local repository.
- Verify generated report includes ProjectBrief, ContextBundle, TaskGraph, RuntimeState, worker packages, and DONE result.
- Preserve existing runtime and one-line demo behavior.

## Phase 3: Documentation And Audit

- Add V2.6 documentation.
- Update README, V2 plan, and alignment audit to distinguish dry-run end-to-end from real Codex execution.

## Phase 4: Delivery

- Run focused and full test suites.
- Validate JSON specs and long-running state.
- Commit, push, and notify.
