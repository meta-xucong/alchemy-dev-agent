# V2 UI And API Requirements

## Purpose

The v2 interface must make the document-driven workflow usable by a human operator.

The UI is not a landing page. It is an operational console for:

- Creating a project package.
- Uploading development documents and supporting files.
- Linking a GitHub repository.
- Reviewing parsed requirements.
- Previewing the task graph.
- Starting execution.
- Monitoring agents, workers, tests, retries, and evaluation.
- Reviewing final delivery evidence.

## Product Flow

```text
Create Project
  -> Upload Files
  -> Link GitHub Repository
  -> Inspect Repository Source
  -> Review Intake
  -> Generate Plan
  -> Preview Task Graph
  -> Start Execution
  -> Monitor Run
  -> Review Delivery
```

Execution must not start until the intake review and task graph preview are available.

## Screens

### Project Create

Required controls:

- Objective text area.
- Primary input mode selector.
- Primary development document upload.
- Supporting file upload.
- GitHub repository URL input.
- Branch or tag input.
- Local path input for already-cloned repositories.
- Public repository source status indicator.
- Optional `gh` authentication status indicator when private repository mode is enabled.
- Create project action.

Required states:

- Empty.
- Uploading.
- Repository inspection pending.
- Authentication missing.
- Ready for intake review.
- Blocked.

### File Intake

Required controls:

- File list.
- Primary document selector.
- File role selector.
- Required file toggle.
- Remove file action before execution.
- Re-parse file action.

Required displayed data:

- File name.
- File type.
- Size.
- Content hash.
- Parse status.
- Role.
- Parse confidence.
- Extracted summary.

### GitHub Source

Required controls:

- Repository URL.
- Target branch.
- Base branch.
- Inspect action.
- Optional private repository mode.
- Re-auth check action when private mode is enabled.

Required displayed data:

- Repository owner and name.
- Visibility if known.
- Access status.
- Selected branch.
- Local checkout path.
- Latest inspected commit.
- CI workflow detection.
- `gh` installed status only when private mode is enabled.
- `gh` authenticated account only when private mode is enabled.

The UI must not ask the user to paste a GitHub token.

### Intake Review

Required views:

- ProjectBrief summary.
- Document index.
- Requirement map.
- Acceptance criteria.
- Repository map summary.
- Test profile.
- Blockers and assumptions.

Required actions:

- Approve intake.
- Edit objective.
- Reclassify file roles.
- Stop and resolve blockers.
- Generate task graph.

### Task Graph Preview

Required views:

- Nodes.
- Dependencies.
- Agent assignment.
- Task type.
- Required context files.
- Completion criteria.
- Retry policy.

Required actions:

- Approve graph.
- Regenerate graph from intake.
- Start execution.

### Execution Monitor

Required views:

- Run status.
- Active tasks.
- Completed tasks.
- Failed tasks.
- Retried tasks.
- Worker logs.
- Test output.
- GitHub evidence.
- Evaluation score.
- Blockers.

Required actions:

- Pause after current task.
- Resume.
- Stop and mark blocked.
- Retry failed task.
- Open generated branch or PR.

### Delivery Review

Required views:

- Final state.
- Final gate score.
- Requirements satisfied.
- Tests executed.
- Reviewer approval.
- GitHub branch, commit, and PR links.
- Remaining risks.
- Blockers if not complete.

Required actions:

- Accept delivery.
- Request another retry.
- Export report.

## API Endpoints

The exact framework is not specified. The behavioral contract is:

```text
POST   /projects
GET    /projects/{project_id}
POST   /projects/{project_id}/files
GET    /projects/{project_id}/files
PATCH  /projects/{project_id}/files/{file_id}
DELETE /projects/{project_id}/files/{file_id}
POST   /projects/{project_id}/github/inspect
POST   /projects/{project_id}/intake/build
GET    /projects/{project_id}/brief
GET    /projects/{project_id}/context
POST   /projects/{project_id}/plan
GET    /projects/{project_id}/task-graph
POST   /projects/{project_id}/runs
GET    /projects/{project_id}/runs/{run_id}
GET    /projects/{project_id}/runs/{run_id}/events
POST   /projects/{project_id}/runs/{run_id}/pause
POST   /projects/{project_id}/runs/{run_id}/resume
POST   /projects/{project_id}/runs/{run_id}/stop
GET    /projects/{project_id}/delivery
```

