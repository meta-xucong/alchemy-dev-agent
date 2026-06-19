# alchemy-dev-agent

`alchemy-dev-agent` is a specification repository and prototype runtime for an autonomous software development agent system.

Its purpose is to define the architecture, protocols, state model, task graph model, worker contract, GitHub execution flow, retry loop, and evaluation gates required to build a multi-agent autonomous development system. The included `runtime/` package is a usable CLI runtime with deterministic dry-run defaults and opt-in real Codex/GitHub adapters.

## Goal

The system is designed primarily for workflows where a user provides a complete project package:

- A development objective, such as a feature, product, system, or migration.
- A detailed development document, requirements brief, or acceptance specification.
- Supporting files such as API specs, database schemas, design notes, test plans, logs, or reference material.
- An optional public GitHub repository link, with private repositories supported as an explicit local `gh`-authenticated path.

The autonomous development system should then:

- Normalize the uploaded material into a project brief and context bundle.
- Decompose the objective into a dependency-aware task graph.
- Assign tasks to specialized agents.
- Use Codex CLI as an execution worker.
- Write code, run tests, fix failures, and report artifacts.
- Evaluate completion against explicit delivery criteria.
- Stop only after the system reaches delivery quality.

## Foundation

The design assumes three major implementation foundations:

- **OpenAI Agent SDK** for orchestration, agent roles, tool routing, and structured reasoning.
- **Codex CLI worker model** for isolated code execution, test execution, debugging, and patch generation.
- **GitHub-based execution loop** for repository synchronization, branch management, pull requests, CI checks, and review history.

## Core Model

The system is centered on:

- **Multi-agent planning and execution**: architecture, implementation, testing, debugging, and review are separate responsibilities.
- **Task graph execution**: work is represented as nodes with dependencies, status, ownership, and completion criteria.
- **Evaluation gate**: test success alone is insufficient; completion requires spec alignment, reviewer approval, and a final gate score of at least `0.85`.

## Repository Map

