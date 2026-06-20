# V2.39 Unified Entrypoint Implementation Checklist

This checklist complements `docs/46_v2_39_unified_entrypoint.md`. It is the
execution checklist for the next coding phase.

## Goal

Build one product-facing entrypoint that accepts:

- a user objective;
- one or more development documents;
- supporting files;
- optional local repository path;
- optional public or private GitHub URL;
- execution and delivery options.

The entrypoint must route into the existing Alchemy contracts and produce the
same evidence quality as staged document-run or API workflows.

## Required Artifacts

| Artifact | Purpose | Required Evidence |
| --- | --- | --- |
| `autodev/unified_request.py` | Normalize user-facing run inputs. | Implemented; covered by `tests.test_unified_run`. |
| `autodev/run.py` | Unified CLI facade. | Implemented; covered by one-line and local-repo CLI tests. |
| `ProjectService.run_unified_request` | Service-level one-shot run facade. | Implemented; covered by service sync test. |
| `POST /runs` | HTTP one-shot endpoint. | Implemented; covered by route-level HTTP test. |
| Browser console one-shot form | UI product entry. | Initial `Unified Run` button implemented; still needs browser smoke. |
| Project-type route evidence | Runtime profile selection. | Tests for canvas, static app, Node, Python, docs-only, and unknown profiles. |
| `unified_run_report.json` | Common run report for all modes. | File existence and schema-like assertions in acceptance harness. |

## Request Model Checklist

- [x] Defines `objective`.
- [x] Defines `documents`.
- [x] Defines `attachments`.
- [x] Defines `repository_url`.
- [x] Defines `repository_path`.
- [x] Defines `source_mode`.
- [x] Defines `execution_mode`.
- [x] Defines `delivery_mode`.
- [x] Defines `output_dir`.
- [x] Preserves `repository_visibility`.
- [x] Preserves `prepare_repository`.
- [x] Preserves `codex_executable`.
- [x] Preserves `max_worker_seconds`.
- [x] Preserves `isolate_real_run`.
- [x] Preserves `keep_worktree`.
- [x] Preserves `auto_browser_verify`.
- [x] Preserves `generate_static_ci`.
- [x] Preserves `write_native_ui_tests`.
- [x] Preserves `github_collect_ci`.
- [x] Preserves `github_ci_wait_seconds`.
- [x] Preserves `github_ci_poll_interval_seconds`.
- [x] Preserves `auto_merge`.
- [x] Preserves `resume_from`.
- [x] Preserves `resume_tasks`.
- [x] Preserves `feedback_files`.
- [x] Rejects or blocks missing document paths.
- [x] Rejects or blocks missing local repository paths.
- [x] Infers one-line fallback only when no documents, attachments, or source are present.
- [x] Infers local source when `repository_path` is present.
- [x] Infers public GitHub source for public URLs.
- [x] Infers private GitHub source when visibility is private.
- [x] Records normalized input in the final report.

## Routing Checklist

- [x] `resume_from` routes to existing document-run recovery.
- [x] Documents route to `DocumentRunPipeline`.
- [x] Attachments without documents still route to document-run with low document confidence.
- [x] `repository_path` routes to local repository mode.
- [x] `repository_url` plus `prepare_repository` routes to GitHub source preparation.
- [x] No source package routes to `AutoDevPipeline` in the CLI.
- [x] Feedback files for a delivered run route to feedback reopen through the API service.
- [x] Source preparation failure returns blocked evidence before planning.
- [x] Real Codex remains opt-in.
- [x] Real GitHub remains opt-in.
- [x] Auto-merge remains opt-in.

## CLI Checklist

Supported examples:

```bash
python -m autodev.run --objective "build a retro platform game" --output .alchemy/runs/game
python -m autodev.run --objective "build a todo app" --document spec.md --output .alchemy/runs/todo
python -m autodev.run --document spec.md --repository-path ./repo --auto-browser-verify
python -m autodev.run --document spec.md --repository-url https://github.com/org/repo --prepare-repository
```

Required behavior:

- [x] Exits `0` for completed delivery.
- [x] Exits nonzero for failed, blocked, or needs-iteration delivery.
- [x] Prints concise JSON summary.
- [x] Writes `unified_run_report.json`.
- [x] Links to underlying `document_run_report.json` or `autodev_report.json`.
- [x] Keeps existing `autodev.demo_run` behavior unchanged.
- [x] Keeps existing `autodev.document_run` behavior unchanged.

## API Checklist

Endpoint:

```http
POST /runs
```

Required response fields:

- [x] `project_id`.
- [x] `run_id`.
- [x] top-level `status`.
- [x] `events_url`.
- [x] `events_stream_url`.
- [x] `delivery_url`.
- [x] `artifact_manifest_url`.
- [x] `source_mode`.
- [x] `execution_mode`.
- [x] `delivery_mode`.

Required behavior:

- [x] Creates a project record.
- [x] Attaches document and supporting file metadata.
- [x] Preserves local repository path or GitHub URL.
- [x] Starts an async run.
- [x] Records event stream evidence.
- [x] Returns API errors without orphaning invalid project state.
- [x] Keeps staged endpoints unchanged.

