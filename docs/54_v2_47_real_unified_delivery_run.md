# V2.47 Real Unified Delivery Run

V2.47 keeps the original Alchemy Dev Agent objective unchanged:

> Users provide a development objective, detailed documents, supporting files,
> and optionally a local or GitHub repository. The agent system should analyze
> the inputs, plan work, execute with agents/Codex workers, test, repair, verify,
> and deliver only when the result is reviewable.

V2.42 through V2.46 proved individual real links:

- real environment readiness;
- real Codex worker smoke;
- real document-run local smoke;
- real GitHub branch, draft PR, and CI probe;
- unified probe evidence indexing.

Those are necessary, but they are still separate reports. V2.47 adds the
missing total-control report for a whole unified run.

## Purpose

V2.47 answers:

> Given one normalized user request, can Alchemy produce a single evidence
> object that proves preflight, planning, execution, review gates, optional real
> worker evidence, optional browser verification, optional GitHub PR evidence,
> and probe history are all aligned?

## Runtime Contract

The new harness is:

```bash
python -m autodev.real_unified_delivery \
  --objective "Add workspace support" \
  --document spec.md \
  --repository-path ./repo \
  --output .alchemy/real_unified_delivery \
  --summary
```

Default behavior is safe:

- dry-run worker mode;
- local/report delivery;
- no remote branch;
- no PR;
- no auto-merge;
- optional probe-index aggregation.

Real execution stays explicit:

```bash
python -m autodev.real_unified_delivery \
  --objective "Implement the supplied development document" \
  --document spec.md \
  --repository-path ./repo \
  --real-codex \
  --real-github \
  --auto-browser-verify \
  --github-ci-wait-seconds 120 \
  --github-ci-poll-interval-seconds 10 \
  --output .alchemy/real_unified_delivery
```

`--real-github` creates real remote state through the existing GitHub delivery
flow. It must be used only with an approved repository.

## Report Contract

The harness writes:

```text
.alchemy/real_unified_delivery/real_unified_delivery_report.json
```

The report contains:

- normalized `request`;
- unified preflight report;
- exact unified CLI command, exit code, stdout, and stderr;
- `unified_run_report.json`;
- `document_run_report.json` when the route is document-driven;
- optional `real_probe_index.json`;
- required and optional delivery gates;
- blockers;
- report paths.

The report schema version is `2.47`.

## Gate Model

Required for every document-driven full delivery:

- `preflight_passed`;
- `path_validation`;
- `unified_command_exit_zero`;
- `unified_run_done`;
- `delivery_ready_for_review`;
- `final_gate_score >= 0.85` when a final score exists.

Required only when enabled by the request:

- `real_codex_worker_evidence` when `--real-codex` is enabled;
- `real_github_pr_evidence` when `--real-github` is enabled;
- `browser_verification_evidence` when `--auto-browser-verify` is enabled;
- `real_probe_index_available` when `--require-probe-index` is enabled.

Optional gates may be `skipped` without blocking the run.

## Relationship To Existing Modules

V2.47 does not replace the existing runtime. It orchestrates and audits:

- `autodev.run` for the unified user-facing entrypoint;
- `autodev.document_run` for document-driven implementation;
- `autodev.unified_preflight` for start safety;
- `autodev.real_probe_index` for historical real-probe evidence;
- `runtime.github_flow` and `runtime.codex_worker` through the normal
  document-run path when real modes are explicitly enabled.

This prevents a second execution model from appearing. The harness is an
acceptance shell around the existing single execution contract.

## Acceptance Criteria

V2.47 is accepted when:

- `autodev.real_unified_delivery` can run a document + local repository request
  through `autodev.run`;
- the resulting report includes all gate decisions and blockers;
- the harness blocks on a failed unified command;
- command construction preserves real Codex/GitHub, browser, CI, and merge
  flags;
- `real_probe_index` can index `real_unified_delivery_report.json`;
- full unit tests pass;
- JSON specs parse, diff hygiene passes, and long-running state validates.

## Remaining Boundary

V2.47 provides a total-control report and dry-run-safe acceptance harness. A
fresh mutating real app delivery should still be run only against an explicitly
approved target repository because it can create remote branches and PRs.

