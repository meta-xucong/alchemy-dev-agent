# V2.60 Project Workspace, History, And Score Diagnosis

## Objective

Alchemy must behave like a beginner-friendly product builder, not a single-run developer console.
Each development request is a separate local project workspace with its own folder, run history,
progress state, result actions, and acceptance score explanation.

This keeps the original system goal unchanged:

> user input or development documents -> agent cluster -> code -> tests -> review -> deliverable product.

V2.60 closes the product-level gap where a finished run stays at 100% and makes the next project
look indistinguishable from the previous one.

## Problem

The backend already stores projects under a project-specific local directory:

```text
.alchemy/<server-root>/projects/<project_id>/
  project.json
  brief.json
  context.json
  task_graph.json
  runs/
    run_001/
    run_002/
```

The frontend did not expose this as a project model. As a result:

- users could not see historical projects;
- starting a new project was not a clear action;
- an old completed run could leave the progress bar at `100%`;
- result buttons could be rendered from fallback delivery actions but not found by the click handler;
- a score such as `0.87` looked arbitrary because the UI did not explain missing evidence.

## Required Product Behavior

### 1. Project Workspace

The first visible area is a project workspace panel.

It must show:

- a clear **New Project** action;
- the currently selected project, if any;
- recent historical projects;
- latest run id, latest run status, and latest score when available.

Clicking **New Project** must:

- clear active `project_id` and `run_id`;
- clear delivery/result state;
- reset progress to `0%`;
- keep environment readiness and model configuration intact;
- remove project/run query parameters from the URL;
- let the user pick a new source.

### 2. Project History

The backend must expose a read-only project list endpoint:

```http
GET /projects
```

Response shape:

```json
{
  "projects": [
    {
      "project_id": "proj_x",
      "objective": "Build a small game",
      "status": "done",
      "created_at": "2026-06-21T00:00:00+00:00",
      "updated_at": "2026-06-21T00:20:00+00:00",
      "workspace_path": "D:\\...\\.alchemy\\...\\projects\\proj_x",
      "run_count": 1,
      "latest_run_id": "run_001",
      "latest_run_status": "done",
      "latest_score": 0.87,
      "local_delivery": true,
      "console_url": "/?project_id=proj_x&run_id=run_001"
    }
  ]
}
```

History cards must be simple by default. Technical identifiers and full paths are allowed in
advanced details but should not dominate the beginner view.

### 3. Result Actions

If the UI displays **Open Result** or **Open Folder**, clicking must be actionable.

Rules:

- The same normalized action list used for rendering must be used for click lookup.
- `open_result` opens the artifact URL in a browser tab.
- `open_folder` calls the local API endpoint that opens the result folder on the machine.
- Disabled GitHub/PR actions stay hidden in beginner mode unless advanced details are enabled.
- Local-only runs must not pretend that PR or merge actions are available.

### 4. Score Diagnosis

The delivery score is an evidence-backed acceptance score, not a subjective beauty score.

The default result panel must explain why a passed delivery is not perfect:

- requirement coverage gaps;
- browser/scenario/gameplay probe gaps;
- partial development-cycle steps;
- local dry-run instead of real GitHub PR/CI/merge evidence;
- explicit blockers or required changes.

For example, a `0.87` score can be valid because:

- the final gate threshold is `>= 0.85`, so the run is shippable;
- requirement coverage can be `1.0`;
- development-cycle evidence can still be partial if browser/gameplay probes did not complete;
- dry-run delivery cannot provide real PR/CI/merge proof.

The UI must answer:

```text
Can it be reviewed now? Yes.
Why not perfect? Some verification evidence is missing.
Can the score be higher? Yes, rerun with browser/gameplay verification and real GitHub/CI when needed.
```

## Acceptance Criteria

- `GET /projects` returns recent project summaries sorted by updated time.
- The UI has a project workspace panel with New Project and history.
- New Project resets active run state and progress to `0%`.
- Historical project selection restores the selected project/run.
- Delivery action click handling works for both server-provided and fallback actions.
- The result panel includes beginner-readable score diagnosis.
- Unit tests cover project history API and static UI assets.
- Browser smoke testing verifies project history, new project reset, and result action availability.