```text
docs/
  00_overview.md             System motivation and operating context.
  01_architecture.md         Layered architecture and component contracts.
  02_agent_design.md         Agent roles, inputs, outputs, and boundaries.
  03_task_graph.md           Task graph model and execution rules.
  04_codex_worker.md         Codex CLI worker contract.
  05_evaluation_system.md    Completion criteria and scoring.
  06_execution_loop.md       End-to-end execution loop.
  07_v2_development_plan.md  Document-driven v2 development plan.
  08_intake_and_context.md   Project intake and context bundle contract.
  09_ui_and_api_requirements.md
                              Planned v2 UI/API workflow and endpoints.
  10_v2_alignment_audit.md   V2 readiness and gap audit.
  11_v2_repository_context_runtime.md
                              V2.2 local repository context runtime.
  12_v2_public_github_source_runtime.md
                              V2.3 public GitHub clone/fetch runtime.
  13_v2_document_to_plan_runtime.md
                              V2.4 requirement extraction and task planning runtime.
  14_v2_plan_to_execution_handoff.md
                              V2.5 runtime handoff and worker package bridge.
  15_v2_document_run_cli.md
                              V2.6 document-driven dry-run CLI.
  16_v2_real_execution_preflight.md
                              V2.7 real execution flags and preflight checks.
  17_v2_local_api_runtime.md  V2.8 local JSON API and project service runtime.
  18_v2_browser_ui_async_runtime.md
                              V2.9 browser console, multipart upload, and async run jobs.
  19_v2_task_boundary_and_private_github_preflight.md
                              V2.10 task-boundary controls and private GitHub auth preflight.
  20_v2_private_github_source_adapter.md
                              V2.11 private GitHub source adapter.
  21_v2_acceptance_harness.md
                              V2.12 local acceptance harness.
  22_real_environment_validation.md
                              V2.13 real environment validation and current blocker.
  23_codex_cli_api_integration.md
                              V2.14 standalone Codex CLI installation and API integration.
  24_real_codex_worker_hardening.md
                              V2.15 real Codex worker file-boundary hardening.
  25_real_run_worktree_lifecycle.md
                              V2.16 isolated worktree lifecycle for real Codex runs.
  26_resumable_real_worker_execution.md
                              V2.17 explicit resume/retry recovery controls.
  27_real_delivery_validation.md
                              V2.18 real GitHub branch, PR, and CI validation.
  28_representative_delivery_probe.md
                              V2.19 representative real worker probe.
  29_v2_22_external_docs_only_delivery.md
                              V2.22 external docs-only repository closure plan.
  30_v2_23_perfect_delivery_optimization.md
                              V2.23 optimization plan from proof to product-grade delivery.
  31_v2_24_development_cycle_brain.md
                              V2.24 machine-checkable long-running development-cycle contract.
  32_v2_25_playability_feedback_loop.md
                              V2.25 semantic gameplay probe and feedback-loop gate.
  33_v2_26_semantic_web_and_feedback.md
                              V2.26 semantic web probes and feedback intake loop.
  34_v2_27_acceptance_scenario_browser_probes.md
                              V2.27 acceptance-scenario browser probes for CRUD/auth/upload/dashboard flows.
  35_v2_28_feedback_reopen_loop.md
                              V2.28 feedback-driven reopen and repair loop.
  36_v2_29_local_and_github_source_modes.md
                              V2.29 local and GitHub source-mode unification.
  37_v2_30_native_ui_acceptance_tests.md
                              V2.30 repository-native Playwright/Cypress acceptance test generation.
  38_v2_31_delivery_evidence_console.md
                              V2.31 human-reviewable delivery evidence console.
  39_v2_32_feedback_recovery_comparison.md
                              V2.32 source-vs-repair run comparison evidence.
  40_v2_33_artifact_file_previews.md
                              V2.33 safe artifact manifest and file preview contract.
  41_v2_34_delivery_readiness_gate.md
                              V2.34 evidence-consistent delivery readiness gate.
  42_v2_35_native_ui_test_repository_write.md
                              V2.35 controlled repository write switch for native UI tests.

specs/
  project_brief_schema.json  Document-driven intake schema.
  context_bundle_schema.json Planner-ready context bundle schema.
  state_schema_v2.json       Persistent project state schema.
  task_graph_schema.json     Task graph schema.

examples/
  one_line_game_demo.md       Current one-line generated game demo boundary.
  full_autodev_example.md    Example autonomous development run.
  document_driven_project_example.md
                              Example with documents, attachments, and GitHub repository input.
  external_docs_only_delivery_acceptance.md
                              V2.22 external docs-only delivery acceptance scenario.

runtime/
  control.py                 Task-boundary pause/stop control hook.
  orchestrator.py            Runtime entry point and control loop coordinator.
  task_graph_engine.py       Dependency resolution and graph status updates.
  agent_router.py            Task-to-agent mapping.
  codex_worker.py            Dry-run and real Codex subprocess worker adapter.
  evaluator.py               DONE gate scoring.
  github_flow.py             Dry-run and real git/gh execution flow adapter.
  handoff.py                 ProjectBrief/ContextBundle/TaskGraph to RuntimeState bridge.
  native_ui_tests.py         Playwright/Cypress acceptance test draft generator.
  recovery.py                Resume/retry recovery from persisted run state.
  state_manager.py           JSON state persistence.
  run_loop.py                CLI loop entry point.

intake/
  project_brief.py           V2.1 ProjectBrief builder and CLI.
  document_loader.py         Local file cataloging, hashing, summaries, and role inference.
  github_source.py           GitHub URL parsing and source normalization.
  github_runtime.py          Public GitHub clone/fetch/checkout source runtime.
  gh_auth.py                 Optional GitHub CLI auth preflight for private repositories.
  private_github_runtime.py  Private GitHub clone/fetch through local gh authentication.
  schema_validation.py       Local contract validation for intake payloads.

context/
  builder.py                 ContextBundle builder.
  repository_indexer.py      Local repository indexing and test profile detection.
  requirement_extractor.py   Deterministic requirement extraction and traceability.

planner/
  task_graph_builder.py      ContextBundle-to-task-graph planning.

autodev/
  acceptance_run.py          Local end-to-end acceptance harness.
  artifact_manifest.py       Safe run artifact manifest and preview content resolver.
  local_repository_acceptance.py
                             Local repository import and feedback-reopen acceptance harness.
  recovery_comparison.py     Source-vs-repair run comparison summaries.
  real_env_check.py          Real git/gh/Codex environment readiness report.
  real_delivery_validation.py
                              Controlled real GitHub delivery validation harness.
  document_run.py            Document-driven end-to-end dry-run CLI.
  preflight.py               Real execution environment preflight checks.
  demo_run.py                One-line local app generation demo.
  agents.py                  Deterministic local agent cluster for demo delivery.
  game_generator.py          Original retro platformer artifact generator.

server/
  project_service.py         Persistent project service for intake, planning, runs, and delivery reports.
  jobs.py                    Async run job records, controls, and events.
  api.py                     Standard-library local JSON API server.
  static/                    Browser console assets.

tests/
  test_runtime.py            Unit and smoke tests for the runtime contract.
  test_intake.py             Unit and CLI tests for v2.1 intake.
  test_autodev_pipeline.py   End-to-end local demo generation tests.
  test_repository_context.py Repository context runtime tests.
  test_document_to_plan.py   Requirement extraction and task graph planning tests.
  test_runtime_handoff.py    Plan-to-execution handoff tests.
  test_document_run_pipeline.py
                              Document-driven dry-run CLI tests.
  test_execution_preflight.py
                              Real execution preflight tests.
  test_api_server.py         Local API and project service tests.
```

