# V2.71 Final Audit And Test Convergence

## Objective

V2.71 turns the user's manual Codex completion habit into a built-in system stage:

```text
all planned code complete
  -> multi-angle final audit
  -> repair if any angle fails
  -> broad simulation tests
  -> real tests where available
  -> repair if tests fail
  -> final handoff only when all major gates pass
```

This stage prevents the system from handing off merely because every roadmap phase
has a green local gate.

## Why This Exists

Human operators normally do a skeptical pass after implementation:

- reread the development document;
- question whether the code actually matches the intended product;
- inspect edge cases, UX, architecture, tests, and delivery details;
- run broad tests beyond the narrow phase tests;
- fix defects and repeat;
- only then publish or hand off.

Alchemy Dev Agent must perform that same loop automatically.

## Final Verification State Machine

```text
roadmap phases done
  |
  v
evidence final audit
  |
  +-- failed -> final repair document -> repair run -> audit again
  |
  v
adversarial final worker audit (real Codex full-roadmap runs)
  |
  +-- failed -> final verification repair -> rerun final worker
  |
  v
simulation and scenario test review
  |
  +-- failed -> repair -> rerun tests
  |
  v
real-environment test review
  |
  +-- failed/blocker -> precise blocker or repair
  |
  v
final handoff
```

## Audit Angles

The final audit must challenge the completed system from at least these angles:

- roadmap completion;
- phase gate quality;
- blockers, hard failures, and required changes;
- requirement traceability;
- scope and protected-path boundary;
- known suspicious findings supplied by the controller, user, previous run, or diagnostic probe;
- adversarial review before handoff.

Warnings are surfaced to the user and recorded in the final report.
Hard failures block handoff.

## Test Stages

The final test stage is separate from the audit stage:

- deterministic tests: unit, integration, static, lint, or equivalent phase gates;
- simulation tests: scenario, browser, golden case, static artifact, UI, or gameplay probes;
- real tests: real Codex worker evidence, GitHub/CI evidence, legacy regression tests, or an explicit blocker/waiver.

Full-roadmap runs using real Codex automatically add a final worker phase:

```text
Final Full-System Audit And Testing
```

That worker receives the root objective, phase evidence, and audit checklist.
It must repair defects before returning a passing result.

For real Codex full-roadmap runs, the final worker must also return exact
machine-readable status markers:

```text
FINAL_AUDIT_STATUS: PASS
SIMULATION_TEST_STATUS: PASS
REAL_TEST_STATUS: PASS
```

A high score or generic "done" result is not sufficient. Missing markers, FAIL
markers, blockers, or required actions prevent final handoff and force repair or
an explicit blocker.

The worker must not only rerun existing tests. It must derive fresh semantic
probes from the source documents, especially for cases where tests can pass while
the product contract is still subtly wrong.

Examples:

- requirement classification versus selected agent/module;
- source mode versus GitHub/local delivery behavior;
- protected scope versus changed files;
- user-facing examples versus generated output;
- documented golden cases versus implemented rule selection.

## Handoff Rule

Final handoff is allowed only when:

- all required roadmap phases are complete;
- final audit status is passed;
- final test status is passed;
- final worker verification passes when required;
- real Codex final workers provide explicit PASS markers for final audit,
  simulation tests, and real tests;
- no blockers remain.

## Repair Rule

If final verification fails but has no external blocker, the system writes a final
verification repair document and retries within the configured repair limit.

The repair prompt must preserve:

- completed roadmap work;
- original documents;
- scope controls;
- protected paths;
- delivery policy.

## Implementation Touchpoints

- `autodev/final_verification_loop.py`
- `autodev/final_system_audit.py`
- `autodev/full_roadmap_executor.py`
- `specs/final_verification_report_schema.json`

## Acceptance Criteria

- Final audit report includes audit dimensions and test stages.
- Missing required phases block handoff.
- Low final/phase scores block or iterate before handoff.
- Real Codex full-roadmap runs add a final verification worker by default.
- Dry-run full-roadmap tests can use evidence-only final verification.
- Final worker failures prevent `status=done`.
- Final worker results without explicit PASS markers prevent `status=done` in
  strict real full-roadmap mode.
- Final worker success is recorded in `full_roadmap_report.json`.
