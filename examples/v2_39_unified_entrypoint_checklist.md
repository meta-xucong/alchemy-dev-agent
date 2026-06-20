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
| `autodev/unified_request.py` | Normalize user-facing run inputs. | Unit tests for source, delivery, and execution mode inference. |
| `autodev/run.py` | Unified CLI facade. | CLI tests for one-line, document-only, and local repo modes. |
| `ProjectService.run_unified_request` | Service-level one-shot run facade. | API/service tests proving it creates a project and starts a run. |
| `POST /runs` | HTTP one-shot endpoint. | HTTP test for project/run IDs and URLs. |
| Browser console one-shot form | UI product entry. | Static asset tests and one browser smoke. |
| Project-type route evidence | Runtime profile selection. | Tests for canvas, static app, Node, Python, docs-only, and unknown profiles. |
| `unified_run_report.json` | Common run report for all modes. | File existence and schema-like assertions in acceptance harness. |

## Request Model Checklist

- [ ] Defines `objective`.
- [ ] Defines `documents`.
- [ ] Defines `attachments`.
- [ ] Defines `repository_url`.
- [ ] Defines `repository_path`.
- [ ] Defines `source_mode`.
- [ ] Defines `execution_mode`.
- [ ] Defines `delivery_mode`.
- [ ] Defines `output_dir`.
- [ ] Preserves `repository_visibility`.
- [ ] Preserves `prepare_repository`.
- [ ] Preserves `codex_executable`.
- [ ] Preserves `max_worker_seconds`.
- [ ] Preserves `isolate_real_run`.
- [ ] Preserves `keep_worktree`.
- [ ] Preserves `auto_browser_verify`.
- [ ] Preserves `generate_static_ci`.
- [ ] Preserves `write_native_ui_tests`.
- [ ] Preserves `github_collect_ci`.
- [ ] Preserves `github_ci_wait_seconds`.
- [ ] Preserves `github_ci_poll_interval_seconds`.
- [ ] Preserves `auto_merge`.
- [ ] Preserves `resume_from`.
- [ ] Preserves `resume_tasks`.
- [ ] Preserves `feedback_files`.
- [ ] Rejects or blocks missing document paths.
- [ ] Rejects or blocks missing local repository paths.
- [ ] Infers one-line fallback only when no documents, attachments, or source are present.
- [ ] Infers local source when `repository_path` is present.
- [ ] Infers public GitHub source for public URLs.
- [ ] Infers private GitHub source when visibility is private or `gh` auth is required.
- [ ] Records normalized input in the final report.

## Routing Checklist

- [ ] `resume_from` routes to existing document-run recovery.
- [ ] Documents route to `DocumentRunPipeline`.
- [ ] Attachments without documents still route to document-run with low document confidence.
- [ ] `repository_path` routes to local repository mode.
- [ ] `repository_url` plus `prepare_repository` routes to GitHub source preparation.
- [ ] No source package routes to `AutoDevPipeline`.
- [ ] Feedback files for a delivered run route to feedback reopen.
- [ ] Source preparation failure returns blocked evidence before planning.
- [ ] Real Codex remains opt-in.
- [ ] Real GitHub remains opt-in.
- [ ] Auto-merge remains opt-in.

## CLI Checklist

Supported examples:

```bash
python -m autodev.run --objective "build a retro platform game" --output .alchemy/runs/game
python -m autodev.run --objective "build a todo app" --document spec.md --output .alchemy/runs/todo
python -m autodev.run --document spec.md --repository-path ./repo --auto-browser-verify
python -m autodev.run --document spec.md --repository-url https://github.com/org/repo --prepare-repository
```

Required behavior:

- [ ] Exits `0` for completed delivery.
- [ ] Exits nonzero for failed, blocked, or needs-iteration delivery.
- [ ] Prints concise JSON summary.
- [ ] Writes `unified_run_report.json`.
- [ ] Links to underlying `document_run_report.json` or `autodev_report.json`.
- [ ] Keeps existing `autodev.demo_run` behavior unchanged.
- [ ] Keeps existing `autodev.document_run` behavior unchanged.

## API Checklist

Endpoint:

```http
POST /runs
```

Required response fields:

- [ ] `project_id`.
- [ ] `run_id`.
- [ ] `status`.
- [ ] `events_url`.
- [ ] `events_stream_url`.
- [ ] `delivery_url`.
- [ ] `artifact_manifest_url`.
- [ ] `source_mode`.
- [ ] `execution_mode`.
- [ ] `delivery_mode`.

Required behavior:

- [ ] Creates a project record.
- [ ] Attaches document and supporting file metadata.
- [ ] Preserves local repository path or GitHub URL.
- [ ] Starts an async run.
- [ ] Records event stream evidence.
- [ ] Returns API errors without orphaning invalid project state.
- [ ] Keeps staged endpoints unchanged.

## Browser Console Checklist

- [ ] One-shot run section exists.
- [ ] Objective input exists.
- [ ] Multiple document upload exists.
- [ ] Supporting file upload exists.
- [ ] GitHub URL input exists.
- [ ] Local repository path input exists.
- [ ] Source mode selection exists.
- [ ] Real Codex toggle exists.
- [ ] Real GitHub toggle exists.
- [ ] Auto browser verification toggle exists.
- [ ] Generated static CI toggle exists.
- [ ] Native UI test write toggle exists.
- [ ] Auto-merge toggle exists and is off by default.
- [ ] Run starts through `POST /runs`.
- [ ] UI navigates to the generated project/run evidence view.
- [ ] Existing evidence panels continue rendering.
- [ ] EventSource stream is used when available.
- [ ] Polling fallback remains available.

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

- [ ] One-line fallback generates a safe playable artifact.
- [ ] Document-only static web app routes through document-run.
- [ ] Local repository import routes through provider `local`.
- [ ] Feedback reopen routes to Debug Agent tasks.
- [ ] API one-shot run returns project/run IDs and delivery evidence.
- [ ] Browser one-shot UI smoke can start or simulate a run.
- [ ] Existing acceptance harness still passes.
- [ ] Existing local repository acceptance harness still passes.

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

- [ ] Unified CLI works for one-line fallback.
- [ ] Unified CLI works for document-only projects.
- [ ] Unified CLI works for local repositories.
- [ ] Unified API one-shot run works.
- [ ] Browser console one-shot mode works.
- [ ] Unified reports are written for all modes.
- [ ] Project type and source mode evidence are present.
- [ ] Readiness gates consume the same evidence as staged runs.
- [ ] Old CLIs and existing API endpoints remain compatible.
- [ ] Focused tests pass.
- [ ] Full unit suite passes.
- [ ] Acceptance harnesses pass.
- [ ] Documentation and README references are updated.

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
