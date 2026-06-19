# V2.23 Perfect Delivery Optimization Plan

V2.23 keeps the original Alchemy Dev Agent goal unchanged:

> Given a user objective, detailed development documents, supporting files, and
> a GitHub repository, the system should autonomously understand the work,
> plan the task graph, execute through agent workers, test, debug, evaluate,
> and deliver only when the result is product-ready.

V2.22 proved this path with a real docs-only repository and a playable browser
game PR. V2.23 defines the remaining optimization work required to move from
successful proof to stable product-grade one-click delivery.

## Current Baseline

The V2.22 real target run delivered:

```text
Repository: https://github.com/meta-xucong/-super-mario-test
PR:         https://github.com/meta-xucong/-super-mario-test/pull/2
Branch:     agent/super-mario-v2-22b-20260619033500199673
Commit:     72f2b6e27e972c43e135f3eec3ff0c5bc80b3bb8
```

Verified evidence:

- generated a playable original retro platformer Level 1 from a docs-only repo
- produced modular browser game files under `index.html`, `src/`, and `tests/`
- passed target static checks
- passed runtime `StaticWebArtifactVerifier`
- passed manual browser smoke verification
- recorded no protected commercial game terms in generated artifacts
- created a real public GitHub PR with explicit no-CI waiver evidence

This proves the core system path is viable. The remaining work is mostly
stability, automation, recovery, evidence quality, and product breadth.

## Observed Gaps From The Real Run

### 1. Browser Playability Evidence Is Not Yet First-Class

The generated game was verified in a browser with screenshots, keyboard input,
and pixel-diff evidence. However, this evidence was collected as a final manual
audit step rather than as a built-in `DocumentRunPipeline` stage.

Impact:

- the final report cannot automatically include browser screenshots
- the evaluator cannot score playability or visual rendering directly
- future HTML/canvas apps need repeated manual verification

Required direction:

- add an artifact browser verifier that can launch a local static server
- capture initial and post-interaction screenshots
- compute canvas/page pixel difference
- record console errors
- persist evidence paths in the document-run report

### 2. Timeout And Child Process Supervision Need Hardening

The real run exceeded the outer command timeout while a child Python/Codex
process continued running. The generated worktree could be recovered, but this
must be controlled by the runtime instead of operator cleanup.

Impact:

- background workers can continue mutating a worktree after the parent command
  has stopped
- state can show stale `active` tasks
- recovery requires manual process inspection

Required direction:

- run Codex workers under a process group or managed child-process registry
- persist worker PID, start time, timeout, and current task id
- terminate worker process trees on timeout
- mark interrupted tasks as retryable with exact timeout evidence
- add a `document_run cleanup` or recovery command for abandoned workers

### 3. Web Game / Web App Delivery Needs A Built-In Acceptance Profile

V2.22 added deterministic static artifact verification, but product-quality web
apps need richer acceptance checks than file existence and markers.

Impact:

- a page can pass static checks while having weak runtime behavior
- game-specific logic such as movement, win condition, collision, or restart may
  require custom smoke actions
- screenshots and console logs are not yet scored by the evaluator

Required direction:

- add an `artifact_profile` field such as `static_web_app`, `canvas_game`,
  `react_app`, or `api_service`
- derive profile from docs, repository files, and generated scaffold
- run profile-specific checks
- require browser smoke evidence for `canvas_game`
- let profiles define expected commands, browser actions, and evidence types

### 4. CI Strategy For Docs-Only Repositories Is Still Minimal

The real target repository had no GitHub Actions workflow. The delivery used an
explicit no-CI waiver, which is correct but not ideal for product-grade
automation.

Impact:

- PR quality evidence depends on local verification only
- GitHub cannot independently re-run checks after review
- public target repos may look incomplete to downstream reviewers

Required direction:

- support optional generated CI workflows for static web artifacts
- for Node-free static apps, generate a lightweight workflow that runs static
  checks with built-in Node
- for package-based repos, use existing package scripts first
- keep no-CI waiver as an explicit operator option, not the default when CI can
  be generated safely

### 5. Requirement Coverage Needs Stronger Runtime Scoring

The system now extracts richer requirements, but the final evaluator still uses
mostly graph/test/review evidence. It does not deeply prove that each
requirement is implemented in the final artifact.

Impact:

