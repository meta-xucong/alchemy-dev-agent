# V2.24 Development Cycle Brain

## Purpose

V2.24 converts the manual long-running engineering loop into an explicit
machine-checkable development-cycle contract.

The target loop is:

```text
long task state
  -> read development documents
  -> central-brain refinement and polishing
  -> phase planning
  -> implementation
  -> audit
  -> tests
  -> iteration/debug/retry
  -> next phase
  -> full-project audit
  -> simulated acceptance
  -> real delivery
  -> GitHub PR and optional merge
```

V2.22 and V2.23 implemented most single-project delivery mechanics. V2.24 adds
the missing meta-layer: each run now reports whether the full engineering loop
was actually followed.

## Current Assessment

The system already covers these parts in executable form:

- read detailed development documents and supporting files
- inspect public GitHub repositories, with optional private `gh` auth path
- normalize documents into ProjectBrief and ContextBundle
- refine requirements into a task graph
- dispatch implementation/test/review/release tasks
- execute real Codex workers in isolated worktrees
- run static checks, browser artifact verification, CI, and evaluator gates
- create branch/commit/PR evidence
- recover paused/stopped/failed runs
- produce delivery reports with requirement coverage and evidence

The remaining gap before V2.24 was that "central-brain refinement, audit,
iteration, next-stage development, final audit, simulated test, real test, and
merge" were spread across runtime behavior, acceptance harnesses, and operator
practice. They were not represented as one top-level contract.

## Development-Cycle Contract

Every document-run should include:

```json
{
  "development_cycle": {
    "status": "passed|partial|missing",
    "score": 1.0,
    "steps": [
      {
        "name": "read_documents",
        "status": "passed",
        "evidence": ["1 document(s) indexed."],
        "gaps": []
      }
    ],
    "next_actions": []
  }
}
```

Required steps:

| Step | Meaning |
| --- | --- |
| `long_task_state` | Persistent execution history exists. |
| `read_documents` | Development documents were indexed, or one-line fallback was explicitly waived. |
| `brain_refinement` | Requirements were normalized and mapped to task graph nodes. |
| `phase_planning` | Architecture, implementation, test, review, and release phases exist where relevant. |
| `execution` | Concrete task execution evidence exists. |
| `audit` | Reviewer evidence and requirement coverage exist. |
| `testing` | Runtime, static, browser, or CI verification evidence exists. |
| `iteration` | Debug/retry evidence exists, or clean pass waives retry. |
| `full_review` | Final gate and delivery readiness pass. |
| `simulated_acceptance` | Dry-run evidence exists, or real delivery makes simulation unnecessary. |
| `real_delivery` | Real PR evidence exists, or dry-run mode is explicitly waived. |
| `merge` | Merge evidence exists, or merge was not requested. |

## Auto-Merge Policy

Auto-merge is supported but explicit.

Default:

- `auto_merge = false`
- final delivery creates or updates a PR but does not merge it

When enabled:

- runtime attempts merge only after real GitHub delivery
- CI status must be `passed`
- failed, pending, unknown, or waived CI prevents merge
- merge evidence is stored under `runtime_state.github.merge`

This preserves safety while allowing a fully automated "develop, test, deliver,
and merge" path for trusted test repositories.

## Acceptance Criteria

V2.24 is complete when:

- `DocumentRunPipeline` writes `development_cycle` into reports
- API delivery output exposes `development_cycle`
- delivery summaries include merge status
- GitHubFlow supports explicit `auto_merge`
- unit tests cover cycle reports, auto-merge success, auto-merge skip, and UI/API payload wiring
- a new external docs-only test repository is delivered through the improved path

## External Rerun Evidence

V2.24 was validated against a fresh public docs-only repository:

- Repository:
  `https://github.com/meta-xucong/super-mario-agent-v2-24-test-20260619163034`
- Source input: one original development document copied from the prior
  `meta-xucong/-super-mario-test` experiment.
- Result: the document-run reached `done`, produced a playable original retro
  canvas platformer, generated static web CI, collected terminal GitHub check
  status, and merged PR #1.
- GitHub check: `Alchemy Static Checks / static-web` passed.
- Delivery cycle: `development_cycle.status = passed`,
  `development_cycle.score = 1.0`.

The rerun also exposed a real integration edge case: `gh pr merge` can merge a
PR successfully but still return a local cleanup error when another worktree
already owns the base branch. `GitHubFlow.merge_pull_request` now verifies the
remote PR state after merge command failures, and records `merged` when GitHub
reports the PR is already merged.

## Remaining Product Work

The next practical improvement after V2.24 is to make the development-cycle
report interactive in the browser console:

- show each step as a checklist
- let users inspect gaps before starting a real run
- show which next action will be attempted during resume
- show real delivery and merge evidence in one compact panel
