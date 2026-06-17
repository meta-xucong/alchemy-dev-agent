# Long-Running Roadmap

Objective: Implement Alchemy Dev Agent Runtime Engine v0.1 as a deterministic CLI prototype.

## Phase 1: Runtime Skeleton

- Create `runtime/` package.
- Add orchestrator, task graph engine, agent router, worker adapter, evaluator, state manager, and run loop.
- Keep runtime deterministic and standard-library only.

## Phase 2: Verification

- Add focused unit tests for graph readiness, routing, evaluation, state persistence, and loop termination.
- Add a CLI smoke test.

## Phase 3: Documentation And Delivery

- Update README with runtime usage.
- Validate tests.
- Commit and push implementation.
