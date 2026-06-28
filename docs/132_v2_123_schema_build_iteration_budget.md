# V2.123 Schema/Build Iteration Budget

## Problem

V2.122 split Billing Core phase_011 final verification into four serial tasks.
That fixed the 900 second timeout, and the next real run completed:

- T022 `Verify backend tests`
- T023 `Verify frontend tests`
- T024 `Verify backend build`
- T025 `Verify frontend build and lint`

However, the supervised resume entrypoint still passed `--max-iterations 4`.
Those four verification tasks consumed the whole document-run iteration budget,
so T026 `Review delivery readiness` and T027 `Record delivery evidence` stayed
pending. The parent phase then blocked with a low promotion score even though
all split verification commands had passed.

## Fix

Full-roadmap phase payloads now give schema/build phases a minimum document-run
iteration budget of 8. This is deliberately narrow: it only applies to phases
whose title or requirements mention schema, Ent, migration, migrate, or fresh DB.
Other phases still respect the caller's explicit `max_iterations` value.

This keeps old supervised resume scripts usable after verification splitting:
the script can still pass `--max-iterations 4`, while the schema/build phase run
gets enough room for split verification, review, and delivery evidence.

## Verification

- Focused full-roadmap regression: schema/build phases with
  `max_iterations=4` are raised to 8, while a frontend phase stays at 4.
- Existing schema/build repair-context regression still passes with the V2.123
  helper reused by the context-retention logic.
