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
- Codex CLI executable input.
- Real Codex, real GitHub, isolated worktree, and keep-worktree run controls.
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

The current execution engine runs a document pipeline inside a background
thread and checks controls at task boundaries.

Pause, resume, and stop use these semantics:

- `pause` records `pause_requested=true`; the runtime pauses before the next
  worker dispatch and records `run_paused`.
- `resume` clears `pause_requested`; if the source job is already paused, the
  API starts a new recovery run from the prior `state.json` and returns
  `resumed_run_id`.
- `stop` records `stop_requested=true`; the runtime stops before the next
  worker dispatch and records blocker `B-RUN-STOPPED`.

These controls are persisted and visible to the UI. Hard interruption of an
already-running real Codex subprocess is not yet implemented.

## Verification

V2.9 adds tests for:

- Async service-level run jobs.
- HTTP async run start and controls.
- Run event retrieval while using job events.
- Multipart file upload through HTTP.
- Browser console static asset serving.

## Boundary

V2.16 extends the browser console run payload with real-execution controls that
match the CLI/API contract. Real Codex mode remains opt-in and uses isolated
worktrees by default.

V2.17 adds recovery-run resume for paused, stopped, failed, or blocked run
state. The browser console switches monitoring to the returned resumed run when
the API returns `resumed_run_id`.

Still planned:

- Safe cancellation for real Codex subprocesses.
- Live server-sent events or WebSocket streaming.
- More polished visual graph rendering.
