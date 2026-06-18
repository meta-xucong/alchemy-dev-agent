# V2 Alignment Audit

## Audit Result

Status: `V2_RUNTIME_READY_FOR_CONTROLLED_REAL_DELIVERY_VALIDATION`

This audit checks whether the v2 development plan matches the user's intended workflow:

> A user provides detailed development documents, supporting files, and an optional GitHub repository. The system must analyze that package, build context, coordinate agents, execute code changes through Codex workers, test, review, and close the loop only when delivery quality is reached.

## Audit 1: Scenario Fit

| Requirement | Covered By | Result |
| --- | --- | --- |
| Detailed development document is the main path. | `docs/07_v2_development_plan.md`, `docs/08_intake_and_context.md` | Pass |
| Multiple supporting files are supported. | `docs/08_intake_and_context.md`, `docs/09_ui_and_api_requirements.md`, `specs/project_brief_schema.json` | Pass |
| GitHub repository links are supported. | `docs/07_v2_development_plan.md`, `docs/08_intake_and_context.md` | Pass |
| Public repositories are the primary GitHub path. | `docs/08_intake_and_context.md`, `docs/09_ui_and_api_requirements.md`, `docs/12_v2_public_github_source_runtime.md` | Pass |
| Private repositories remain an optional GitHub CLI authentication path. | `docs/08_intake_and_context.md`, `docs/09_ui_and_api_requirements.md`, `docs/20_v2_private_github_source_adapter.md` | Pass |
| One-line prompt is only a fallback. | `docs/07_v2_development_plan.md`, `specs/project_brief_schema.json` | Pass |
| Agent cluster remains the execution mechanism. | `docs/07_v2_development_plan.md` | Pass |
| Document-driven plans can enter runtime execution. | `runtime/handoff.py`, `autodev/document_run.py`, `docs/14_v2_plan_to_execution_handoff.md`, `docs/15_v2_document_run_cli.md` | Pass |

## Audit 2: Contract Fit

| Contract | Source | Result |
| --- | --- | --- |
| Intake contract | `ProjectBrief` | Pass |
| Context contract | `ContextBundle` | Pass |
| Planning handoff | `ProjectBrief -> ContextBundle -> TaskGraph` | Pass |
| Execution contract | Existing runtime state, task graph, worker, evaluator | Pass |
| Completion contract | Existing evaluation gate plus document acceptance criteria | Pass |

The v2 documents do not create a second runtime model. They add pre-execution contracts that feed the existing graph and execution loop.

## Audit 3: Current Runtime Boundary

Current runtime capabilities:

- CLI objective input.
- Deterministic dry-run execution.
- Real Codex worker adapter.
- Task graph scheduling.
- Retry and debug task generation.
- Evaluation gate.
- GitHub execution evidence.
- Persistent runtime state.
- V2.1 ProjectBrief generation from local files and GitHub URL metadata.
- A narrow local one-line demo pipeline that generates an original retro platformer artifact through ProjectBrief, ContextBundle, TaskGraph, deterministic local agents, static verification, and reviewer evidence.
- V2.2 local repository indexing and ContextBundle repository/test-profile enrichment.
- V2.3 public GitHub clone/fetch/checkout source runtime.
- V2.4 deterministic requirement extraction, traceability, and task graph generation from ContextBundle.
- V2.5 plan-to-execution handoff from ProjectBrief/ContextBundle/TaskGraph to RuntimeState, worker packages, and orchestrator dry-run completion.
- V2.6 document-driven dry-run CLI that writes a complete integration report.
- V2.7 real execution flags, preflight checks, and optional public source preparation in the document-run CLI.
- V2.8 local JSON API and persistent project service for project creation, file references, intake, planning, execution runs, run events, and delivery summaries.
- V2.9 browser console, multipart uploads, async run job records, persisted run controls, and event retrieval.
- V2.10 task-boundary pause/stop controls and optional private GitHub CLI auth preflight.
- V2.11 private GitHub clone/fetch adapter through local `gh` authentication.
- V2.12 local acceptance harness that verifies intake, planning, async execution, events, and delivery reports.
- V2.13 real environment validation for local `git`, `gh`, GitHub auth, and Codex readiness.
- V2.14 standalone Codex CLI integration through an explicit executable path.
- V2.15 real Codex allowed-file and dirty-diff boundary hardening.
- V2.16 isolated real-run worktree lifecycle.
- V2.17 resumable worker execution with persisted recovery checkpoints.
- V2.18 real GitHub PR/CI validation harness and minimal CI workflow.

Planned v2 capabilities:

- Deep PDF/DOCX parsing beyond current text/Markdown/JSON/YAML/local file cataloging.
- Private repository end-to-end delivery validation through optional `gh` authentication.
- Deep document parser pipeline and semantic code summarization.
- Representative end-to-end real Codex plus GitHub delivery against non-trivial target repositories.
- Richer browser UI for graph visualization and delivery evidence review.
- Hard worker cancellation and true live event streaming.

Result: Pass.

The v2 plan clearly separates implemented runtime capabilities from planned product/runtime expansion.

## Audit 4: Missing Capability Inventory

The current codebase does not yet implement or prove:

- Deep PDF/DOCX document parser pipeline.
- Proven private GitHub end-to-end delivery against a representative private repository.
- Semantic requirement contradiction detection.
- Semantic code summarization beyond deterministic file/path matching.
- Proven real Codex plus GitHub PR and CI execution across representative target repositories.
- Safe real Codex subprocess cancellation after dispatch.
- Server-sent events or WebSocket live event streaming.

It does include a deterministic local demo for one-line game generation, but that path is intentionally narrow and should not be treated as proof of general autonomous software delivery.

These are expected gaps for the next implementation phase, not contradictions in the current repository.

## Audit 5: Logic Consistency

The intended v2 flow is internally consistent:

```text
Inputs -> ProjectBrief -> ContextBundle -> TaskGraph -> Runtime Execution -> Evaluation -> Delivery
```

No step depends on unstructured user files after the context bundle is created. This keeps agents aligned with a single structured contract.

## Audit 6: Risk Review

| Risk | Status | Required Control |
| --- | --- | --- |
| Ambiguous or contradictory documents. | Known | Requirement traceability and reviewer gate. |
| Public repository clone or fetch failure. | Known | Git command blocker before planning. |
| Missing optional private repository access. | Controlled | `gh auth status` blocker before planning; private clone/fetch uses local `gh` when enabled. |
| Unsupported file type. | Known | File parser blocker before planning. |
| Weak one-line fallback requirements. | Known | Mark as generated and lower confidence. |
| UI starts execution too early. | Known | Require intake review and graph preview. |
| Spec/runtime drift. | Known | Keep schema validation and runtime contract tests. |

## Final Determination

The v2 runtime is logically ready for controlled real delivery validation.

The current application performs the local document-driven workflow, has
bounded real Codex worker validation, and now has a controlled GitHub PR/CI
validation harness. It still needs representative real Codex plus GitHub
delivery on non-trivial target repositories, deeper parsing, richer UI
observability, and hard subprocess cancellation before it should be described
as a production autonomous development system.
