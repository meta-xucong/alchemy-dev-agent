# V2.8 Local API Runtime

## Purpose

V2.8 adds a local JSON API and persistent project service around the document-driven runtime.

This began as the backend foundation for the UI console. The local runtime now
has browser file upload widgets and async run jobs; production database support
remains out of scope.

Update: V2.9 adds the first browser console, multipart upload path, async run job records, and persisted pause/resume/stop requests on top of this API foundation. V2.17 adds recovery-run resume from prior persisted run state. See `docs/18_v2_browser_ui_async_runtime.md` and `docs/26_resumable_real_worker_execution.md`.

## Implemented Scope

The local API can:

- Create a project from an objective, document paths, supporting file paths, and an optional public GitHub repository URL.
- Accept multi-file project input through either `documents`/`attachments` arrays or a UI-oriented `files` array.
- Persist project metadata, ProjectBrief, ContextBundle, TaskGraph, run reports, and delivery summaries under a per-project storage root.
- Build intake and planning artifacts through the existing `ProjectBrief -> ContextBundle -> TaskGraph` contracts.
- Start a document-driven execution run through `DocumentRunPipeline`.
- Return completed run reports and run event history.
- Preserve dry-run defaults while exposing real Codex/GitHub run flags through the run endpoint payload.

## Server

Start the local API:

```bash
python -m server.api --host 127.0.0.1 --port 8765 --storage-root .alchemy/server
```

Health check:

```text
GET /health
```

## Core Endpoints

Implemented endpoints:

```text
POST /projects
GET  /projects/{project_id}
POST /projects/{project_id}/files
GET  /projects/{project_id}/files
POST /projects/{project_id}/github/inspect
POST /projects/{project_id}/intake/build
GET  /projects/{project_id}/brief
GET  /projects/{project_id}/context
POST /projects/{project_id}/plan
GET  /projects/{project_id}/task-graph
POST /projects/{project_id}/runs
GET  /projects/{project_id}/runs/{run_id}
GET  /projects/{project_id}/runs/{run_id}/job
GET  /projects/{project_id}/runs/{run_id}/events
POST /projects/{project_id}/runs/{run_id}/pause
POST /projects/{project_id}/runs/{run_id}/resume
POST /projects/{project_id}/runs/{run_id}/stop
GET  /projects/{project_id}/delivery
```

The endpoint names match the V2 UI/API contract where possible. Mutation endpoints for file patch/delete remain planned.

## Create Project Payload

Path-list form:

```json
{
  "objective": "Add workspace support",
  "documents": ["docs/workspace_feature_spec.md"],
  "attachments": ["docs/api_contract.yaml"],
  "repository": "https://github.com/example/saas-dashboard",
  "repository_path": ".alchemy/projects/proj_workspace_support/repo"
}
```

UI-oriented file list form:

```json
{
  "objective": "Add workspace support",
  "files": [
    {
      "path": "docs/workspace_feature_spec.md",
      "role": "primary_requirements",
      "required": true
    },
    {
      "path": "docs/api_contract.yaml",
      "role": "api_spec",
      "required": false
    }
  ],
  "repository": "https://github.com/example/saas-dashboard"
}
```

## Run Payload

```json
{
  "max_iterations": 50,
  "prepare_repository": false,
  "real_codex": false,
  "real_github": false,
  "codex_executable": "codex",
  "max_worker_seconds": 1800
}
```

Dry-run remains the safe default.

## State Rules

The service uses these project statuses:

- `intake_ready`
- `intake_blocked`
- `planned`
- `running`
- `done`
- `blocked`

Planning is blocked when intake has hard blockers. Execution automatically builds a plan when the project is intake-ready but not yet planned.

## Persistence Layout

```text
.alchemy/server/projects/{project_id}/
  project.json
  brief.json
  context.json
  task_graph.json
  runs/
    run_001/
      state.json
      document_run_report.json
      run.json
```

## Boundary

V2.8 began as a local API runtime. Later phases add the browser console,
async job model, task-boundary controls, private GitHub preparation, real Codex
configuration, isolated worktrees, and recovery-run resume.

The remaining boundaries below are current production-readiness gaps.

Still planned:

- Richer browser UI screens and visual graph rendering.
- A separate asynchronous worker daemon process.
- Production database or multi-user access control.
