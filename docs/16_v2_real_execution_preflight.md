# V2.7 Real Execution Preflight

## Purpose

V2.7 makes the document-driven CLI configurable for real execution while keeping dry-run mode as the safe default.

The document-run command now supports:

- dry-run Codex worker execution
- optional real Codex CLI execution
- dry-run GitHub delivery evidence
- optional real git/gh delivery flow
- local tool preflight checks
- optional public repository preparation

## CLI Flags

```bash
python -m autodev.document_run \
  --objective "Add workspace support" \
  --document workspace_feature_spec.md \
  --repository https://github.com/example/saas-dashboard \
  --repository-path .alchemy/projects/proj_workspace_support/repo \
  --real-codex \
  --real-github \
  --codex-executable codex
```

Dry-run remains the default. Real execution starts only when the relevant flags are present.

## Preflight Checks

Before execution, the CLI records preflight checks for:

- repository path
- `git`
- Codex executable when `--real-codex` is enabled
- `gh` when `--real-github` is enabled

If a required check fails, the run is marked `blocked` before worker execution begins. The report includes the preflight result and runtime blocker.

## Public Repository Preparation

When `--prepare-repository` is used with a public GitHub URL and no local repository path, the CLI uses the V2.3 public GitHub source runtime to clone or fetch the repository before context indexing.

Private repositories are handled by the later V2.11 private GitHub source
adapter through local `gh` authentication. The public source runtime still
returns a blocker for private repository requests instead of collecting tokens.

## Report Contract

`document_run_report.json` now includes:

- `preflight`
- `project_brief`
- `context_bundle`
- `task_graph`
- `worker_packages`
- `runtime_state`
- `status`
- `validation_errors`

## Boundary

V2.7 does not claim that arbitrary real repositories can be safely completed without supervision. It provides the execution switches, preflight gating, and reporting needed to begin controlled real-world validation.
