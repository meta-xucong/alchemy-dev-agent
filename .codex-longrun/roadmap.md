# Long-Running Roadmap

Objective: Contract Alignment Fix for `alchemy-dev-agent`.

## Phase 1: Contract Audit

- Compare docs, specs, runtime, tests, and README.
- Identify semantic drift without adding features.

## Phase 2: Minimal Alignment Fixes

- Update schemas to recognize intentional runtime fields.
- Update stale README or CLI wording.
- Keep runtime behavior unchanged unless it violates the documented contract.

## Phase 3: Verification

- Add regression tests that prevent schema/runtime contract drift.
- Run unit tests, CLI smoke, JSON parsing, and long-running state validation.

## Phase 4: Delivery

- Record mismatches found and fixes applied.
- Commit and push the alignment fix.