## Runtime

The runtime is intentionally standard-library only. By default it runs in deterministic dry-run mode so local tests and smoke runs do not require credentials or mutate remotes.

Implemented runtime capabilities:

- Dependency-aware task graph scheduling.
- Task-to-agent routing.
- Bounded Codex worker task packages.
- Real Codex subprocess adapter with structured JSON parsing.
- Isolated git worktree lifecycle for real Codex document-runs.
- Deterministic dry-run worker for tests and demos.
- Retry/debug loop with generated debug tasks.
- Explicit resume/retry recovery from prior run state.
- Weighted evaluation gate across test health, spec alignment, graph completion, reviewer approval, and risk quality.
- GitHub execution evidence through dry-run records or real `git`/`gh` commands.
- Real PR/CI evidence collection through the V2.18 delivery validation harness.
- Safe delivery artifact manifests for screenshots, generated UI test drafts, artifact files, and generated CI previews.
- Evidence-consistent readiness gates so partial must coverage or failed browser probes require iteration.
- Controlled repository writes for generated Playwright/Cypress acceptance tests when a supported UI test framework is already present.
- Persistent JSON runtime state under `.alchemy/state.json`.

DONE requires final gate score `>= 0.85`, completed required graph nodes, passing verification evidence, reviewer approval, no hard failures, and GitHub execution evidence.

## V2.1 Intake

The v2.1 intake runtime can generate a schema-compatible `ProjectBrief` from local development documents, supporting files, and optional GitHub repository metadata.

Implemented intake capabilities:

- Document-driven and one-line fallback modes.
- Local file cataloging with deterministic file IDs and SHA-256 content hashes.
- File role inference for primary requirements, API specs, database schemas, design notes, test plans, reference code, data samples, and supplemental files.
- Explicit blockers for missing primary documents, unreadable files, unsupported required files, missing objectives, and invalid GitHub URLs.
- GitHub URL parsing for HTTPS and SSH repository URLs without network access.
- Public repository metadata by default, with optional private metadata flagging through `visibility=private` and `gh_auth_required=true`.
- ProjectBrief contract validation against `specs/project_brief_schema.json`.

Build a ProjectBrief:

```bash
python -m intake.project_brief \
  --objective "Add workspace support" \
  --document docs/workspace_feature_spec.md \
  --attachment docs/api_contract.yaml \
  --repository https://github.com/example/saas-dashboard \
  --validate
```

## Local One-Line Demo

The repository now includes a narrow local demo pipeline that exercises the v2 contracts end to end:

```text
one-line objective
  -> ProjectBrief
  -> ContextBundle
  -> TaskGraph
  -> deterministic local agent cluster
  -> generated local artifact
  -> static verification
  -> reviewer evidence
```

Generate an original retro platform game:

```bash
python -m autodev.demo_run \
  --objective "Build a small retro platform game" \
  --output .alchemy/generated/retro_platformer
```

The demo writes:

- `index.html`
- `autodev_report.json`

Important boundary: this is a deterministic local demo, not the full production autonomous development system. It proves the contract path and generated-artifact loop, but it does not yet use the Agent SDK, real Codex worker sessions, CI, or UI/API intake.

## V2.2 Repository Context

The repository context runtime can enrich a `ContextBundle` from a local repository checkout path.

Implemented repository context capabilities:

- File discovery with ignored directory filtering.
- File kind classification for source, test, docs, config, CI, assets, migrations, and unknown files.
- Language detection by file suffix.
- Package file detection.
- GitHub Actions and CI file detection.
- Package manager detection.
- Test, build, and lint command inference.
- ContextBundle population with repository map and test profile.
- Hard blockers for missing or invalid repository paths.

## V2.3 Public GitHub Source Runtime

The GitHub source runtime can prepare public repositories for intake without requiring `gh` login or stored tokens.

Implemented public source capabilities:

- Public GitHub repository clone into `RepositorySource.local_path`.
- Fetch and deterministic checkout for an existing local git checkout.
- Default repository visibility of `public` for ProjectBrief and CLI intake.
- Structured blockers for invalid repository paths, clone failures, fetch failures, and explicit private repository requests.
- CLI entry point for source preparation:

```bash
python -m intake.github_runtime \
  --repository https://github.com/example/saas-dashboard \
  --project-id proj_workspace_support \
  --target-branch main
```

Private repositories are still not the primary path for public-source runtime.
When `visibility=private` is selected on the public source runtime it returns
an explicit blocker instead of collecting tokens. Use
`intake.private_github_runtime` or document-run/API private preparation to
clone or fetch through the locally authenticated GitHub CLI.

## V2.4 Document-To-Plan Runtime

The document-to-plan runtime can turn parsed development documents and repository evidence into requirements and a task graph.

Implemented document-to-plan capabilities:

- Deterministic requirement extraction from structured Markdown, text, JSON, YAML, and YML inputs.
- Priority inference for `must`, `should`, and `could` requirements.
- Acceptance criteria extraction from document sections and explicit ProjectBrief criteria.
- Traceability from requirement to source document, related repository files, implementation task, verification task, and review task.
- Task graph generation with architecture, implementation, verification, and review nodes.
- Implementation task assignment to backend, frontend, test, documentation, or integration work based on requirement and repository-file signals.
- Preservation of the existing one-line generated-app demo graph.

## V2.5 Plan-To-Execution Handoff

The handoff runtime connects document-driven planning to the existing orchestrator loop.

Implemented handoff capabilities:

- Convert `ProjectBrief`, `ContextBundle`, and generated `TaskGraph` into `RuntimeState`.
- Preserve repository metadata, blockers, objective, task graph, and document-aware done criteria.
- Build `CodexWorkerInput` packages from generated task nodes.
- Include objective, assigned agent, upstream task IDs, acceptance criteria, related files, and verification commands in worker packages.
- Append a release task when needed so the existing DONE gate can record GitHub or dry-run delivery evidence.
- Run generated document-driven graphs through the `Orchestrator` dry-run loop to DONE.

## V2.6 Document-Driven Dry-Run CLI

The document-run CLI provides a single local command for the document-driven pipeline:

```bash
python -m autodev.document_run \
  --objective "Add workspace support" \
  --document workspace_feature_spec.md \
  --repository https://github.com/example/saas-dashboard \
  --repository-path .alchemy/projects/proj_workspace_support/repo \
  --output .alchemy/document_run
```

The command emits a JSON report containing ProjectBrief, ContextBundle, TaskGraph, worker packages, RuntimeState, and final dry-run status. It proves the contract path can execute end to end without requiring credentials or mutating a remote repository.

