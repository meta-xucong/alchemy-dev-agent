# Long-Running Roadmap

Objective: Implement V2.3 public GitHub source runtime and make public repositories the primary path.

## Phase 1: Public GitHub Source Runtime

- Add a source runtime that clones public GitHub repositories into `RepositorySource.local_path`.
- Fetch and deterministically check out the requested target branch when a local git checkout already exists.
- Return structured blockers for clone, fetch, checkout, invalid path, and explicit private repository requests.
- Provide a CLI entry point for public source preparation.

## Phase 2: Public-First Contract Alignment

- Make ProjectBrief and CLI repository visibility default to `public`.
- Keep private repository metadata as an explicit optional path.
- Update README, V2 plan, intake/context contract, UI/API contract, audit docs, and examples.
- Add a V2.3 public GitHub source runtime design document.

## Phase 3: Verification And Delivery

- Add tests for public clone, fetch, and private optional blocker behavior.
- Update existing intake tests to assert public-first defaults.
- Run full test suite.
- Validate JSON specs and long-running state.
- Commit, push, and notify.