- a broad task can mark many requirements done without per-requirement runtime
  evidence
- final reports may be weaker for complex product documents
- reviewer agent has limited machine-checkable coverage context

Required direction:

- generate a requirement coverage matrix after implementation
- map each requirement to changed files, tests, browser evidence, and PR diff
- flag requirements with no implementation evidence
- lower the final gate score when must-requirements lack concrete artifacts
- include the matrix in `document_run_report.json`

### 6. Multi-File Upload And GitHub Link UI Need Full Product Polish

The current system supports document and attachment intake through CLI/API and
has browser console controls. The ideal product workflow needs a cleaner user
experience for multi-file upload, repository selection, and run evidence.

Impact:

- non-technical users may not trust or understand the run state
- uploaded files, GitHub source status, task graph, live workers, evidence, and
  PR status need a more integrated view

Required direction:

- improve the browser console into a project intake dashboard
- support multi-file drag/drop with role inference and editable roles
- show GitHub clone/auth/preflight status
- preview task graph and requirement coverage before execution
- stream worker status and final evidence links
- show PR, screenshots, checks, and blockers in one delivery report view

### 7. Worker Prompting Needs More Product-Specific Guardrails

V2.22 fixed protected-term leakage and scaffold grouping. More domains will need
similar guardrails: API apps, SaaS dashboards, data pipelines, document
generators, browser extensions, mobile-like frontends, and test harnesses.

Impact:

- worker output quality depends on generic instructions
- different project types need different file boundaries and verification plans

Required direction:

- introduce domain-specific worker prompt templates keyed by artifact profile
- keep the worker protocol unchanged
- include profile-specific safety, testing, and evidence instructions
- add regression fixtures for at least three representative project profiles

## V2.23 Required Contracts

### Artifact Verification Contract

Every document-run should be able to produce:

```json
{
  "artifact_profile": "canvas_game",
  "static_verification": {
    "status": "passed",
    "commands": [],
    "evidence": []
  },
  "browser_verification": {
    "status": "passed",
    "url": "http://127.0.0.1:<port>/index.html",
    "screenshots": {
      "initial": ".alchemy/.../browser_initial.png",
      "after_interaction": ".alchemy/.../browser_after_interaction.png"
    },
    "pixel_diff": {
      "changed_pixels": 49998,
      "bbox": [191, 239, 673, 369]
    },
    "console_errors": []
  }
}
```

### Worker Supervision Contract

Every real worker execution should persist:

```json
{
  "task_id": "T009",
  "worker_pid": 12345,
  "started_at": "2026-06-19T04:00:00Z",
  "timeout_seconds": 900,
  "status": "running|completed|timed_out|terminated",
  "process_group": "alchemy-run-...",
  "cleanup_required": false
}
```

### Requirement Coverage Contract

Every final report should include:

```json
{
  "requirement_id": "REQ-013",
  "priority": "must",
  "text": "基础敌人 AI（basic walking enemy）.",
  "implementation_files": ["src/entities.js", "src/engine.js"],
  "verification_evidence": [
    "Static artifact inspection",
    "Browser smoke screenshot"
  ],
  "coverage_status": "covered|partial|missing"
}
```

## Implementation Plan

### V2.23.1 Browser Artifact Verifier

Build a runtime verifier for local browser artifacts.

Scope:

- start a local static server from a generated worktree
- open the artifact in a browser-capable test surface
- capture initial screenshot
- run configured interactions
- capture post-interaction screenshot
- compute image difference
- collect console errors
- persist evidence in the run output directory

Acceptance:

- canvas game fixture records nonblank screenshots
- post-interaction pixel diff is greater than zero
- console errors fail the browser verification gate
- report paths are included in `document_run_report.json`

### V2.23.2 Artifact Profiles

Add profile detection and profile-specific verification.

Initial profiles:

- `static_web_app`
- `canvas_game`
- `node_project`
- `python_project`
- `documentation_only`

Acceptance:

- docs-only platformer fixture resolves to `canvas_game`
- documentation probe resolves to `documentation_only`
- Node package fixture resolves to `node_project`
- each profile produces appropriate default checks

### V2.23.3 Managed Worker Process Lifecycle

Harden real Codex execution process control.

Scope:

- track worker PID/task id/timeouts in state
- terminate process tree on timeout
- persist timeout evidence
- reset timed-out task into a retryable state
- provide cleanup for stale workers

