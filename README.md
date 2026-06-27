# alchemy-dev-agent

`alchemy-dev-agent` is a specification repository and prototype runtime for an autonomous software development agent system.

Its purpose is to define the architecture, protocols, state model, task graph model, worker contract, GitHub execution flow, retry loop, central review, auto-iteration contracts, and evaluation gates required to build a multi-agent autonomous development system. The included `runtime/` package is a usable CLI runtime with deterministic dry-run defaults and opt-in real Codex/GitHub adapters.

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
- Convert review gaps into repair plans and follow-up iterations when the result is not ready.
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
- **Central review and auto-iteration**: final evidence is summarized into a `handoff|iterate|blocked|continue` decision; repairable gaps become structured repair plans for the next run.

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
  43_v2_36_repair_suggestions.md
                              V2.36 comparison-driven Debug Agent repair suggestions.
  44_v2_37_graph_and_coverage_visualization.md
                              V2.37 browser graph and requirement coverage visualization.
  45_v2_38_production_gap_closure.md
                              V2.38 file lifecycle API, SSE event stream, contradiction warnings, and code summaries.
  46_v2_39_unified_entrypoint.md
                              V2.39 unified product entrypoint and project-type runtime plan.
  47_v2_40_unified_preflight.md
                              V2.40 unified run preflight and start-readiness gate.
  48_v2_41_unified_acceptance_harness.md
                              V2.41 unified acceptance harness for product-facing modes.
  49_v2_42_real_readiness_probe.md
                              V2.42 non-mutating real Codex/GitHub readiness probe.
  50_v2_43_controlled_real_worker_smoke.md
                              V2.43 controlled local real Codex worker smoke.
  51_v2_44_real_document_run_local_smoke.md
                              V2.44 controlled real document-run local smoke.
  52_v2_45_real_probe_evidence_index.md
                              V2.45 real probe evidence index.
  53_v2_46_controlled_real_github_pr_probe.md
                              V2.46 controlled real GitHub PR probe.
  54_v2_47_real_unified_delivery_run.md
                              V2.47 unified full-delivery validation harness.
  55_v2_48_pr_lifecycle_controls.md
                              V2.48 PR review and cleanup lifecycle controls.
  56_v2_49_evidence_package_export.md
                              V2.49 evidence package export for review/archival.
  57_v2_50_benchmark_suite.md
                              V2.50 deterministic benchmark suite.
  58_v2_51_evidence_api_service.md
                              V2.51 evidence index/package service API.
  59_v2_52_benchmark_regression_gate.md
                              V2.52 benchmark regression comparison gate.
  60_v2_53_benchmark_regression_api.md
                              V2.53 benchmark regression service/API endpoint.
  61_v2_54_evidence_readiness_gate.md
                              V2.54 final evidence readiness gate.
  62_v2_55_evidence_console_redesign.md
                              V2.55 beginner-readable evidence console and i18n controls.
  63_v2_56_configuration_first_source_intake.md
                              V2.56 configuration-first source intake.
  64_v2_57_beginner_delivery_and_progress.md
                              V2.57 beginner progress and delivery actions.
  65_v2_58_beginner_first_console.md
                              V2.58 beginner-first console simplification.
  66_v2_59_five_issue_experience_audit.md
                              V2.59 five-issue beginner experience audit.
  67_v2_60_project_workspace_history_and_score_diagnosis.md
                              V2.60 project workspace, history, and score diagnosis.
  68_v2_61_central_review_agent.md
                              V2.61 central review decision layer.
  69_v2_62_central_auto_iteration_controller.md
                              V2.62 central auto-iteration controller plan.
  70_v2_62_repair_plan_contract.md
                              V2.62 repair plan contract.
  71_v2_62_acceptance_and_test_plan.md
                              V2.62 acceptance and test plan.
  72_v2_64_repair_convergence_gate.md
                              V2.64 target-file repair convergence gate.
  73_v2_65_full_roadmap_execution_mode.md
                              V2.65 full-roadmap execution mode.
  74_v2_66_project_analysis_gate.md
                              V2.66 mandatory pre-development project analysis gate.
  75_v2_67_entry_document_reference_expansion.md
                              V2.67 entry prompt referenced-document expansion for full-roadmap analysis.
  76_v2_68_project_analysis_false_blocker_and_phase_hardening.md
                              V2.68 false-blocker and phase-extraction hardening for full-roadmap analysis.
  77_v2_69_runtime_artifact_boundary_hardening.md
                              V2.69 runtime artifact boundary hardening.
  78_v2_70_phase_gate_auto_repair.md
                              V2.70 automatic phase-gate repair.
  79_v2_71_final_audit_test_convergence.md
                              V2.71 final audit and test convergence.
  80_v2_72_one_shot_document_readiness_hardening.md
                              V2.72 one-shot target document readiness hardening.
  81_v2_73_large_refactor_execution_mode.md
                              V2.73 large-refactor execution mode and boundary model.
  82_v2_74_alchemy_stability_hardening.md
                              V2.74 package-manager, frontend setup, and debug convergence hardening.
  83_v2_75_windows_worker_command_hardening.md
                              V2.75 Windows PowerShell worker command hardening.
  84_v2_76_windows_go_execution_hardening.md
                              V2.76 Windows Go execution hardening.
  85_v2_77_windows_spaced_path_hardening.md
                              V2.77 Windows spaced-path command hardening.
  86_v2_78_nonpartial_blocker_stop.md
                              V2.78 non-partial blocker dispatch-stop hardening.
  87_v2_79_existing_blocker_resume_stop.md
                              V2.79 existing non-partial blocker resume-stop hardening.
  88_v2_80_go_worker_env_bootstrap.md
                              V2.80 real-worker Go environment bootstrap.
  89_v2_81_technical_blocker_phase_repair.md
                              V2.81 technical-blocker phase repair handoff.
  90_v2_82_resume_attempt_order_hardening.md
                              V2.82 resume attempt ordering hardening.
  91_v2_83_windows_real_codex_policy_bypass.md
                              V2.83 Windows real Codex policy bypass and plugin-sync suppression.
  92_v2_84_worker_timeout_stop.md
                              V2.84 worker timeout stop and debug replay prevention.
  93_v2_85_terminal_active_resume_skip.md
                              V2.85 terminal active attempt resume skip.
  94_v2_86_package_lock_boundary_expansion.md
                              V2.86 package lockfile boundary expansion.
  95_v2_87_dead_debug_resume_skip.md
                              V2.87 dead debug active attempt resume skip.
  96_billing_core_crm_supervision_assessment.md
                              Billing Core CRM supervision assessment and delivery gates.
  97_v2_88_focused_phase_repair_resume.md
                              V2.88 focused blocked-phase repair resume handoff.
  98_v2_89_repair_scope_handoff.md
                              V2.89 repair scope handoff and frontend large-refactor recovery.
  99_v2_90_codex_usage_limit_blocker.md
                              V2.90 local Codex usage-limit blocker classification.
  100_v2_91_usage_limit_false_positive.md
                              V2.91 usage-limit false positive guard.
  101_v2_92_frontend_api_caller_repair_scope.md
                              V2.92 frontend API caller repair scope expansion.
  102_v2_93_timeout_repair_split_frontend_copy.md
                              V2.93 timeout repair split for frontend copy sweep.
  103_v2_94_disk_repair_brief_resume.md
                              V2.94 disk repair brief resume handoff.
  104_v2_95_preserve_completed_repair_tasks.md
                              V2.95 completed repair task preservation.

