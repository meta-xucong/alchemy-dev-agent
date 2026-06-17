# Long-Running Roadmap

Objective: Implement V2.2 repository context runtime and documentation.

## Phase 1: Repository Context Runtime

- Add local repository indexing.
- Classify repository files by kind and language.
- Detect package files and CI workflow files.
- Detect package managers.
- Infer test, build, and lint commands.
- Record blockers for missing or invalid local repository paths.

## Phase 2: ContextBundle Integration

- Enrich ContextBundle repository map from local repository evidence.
- Enrich ContextBundle test profile from detected package signals.
- Preserve one-line demo behavior when no repository is provided.

## Phase 3: Documentation

- Add V2.2 repository context runtime documentation.
- Update README and v2 plan status.
- Update alignment audit with current capability and remaining gaps.

## Phase 4: Verification And Delivery

- Add repository context tests.
- Run full test suite.
- Validate JSON specs and long-running state.
- Commit, push, and notify.