V2.8 implements a local JSON API subset with synchronous execution:

```text
GET    /health
POST   /projects
GET    /projects/{project_id}
POST   /projects/{project_id}/files
GET    /projects/{project_id}/files
POST   /projects/{project_id}/github/inspect
POST   /projects/{project_id}/intake/build
GET    /projects/{project_id}/brief
GET    /projects/{project_id}/context
POST   /projects/{project_id}/plan
GET    /projects/{project_id}/task-graph
POST   /projects/{project_id}/runs
GET    /projects/{project_id}/runs/{run_id}
GET    /projects/{project_id}/runs/{run_id}/events
GET    /projects/{project_id}/delivery
```

Not yet implemented:

- `PATCH /projects/{project_id}/files/{file_id}`
- `DELETE /projects/{project_id}/files/{file_id}`

V2.9 adds:

- Browser console at `GET /`.
- Static assets at `GET /static/styles.css` and `GET /static/app.js`.
- Multipart upload to `POST /projects/{project_id}/files`.
- Async run start using `POST /projects/{project_id}/runs` with `{ "async": true }`.
- `GET /projects/{project_id}/runs/{run_id}/job`.
- `POST /projects/{project_id}/runs/{run_id}/pause`.
- `POST /projects/{project_id}/runs/{run_id}/resume`.
- `POST /projects/{project_id}/runs/{run_id}/stop`.

Still not implemented:

- `PATCH /projects/{project_id}/files/{file_id}`
- `DELETE /projects/{project_id}/files/{file_id}`
- hard worker cancellation
- server-sent events or WebSocket live streaming

## Data Objects

### Project

Required fields:

- `project_id`
- `objective`
- `primary_input_mode`
- `status`
- `created_at`
- `updated_at`

### UploadedFile

Required fields:

- `file_id`
- `project_id`
- `name`
- `path`
- `media_type`
- `role`
- `required`
- `content_hash`
- `parse_status`

### RepositorySource

Required fields:

- `provider`
- `url`
- `owner`
- `name`
- `target_branch`
- `base_branch`
- `local_path`
- `visibility`
- `gh_auth_required`
- `access_status`

### RunEvent

Required fields:

- `event_id`
- `run_id`
- `timestamp`
- `level`
- `source`
- `message`
- `task_id`
- `agent`

## API State Rules

Allowed project statuses:

- `created`
- `intake_pending`
- `intake_blocked`
- `intake_ready`
- `planned`
- `running`
- `paused`
- `done`
- `blocked`
- `failed`

Execution can start only from `planned`.

Planning can start only from `intake_ready`.

`intake_blocked` requires user action or external access changes before planning.

## File Handling Rules

The API must:

- Preserve original filenames.
- Store content hashes.
- Enforce per-project file isolation.
- Track file role and required status.
- Reject dangerous path traversal names.
- Record parser errors without crashing the project.

## Security Rules

- Do not persist GitHub tokens.
- Do not display secret-looking values from repository files in logs.
- Do not upload user files to external systems unless explicitly configured.
- Redact environment variables and credentials in execution events.
- Keep user repository checkouts outside the Alchemy runtime source tree unless explicitly requested.

## Acceptance Criteria

V2 UI/API is ready when:

- A user can create a project with a detailed document and multiple supporting files.
- A user can link and inspect a public GitHub repository without `gh` login.
- Private repository access, when enabled, uses local `gh` authentication.
- Parsed requirements and blockers are visible before execution.
- A task graph can be previewed before execution.
- Execution can be monitored with task, agent, test, and evaluation state.
- Delivery evidence is visible after execution.