specs/
  project_brief_schema.json  Document-driven intake schema.
  context_bundle_schema.json Planner-ready context bundle schema.
  state_schema_v2.json       Persistent project state schema.
  task_graph_schema.json     Task graph schema.
  central_review_schema.json Central review evidence schema.
  repair_plan_schema.json    Repair plan schema for auto-iteration.
  auto_iteration_report_schema.json
                              Auto-iteration report schema.

examples/
  one_line_game_demo.md       Current one-line generated game demo boundary.
  full_autodev_example.md    Example autonomous development run.
  document_driven_project_example.md
                              Example with documents, attachments, and GitHub repository input.
  external_docs_only_delivery_acceptance.md
                              V2.22 external docs-only delivery acceptance scenario.
  v2_39_unified_entrypoint_checklist.md
                              V2.39 implementation and acceptance checklist.
  central_auto_iteration_example.md
                              V2.62 central review to repair-run example.

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
  unified_acceptance.py       Unified entrypoint acceptance harness across one-line, docs-only, local, and GitHub URL modes.
  real_readiness_probe.py    Non-mutating real Codex/GitHub environment readiness probe.
  real_worker_smoke.py       Controlled disposable local real Codex worker smoke.
  real_document_run_smoke.py Controlled real Codex document-run smoke on a local fixture repository.
  real_probe_index.py        Evidence indexer for real readiness, worker, document-run, and GitHub PR reports.
  real_unified_delivery.py   Unified full-delivery validation harness and gate report.
  github_pr_lifecycle.py     Safe inspect, ready, close, and branch cleanup controls for PRs.
  evidence_package.py        Evidence package exporter with manifest and Markdown summary.
  benchmark_suite.py         Deterministic dry-run benchmark matrix for key delivery paths.
  benchmark_regression.py    Benchmark report comparison and regression gate.
  evidence_readiness.py      Final evidence readiness aggregation gate.
  repair_suggestions.py       Debug Agent repair suggestions from recovery comparison evidence.
  recovery_comparison.py     Source-vs-repair run comparison summaries.
  real_env_check.py          Real git/gh/Codex environment readiness report.
  real_delivery_validation.py
                              Controlled real GitHub delivery validation harness.
  document_run.py            Document-driven end-to-end dry-run CLI.
  preflight.py               Real execution environment preflight checks.
  unified_preflight.py       Request-level preflight for CLI, API, and UI unified runs.
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
- Central review evidence that turns run status, delivery evidence, requirement coverage, and development-cycle progress into a beginner-readable next decision.
- Controlled repository writes for generated Playwright/Cypress acceptance tests when a supported UI test framework is already present.
- Persistent JSON runtime state under `.alchemy/state.json`.

