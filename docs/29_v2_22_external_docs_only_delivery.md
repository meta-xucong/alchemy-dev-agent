# V2.22 External Docs-Only Delivery Closure Plan

## Purpose

V2.22 is a supplemental development document for the same Alchemy Dev Agent
goal defined in the earlier v2 documents:

```text
User objective + development documents + supporting files + GitHub repository
  -> structured context
  -> task graph
  -> Codex worker execution
  -> tests and review
  -> GitHub PR delivery
```

This document does not replace the existing v2 plan. It records the gaps found
during a real external repository test and turns those gaps into the next
implementation contract.

The tested repository contained only an initial development document. That is
exactly the representative target scenario for Alchemy: a user has already
written a project brief and wants the system to implement the product into the
linked GitHub repository.

## Relationship To Earlier Versions

V2.22 complements the existing versions as follows:

| Version | Existing role | V2.22 supplement |
| --- | --- | --- |
| V2.0 / `docs/07_v2_development_plan.md` | Defines document-driven development as the primary workflow. | Adds a real external docs-only repository acceptance target. |
| V2.4 / `docs/13_v2_document_to_plan_runtime.md` | Converts documents into requirements and task graph nodes. | Requires document-dominant planning even when the objective looks like a generated app or game. |
| V2.6 / `docs/15_v2_document_run_cli.md` | Runs document intake, planning, handoff, and execution in one command. | Requires real GitHub PR delivery to be completed by the same document-run command. |
| V2.16 / `docs/25_real_run_worktree_lifecycle.md` | Executes real Codex in an isolated worktree. | Requires the isolated worktree to be the source of the final branch, commit, PR, and report evidence. |
| V2.18 / `docs/27_real_delivery_validation.md` | Validates branch, push, PR, and CI plumbing. | Applies that delivery path to external document-driven product repositories, not only validation PRs. |
| V2.21 quality gate hardening | Blocks unhealthy CI when CI collection is enabled. | Adds explicit no-CI handling for new public repositories that do not yet define checks. |
| `examples/one_line_game_demo.md` | Demonstrates the one-line fallback artifact path. | Clarifies that one-line fallback must never override a parsed primary development document. |

## Real Test Summary

External repository:

```text
https://github.com/meta-xucong/-super-mario-test
```

Initial repository contents:

```text
super_mario_level1_spec.md
```

The document requested a complete first-level side-scrolling platform game and
included engineering details such as:

- engine, physics, renderer, input, and entity module boundaries
- tile-map level definition
- player, enemy, coin, and flag behavior
- AABB and tile collision design
- game state machine
- score and completion conditions
- performance and architecture requirements
- implementation milestones

Safety adjustment:

- The implementation target must be an original retro platformer.
- The system must not copy protected Nintendo names, characters, art, assets,
  level layouts, or exact branding.

Observed result:

- `ProjectBrief` was correctly marked `document_driven` with high confidence.
- The source repository was cloned and an isolated real-run worktree was
  created.
- Real Codex generated a playable `index.html` artifact.
- Browser smoke verification showed a nonblank rendered canvas scene with HUD
  and controls.
- A real GitHub PR was manually created after the Alchemy run:
  `https://github.com/meta-xucong/-super-mario-test/pull/1`.

The test proved that Alchemy can already produce a runnable artifact through a
real Codex worker from a docs-only repository. It also exposed several gaps that
must be closed before the system can claim product-grade one-command delivery.

## Gaps Found

### G-001: Document-Dominant Planning Was Bypassed

The run produced only one requirement:

```text
REQ-001: Create an original retro side-scrolling platform game from the user's one-line objective.
```

That happened even though the ProjectBrief was document-driven. The context
builder detected a platformer/game objective and routed to the generated
artifact path, which is intended for one-line fallback demos.

Required correction:

- If a parsed primary development document exists, planning must use document
  extraction by default.
- Generated-app fallback may run only when the brief is explicitly one-line
  generated or when no parsed requirement document exists.
- Copyright safety mitigation may rewrite unsafe protected references into
  original equivalents, but it must preserve the engineering requirements from
  the document.

### G-002: Chinese And Outline-Style Specs Need Richer Extraction

The source document used short Chinese section headings and bullet lists such as
purpose, contents, technical goals, scope, and next steps. The extractor did not
turn those bullets into separate requirements.

Required correction:

- Treat engineering sections such as contents, technical goals, architecture,
  scope, milestones, file structure, and next steps as requirement-bearing
  sections.
- Extract list items under those sections even when the heading is not literally
  "requirements" or "acceptance criteria".
- Preserve technical nouns as planning signals, including Engine, Physics,
  Renderer, Input, Entity, TileMap, AABB, collision, state machine, score,
  level, enemy AI, and finish flag.