V2.7 adds controlled real-execution switches:

```bash
python -m autodev.document_run \
  --objective "Add workspace support" \
  --document workspace_feature_spec.md \
  --repository https://github.com/example/saas-dashboard \
  --repository-path .alchemy/projects/proj_workspace_support/repo \
  --real-codex \
  --real-github
```

The CLI records preflight checks for repository path, `git`, Codex, and `gh`. Missing required tools block real execution before worker tasks start.

## V2.8 Local API Runtime

The local API wraps the document-driven runtime with project persistence and HTTP endpoints:

```bash
python -m server.api --host 127.0.0.1 --port 8765 --storage-root .alchemy/server
```

Core implemented endpoints include:

```text
POST /projects
GET  /projects/{project_id}
POST /projects/{project_id}/files
GET  /projects/{project_id}/files
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

The API accepts local file paths through `documents`, `attachments`, or a UI-oriented `files` list. V2.9 builds browser upload, async run jobs, and a local console on top of this backend.

## V2.29 Local And GitHub Source Modes

The project source can now be provided in either mode:

- `repository_path` only: local repository import, recorded as `provider = local`
- `repository`: GitHub repository import, recorded as `provider = github`

Both modes converge into the same intake, context, task graph, runtime, feedback
reopen, and delivery contracts. GitHub mode may clone/fetch first; local mode
starts from an existing directory and does not require a GitHub URL.

Run the local-only source-mode acceptance harness:

```bash
python -m autodev.local_repository_acceptance \
  --output .alchemy/local_repository_acceptance
```

Optional local browser verification:

```bash
python -m autodev.local_repository_acceptance \
  --output .alchemy/local_repository_acceptance \
  --auto-browser-verify
```

See `docs/36_v2_29_local_and_github_source_modes.md`.

## V2.9 Browser Console And Async Runs

The local API server now serves an operational browser console:

```text
http://127.0.0.1:8765/
```

The console can create a project, upload files, build a task graph, start an async run, request pause/resume/stop, show events, and show delivery output.

Use a free port if `8765` is already occupied:

```bash
python -m server.api --host 127.0.0.1 --port 18765 --storage-root .alchemy/server
```

Async run start:

```json
{
  "async": true
}
```

Multipart upload is supported through:

```text
POST /projects/{project_id}/files
Content-Type: multipart/form-data
```

Pause/resume/stop are persisted controls. V2.10 upgrades those controls into task-boundary runtime decisions: stop requests prevent the next task from dispatching and record blocker `B-RUN-STOPPED`; pause requests stop before the next task and record `run_paused`.

Private GitHub preflight is available without storing tokens:

```bash
python -m intake.gh_auth
```

Document-run private repository checks:

```bash
python -m autodev.document_run \
  --objective "Add workspace support" \
  --document workspace_feature_spec.md \
  --repository https://github.com/example/private-repo \
  --repository-visibility private
```

Prepare a private repository source through local `gh` authentication:

```bash
python -m intake.private_github_runtime \
  --repository https://github.com/example/private-repo \
  --project-id proj_private \
  --target-branch main
```

## V2.12 Local Acceptance Harness

Run the current local product path end to end:

```bash
python -m autodev.acceptance_run --output .alchemy/acceptance
```

The harness creates a fixture repository and development document, builds intake/context/task graph artifacts, starts an async run, collects events, checks delivery, and writes `.alchemy/acceptance/acceptance_report.json`.

## V2.13 Real Environment Validation

Check whether this machine can run real Codex/GitHub execution:

```bash
python -m autodev.real_env_check --output .alchemy/real_env_check
```

The original default-path validation was blocked because Windows resolved `codex` to a WindowsApps desktop package path that failed with access denied. V2.14 resolves this with an explicit standalone CLI path. See `docs/22_real_environment_validation.md`.

## V2.14 Codex CLI API Integration

The previous WindowsApps Codex entry point can be bypassed by installing the standalone CLI outside this repository:

```powershell
$env:CODEX_NON_INTERACTIVE = "1"
$env:CODEX_INSTALL_DIR = "D:\AI\Tools\CodexCLI\bin"
irm https://chatgpt.com/codex/install.ps1 | iex
```

Validate the explicit executable path:

```powershell
python -B -m autodev.real_env_check `
  --output .alchemy\real_env_check `
  --codex-executable "D:\AI\Tools\CodexCLI\bin\codex.exe"