Acceptance:

- test runner simulates a timed-out worker and verifies state cleanup
- stale `active` task recovery produces retry instructions
- no worker process remains after timeout cleanup

### V2.23.4 Requirement Coverage Matrix

Generate a per-requirement coverage matrix after implementation.

Scope:

- map requirements to implementation tasks and changed files
- map requirements to static/browser/test evidence
- compute `covered`, `partial`, or `missing`
- feed missing must requirements into evaluator hard failures

Acceptance:

- V2.22 platformer fixture reports all must requirements covered
- missing generated file produces partial/missing coverage
- final gate score decreases when must coverage is incomplete

### V2.23.5 Generated CI For Docs-Only Static Apps

Add optional generated CI workflow for docs-only output repos.

Scope:

- detect absence of CI in public target repo
- when safe, generate `.github/workflows/alchemy-static-checks.yml`
- run `node tests/static_checks.js` or configured static checks
- keep `--no-github-ci` as an explicit escape hatch

Acceptance:

- docs-only static app repo receives a generated CI workflow by default
- no-CI waiver remains recorded when operator selects `--no-github-ci`
- GitHubFlow blocks failed/pending/unknown CI when CI collection is enabled

### V2.23.6 Delivery Report Productization

Make final reports reviewer-friendly.

Scope:

- include PR URL, branch, commit, CI/no-CI status
- include requirement coverage matrix
- include static and browser artifact evidence
- include screenshots
- include exact blockers and retry instructions

Acceptance:

- `document_run_report.json` has a stable `delivery_report` section
- browser console can display the final report
- PR body can include a concise evidence summary

### V2.23.7 UI Intake And Evidence Polish

Improve the local browser console for the primary user workflow.

Scope:

- multi-file upload with role inference
- GitHub URL input with public/private/preflight status
- task graph preview
- live worker state
- final PR/evidence screen

Acceptance:

- user can upload multiple docs and attachments from UI
- user can provide a GitHub URL and see preflight result
- user can start a real run and inspect final evidence without opening raw JSON

## Acceptance Criteria

V2.23 is complete when:

- a docs-only canvas game repo runs end-to-end with built-in browser evidence
- no manual process cleanup is required after worker timeout
- final report includes requirement coverage, screenshots, PR, commit, and
  CI/no-CI status
- a generated or existing CI path is used when available
- the UI can drive the primary document-plus-GitHub workflow
- the full repository test suite passes
- a real external target repository delivery succeeds without manual
  post-processing

## Non-Goals

V2.23 does not change the high-level agent architecture, task graph schema
concept, Codex worker model, or final evaluator philosophy.

V2.23 does not attempt to guarantee perfect product design quality for arbitrary
one-line prompts. The primary target remains detailed development documents and
supporting files.

## Recommended Next Step

Start with V2.23.1 and V2.23.2. Built-in browser artifact verification and
artifact profiles will turn the current manual final audit into a repeatable
runtime contract, which is the largest remaining gap between a successful proof
and stable one-click delivery.

## Implementation Update

The first V2.23 implementation pass is complete:

- `runtime.artifact_profile.ArtifactProfileDetector` classifies
  `canvas_game`, `static_web_app`, `node_project`, `python_project`,
  `documentation_only`, and `unknown` artifact profiles.
- `StaticWebArtifactVerifier` now records the detected artifact profile in its
  verification result.
- `BrowserArtifactEvidenceVerifier` validates externally captured browser
  evidence, including initial/post-interaction screenshots, pixel diff, URL,
  console errors, and pass/fail evidence.
- `DocumentRunPipeline` now writes an `artifact_report` section containing
  `artifact_profile`, `static_verification`, optional `browser_verification`,
  and the artifact files selected from the task graph.
- The document-run CLI accepts `--browser-url`,
  `--browser-initial-screenshot`, `--browser-after-screenshot`, and
  `--browser-console-error` so real browser smoke evidence can be imported into
  the final report.
- `BrowserArtifactRunner` can now start a local static server, invoke a browser
  runner, capture initial and post-interaction screenshots, compute pixel diff,
  check for blank screenshots, collect console errors, and write the same
  `browser_verification` contract.
