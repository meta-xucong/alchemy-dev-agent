# Long-Running Roadmap

Objective: Implement V2.7 real execution preflight and configurable document-run adapters.

## Phase 1: Execution Preflight

- Add deterministic preflight checks for repository path, git, Codex executable, and gh availability.
- Report preflight results in document-run output.
- Block real execution when required local tools are unavailable.

## Phase 2: Configurable Execution Adapters

- Add document-run options for real Codex and real GitHub execution.
- Wire options into Orchestrator and Codex/GitHub adapters.
- Keep dry-run as the default safe path.

## Phase 3: Repository Source Preparation

- Optionally prepare public GitHub repositories before context indexing when a repository URL is provided without a local path.
- Preserve public-first behavior and explicit blockers for private repositories.

## Phase 4: Verification And Continuous Delivery

- Add tests for preflight, adapter flags, source preparation, and report fields.
- Update docs and audit.
- Run full verification, commit, push, and continue to the next phase unless blocked.