- Attach extracted requirements to the source document ID and mark them as
  document-derived, not generated from a one-liner.

### G-003: Product Structure Was Collapsed Into One Artifact

The generated result was a playable single-file game. That is useful as an MVP,
but it did not reflect the document's engineering split into engine, physics,
renderer, input, entity, tile-map, and verification work.

Required correction:

- For an empty or docs-only repository, create a target project scaffold from
  the document instead of assuming all implementation belongs in one file.
- The planner may still choose a self-contained artifact when appropriate, but
  the task graph must preserve the document's implementation milestones and
  acceptance criteria.
- For HTML/canvas game projects, a default scaffold should be available:

```text
index.html
src/
  main.js
  engine.js
  input.js
  physics.js
  tilemap.js
  entities.js
  renderer.js
tests/
  static_checks.js
```

The exact file layout may adapt to the repository, but the task graph must not
lose the module boundaries described by the user.

### G-004: Real GitHub Delivery Was Not Productized In The Main Run

The Alchemy report recorded dry-run GitHub evidence. The actual branch, commit,
push, and PR were created manually after the generated worktree passed local
checks.

Required correction:

- A document-run started with `--real-github` must commit, push, and create or
  update a PR from the isolated execution worktree.
- The final `document_run_report.json` must contain the real PR URL, branch,
  commit SHA, and CI or no-CI evidence.
- No manual `git` or `gh` commands should be necessary after the document-run
  command succeeds.

### G-005: New Repositories Without CI Need An Explicit Delivery Policy

The external repository did not contain GitHub Actions or another check system.
`gh pr checks` therefore reported no checks.

Required correction:

- If CI exists, failed, pending, or missing terminal CI status must block the
  release gate.
- If CI does not exist, the run must choose one explicit policy:
  - bootstrap a minimal project-specific CI/check workflow before delivery; or
  - continue with an explicit no-CI waiver when the operator requested
    `--no-github-ci`.
- The report must distinguish `ci_status=passed`, `ci_status=failed`,
  `ci_status=pending`, `ci_status=unknown`, and an intentional no-CI waiver.

### G-006: Browser Artifact Verification Is Still Manual

The generated game was verified with a local browser smoke test outside the
main document-run gate.

Required correction:

- HTML/canvas/web artifacts must trigger an artifact verification step.
- The verifier should start a local HTTP server, open the page, collect console
  logs, capture a screenshot, and perform a nonblank canvas/page pixel check.
- The artifact gate should record evidence in the runtime state and final
  report.
- A browser gate should be part of DONE for generated web artifacts, not a
  manual after-check.

### G-007: External Representative Acceptance Is Missing

Existing acceptance tests validate local fixtures, internal representative
documentation runs, and GitHub delivery plumbing. They do not yet validate the
combined external docs-only path.

Required correction:

- Add a representative external or fixture-based docs-only acceptance harness.
- It must start from a repository containing only a development document.
- It must run real Codex when a configured executable is available.
- It must produce a branch, PR evidence, verification evidence, and final
  report without manual post-processing.

## Required V2.22 Contracts

### Document Dominance Rule

```text
If ProjectBrief.primary_input_mode == document_driven
and at least one required primary document has parse_status == parsed:
    ContextBundle requirements must be extracted from documents.
    Generated one-line fallback is prohibited.
```

Exceptions:

- The document is unreadable and intake records a blocker.
- The user explicitly requests one-line fallback mode.
- A deterministic safety rewrite is needed for protected IP, but the rewrite
  must preserve document-derived engineering requirements.

### Safety Rewrite Rule

Unsafe protected terms should be normalized into safe original equivalents:

```text
Super Mario / Mario / Goomba / Nintendo-specific art
  -> original retro side-scrolling platformer terms
```

The rewrite applies to names, branding, visual identity, and exact layouts. It
does not remove broad genre mechanics such as jumping, platforms, coins,
enemies, timers, score, and finish flags.

### Requirement Coverage Rule

A document-driven run must report:

- `document_requirement_count`
- `generated_fallback_requirement_count`
- `document_requirement_coverage`
- list of headings or sections used for extraction
- list of ignored sections with reasons

Minimum acceptance for a structured docs-only repository:

```text
document_requirement_count >= 5
generated_fallback_requirement_count == 0
document_requirement_coverage >= 0.80
```

The exact threshold can be adjusted for tiny documents, but fallback must be
visible and reviewable.

### External Delivery Evidence Rule

When `--real-github` is enabled, final delivery evidence must include:

- execution worktree path
- branch name
- commit SHA
- PR URL
- base branch
- changed files
- CI status or explicit no-CI waiver
- commands run by the GitHub flow

`status=done` must not rely on dry-run PR evidence when real GitHub mode was
requested.