```

For one-click browser artifact acceptance, require browser automation during the
same check:

```powershell
python -m pip install -e ".[browser]"
python -m playwright install chromium
```

```powershell
python -B -m autodev.real_env_check `
  --output .alchemy\real_env_check `
  --codex-executable "D:\AI\Tools\CodexCLI\bin\codex.exe" `
  --require-browser
```

The API also exposes:

```text
POST /environment/check
```

Run payloads can pass:

```json
{
  "real_codex": true,
  "codex_executable": "D:\\AI\\Tools\\CodexCLI\\bin\\codex.exe",
  "require_browser": true
}
```

The browser console includes the same Codex CLI executable field. When
`Auto browser verify` is checked, the environment check also treats browser
automation readiness as required. Dry-run mode remains the default; real Codex
and real GitHub execution require explicit flags.

## V2.15 Real Codex Worker Hardening

Real Codex worker execution now carries a machine-enforced file boundary:

- Worker packages include `allowed_files`.
- Architecture, review, and test tasks are read-only by default.
- Implementation tasks may edit only task `relevant_files`.
- The adapter audits `git status --porcelain` before and after `codex exec`.
- Out-of-scope file changes are rolled back and the task is marked failed.
- Timeout cleanup rolls back task-local changes.

See `docs/24_real_codex_worker_hardening.md`.

## V2.16 Real-Run Worktree Lifecycle

Document-driven real Codex runs now default to an isolated git worktree:

- The source repository must be a clean git repository root.
- Preflight runs before worktree creation.
- The runtime creates a run-local branch and worktree under the output directory.
- Context indexing, task graph planning, worker packages, and orchestrator execution all use the worktree path.
- The source repository is not the direct mutation target.
- The worktree is kept by default for audit.

Example:

```powershell
python -m autodev.document_run `
  --objective "Implement the requested feature" `
  --document feature_spec.md `
  --repository-path D:\path\to\repo `
  --real-codex `
  --codex-executable "D:\AI\Tools\CodexCLI\bin\codex.exe"
```

Optional controls:

```text
--no-isolated-worktree   Run directly in the repository path.
--cleanup-worktree       Remove the worktree and branch after the run.
--worktree-branch-prefix Branch prefix for isolated real runs.
```

API run payloads can pass `isolate_real_run`, `keep_worktree`, and `worktree_branch_prefix`.

See `docs/25_real_run_worktree_lifecycle.md`.

## V2.17 Resumable Worker Execution

Document-run and API execution can now resume from a prior run state:

```powershell
python -m autodev.document_run `
  --objective "Implement the requested feature" `
  --document feature_spec.md `
  --repository-path D:\path\to\repo `
  --output .alchemy\document_run_resume `
  --resume-from .alchemy\document_run_previous
```

The recovery controller loads the old state, clears operator stop blockers,
resets retryable failed/blocked/active tasks, records a recovery checkpoint, and
then hands the recovered state back to the normal orchestrator.

API runs can pass:

```json
{
  "async": true,
  "resume_from_run_id": "run_001"
}
```

The browser `Resume` control starts a new recovery run when the source run is
paused and switches monitoring to the returned `resumed_run_id`.

See `docs/26_resumable_real_worker_execution.md`.

## V2.18 Real Delivery Validation

The repository includes a controlled real GitHub validation harness:

```bash
python -m autodev.real_delivery_validation \
  --repository-path . \
  --output .alchemy/real_delivery_validation \
  --branch agent/alchemy-real-delivery-validation \
  --base-branch master
```