## Browser Console Checklist

- [x] One-shot run button exists.
- [x] Objective input exists.
- [x] Multiple document upload exists.
- [x] Supporting file upload exists.
- [x] GitHub URL input exists.
- [x] Local repository path input exists.
- [x] Source mode selection exists.
- [x] Real Codex toggle exists.
- [x] Real GitHub toggle exists.
- [x] Auto browser verification toggle exists.
- [x] Generated static CI toggle exists.
- [x] Native UI test write toggle exists.
- [x] Auto-merge toggle exists and is off by default.
- [x] Run starts through `POST /runs`.
- [x] UI navigates to the generated project/run evidence view.
- [x] Existing evidence panels continue rendering.
- [x] EventSource stream is used when available.
- [x] Polling fallback remains available.

## Project-Type Matrix

| Profile | Detection Signals | Verification Route | Delivery Gate |
| --- | --- | --- | --- |
| `canvas_game` | Canvas, game, player, level, score, timer, hook markers. | Static artifact verifier plus gameplay probe. | Movement, jump, victory, restart, no console errors, nonblank screenshot. |
| `static_web_app` | HTML app root, forms, buttons, dashboard/list/detail language. | Static verifier plus semantic/scenario probes. | Safe interaction changes state or completes generated scenarios. |
| `node_project` | `package.json`, Node scripts, JS/TS source. | Package test command or detected scripts. | Tests pass or explicit no-test waiver with reviewer evidence. |
| `python_project` | `pyproject.toml`, `requirements.txt`, `pytest`/`unittest` markers. | Python test command or detected suite. | Tests pass or explicit no-test waiver with reviewer evidence. |
| `fullstack_project` | Frontend and backend package markers. | Combined backend tests, frontend tests, browser probe when available. | All available suites pass and UI evidence exists when browser artifact is present. |
| `documentation_only` | Markdown/spec files, no app package markers. | Static document verification. | Spec/report output and reviewer approval. |
| `unknown` | No strong profile. | Conservative deterministic checks. | Needs review unless strong evidence is produced. |

## Acceptance Harness Checklist

Required local harness cases:

- [x] One-line fallback generates a safe playable artifact.
- [x] Document-only static web app routes through document-run.
- [x] Local repository import routes through provider `local`.
- [x] Feedback reopen routes to Debug Agent tasks.
- [x] API one-shot run returns project/run IDs and delivery evidence.
- [x] Browser one-shot UI smoke can start or simulate a run.
- [x] Existing acceptance harness still passes through the full unit suite.
- [x] Existing local repository acceptance harness still passes through the full unit suite.

Optional real-environment cases:

- [ ] Real Codex bounded smoke.
- [ ] Public GitHub dry-run or real PR smoke.
- [ ] Private GitHub preflight with local `gh auth status`.
- [ ] Auto-merge only after CI success.

## Verification Commands

Run focused tests first:

```bash
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest tests.test_autodev_unified_request
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest tests.test_autodev_unified_run
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest tests.test_api_server
```

Then run acceptance:

```bash
PYTHONDONTWRITEBYTECODE=1 python -B -m autodev.acceptance_run --output .alchemy/acceptance_v2_39
PYTHONDONTWRITEBYTECODE=1 python -B -m autodev.local_repository_acceptance --output .alchemy/local_repository_acceptance_v2_39 --auto-browser-verify
```

Then run full repository checks:

```bash
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests
python -c "import json, pathlib; [json.loads(p.read_text(encoding='utf-8')) for p in pathlib.Path('specs').glob('*.json')]"
git diff --check
python "%USERPROFILE%\.codex\skills\long-running-task\scripts\validate_state.py" --project .
```

## Done Criteria

V2.39 implementation is done only when:

- [x] Unified CLI works for one-line fallback.
- [x] Unified CLI works for document-only projects.
- [x] Unified CLI works for local repositories.
- [x] Unified API one-shot run works.
- [x] Browser console one-shot mode works.
- [x] Unified reports are written for all modes.
- [x] Project type and source mode evidence are present.
- [x] Readiness gates consume the same evidence as staged runs.
- [x] Old CLIs and existing API endpoints remain compatible.
- [x] Focused tests pass.
- [x] Full unit suite passes.
- [x] Acceptance harnesses pass.
- [x] Documentation and README references are updated.

## Audit Questions

Before marking V2.39 complete, answer these:

- Does the facade call existing runtime contracts instead of duplicating logic?
- Can a user start from detailed documents without knowing internal script names?
- Does one-line fallback remain secondary and low-confidence?
- Are local and GitHub source modes represented by the same report shape?
- Does the result include evidence, not just status?
- Can a failed run be reopened with feedback?
- Can the user inspect artifacts, tests, probes, and readiness issues?
- Are real Codex, real GitHub, and auto-merge impossible to trigger by accident?
- Are existing specialized paths still covered by tests?
- Is every new claim backed by an automated check or explicit report evidence?
