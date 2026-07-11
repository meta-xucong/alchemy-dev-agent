# V2.187 Goal-Locked Implementation Notes

This implementation makes deterministic V2.187 goal locking the default for
new full-roadmap CLI, API, and project-service runs. The legacy compatibility
planner remains available only through the explicit `--legacy-unlocked` CLI
escape hatch or an equivalent API request.

Added contract layers:

- `context/objective_compiler.py` and `context/objective_models.py` compile
  detailed documents into immutable requirement records with source spans,
  requirement classes, subjects, scopes, proof obligations, and revision hashes.
- `context/reference_baseline.py` records target, reference, orchestrator, and
  artifact repository roles and rejects writable or overlapping references.
- `context/semantic_inventory.py` indexes forbidden-domain hits across source,
  schema, runtime route, frontend contract, config/deploy, generated, archived,
  and test surfaces.
- `planner/transformation_manifest.py` distinguishes delete/transplant/add/modify
  state transitions and requires delete transformations to prove zero inventory.
- `planner/convergence_graph_builder.py` builds requirement-locked task graphs
  with transformation IDs, expected final state, allowed write paths, and
  strategy-decision obligations.
- `runtime/independent_verifier.py`, `runtime/verification_matrix.py`, and
  `runtime/progress_model.py` generate objective-derived proof, hard failures,
  stale/failing evidence gates, and proof-based progress.
- `runtime/convergence_controller.py` fingerprints repeated failures and escalates
  unchanged timeout loops to strategy backtracking instead of endless leaf splits.
- `runtime/task_packet.py`, `runtime/decision_record.py`,
  `runtime/accepted_checkpoint.py`, and `runtime/delivery_ledger.py` define the
  worker packet, strategy decision, accepted checkpoint, and coherent handoff
  records required by the design.
- `autodev/goal_locked_run.py` bootstraps those contracts, converts the
  convergence graph into the actual executable roadmap, records fresh phase
  proofs, detects reference drift, classifies convergence failures, and emits
  the final verification matrix and delivery ledger.
- `runtime/tool_discovery.py` gives preflight and workers one Windows-safe Codex
  discovery policy. Versioned Codex Desktop binaries are preferred over stale
  WindowsApps shims, an explicit model is propagated end to end, and copied
  worker config is repaired without mutating the user's source config.

## Activation

New full-roadmap runs use goal locking by default:

```bash
python -m autodev.run \
  --full-roadmap \
  --real-codex \
  --repository-path /path/to/target \
  --document /path/to/development-plan.md \
  --reference-repository-path /path/to/read-only-reference \
  --codex-model gpt-5.5 \
  --output .alchemy/project-run
```

`--reference-repository-path` is repeatable. If the objective contract says a
reference must be used and no reference path is declared, the run blocks before
coding. Target, reference, orchestrator, and artifact roots must not overlap.

`--legacy-unlocked` is an explicit compatibility fallback. A legacy run cannot
silently resume as goal-locked, and an existing goal-locked objective revision
cannot be replaced during resume.

## Run Artifacts

The coordinator writes these fresh artifacts under `<output>/goal_locked/`:

- `objective_contract.json`
- `reference_baseline.json`
- `repository_inventory.initial.json`
- `transformation_manifest.json`
- `convergence_task_graph.json`
- `verification_matrix.initial.json`
- `phase_proofs/*.json`
- `repository_inventory.current.json`
- `verification_matrix.current.json`
- `convergence_history.json`
- `delivery_ledger.json`
- `goal_locked_status.json`

All contract artifacts are schema validated. The delivery ledger must identify
one coherent target worktree, revision, diff, repository fingerprint, matrix
revision, and accepted checkpoint set.

## Completion Rules

Worker completion is advisory. A phase is accepted only when its contract has
fresh edit or verified-existing evidence, required decisions and reference
files are recorded, declared checks pass, and the reference baseline has not
drifted. A broad final worker result also needs all three explicit markers:
`FINAL_AUDIT_STATUS: PASS`, `SIMULATION_TEST_STATUS: PASS`, and
`REAL_TEST_STATUS: PASS`.

Positive requirements without current proof remain `unproven`; stale repository
fingerprints remain `stale`; negative requirements pass only when the current
semantic inventory proves zero prohibited surfaces. Explicit waivers require
authority, reason, authorization, and expiry. Progress reaches 100 percent only
when every matrix item is passed or validly waived and the delivery ledger is
coherent.

The existing evaluator now consumes `state.repository["verification_matrix"]`
and rejects delivery when any objective-derived proof item is failed, stale,
unproven, or blocked, even if graph completion and reviewer evidence would
otherwise produce a passing numeric score.

The regression case in `tests/test_goal_locked_convergence.py` is read-only and
synthetic. It proves that prohibited capacity inventory fails independent
verification, that delete obligations cannot be replaced by retained-contract
repair tasks, that missing references block before coding, and that a worker's
false completion claim cannot produce a successful delivery.