DONE requires final gate score `>= 0.85`, completed required graph nodes, passing verification evidence, reviewer approval, no hard failures, and GitHub execution evidence.

The V2.62 documentation package defines the next contract: central review decisions that require iteration will become repair plans and feedback-reopen runs instead of waiting for a human to translate the gaps manually.

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

The unified product CLI also supports request-level preflight without creating
or executing a project:

```bash
python -m autodev.run \
  --objective "Build from the supplied project documents" \
  --document docs/product_spec.md \
  --repository-path ./target-repo \
  --preflight-only
```

This writes `unified_preflight_report.json`. Normal unified runs write the same
report before execution and block impossible combinations, such as real GitHub
delivery without real Codex execution.

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
POST /runs/preflight
POST /runs
```

The API accepts local file paths through `documents`, `attachments`, or a UI-oriented `files` list. V2.9 builds browser upload, async run jobs, and a local console on top of this backend.

`POST /runs/preflight` validates the exact unified request without creating a
project. `POST /runs` runs the same preflight first and returns
`unified_preflight_blocked` before project creation when required source,
worker, GitHub, or delivery evidence is missing.

Run the unified product-path acceptance harness locally:

```bash
python -m autodev.unified_acceptance --output .alchemy/unified_acceptance
```

It verifies one-line fallback, document-only generated repository, local
repository package, and GitHub URL dry-run metadata modes through the same
preflight/start/evidence contracts.

Run a non-mutating real-environment readiness probe:

```bash
python -m autodev.real_readiness_probe \
  --output .alchemy/real_readiness \
  --codex-executable codex \
  --summary
