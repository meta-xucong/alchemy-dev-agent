# V2.70 Phase Gate Auto-Repair

## Objective

Close the gap found during the real `alchemy-media-agent` full-roadmap validation:

```text
phase workers completed
tests passed
review was approved
promotion score was 0.84
required score was 0.85
executor stopped as blocked
```

This is not the desired product behavior. In full-roadmap mode, a slightly failing
phase gate should become an automatic repair iteration before the user is asked
to intervene.

The original goal remains unchanged:

```text
development docs or one-line goal
-> central analysis
-> full roadmap
-> agents implement each phase
-> tests and review run
-> low-score gaps become repair feedback
-> same phase is retried
-> next phase starts automatically
-> final handoff happens only when the root objective is complete
```

## Real-Run Finding

The V3.5 Product API and Minimal UX phase reached:

- `status = done`
- all worker lifecycle records completed
- no runtime blockers
- final gate score `0.84`
- low score dimensions included `spec_alignment` and `risk_quality`

The parent full-roadmap executor treated the score gap as a terminal blocker.
That still required a human operator to do the next step that the central brain
should have done automatically.

## Required Behavior

When a phase run returns `status=done` and has no real blockers, but the
promotion gate score is below the required score:

1. Do not mark the full roadmap blocked immediately.
2. Write a phase-local auto-repair document.
3. Include promotion reasons, low score dimensions, hard failures, required
   changes, and original phase requirements.
4. Re-run the same phase with the repair document appended to the phase
   requirements.
5. Preserve the same repository/worktree so prior phase work is cumulative.
6. Repeat only within a bounded repair-attempt limit.
7. Block only when the repair limit is reached, a real blocker appears, or the
   phase run itself fails in a non-repairable way.

## Non-Goals

- Do not weaken V1/V2/Alchemy Lab protection.
- Do not lower the `0.85` final gate.
- Do not count a phase as complete merely because tests passed.
- Do not ask the user to click continue after a repairable phase gate miss.
- Do not create a parallel runtime outside the existing phase execution path.

## Implementation Contract

`autodev/full_roadmap_executor.py` owns this loop because it is the parent of
phase execution and promotion.

The executor must persist:

- every phase attempt;
- every generated phase repair document;
- the final promotion decision;
- the reason a phase was finally promoted or blocked.

Default guardrail:

```text
max_phase_repair_attempts = 2
```

The value may be overridden through run payloads for controlled probes, but it
must not be a wall-clock timeout.

## Acceptance Tests

Focused regression:

```bash
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest tests.test_full_roadmap_execution.FullRoadmapExecutionTests.test_executor_auto_repairs_low_scoring_phase_before_blocking -v
```

Broader checks:

```bash
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest tests.test_full_roadmap_execution tests.test_unified_run -v
PYTHONDONTWRITEBYTECODE=1 python -B -m compileall autodev tests
```

## Done Definition

V2.70 is complete when:

- low-score phase promotion failures generate repair documents automatically;
- the same phase is retried without human intervention;
- successful repair promotes the next phase;
- repeated low-score repair attempts stop with precise evidence;
- existing full-roadmap extraction, project analysis, and scope controls still pass.
