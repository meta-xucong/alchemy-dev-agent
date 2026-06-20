# V2.39 Unified Entrypoint And Project-Type Runtime Plan

V2.39 is the next planning phase after V2.38. It keeps the original Alchemy
goal unchanged:

> detailed documents, supporting files, and optional local or GitHub repository
> context should drive autonomous planning, execution, testing, review, repair,
> and delivery through an agent cluster.

The current repository already proves the core runtime with several entry
points:

- `autodev.demo_run` for one-line fallback game generation.
- `autodev.document_run` for document-driven execution.
- `ProjectService` and the HTTP API for persisted project intake and runs.
- `autodev.acceptance_run` for local service acceptance.
- `autodev.local_repository_acceptance` for local repository and feedback
  reopen acceptance.

V2.39 does not replace those systems. It defines the engineering plan to
converge them behind one product-facing run contract so users do not need to
know which script or internal pathway is appropriate.

## Problem Statement

The runtime has enough pieces to build real products, but they are exposed as
specialized workflows. This creates three practical problems:

1. A user must choose between demo, document, API, local repository, and GitHub
   paths before the system has interpreted the project package.
2. Acceptance evidence is strong but spread across several report shapes and
   harness names.
3. Product-type handling is implicit. Canvas games, static apps, Node projects,
   Python projects, and documentation-only projects share contracts, but users
   do not see a single mode that routes them consistently.

The next implementation phase should make the product behave like:

```bash
python -m autodev.run \
  --objective "build a todo app with login" \
  --document docs/product_spec.md \
  --attachment docs/api_contract.json \
  --repository-path ./target-repo \
  --auto-browser-verify \
  --output .alchemy/runs/todo-login
```

The same command should work when the repository source is a public GitHub URL,
a private GitHub URL available through local `gh` authentication, a local path,
or no repository at all.

## Scope

V2.39 is a planning and implementation-readiness phase for a unified runtime
entrypoint. It covers:

- a unified run request model;
- a CLI facade;
- an API one-shot run facade;
- browser console alignment;
- project-type routing;
- source-mode routing;
- common output and evidence contracts;
- acceptance and regression checklists for the next coding phase.

It does not add a new agent taxonomy, task graph, evaluator, or worker model.
It must reuse:

- `ProjectBrief`;
- `ContextBundle`;
- `TaskGraph`;
- `RuntimeState`;
- `DocumentRunPipeline`;
- `ProjectService`;
- existing artifact, browser, native UI, delivery, and development-cycle
  evidence contracts.

## Design Principles

### Document-Dominant By Default

If development documents or supporting files are supplied, the system must route
through the document-driven path. One-line fallback is allowed only when no
documents, attachments, source repository, or existing project package is
provided.

### One Contract Per Concept

The unified entrypoint must not introduce a second version of project intake,
task graph execution, or delivery evaluation. It should translate user-facing
inputs into existing contracts and then call the existing runtime.

### Source-Mode Parity

Local repository, public GitHub repository, private GitHub repository, and
docs-only source modes must all produce the same top-level run result shape:

- project brief;
- context bundle;
- task graph;
- runtime state;
- artifact report;
- requirement coverage;
- delivery report;
- delivery evidence;
- development cycle.

### Evidence Before Claims

The unified entrypoint cannot claim delivery because a command exited
successfully. It must surface the same readiness gate used by V2.34 and later:

- final gate score;
- must requirement coverage;
- static artifact checks;
- browser semantic, scenario, or gameplay probe evidence;
- native UI test draft/write evidence when applicable;
- GitHub branch, PR, CI, and merge or waiver evidence;
- blockers and next repair actions.

### Safe Real Execution

Real Codex and real GitHub execution remain opt-in. Dry-run execution should be
the default. When real execution is enabled, V2.39 must preserve:

- isolated worktree execution;
- allowed-file boundaries;
- dirty diff audit;
- worker lifecycle records;
- best-effort cancellation;
- CI-gated delivery when CI collection is enabled;
- explicit auto-merge opt-in.

## Unified Run Request

The next implementation should introduce a small request object, for example
`AutoDevRunRequest`, that is used by CLI, API, tests, and UI wiring.

Required fields:

- `objective`: user objective or product goal.
- `documents`: ordered development document paths or uploaded project files.
- `attachments`: supporting files that are not primary requirement documents.
- `repository_url`: optional GitHub repository URL.
- `repository_path`: optional local repository path.
- `source_mode`: `auto`, `none`, `local`, `github_public`, or
  `github_private`.
- `execution_mode`: `dry_run` or `real_codex`.
- `delivery_mode`: `report_only`, `local`, or `github_pr`.
- `output_dir`: run output directory.

Optional flags:

- `prepare_repository`;
- `repository_visibility`;
- `codex_executable`;
- `max_worker_seconds`;
- `isolate_real_run`;
- `keep_worktree`;
- `auto_browser_verify`;
- `generate_static_ci`;
- `write_native_ui_tests`;
- `github_collect_ci`;
- `github_ci_wait_seconds`;
- `github_ci_poll_interval_seconds`;
- `auto_merge`;
- `resume_from`;
- `resume_tasks`;
- `feedback_files`;

The request object should normalize aliases but should not execute work. It
should have a deterministic `to_project_brief_kwargs()` or equivalent mapping
into existing intake code.

## Entrypoint Router

The unified entrypoint should use a deterministic router:

1. If `resume_from` is set, route to the existing resume path in
   `DocumentRunPipeline`.
2. If documents, attachments, repository path, or repository URL exist, route to
   `DocumentRunPipeline`.
3. If only an objective exists, route to the current one-line fallback path.
4. If feedback files are supplied for a delivered run, route through the
   feedback reopen path.
5. If source preparation fails, return a blocked result with source blocker
   evidence and do not fabricate a plan.

This router is intentionally simple. It should make the user-facing interface
easy without making the runtime less explicit.

## CLI Technical Route

Add a new CLI module:

```text
autodev/run.py
```

The CLI should support both product-style and compatibility-style flags:

```bash
python -m autodev.run --objective "build a CRM dashboard" --document spec.md
python -m autodev.run --objective "build a game" --output .alchemy/generated/game
python -m autodev.run --document spec.md --repository-path ./repo --real-codex
python -m autodev.run --document spec.md --repository-url https://github.com/org/repo --prepare-repository
```

The implementation should call existing APIs rather than copying pipeline
logic. The expected shape is:

```text
parse args
normalize AutoDevRunRequest
route request
call DocumentRunPipeline or AutoDevPipeline
write unified run report
print concise JSON summary
exit nonzero only when result status is failed, blocked, or needs_iteration
```

Compatibility should be preserved:

- `autodev.demo_run` keeps working.
- `autodev.document_run` keeps working.
- Existing API endpoints keep working.
- New callers can use the unified facade.

## API Technical Route

The HTTP API already supports project creation, file upload, intake, context,
plan, run, feedback reopen, delivery, artifacts, and event streaming. V2.39
should add a one-shot facade without removing the existing staged workflow.

Recommended endpoint:

```http
POST /runs
```

Request body:

```json
{
  "objective": "build a todo app with login",
  "documents": ["D:/project/spec.md"],
  "attachments": ["D:/project/openapi.json"],
  "repository_path": "D:/project/repo",
  "repository_url": "",
  "source_mode": "auto",
  "execution": {
    "real_codex": false,
    "codex_executable": "codex",
    "max_worker_seconds": 1800
  },
  "verification": {
    "auto_browser_verify": true,
    "write_native_ui_tests": false,
    "generate_static_ci": true
  },
  "delivery": {
    "real_github": false,
    "github_collect_ci": true,
    "auto_merge": false
  }
}
```

The endpoint should internally create a project, attach files, build intake,
start an async run, and return:

- `project_id`;
- `run_id`;
- initial `status`;
- event stream URL;
- delivery URL;
- artifact manifest URL when available.

This endpoint is for product ergonomics. The existing granular endpoints remain
the canonical API for reviewable staged operation.

## Browser Console Technical Route

The browser console should continue supporting the staged workflow, but V2.39
should add a clear "single-run" mode:

1. User enters objective.
2. User uploads multiple development documents and supporting files.
3. User optionally enters GitHub URL or local repository path.
4. User chooses dry-run or real Codex.
5. User chooses local report or GitHub PR delivery.
6. User starts a run.
7. UI shows intake, graph, event stream, artifacts, coverage, probes, readiness,
   feedback reopen, and delivery evidence using existing panels.

The UI should not hide the underlying evidence. It should reduce entry friction
while preserving inspectability.

## Project-Type Routing

V2.39 should introduce an explicit project-type routing contract, implemented
as deterministic profile selection around existing artifact profile and context
signals.

Initial profiles:

- `canvas_game`;
- `static_web_app`;
- `node_project`;
- `python_project`;
- `fullstack_project`;
- `documentation_only`;
- `unknown`.

Profile selection inputs:

- extracted requirements and acceptance criteria;
- repository file map;
- package files and test commands;
- artifact profile detector;
- generated or existing CI evidence;
- explicit user constraints when provided.

Profile outputs:

- recommended test commands;
- browser verification mode;
- native UI test generation eligibility;
- generated static CI eligibility;
- release readiness gates;
- repair suggestion categories.

The selector should not override the task graph. It should annotate the run so
workers, verifiers, and delivery reports use the right gates.

## Implementation Work Breakdown

### 1. Request Model

Implementation idea:

- Add a dataclass in `autodev/unified_request.py`.
- Normalize document and attachment paths.
- Validate mutually exclusive source inputs.
- Infer `source_mode`.
- Infer `delivery_mode`.
- Preserve all raw inputs in the final run report for audit.

Tests:

- no source plus only objective routes to one-line fallback;
- documents route to document run;
- local path routes to local source mode;
- public URL routes to public GitHub source;
- private URL plus visibility private requires `gh` preflight;
- conflicting local path and prepared GitHub path are reported clearly.

### 2. CLI Facade

Implementation idea:

- Add `autodev/run.py` with `argparse`.
- Reuse `DocumentRunPipeline` and `AutoDevPipeline`.
- Emit `unified_run_report.json`.
- Print a compact JSON summary with result status and key evidence paths.

Tests:

- CLI one-line fallback produces an artifact and report;
- CLI document path produces document-run report;
- CLI local repository path preserves provider `local`;
- CLI invalid document path returns a blocked/failed status with evidence.

### 3. API One-Shot Facade

Implementation idea:

- Add `ProjectService.run_unified_request()`.
- Add `POST /runs`.
- Internally call existing create/upload/run methods.
- Preserve staged workflow fields so existing UI and tests still work.

Tests:

- HTTP `POST /runs` with local docs starts an async run;
- response includes project id, run id, event stream URL, and delivery URL;
- invalid source reports API error without partial orphan records;
- delivery evidence matches the same shape as staged runs.

### 4. Browser Console Single-Run Mode

Implementation idea:

- Add a compact start form backed by the new endpoint.
- Reuse existing project/run panels after run creation.
- Use EventSource SSE as the primary event path with polling fallback.
- Keep raw JSON and artifact previews visible.

Tests:

- static HTML contains controls for objective, documents, repository source,
  execution mode, and verification options;
- UI can start a single-run request against the local API;
- project/run deep link opens the generated evidence view.

### 5. Project-Type Matrix

Implementation idea:

- Add a profile routing helper that consumes context bundle and artifact
  profile evidence.
- Keep it deterministic and testable.
- Store selected profile and rationale in runtime repository state.

Tests:

- canvas game routes to gameplay probe;
- static app routes to semantic and scenario probes;
- Node project skips static web gate and uses package test commands;
- Python project skips static web gate and uses Python test commands;
- documentation-only project records a report-only delivery profile.

### 6. Acceptance Harness

Implementation idea:

- Add `autodev.unified_acceptance` or extend existing acceptance harnesses with
  a unified-run path.
- Cover one-line, document-only, local repo, and public GitHub dry-run cases.
- Keep real Codex and real GitHub cases behind opt-in flags.

Tests:

- unit tests for request model and routing;
- focused API tests;
- browser console smoke;
- full unit suite;
- unified acceptance harness;
- optional real Codex smoke;
- optional real GitHub validation.

## Output Contract

Every unified run should write:

```text
output_dir/
  unified_run_report.json
  project_brief.json
  context_bundle.json
  task_graph.json
  runtime_state.json
  delivery_report.json
  delivery_evidence.json
```

When the selected path is already producing richer reports, `unified_run_report`
can link to those files rather than duplicate large payloads. It must still
include:

- status;
- project id;
- run id;
- source mode;
- execution mode;
- delivery mode;
- selected project profile;
- final gate score;
- readiness status;
- blockers;
- next actions;
- artifact manifest URL or path;
- report paths.

## Acceptance Criteria

V2.39 is implementation-ready when this document and the checklist are present.

The later coding phase is accepted when:

- a single CLI command can run one-line, document-only, local repository, and
  public GitHub dry-run workflows;
- API `POST /runs` can create a project and start the same run without using
  the staged API manually;
- the browser console exposes a one-shot run mode while retaining evidence
  panels;
- all unified runs emit `unified_run_report.json`;
- project profile selection is recorded in run evidence;
- the old specialized CLIs still pass compatibility tests;
- delivery readiness continues to use V2.34 and later evidence gates;
- full unit tests, JSON validation, diff hygiene, and acceptance harnesses pass.

## Risks And Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| The facade becomes a second runtime. | Contract drift and duplicated bugs. | Route through existing pipelines and keep the facade thin. |
| One-line fallback hides weak requirements. | Low-quality generated projects. | Use fallback only with no documents or source package and mark confidence low. |
| Project type is misdetected. | Wrong verification gate. | Store rationale and allow profile override in later phases. |
| Real execution is triggered accidentally. | Unwanted file or GitHub changes. | Keep dry-run default and require explicit real Codex/GitHub flags. |
| UI hides important evidence. | User cannot judge delivery quality. | Reuse existing evidence panels and keep raw JSON links. |
| Private GitHub access fails. | Source cannot be inspected. | Use `gh auth status` preflight and return a source blocker. |

## Non-Goals

V2.39 does not implement:

- a new LLM planner;
- a new Agent SDK runtime;
- a production worker daemon;
- multi-user authentication;
- universal private repository validation;
- domain-specific generated apps beyond current profile-based routing;
- guaranteed perfect one-line product generation.

Those remain compatible future phases. V2.39's job is to make the current
document-driven autonomous development system callable through one coherent
product entrypoint.