```

This checks local `git`, `gh`, `gh auth status`, Codex CLI, and real-mode unified
request preflight without starting workers or opening pull requests.

Run a controlled local real Codex worker smoke after readiness passes:

```bash
python -m autodev.real_worker_smoke \
  --output .alchemy/real_worker_smoke \
  --codex-executable codex \
  --timeout-seconds 300 \
  --summary
```

This uses a disposable local fixture repository and does not touch GitHub.

Run a controlled real document-run smoke after the worker smoke passes:

```bash
python -m autodev.real_document_run_smoke \
  --output .alchemy/real_document_run_smoke \
  --codex-executable codex \
  --timeout-seconds 300 \
  --summary
```

This exercises document intake, task planning, real Codex implementation, local
verification, and dry-run GitHub delivery evidence on a disposable local
repository.

Index real probe evidence after running readiness/smoke checks:

```bash
python -m autodev.real_probe_index \
  --root .alchemy \
  --output .alchemy/real_probe_index.json \
  --summary
```

This creates a compact review index for real readiness, worker smoke, and
document-run smoke reports.

After explicit approval for a mutating GitHub probe, run a controlled draft PR
validation:

```bash
python -m autodev.real_delivery_validation \
  --repository-path . \
  --output .alchemy/v2_46_real_github_pr_probe \
  --branch agent/alchemy-v2-46-pr-probe \
  --base-branch master \
  --ci-wait-seconds 120 \
  --ci-poll-interval-seconds 10
```

The probe creates a real remote validation branch and draft pull request, keeps
auto-merge off, and writes
`.alchemy/v2_46_real_github_pr_probe/real_delivery_validation_report.json`.
`real_probe_index` includes that report as `real_github_pr_probe` evidence.

See `docs/53_v2_46_controlled_real_github_pr_probe.md`.

Run the V2.47 full-delivery validation harness:

```bash
python -m autodev.real_unified_delivery \
  --objective "Add workspace support" \
  --document spec.md \
  --repository-path ./repo \
  --output .alchemy/real_unified_delivery \
  --summary
```

It drives the unified CLI, reads the generated preflight/run/document reports,
optionally aggregates `real_probe_index`, and writes
`.alchemy/real_unified_delivery/real_unified_delivery_report.json` with delivery
gates for preflight, command execution, final gate, review readiness, real Codex
worker evidence, real GitHub PR evidence, and browser verification evidence.

See `docs/54_v2_47_real_unified_delivery_run.md`.

Inspect or safely transition a delivery PR:

```bash
python -m autodev.github_pr_lifecycle \
  --selector 3 \
  --action inspect \
  --output .alchemy/github_pr_lifecycle \
  --summary
```

Mutating actions such as `ready` and `close --delete-branch` require
`--confirm`; without it the command records `status=planned` and does not call
the mutating GitHub operation.

See `docs/55_v2_48_pr_lifecycle_controls.md`.

Export a compact evidence package:

```bash
python -m autodev.evidence_package \
  --root .alchemy/v2_47_real_unified_delivery \
  --root .alchemy/v2_48_pr_lifecycle_inspect \
  --output .alchemy/v2_49_evidence_package \
  --summary
```

The package writes `evidence_package_manifest.json`, `summary.md`, and copied
known JSON reports under `reports/`.

See `docs/56_v2_49_evidence_package_export.md`.

Run deterministic dry-run benchmarks:

```bash
python -m autodev.benchmark_suite \
  --output .alchemy/benchmark_suite \
  --summary
```

Use `--skip-unified-acceptance` for a faster local smoke.

See `docs/57_v2_50_benchmark_suite.md`.

Compare benchmark runs for regressions:

```bash
python -m autodev.benchmark_regression \
  --baseline .alchemy/benchmark_suite_previous/benchmark_suite_report.json \
  --current .alchemy/benchmark_suite/benchmark_suite_report.json \
  --output .alchemy/benchmark_regression \
  --summary
