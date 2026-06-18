# V2.10 Task-Boundary Controls And Private GitHub Preflight

## Purpose

V2.10 tightens operational control for async runs and adds an optional GitHub CLI authentication preflight for private repository workflows.

## Task-Boundary Controls

The runtime now supports an `ExecutionController` hook before each task is dispatched.

Default CLI behavior uses a no-op controller.

The local API async job path injects a job controller that reads persisted run controls from:

```text
runs/{run_id}/job.json
```

Control behavior:

- `stop_requested=true` stops before the next task dispatch.
- `pause_requested=true` pauses before the next task dispatch.
- stop records a runtime blocker with ID `B-RUN-STOPPED`.
- pause records `run_paused` in iteration history.

This is safer than killing an active worker process mid-edit. It guarantees task-boundary auditability while keeping hard subprocess cancellation as a later capability.

## Runtime Contract

New runtime module:

```text
runtime/control.py
```

Core objects:

- `ControlDecision`
- `ExecutionController`
- `NoopExecutionController`

The orchestrator checks the controller before executing each ready task.

## Private GitHub Preflight

New intake module:

```text
intake/gh_auth.py
```

The preflight checks:

- `gh --version`
- `gh auth status`

The result records:

- status
- checks
- optional account name

It does not read or store tokens. Token-looking lines are not used as summaries.

## Document Run Integration

`autodev.document_run` now accepts:

```text
--repository-visibility public|private|unknown
```

When repository visibility is `private`, execution preflight requires local GitHub CLI authentication. Public repositories remain the default path and do not require `gh auth status`.

## Boundary

V2.10 still does not implement:

- private repository clone/fetch through `gh`
- hard cancellation of already-running Codex subprocesses
- server-sent event streaming

Those remain V2.11+ delivery/runtime hardening work.
