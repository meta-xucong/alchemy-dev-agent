# Long-Running Roadmap

Objective: Implement Alchemy Dev Agent Runtime Engine as a usable autonomous development runtime.

## Phase 1: Runtime Skeleton

- Create `runtime/` package.
- Add orchestrator, task graph engine, agent router, worker adapter, evaluator, state manager, and run loop.
- Keep runtime standard-library only with deterministic dry-run defaults.

## Phase 2: Autonomous Runtime Capabilities

- Add real Codex subprocess worker adapter behind explicit CLI flag.
- Add retry/debug loop and task graph retry scheduling.
- Add weighted evaluation gate with hard failures.
- Add GitHub execution flow adapter with dry-run and real `git`/`gh` modes.

## Phase 3: Verification

- Add focused unit tests for graph readiness, routing, evaluation, state persistence, and loop termination.
- Add a CLI smoke test.
- Add worker subprocess parsing, retry/debug, and GitHub flow tests.

## Phase 4: Documentation And Delivery

- Update README with runtime usage.
- Validate tests.
- Record long-running state and verification.