```

The regression gate blocks missing baseline-passed scenarios, newly failed
scenarios, increased failed-scenario counts, and current benchmark status other
than `passed`.

See `docs/59_v2_52_benchmark_regression_gate.md`.

Aggregate final evidence readiness:

```bash
python -m autodev.evidence_readiness \
  --evidence-index .alchemy/real_probe_index.json \
  --evidence-package .alchemy/evidence_package/evidence_package_manifest.json \
  --benchmark-regression .alchemy/benchmark_regression/benchmark_regression_report.json \
  --output .alchemy/evidence_readiness \
  --summary
```

This produces one `ready|blocked` evidence gate over indexed evidence,
review packages, and benchmark regression results.

See `docs/61_v2_54_evidence_readiness_gate.md`.

Expose evidence through the local API service:

```bash
python -m server.api --port 18739
```

Then use:

- `GET /evidence/index`
- `POST /evidence/index`
- `POST /evidence/package`
- `POST /evidence/benchmark-regression`
- `POST /evidence/readiness`

These endpoints reuse the same real-probe index and evidence-package contracts
as the CLI tools. The benchmark regression endpoint reuses the V2.52 comparison
gate, and the readiness endpoint reuses the V2.54 aggregate evidence gate. They
do not run Codex, mutate GitHub, or rerun delivery.

See `docs/58_v2_51_evidence_api_service.md`.
See `docs/60_v2_53_benchmark_regression_api.md`.

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
- Recovery comparisons now include deterministic Debug Agent `repair_suggestions`
  for newly missing or partial must requirements, uncovered feedback must items,
  score or coverage regressions, new blockers, and regressed probes.
- The browser console now renders task graph statistics, agent/status
  distribution, task cards, requirement coverage statistics, and a compact
  requirement coverage matrix in addition to raw JSON evidence.
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

## V2.75 Windows Worker Command Hardening

V2.75 adds worker-prompt guidance for real Windows PowerShell runs so Codex
spends less effort on shell-formulation mistakes during large repository
migrations. The prompt now explicitly tells the worker to:

- confirm uncertain file paths from repository evidence such as `rg --files`;
- avoid wildcard paths as literal arguments to `rg` or `Get-Content`;
- use `$lines[start..end]` instead of `Select-Object -Index start..end` for
  PowerShell line-range reads;
- avoid inline shell commands with unsafe unescaped `|` when a simpler split
  command will do;
- treat shell globbing, quoting, and path-syntax failures as command issues to
  reformulate before drawing repository conclusions.

See `docs/83_v2_75_windows_worker_command_hardening.md`.

## V2.76 Windows Go Execution Hardening

V2.76 extends the Windows worker prompt specifically for Go verification on
Windows hosts. The prompt now explicitly tells the worker to:

- confirm the active Go module root from repository evidence before running Go
  commands;
- run Go verification from the nested module directory when `go.mod` lives
  under a path such as `backend/`;
- avoid inline `go test -run` alternation with `|` in PowerShell and prefer
  separate test invocations;
- prefer an already populated writable `GOMODCACHE` when one exists;
- avoid launching parallel `go test` processes against a fresh shared module
  cache on Windows.

See `docs/84_v2_76_windows_go_execution_hardening.md`.

## V2.77 Windows Spaced-Path Hardening

V2.77 extends the Windows worker prompt for repositories and helper scripts
whose absolute paths contain spaces. The prompt now explicitly tells the worker
to:

- quote Windows paths that contain spaces before passing them to scripts or
  flags such as `--project`;
- prefer setting the working directory instead of embedding long absolute paths
  when a command already supports a repo-local form;
- treat quoting-related path failures as command-formulation issues first.

See `docs/85_v2_77_windows_spaced_path_hardening.md`.

## V2.78 Non-Partial Blocker Dispatch Stop

V2.78 hardens the orchestrator so a newly recorded blocker with
`can_continue_partially=false` stops the current ready-task batch immediately.
This prevents sibling tasks from consuming more tokens after the controller has
already concluded the current run needs manual resolution.

The runtime now:

- snapshots non-partial blocker IDs before each task dispatch;
- compares blocker IDs again after the task finishes;
- records a `run_blocked` history event and returns immediately when a new
  non-partial blocker appears.

This preserves existing debug-first behavior for retryable failures, while
stopping adjacent work after retry exhaustion or other non-partial blockers.

See `docs/86_v2_78_nonpartial_blocker_stop.md`.

## V2.79 Existing Blocker Resume Stop

V2.79 extends the non-partial blocker stop rule to resumed or stale states that
already contain a blocker before the fresh controller starts scheduling. After
each evaluation pass, the orchestrator now checks for existing blockers whose
`can_continue_partially` value is false and returns before dispatching another
ready task.

This prevents recovery runs from continuing adjacent or debug work after an old
attempt has already recorded a manual-resolution blocker.

See `docs/87_v2_79_existing_blocker_resume_stop.md`.

## V2.80 Go Worker Environment Bootstrap

V2.80 moves the Windows Go recovery setup from a manual operator workaround
into the real Codex worker environment. When a worker runs in or near a Go
module, Alchemy now seeds only the worker subprocess environment with:

- a discovered Go `bin` directory, including `ALCHEMY_GO_BIN` and common local
  tool installs;
- `GOTOOLCHAIN=auto` so modules that request a newer patch toolchain can use
  the writable Go toolchain cache;
- a writable shared `GOMODCACHE`;
- a worktree-local `GOCACHE`;
- conservative `GOFLAGS=-p=1` when the caller did not provide flags.

This does not write global Go configuration and does not override `APPDATA`, so
GitHub CLI authentication remains visible to preflight checks.

See `docs/88_v2_80_go_worker_env_bootstrap.md`.

## V2.81 Technical Blocker Phase Repair

V2.81 lets the full-roadmap executor recover from implementation-level
technical blockers without violating the non-partial blocker stop rule. Runtime
orchestration still stops immediately when a non-partial blocker is present, but
the parent roadmap executor may now write a phase repair document and launch a
new phase attempt when all blockers are autonomous implementation or test
repair candidates.

Environment, credential, preflight, recovery, operator-stop, and live-worker
blockers still stop the roadmap and require external resolution.

See `docs/89_v2_81_technical_blocker_phase_repair.md`.

## V2.82 Resume Attempt Ordering Hardening

V2.82 prevents a blocked phase from falling back past a newer terminal attempt
to an older stale active attempt. When the newest phase attempt has a
`state.json` and no active tasks, the full-roadmap resume scan now treats that
attempt as the current boundary and starts a fresh attempt instead of resuming
older stale task state.

This protects Billing Core style recovery chains such as `run_attempt_015`
cleanly stopping at blockers while `run_attempt_014` still contains obsolete
`active_tasks` evidence.

See `docs/90_v2_82_resume_attempt_order_hardening.md`.

## V2.84 Worker Timeout Stop

V2.84 treats real worker timeouts as task sizing or budget blockers instead of
ordinary retryable failures. A timed-out implementation task now records a
non-partial technical blocker without creating a same-scope debug task, and a
timed-out debug task blocks its parent instead of replaying the original task.

This prevents Billing Core style large frontend tasks from cycling through
`T002 -> T002-DEBUG-1 -> T002` when each worker exhausts the configured runtime
budget.

See `docs/92_v2_84_worker_timeout_stop.md`.

## V2.85 Terminal Active Resume Skip

V2.85 prevents full-roadmap resume from reusing an active-task attempt when the
same active task already has terminal worker lifecycle evidence such as
`timed_out`, `failed`, `completed`, or `cancelled`. This keeps a stopped Billing
Core probe like `run_attempt_019` from being reset and replayed simply because
its state file still says `active_tasks=["T002"]`.

Active attempts with a live worker still block new runs, and active attempts
without terminal lifecycle evidence remain resumable.

See `docs/93_v2_85_terminal_active_resume_skip.md`.

## V2.86 Package Lock Boundary Expansion

V2.86 expands implementation task file boundaries when `allowed_files` includes
a `package.json`. The orchestrator now adds the same-directory lockfile
companions (`pnpm-lock.yaml`, `package-lock.json`, `npm-shrinkwrap.json`,
`yarn.lock`, and `bun.lockb`) so dependency verification does not get rolled
back as out-of-scope lockfile drift.

This keeps Billing Core style frontend tasks from failing framework boundary
audit solely because `pnpm` updates `frontend/pnpm-lock.yaml` while the task
already allows `frontend/package.json`.

See `docs/94_v2_86_package_lock_boundary_expansion.md`.

## V2.87 Dead Debug Resume Skip

V2.87 prevents full-roadmap resume from reusing a stale active debug attempt
whose worker lifecycle still says `running` but whose recorded PID no longer
exists. Ordinary active implementation attempts with dead PIDs remain resumable;
the skip applies only when all active tasks are debug tasks.

This keeps a stopped Billing Core attempt such as `run_attempt_020` from
resuming `T002-DEBUG-1` after the underlying failure has been fixed in the
framework.

See `docs/95_v2_87_dead_debug_resume_skip.md`.

## V2.88 Focused Phase Repair Resume

V2.88 seeds a resumed blocked full-roadmap phase with a focused
`phase_repair_resume_NNN.md` document built from the previous blocker evidence.
The repair brief now lists failed task IDs, completed tasks to preserve, worker
test failures, out-of-scope follow-ups, changed files, retry state, and timeout
guidance so the next Alchemy attempt can split or widen the exact failed scope
instead of replanning the whole phase.

The blocker classifier also narrows credential markers so product work on API
key management or identity/auth workflows is not mistaken for a missing
external credential.

See `docs/97_v2_88_focused_phase_repair_resume.md`.

## V2.89 Repair Scope Handoff

V2.89 fixes the Billing Core recovery path where good repair evidence still
collapsed into the same narrow router/package task. The planner now keeps
frontend `large_refactor` phases on the frontend decomposition path, avoids
treating repair narrative as global scope controls, recognizes `.vue` file
paths, and treats `supervisor_stop.json`/`operator_stop.json` as terminal
attempt markers.

See `docs/98_v2_89_repair_scope_handoff.md`.

## V2.90 Codex Usage-Limit Blocker

V2.90 classifies local Codex CLI usage-limit JSONL errors as environment
blockers. Alchemy now preserves the raw reset-time evidence, stops without
debug/retry product work, and prevents full-roadmap auto-repair from treating
account quota as a CRM implementation task.

See `docs/99_v2_90_codex_usage_limit_blocker.md`.

## V2.91 Usage-Limit False Positive Guard

V2.91 tightens usage-limit detection so historical quota text inside successful
Codex JSONL command output does not become a live environment blocker. Alchemy
still recognizes structured Codex error events, explicit summaries, known
issues, stderr, and plain non-JSON usage-limit errors.

See `docs/100_v2_91_usage_limit_false_positive.md`.

## V2.92 Frontend API Caller Repair Scope

V2.92 expands the frontend API-service cleanup task to include caller surfaces
under `frontend/src/components/**`, `frontend/src/composables/**`, and
`frontend/src/constants/**`. This keeps focused repair evidence aligned with
the task that can stop the run, instead of leaving the fix to a later task that
may never execute after a non-partial T003 blocker.

See `docs/101_v2_92_frontend_api_caller_repair_scope.md`.

## V2.93 Timeout Repair Split For Frontend Copy Sweep

V2.93 turns the T007 timeout repair instruction into a smaller task graph. When
focused repair evidence says the frontend copy/i18n sweep timed out and should
be split, Alchemy now replaces the broad task with separate i18n and
view/component copy-sweep tasks.

See `docs/102_v2_93_timeout_repair_split_frontend_copy.md`.

## V2.94 Disk Repair Brief Resume

V2.94 makes full-roadmap relaunches reuse a newer on-disk
`phase_repair_NNN.md` when `phase_record.json` is stale. This prevents a
supervisor-stopped parent run from losing the fresh repair evidence it already
wrote and falling back to the original broad phase graph.

See `docs/103_v2_94_disk_repair_brief_resume.md`.

## V2.95 Preserve Completed Repair Tasks

V2.95 makes focused repair resumes honor `Completed tasks to preserve` evidence
from repair briefs. Rebuilt graphs mark those task IDs completed with
preservation evidence, so a T007 repair does not dispatch already completed
T002-T006 work again.

See `docs/104_v2_95_preserve_completed_repair_tasks.md`.

## V2.96 Split Remaining Frontend Closure Timeout

V2.96 extends timeout repair splitting to the fallback remaining-frontend
closure task. When focused repair evidence says T009 timed out and should be
split or checkpointed, Alchemy now replaces the broad `frontend/**` closure
task with smaller shell/route, state/API, and view/component workflow tasks.

See `docs/105_v2_96_split_remaining_frontend_closure_timeout.md`.

## V2.97 Cumulative Repair Brief Context

V2.97 makes full-roadmap relaunches pass recent ordinary repair briefs, not
only the newest one, when those briefs are newer than the phase record. This
preserves earlier split context such as `phase_repair_006.md` while applying a
newer timeout repair such as `phase_repair_007.md`, preventing completed-task
preservation from drifting onto a different task ID.

See `docs/106_v2_97_cumulative_repair_brief_context.md`.

## V2.98 Repair Context Budget

V2.98 separates historical repair context from the current parent run's new
repair budget. Existing repair briefs can be passed to preserve graph context
without consuming the allowance for newly generated repair documents, and
blocked-phase resume briefs now carry recent ordinary repair context even when
`phase_record.json` is newer.

See `docs/107_v2_98_repair_context_budget.md`.

## V2.99 Split State/API Closure Timeout

V2.99 extends frontend timeout splitting to the remaining state/API closure
task. Focused T010 timeout repair now replaces the prior state/API task with
separate API service, store/composable, and constants/type closure tasks.

See `docs/108_v2_99_split_state_api_closure_timeout.md`.

## V2.100 Worker Output Budget Hygiene

V2.100 adds worker prompt and result-sanitization guardrails for large
repositories. Real Codex workers are now instructed to cap broad search, diff,
status, and test-log output, and structured worker result text fields are
truncated before they can pollute later repair context.

See `docs/109_v2_100_worker_output_budget_hygiene.md`.

## V2.101 Live Supervisor Stop Marker

V2.101 makes `supervisor_stop.json` and `operator_stop.json` live execution
controls for document-run attempts. Marker files are now checked before task
dispatch and while workers are running, instead of only affecting future resume
selection.

See `docs/110_v2_101_live_supervisor_stop_marker.md`.

## V2.102 Supervisor-Stopped Completion Context

V2.102 preserves completed task evidence from newer supervisor-stopped attempts
when `phase_record.json` is stale. Bootstrap now writes/reuses a repair context
brief for the stopped attempt and the timeout-split matcher handles task ID
lists, preventing task-ID drift after a supervised pause.

See `docs/111_v2_102_supervisor_stopped_completion_context.md`.

## V2.103 Verification Failure Repair Handoff

V2.103 carries concrete failed verification evidence from completed test/review
tasks into phase repair briefs. Blocked-phase bootstrap can recover older run
attempts that still contain the failing worker result, and the planner creates
an unpreserved focused repair task for those target files instead of marking the
whole regenerated graph completed.

See `docs/112_v2_103_verification_failure_repair_handoff.md`.

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
- Deep LLM-grade code summarization and semantic requirement-to-file mapping
  beyond deterministic file/path/signature signals.
- Proven real external rerun that combines generated static CI, automatic
  browser verification, and terminal GitHub check collection in one PR.
- Domain-specific semantic probes for every app category beyond the current
  canvas-game and generic static-web probes.
- Agent SDK runtime code.
- GitHub App integration.
- GitHub Actions log ingestion.
- Guaranteed hard cancellation of every already-running Codex subprocess across
  every host environment beyond the current best-effort managed subprocess
  cancellation.
- Production database, asynchronous worker daemon process, hard already-running worker cancellation, or multi-user access control.

Those systems should be implemented against the protocols defined here.
