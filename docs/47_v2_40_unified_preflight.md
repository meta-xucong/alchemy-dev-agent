# V2.40 Unified Run Preflight And Start-Readiness Gate

V2.40 keeps the original autonomous development target unchanged:

> a user supplies a product goal, development documents, supporting files, and
> optionally a local or GitHub repository; the agent cluster plans, implements,
> tests, repairs, reviews, and delivers the project with evidence.

V2.39 unified the entrypoint. V2.40 adds a request-level preflight gate so the
system can answer a simpler operational question before it creates a project or
starts workers:

> Can this exact request safely start with the selected source, execution, and
> delivery modes?

## Problem

The runtime already had low-level environment checks for `git`, `gh`, Codex CLI,
private GitHub authentication, and repository paths. Those checks were not
available as one product-facing contract for `python -m autodev.run`,
`POST /runs`, or the browser console.

That left several risky combinations:

- one-line fallback with real Codex/GitHub toggles enabled;
- GitHub URL without a local checkout or `prepare_repository`;
- GitHub PR delivery without real Codex execution;
- auto-merge without CI evidence collection;
- invalid file paths that could be discovered only after a run request;
- private GitHub mode without local `gh` authentication.

V2.40 resolves this by adding a unified preflight report that is generated from
the same `AutoDevRunRequest` used to start the run.

## Contract

Every unified preflight returns:

```json
{
  "schema_version": "2.40",
  "status": "passed|blocked",
  "can_start": true,
  "route": "one_line_fallback|document_run|feedback_reopen",
  "source_mode": "none|local|github_public|github_private",
  "execution_mode": "dry_run|real_codex",
  "delivery_mode": "report_only|local|github_pr",
  "repository_path": "",
  "planned_repository_path": "",
  "checks": [],
  "blockers": [],
  "warnings": [],
  "request": {}
}
```

`status = blocked` means the runtime must not create a new project or start a
worker. `warnings` are non-blocking but must be visible to the operator.

## Blocking Rules

The preflight must block when:

- any supplied document, attachment, feedback file, resume path, or repository
  path does not exist;
- `source_mode=local` is selected without `repository_path`;
- `source_mode=github_public` or `source_mode=github_private` is selected
  without `repository_url`;
- one-line fallback asks for real Codex or real GitHub execution;
- GitHub PR delivery is requested without real Codex execution;
- real Codex/GitHub execution uses only a GitHub URL without
  `prepare_repository` or `repository_path`;
- real Codex execution cannot find or launch the requested Codex executable;
- real GitHub execution cannot satisfy required `git`, `gh`, or private auth
  checks;
- auto-merge is requested without CI collection.

## Warning Rules

The preflight should warn when:

- both `repository_path` and `repository_url` are supplied and repository
  preparation is not requested;
- a GitHub URL is supplied in dry-run mode without `repository_path` or
  `prepare_repository`, because the run can record metadata but cannot inspect
  source files;
- `auto_merge` is enabled while GitHub PR delivery is disabled.

## CLI

The unified CLI now supports:

```bash
python -m autodev.run \
  --objective "Build the app from these docs" \
  --document docs/spec.md \
  --repository-path ./target-repo \
  --preflight-only
```

The command writes:

```text
output_dir/
  unified_preflight_report.json
```

Normal runs also write `unified_preflight_report.json` before execution and
embed the report path in `unified_run_report.json`.

## API

The local API exposes:

```text
POST /runs/preflight
POST /runs
```

`POST /runs/preflight` never creates a project and never starts a job.

`POST /runs` runs the same preflight first. If it is blocked, the API returns
`400 unified_preflight_blocked` without writing an orphan project record.

## Browser Console

The browser console exposes:

- `Prepare GitHub source`: passes `prepare_repository=true` into the unified
  request;
- `Preflight`: calls `POST /runs/preflight` and shows the report in the events
  panel;
- `Unified Run`: starts only after the API preflight passes.

## Acceptance Criteria

V2.40 is accepted when:

- CLI `--preflight-only` writes a preflight report and does not execute a run;
- bad real Codex executable blocks before execution;
- `POST /runs/preflight` returns a report without creating a project;
- `POST /runs` blocks impossible real-execution combinations before project
  creation;
- the browser console includes the preflight and repository-preparation controls;
- full unit tests pass.

## Non-Goals

V2.40 does not add new agents, a new planner, a new worker, or a new delivery
flow. It only makes the existing unified runtime safer and more inspectable
before work starts.