- The document-run CLI accepts `--auto-browser-verify` to use that automatic
  path. The default runner uses Playwright when it is installed; tests inject a
  deterministic runner so the contract remains verified even on machines
  without browser binaries.

V2.24 extends this with real-environment preflight support: `real_env_check`
accepts `--require-browser`, and the browser console sends the same requirement
when `Auto browser verify` is selected. On machines without Playwright, the run
can now block before execution instead of discovering the missing browser
automation step after artifact generation.

Remaining work in V2.23.1 is to make the automatic browser runner available in
more local environments, for example by installing Playwright and its browser
binaries as part of the developer setup path. Until then, external screenshots
can still be imported through the existing browser evidence fields.

The V2.23.3 runtime core is also implemented:

- `runtime.worker_lifecycle.WorkerLifecycleRecorder` persists task id, PID,
  start/end timestamps, timeout seconds, process group id, cleanup status, and
  termination evidence for real Codex workers.
- `ManagedSubprocessRunner` launches real worker subprocesses in a managed
  process group and invokes process-tree termination on timeout.
- `CodexWorkerResult` and `RuntimeState` now carry `worker_lifecycle` evidence
  so reports and recovery flows can inspect worker process state.
- `RuntimeRecovery` includes lifecycle recovery evidence for reset active,
  failed, or blocked tasks.

Remaining work in V2.23.3 is product polish: show lifecycle records in the
browser console, add a user-facing cleanup command, and run one more real
timeout smoke with the standalone Codex CLI when a deliberately long task is
safe to execute.

The first V2.23.4 requirement coverage matrix is implemented:

- `runtime.requirement_coverage.RequirementCoverageBuilder` maps each
  requirement to planned tasks, implementation files, static/browser artifact
  evidence, task evidence, and coverage status.
- `DocumentRunPipeline` now writes `requirement_coverage` into
  `document_run_report.json`.
- Missing must-requirements are listed explicitly as
  `missing_must_requirement_ids`; partial must-requirements are listed as
  `partial_must_requirement_ids`.

The evaluator hard-gate integration is implemented: requirement coverage in
runtime state lowers `spec_alignment`, and missing must-requirements block the
final DONE gate instead of only appearing in the delivery report. Remaining
work in V2.23.4 is report/UI polish for explaining partial coverage to the user
before execution starts.

The first V2.23.5 generated CI path is implemented:

- `runtime.generated_ci.StaticWebCIGenerator` creates
  `.github/workflows/alchemy-static-checks.yml` for static web/canvas artifacts
  when real GitHub CI collection is enabled and no existing workflow is present.
- `DocumentRunPipeline` records the static-CI generation intent and artifact
  profile in runtime state.
- The runtime release task generates the workflow immediately before
  `GitHubFlow.record_execution`, so `git add`, commit, push, and PR creation
  include the workflow in the same delivery branch.
- Existing generated workflow evidence is preserved instead of being overwritten
  by a later "existing workflow" skip result.
- `--no-generate-static-ci` disables this behavior when an operator wants to
  avoid adding workflows.

Remaining work in V2.23.5 is a real external target rerun with CI collection
enabled to confirm the generated workflow appears in the PR and GitHub reports a
terminal check state.

The first V2.23.6 delivery report productization pass is implemented:

- `autodev.delivery_report.build_delivery_report` produces a stable
  `delivery_report` summary with final gate, PR/branch/commit/CI, artifact,
  screenshots, requirement coverage, generated CI, blockers, worker lifecycle,
  preflight, workspace, and next actions.
- `DocumentRunPipeline` writes `delivery_report` into
  `document_run_report.json` and `run.json`.
- `GET /projects/{project_id}/delivery` returns the summary alongside the raw
  runtime state and evidence sections.
- The local browser console shows a compact delivery summary above the raw JSON.
- The console run controls expose auto browser verification and generated static
  CI toggles so UI-driven runs can use the same evidence paths as the CLI.

Remaining work in V2.23.6/V2.23.7 is richer visual task graph and requirement
coverage preview before execution.

V2.23 final local verification passed after the release-time CI hook:

- full unit suite: `132` tests passed
- external docs-only acceptance harness: `6/6` checks passed
- main acceptance harness: `8/8` checks passed
- all JSON specs parse
- `git diff --check` reports no whitespace errors, only CRLF normalization
  warnings for long-running state logs
- long-running state validation passes