The harness defaults to an isolated git worktree, creates or reuses a validation
PR, waits for PR checks by default, and records CI status through `gh pr checks`.
Failed, still-pending, or missing CI status blocks the validation report instead
of being treated as successful delivery when CI collection is enabled. Use
`--ci-wait-seconds` and
`--ci-poll-interval-seconds` to tune that wait. It writes:

```text
.alchemy/real_delivery_validation/real_delivery_validation_report.json
```

The repository also includes `.github/workflows/ci.yml`, which runs the unit
test suite and JSON spec parsing for pushes and pull requests.

See `docs/27_real_delivery_validation.md`.

## V2.19 Representative Real Delivery Probe

V2.19 validates the document-driven real worker path with a bounded
documentation task. The run used a local development document, an isolated
worktree, a real Codex worker for the implementation task, deterministic static
document inspection for the verification task, deterministic review evidence,
and dry-run GitHub delivery evidence. The runtime reached `DONE condition met`
with a final gate score of `0.88` while the source checkout stayed clean.

See `docs/28_representative_delivery_probe.md`.

## V2.22 External Docs-Only Delivery Closure

A real external test against
`https://github.com/meta-xucong/-super-mario-test` proved that Alchemy can turn a
repository containing only a development document into a playable browser game
delivery. The V2.22 implementation now includes:

- document-dominant planning so parsed primary docs cannot be downgraded to the
  one-line generated-artifact fallback
- richer Chinese and outline-style requirement extraction
- scaffold-aware planning for empty web game repositories
- single-task grouping for complete docs-only web game scaffold delivery
- deterministic static HTML/canvas artifact verification
- explicit no-CI waiver evidence when PR checks are intentionally unavailable
- local git commit identity fallback for real GitHub delivery
- release branch binding to the isolated worktree branch

