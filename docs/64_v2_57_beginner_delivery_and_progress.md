# V2.57 Beginner Delivery And Progress Loop

## Purpose

V2.57 closes the product-experience gap found after a real one-line browser-console run:

1. the user could not open the finished product from the delivery page,
2. the user could not tell whether the system was still developing or stuck,
3. worker execution still had a hard default time limit,
4. GitHub PR controls were visible even when the run was local-only,
5. the console still read like an engineering dashboard instead of a beginner software-building assistant.

The original system objective does not change: detailed development documents, uploaded files, or GitHub repositories should drive an autonomous agent loop that plans, implements, tests, reviews, iterates, and delivers. This phase only makes that loop understandable and verifiable for nontechnical users.

## User Contract

The default browser console must communicate four plain states:

| User stage | Meaning | Primary action |
| --- | --- | --- |
| Configure | Required local tools and model access are not ready yet | Check environment |
| Choose source | Environment is ready, but no development source is selected | Pick one source |
| Developing | A run is queued or running | Watch progress, pause, or stop |
| Ready to review | The run has stopped and produced reviewable evidence | Open result or open folder |

Raw JSON, evidence packages, and low-level task events remain available, but they are secondary developer details.

## Delivery Actions

Every completed run must expose artifact-aware actions:

| Action | When shown | Behavior |
| --- | --- | --- |
| Open result | At least one browser-openable artifact exists | Open the best HTML/web artifact in a new browser tab |
| Open folder | The run has a generated repository or repository path | Ask the local OS file manager to open the result folder |
| View report | A delivery report exists | Keep the user on the delivery summary/report view |
| Publish to GitHub | Source was idea/documents/local-only and no PR exists | Future publishing path; shown as unavailable until implemented |
| Open PR | Source was GitHub-backed and a PR URL exists | Open the pull request URL |

The best browser artifact is chosen in this order:

1. `index.html` artifact file,
2. first `artifact_file` with `text/html`,
3. first artifact marked as a static web/canvas-game artifact,
4. first previewable artifact URL.

The result folder is chosen in this order:

1. run-scoped `generated_repository`,
2. project `repository_path`,
3. run directory.

The API must never expose arbitrary local paths as static files. It may return a safe artifact URL already scoped under `/projects/{project_id}/runs/{run_id}/artifacts/{artifact_id}`, and it may provide a local OS-open action for trusted local use.

## Progress Snapshot

The browser console needs a user-facing progress snapshot separate from the raw event stream.

Required fields:

```json
{
  "project_id": "",
  "run_id": "",
  "status": "queued|running|paused|done|failed|blocked|needs_iteration|unknown",
  "phase": "configure|choose_source|planning|developing|testing|reviewing|ready|blocked",
  "progress_percent": 0,
  "summary": "",
  "elapsed_seconds": 0,
  "last_activity_at": "",
  "last_activity_seconds": 0,
  "is_stalled": false,
  "tasks": {
    "total": 0,
    "completed": 0,
    "running": 0,
    "failed": 0
  },
  "current_task": "",
  "current_agent": "",
  "delivery_actions": []
}
```

Progress is intentionally approximate. It is not a promise that software quality is 60% complete; it is a beginner-friendly signal that the system is alive.

Recommended calculation:

- queued: 5%
- running without task graph: 15%
- running with graph: `10 + completed_or_running_ratio * 75`
- paused: preserve computed progress
- done/ready: 100%
- needs_iteration/failed/blocked: at least the computed progress, capped below 100 unless a reviewable artifact exists

A run is considered suspicious, not automatically failed, when no event, job update, run write, or worker lifecycle update has changed for a configurable stall window. Default stall window: 30 minutes. The UI should say "Still running, but no recent activity was detected" and keep the Stop button available.

## Infinite Worker Default

Large projects must not fail solely because a fixed worker timeout expired.

The runtime semantics are:

- `max_worker_seconds = 0` or omitted means no hard worker timeout.
- Positive values remain supported for smoke tests and controlled probes.
- Browser console defaults to unlimited worker time.
- CLI compatibility can keep explicit timeout flags, but new product flows must not inject the old 1800-second default.
- Stalled detection is reporting-only; it does not kill the subprocess.

## GitHub Mode Isolation

GitHub actions must reflect the selected source and delivery mode:

| Source | Default delivery | Visible GitHub action |
| --- | --- | --- |
| Idea prompt | Local result | Publish to new public GitHub repository (unavailable until implemented) |
| Local documents | Local result | Publish to new public GitHub repository (unavailable until implemented) |
| Local repository | Local result or existing remote | Publish or open existing remote action |
| GitHub URL | Branch/PR flow | Open PR / inspect PR / merge only when PR evidence exists |

If a run did not originate from GitHub and has no PR URL, the UI must not show a fake PR row as a primary summary. It should instead say "Local delivery. No pull request was created."

## Beginner UI Requirements

The default visible UI should prioritize plain-language controls:

1. readiness/check environment,
2. source selection,
3. progress,
4. result actions.

Advanced controls remain available but must be visually secondary:

- raw JSON,
- evidence roots,
- CI wait seconds,
- worker internals,
- repository preparation toggles,
- native UI test write options.

Copy must explain outcomes, not implementation details. For example:

- "Open result" instead of "Artifact preview"
- "Development is running" instead of "Job status: running"
- "Local delivery. No pull request was created." instead of `pull_request_url: -`

## Acceptance Criteria

- Delivery page exposes a primary `Open result` link for web artifacts.
- Delivery page exposes `Open folder` through a safe local API action.
- Run status endpoint returns a progress snapshot with phase, progress percent, task counts, activity timestamp, stall flag, and delivery actions.
- Browser polling renders the progress snapshot while the run is active.
- Default browser run payload uses unlimited worker time.
- Runtime worker adapter treats timeout `0` or `None` as unlimited.
- GitHub PR information is hidden or labeled as local-only when the run has no GitHub evidence.
- Tests cover status snapshot generation, delivery action generation, unlimited worker timeout semantics, and static UI asset wiring.
- Existing unified run, artifact, evidence, and environment tests continue to pass.
