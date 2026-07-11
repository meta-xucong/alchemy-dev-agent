# V2.188 Evidence-Bound Autonomous Development

V2.188 hardens the V2.187 goal-locked loop so final progress is bound to
evidence collected by Alchemy, not to claims returned by a worker.

## Audit Findings Closed

1. Worker output is not proof.
   `files_changed`, `tests_passed`, command `exit_code`, and final PASS markers
   are treated as narrative evidence only. Goal-locked phase proof now uses an
   Alchemy-created before/after repository snapshot. Command proof is accepted
   only from commands actually executed by `runtime.independent_verifier`.
   Worker-supplied command names and exit codes are never re-used. Final broad
   PASS markers are ignored unless the controller records both a passing native
   test/build check and `independent_verification_source: alchemy_controller`.

2. Waivers are obligation-scoped.
   A waiver must name `requirement_id`, `obligation`, `authority`, `reason`, and
   a future `expires_at` timestamp. Requirement-level waivers and expired
   waivers do not bypass proof obligations.

3. Delivery identity is coherent.
   The delivery ledger now carries branch and commit identity collected from the
   target worktree. Approved handoff is blocked if branch or commit identity is
   missing or malformed.

4. Goal locking is fail-safe.
   `goal_locked_enabled()` defaults to goal-locked mode unless the run payload
   carries an explicit legacy opt-out. The CLI still exposes `--legacy-unlocked`
   for compatibility inspection, but accidental falsey defaults no longer unlock
   direct full-roadmap or unified runs.

5. Inventory coverage is stack-neutral.
   The semantic inventory scans files in chunks, including large files, and adds
   explicit build and delivery surface classes. Generated, schema, runtime,
   frontend, config, build, documentation, delivery, and test surfaces are now
   visible to the same requirement-derived scanner.

6. Adversarial regression coverage is mandatory.
   The focused goal-locked suite includes cases proving fabricated worker file
   changes, fake test passes, fabricated command exits, and PASS markers cannot
   reach 100 percent progress without independent repository evidence.

## Evidence Model

Each phase record may contain worker output, but `GoalLockedRunCoordinator`
rewrites the proof signals before acceptance:

- changed files come from `independent_changed_files`, derived from Alchemy's
  before/after repository snapshot;
- command and test proof comes from `independent_command_results`;
- those records include `executed`, `kind`, `source`, and real stdout/stderr
  tails; an empty test surface is insufficient for final behavioral proof;
- edit phases require an `independent_snapshot`;
- verification phases require independent passing command records;
- final PASS markers are usable only when `independent_verification` is true.

This makes the accepted checkpoint a repository state transition, not a worker
assertion.

## Acceptance Proof

V2.188 is complete only when these pass in this repository:

- focused V2.188 regression tests in `tests.test_goal_locked_convergence`;
- full `python -m unittest discover -s tests`;
- Python compilation or static import audit for touched modules;
- JSON schema parsing for `specs/*.json`;
- `git diff --check -- ':!.codex-longrun/**'`;
- real read-only Codex smoke when the local Codex CLI is available.

Do not report 100 percent completion if any proof above is missing.
