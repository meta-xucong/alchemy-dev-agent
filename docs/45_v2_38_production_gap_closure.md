# V2.38 Production Gap Closure

V2.38 closes the smallest production-readiness gaps found in the final audit
without changing the original goal:

> detailed documents plus local or GitHub repository context should drive
> autonomous planning, execution, testing, review, repair, and delivery.

The phase deliberately avoids broad redesign. It turns previously documented
gaps into contract-backed runtime behavior where the current local prototype can
verify them deterministically.

## Gap Closure Scope

### File Management API

The browser/API runtime now supports the missing file lifecycle operations:

- `PATCH /projects/{project_id}/files/{file_id}`
- `DELETE /projects/{project_id}/files/{file_id}`

`PATCH` can update uploaded file content, role, and required status. It rebuilds
intake immediately so the ProjectBrief remains the current source of truth.

`DELETE` removes the file from project metadata, rebuilds intake, and deletes
the physical file only when it lives under the project upload directory. External
source files are removed from the project catalog but are not deleted from disk.

### Event Streaming

The runtime now exposes a standard-library SSE endpoint:

```http
GET /projects/{project_id}/runs/{run_id}/events-stream
```

Supported query/header inputs:

- `Last-Event-ID` header
- `last_event_id` query parameter
- `timeout` query parameter
- `poll_interval` query parameter

The stream is backed by the existing append-only `events.jsonl` job store. This
keeps the event model deterministic and replayable while allowing browser or
automation clients to consume run events without polling the JSON endpoint.

This is a finite local SSE response rather than a distributed event bus. A
production deployment can replace the storage-backed stream with a broker while
preserving the event contract.

### Resume Run Race Closure

V2.38 also tightens paused-run resume behavior. A paused source run is marked
`resumed` before the recovery run is created, so the active-run guard no longer
blocks the intended recovery handoff.

### Best-Effort Running Worker Cancellation

Real Codex workers now receive a task-scoped cancellation check while the
managed subprocess is running. When the API sets `stop_requested=true`, the
runner can terminate the worker process tree, mark lifecycle evidence as
`cancelled`, roll back task-local changes, and return a blocked worker result.

This is best-effort because process-tree termination depends on host OS behavior
and subprocess cooperation. It closes the local runtime gap but does not claim a
distributed production cancellation guarantee.

### Requirement Contradiction Warnings

Context building now adds lightweight deterministic contradiction detection for
common opposing requirement pairs such as:

- offline vs online
- no login vs login required
- local only vs cloud only
- read only vs editable
- single page vs multi page

Detected contradictions are stored as warning blockers with code
`requirement_contradiction`. They do not stop execution by themselves, but they
surface early evidence that the development document needs review.

### Code Summary Index

`ContextBundle.repository_map.code_summaries` now records deterministic source
and test file summaries. Each summary contains:

- path
- language
- short semantic summary
- signals such as `exports`, `tests`, `api`, `ui`, `state`, or `auth`

This closes the original "no semantic code summarization" gap at a bounded,
machine-checkable level. It is not an LLM-scale architecture understanding
system; it is a safe first pass that improves planning and audit evidence.

## Remaining Production Boundaries

V2.38 intentionally does not claim universal production perfection. The
remaining large-system boundaries are:

- hard cancellation of an already-running real Codex subprocess in every host
  environment beyond the V2.38 best-effort managed subprocess cancellation;
- separate durable worker daemon and queue deployment;
- production database, authentication, authorization, and multi-user isolation;
- broad LLM-grade semantic contradiction analysis across arbitrary documents and
  codebases;
- broad real-world private repository validation.

Those are deployment/runtime hardening tracks, not blockers for the current
document-driven autonomous development v1 acceptance.

## Verification Contract

V2.38 is accepted only when:

- file update/delete API tests pass;
- SSE event stream tests pass;
- best-effort running worker cancellation tests pass;
- context bundle schema validates with `code_summaries`;
- contradiction warning tests pass;
- full unit suite passes;
- standard document-driven acceptance passes;
- local repository acceptance with feedback reopen and browser verification
  passes.
