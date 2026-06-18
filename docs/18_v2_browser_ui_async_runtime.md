# V2.9 Browser UI And Async Runtime

## Purpose

V2.9 adds the first operational browser console and asynchronous run lifecycle around the local API runtime.

The goal is to make the document-driven workflow usable from a local browser without changing the underlying contracts:

```text
ProjectBrief -> ContextBundle -> TaskGraph -> RuntimeState -> Delivery
```

## Implemented Scope

### Browser Console

The local API server now serves a browser console at:

```text
GET /
```

The console supports:

- Objective entry.
- Local document path entry.
- Local supporting file path entry.
- Browser file selection and upload.
- GitHub repository URL input.
- Local repository path input.
- Project creation.
- Task graph planning.
- Async run start.
- Pause, resume, and stop request buttons.
- Event display.
- Delivery summary display.

Static assets are served from:

```text
GET /static/styles.css
GET /static/app.js
```

### Multipart Upload

The API now accepts real browser file uploads:

```text
POST /projects/{project_id}/files
Content-Type: multipart/form-data
```

Uploaded files are stored under:

```text
.alchemy/server/projects/{project_id}/uploads/
```

Uploaded files are then fed back into the existing ProjectBrief intake path.

Path-reference file intake remains supported for local automation and CLI-oriented workflows.

### Async Run Jobs

The run endpoint supports asynchronous execution:

```json
{
  "async": true
}
```

Async runs persist:

```text
runs/{run_id}/job.json
runs/{run_id}/events.jsonl
runs/{run_id}/run.json
```

Implemented job endpoints:

```text
GET  /projects/{project_id}/runs/{run_id}/job
GET  /projects/{project_id}/runs/{run_id}/events
POST /projects/{project_id}/runs/{run_id}/pause
POST /projects/{project_id}/runs/{run_id}/resume
POST /projects/{project_id}/runs/{run_id}/stop
```

## Control Semantics

The current execution engine still runs a synchronous document pipeline inside a background thread.

Pause, resume, and stop are therefore request controls:

- `pause` records `pause_requested=true`.
- `resume` clears `pause_requested`.
- `stop` records `stop_requested=true`.

These controls are persisted and visible to the UI. Hard worker interruption is not yet implemented because the current Codex worker execution contract does not expose safe task-boundary cancellation.

## Verification

V2.9 adds tests for:

- Async service-level run jobs.
- HTTP async run start and controls.
- Run event retrieval while using job events.
- Multipart file upload through HTTP.
- Browser console static asset serving.

## Boundary

Still planned:

- True task-boundary pause before dispatching the next worker.
- Safe cancellation for real Codex subprocesses.
- Live server-sent events or WebSocket streaming.
- More polished visual graph rendering.
- Private GitHub repository retrieval through local `gh` authentication.