### Web Artifact Verification Rule

If the task graph creates or modifies web entrypoints such as `index.html`,
`src/main.js`, or a detected frontend app, DONE should require web artifact
verification evidence when no stronger project test exists.

Minimum web evidence:

- page can be served locally
- page opens without console errors
- rendered output is nonblank
- expected root element or canvas is present
- screenshot path is recorded

For canvas games:

- canvas element is present
- animation loop or render call is present
- keyboard or touch controls are present
- objective-specific entities or level data are detected where feasible

## Implementation Roadmap

### V2.22.1 Planner Safety Patch

- Remove objective-only generated-app routing for document-driven briefs.
- Add tests that a parsed primary development document overrides game/objective
  keyword shortcuts.
- Ensure the one-line demo path remains available only for one-line fallback.

### V2.22.2 Richer Markdown And Chinese Requirement Extraction

- Add broader heading aliases for Chinese and outline-style technical specs.
- Extract bullets under contents, technical goals, architecture, file
  structure, milestones, and next steps.
- Preserve section metadata in the requirement map.
- Add regression tests using the external platformer spec shape.

### V2.22.3 Empty-Repository Product Scaffolding

- Detect repositories that contain only docs or no implementation files.
- Build scaffold tasks from document-derived architecture and file-structure
  requirements.
- For HTML/canvas game targets, create a safe default project layout or record
  why a single-file implementation was intentionally selected.

### V2.22.4 Built-In Web Artifact Verification

- Add a deterministic artifact verifier for static HTML/canvas outputs.
- Persist screenshot path, console logs, DOM/canvas checks, and pixel evidence.
- Feed verifier evidence into the test and review gate.

### V2.22.5 Real GitHub Document-Run Delivery Closure

- Ensure `autodev.document_run --real-github` commits and pushes from the
  execution worktree.
- Ensure the final report records the real PR URL instead of dry-run evidence.
- Add no-CI waiver evidence when `--no-github-ci` is explicitly selected.

### V2.22.6 External Docs-Only Acceptance Harness

- Add a fixture or controlled external repository scenario containing only a
  development document.
- Run the full pipeline from repository clone to PR/report.
- The harness should pass only when no manual git, gh, browser, or report edits
  are required after the main command.

### V2.22.7 UI/API Evidence Surfacing

- Surface document coverage, fallback use, web artifact evidence, PR URL, and
  CI/no-CI status in the local API and browser console.
- Show a warning before execution when document coverage is low.

## Acceptance Criteria

V2.22 is complete when all of the following pass:

- A docs-only repository with a parsed primary development document produces
  document-derived requirements, not generated one-line fallback requirements.
- The platformer-style external fixture extracts at least these requirement
  themes: engine, physics, renderer, input, entity, tile-map, collision, game
  state, scoring, finish condition, and milestone execution.
- The task graph contains implementation tasks that preserve the document's
  engineering structure.
- A real Codex run can implement the target inside an isolated worktree.
- The document-run command can create or update a real GitHub PR without manual
  post-processing when `--real-github` is enabled.
- Repositories without CI either receive a generated check workflow or record an
  explicit no-CI waiver requested by the operator.
- HTML/canvas outputs include built-in browser artifact verification evidence.
- The final report clearly states whether the run is `done`, `blocked`, or
  `in_progress`, with exact blockers and evidence.

## Non-Goals

V2.22 does not add new agent roles, a new task graph schema, a new evaluator, or
a second worker protocol.

V2.22 also does not permit copying protected commercial game art, exact level
layouts, names, or branding. It supports safe original implementations derived
from the user's functional and technical requirements.

## Implementation Result

V2.22.1 through V2.22.6 are implemented in the current runtime:

- parsed primary documents now dominate one-line generated fallback planning
- Chinese guidance lines and outline-style lists are extracted as requirements
- unsafe protected game references are normalized into original neutral terms
- empty web game repositories receive scaffold-aware file hints
- complete docs-only web game scaffold delivery is grouped into one
  implementation task
- static HTML/canvas artifact verification is deterministic in the runtime
- explicit no-CI waiver evidence is recorded when PR checks are intentionally
  skipped
- real GitHub delivery uses the isolated worktree branch and sets a local bot
  commit identity when needed
- the external docs-only acceptance harness is available as
  `python -m autodev.external_docs_only_acceptance`

The real public target repository was delivered through:

```text
https://github.com/meta-xucong/-super-mario-test/pull/2
```

That PR contains an original playable retro platformer Level 1 generated from
the docs-only repository, with static artifact checks and browser smoke evidence
recorded in the Alchemy run artifacts.

The remaining optional productization step is to automate browser playability
evidence capture inside `DocumentRunPipeline`; the current real delivery already
uses browser smoke verification as an explicit final audit step.
