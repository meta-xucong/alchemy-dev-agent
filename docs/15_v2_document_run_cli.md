# V2.6 Document-Driven Dry-Run CLI

## Purpose

V2.6 provides a single local command that exercises the document-driven development pipeline end to end in deterministic dry-run mode.

The implemented flow is:

```text
development document + optional repository path
  -> ProjectBrief
  -> ContextBundle
  -> TaskGraph
  -> RuntimeState
  -> CodexWorkerInput packages
  -> Orchestrator dry-run execution
  -> document_run_report.json
```

This is not yet real repository mutation. It is an executable integration path that proves the contracts can move from user documents into runtime execution and DONE evaluation.

## CLI

```bash
python -m autodev.document_run \
  --objective "Add workspace support" \
  --document workspace_feature_spec.md \
  --repository https://github.com/example/saas-dashboard \
  --repository-path .alchemy/projects/proj_workspace_support/repo \
  --output .alchemy/document_run
```

## Inputs

Required:

- `--objective`
- at least one `--document`

Optional:

- repeated `--attachment`
- `--repository`
- `--repository-path`
- `--output`
- `--max-iterations`

`--repository-path` points at an already available local checkout. It can be produced by V2.3 public GitHub source runtime or provided directly.

## Output Report

The CLI writes:

```text
<output>/document_run_report.json
<output>/state.json
```

The report includes:

- `project_brief`
- `context_bundle`
- `task_graph`
- `worker_packages`
- `runtime_state`
- `status`
- `validation_errors`

`status=done` means the generated graph reached the existing dry-run DONE gate, including review and delivery evidence.

## Verification Boundary

The CLI proves:

- documents can become structured requirements
- repository evidence can enrich planning
- task graphs can become worker packages
- generated graphs can run through the orchestrator
- dry-run delivery evidence satisfies the current evaluator

The CLI does not prove:

- real Codex can safely mutate arbitrary target repositories
- real GitHub PR and CI evidence are available
- UI/API upload and monitoring are implemented
- deep semantic document parsing is complete

Those are later runtime and product phases.