The latest real target delivery is
[`meta-xucong/-super-mario-test#2`](https://github.com/meta-xucong/-super-mario-test/pull/2).
It generated an original retro platformer Level 1 with modular files under
`index.html`, `src/`, and `tests/static_checks.js`, then passed static artifact
checks and browser playability smoke verification.

See `docs/29_v2_22_external_docs_only_delivery.md` and
`examples/external_docs_only_delivery_acceptance.md`.

## V2.23 Perfect Delivery Optimization

V2.23 captures the remaining work after the successful external docs-only game
delivery. It keeps the original objective unchanged and focuses on moving the
runtime from a successful proof to stable product-grade one-click delivery.

Primary improvements:

- built-in browser artifact verification with screenshots, keyboard/action
  smoke checks, console-error capture, and pixel-diff evidence
- artifact profiles such as `canvas_game`, `static_web_app`, `node_project`,
  `python_project`, and `documentation_only`
- managed real-worker process lifecycle with timeout cleanup and recovery
- per-requirement coverage matrix tied to changed files and evidence
- optional generated CI workflows for docs-only static app repositories
- productized final delivery reports and browser-console evidence display
- polished multi-file upload and GitHub intake workflow

See `docs/30_v2_23_perfect_delivery_optimization.md`.

Current V2.23 implementation status:

- `artifact_report` now records the detected artifact profile and static
  verification result for document-runs.
- Browser evidence can be imported from externally captured screenshots, or
  captured automatically with `--auto-browser-verify` when Playwright is
  installed and browser binaries are available.
- Automatic browser verification starts a local static server, captures initial
  and post-interaction screenshots, computes pixel diff, and fails on console
  errors or blank/static canvas-game evidence.
- Canvas-game browser verification now also requires a deterministic
  `window.__ALCHEMY_GAME_TEST__` hook and a semantic gameplay probe for
  movement, jump, victory, and restart behavior.
- Static-web browser verification records semantic interaction evidence for
  forms, buttons, inputs, and visible DOM state changes when controls exist.
- Real Codex worker runs now persist worker lifecycle records with task id, PID,
  timeout, process-group, termination, and cleanup evidence under the run's
  worker evidence directory.
- Document-run reports now include `requirement_coverage`, mapping each
  extracted requirement to planned tasks, implementation files, verification
  evidence, and missing/partial/covered status.
- Document-run reports now include `native_ui_tests`, converting generated
  CRUD/auth/upload/dashboard acceptance scenarios into Playwright or Cypress
  test drafts when a browser artifact or native UI test framework is detected.
- API delivery responses now include `delivery_evidence`, a display-ready
  summary for final gate, requirements, browser probes, native UI tests,
  GitHub/CI, blockers, next actions, and development-cycle status.
- Feedback reopen delivery responses now include `recovery_comparison`, showing
  source-vs-repair deltas for score, coverage, must gaps, blockers, probes, and
  CI.
- Real GitHub document-runs can generate a lightweight static web CI workflow
  for docs-only canvas/static artifacts immediately before release, so the
  workflow is included in the branch/PR instead of only appearing in the final
  report.
- `delivery_report` summarizes final gate status, PR/branch/commit/CI,
  artifact evidence, semantic/gameplay probe status, requirement coverage,
  generated CI, blockers, worker lifecycle evidence, workspace, preflight, and
  next actions.
- `development_cycle` now maps the manual engineering loop into machine
  evidence: long task state, document reading, central-brain refinement, phase
  planning, execution, audit, testing, iteration, full review, simulated
  acceptance, real delivery, and merge/waiver.
- Real GitHub delivery supports explicit `--auto-merge`; it remains off by
  default and only attempts merge after passing CI.

See also `docs/32_v2_25_playability_feedback_loop.md` for the semantic
playability gate added after manual testing found that a rendered game can still
contain product-level bugs.
See `docs/33_v2_26_semantic_web_and_feedback.md` for the next extension:
semantic probes for ordinary web apps and feedback files as requirement deltas.
See `docs/34_v2_27_acceptance_scenario_browser_probes.md` for deterministic
browser scenarios generated from detailed acceptance documents.
See `docs/35_v2_28_feedback_reopen_loop.md` for reopening delivered runs from
playtest or acceptance feedback and routing fixes through Debug Agent tasks.
See `docs/37_v2_30_native_ui_acceptance_tests.md` for converting generated
acceptance scenarios into repository-native Playwright/Cypress test drafts.
See `docs/38_v2_31_delivery_evidence_console.md` for the browser-console
delivery evidence view that makes run completion human-reviewable.
See `docs/39_v2_32_feedback_recovery_comparison.md` for feedback repair
comparison evidence.

Run a smoke execution:

```bash
python -m runtime.run_loop --objective "build a todo app with login" --reset
```

Run with a real Codex worker:

```bash
python -m runtime.run_loop \
  --objective "implement the requested feature" \
  --project /path/to/repo \
  --real-codex
```

Run with real GitHub branch/commit/push/PR flow:

```bash
python -m runtime.run_loop \
  --objective "implement the requested feature" \
  --project /path/to/repo \
  --real-codex \
  --real-github \
  --github-ci-wait-seconds 120 \
  --github-ci-poll-interval-seconds 10
```

`--real-github` expects local `git` and `gh` authentication to be available.
When CI collection is enabled, failed, pending, or missing CI status blocks the
release gate. Use `--no-github-ci` only for repositories where PR check evidence
is intentionally unavailable. Without real GitHub mode, the runtime records
dry-run branch, commit, PR, and CI evidence instead.

Run tests:

```bash
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests
```

## Non-Goals

This repository does not yet implement:

- Deep PDF/DOCX document parser pipeline.
- Proven private GitHub end-to-end delivery against a real private repository.
- Deep code summarization and semantic requirement-to-file mapping beyond deterministic file/path signals.
- Proven real external rerun that combines generated static CI, automatic
  browser verification, and terminal GitHub check collection in one PR.
- Browser-console visualization for every development-cycle checklist step.
- Artifact file serving for screenshot and generated native UI test previews.
- Domain-specific semantic probes for every app category beyond the current
  canvas-game and generic static-web probes.
- Agent SDK runtime code.
- GitHub App integration.
- GitHub Actions log ingestion.
- Hard cancellation of an already-running Codex subprocess.
- Production database, asynchronous worker daemon process, hard already-running worker cancellation, or multi-user access control.

Those systems should be implemented against the protocols defined here.
