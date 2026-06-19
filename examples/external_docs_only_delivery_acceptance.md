# External Docs-Only Delivery Acceptance Scenario

## Purpose

This acceptance scenario is the representative target for V2.22.

It validates that Alchemy can start from a public GitHub repository containing
only an initial development document and produce a real implementation delivery
without manual post-processing.

## Source Repository

```text
https://github.com/meta-xucong/-super-mario-test
```

Initial expected contents:

```text
super_mario_level1_spec.md
```

The source document describes a first-level side-scrolling platform game with
engine, physics, renderer, input, entity, tile-map, collision, scoring, enemy,
and finish-condition requirements.

## Safety Policy

The source repository uses protected commercial-game references. The Alchemy run
must convert those references into a safe original game implementation:

- no Nintendo branding
- no Mario, Luigi, Bowser, Goomba, Koopa, or Mushroom Kingdom names
- no copied sprites, assets, exact colors, or exact level layout
- broad genre mechanics are allowed: running, jumping, platforms, coins,
  enemies, timer, score, and finish flag

## Preconditions

Local machine:

- `git` is available
- `gh` is installed and authenticated
- a launchable Codex CLI executable is available
- the target repository is public or otherwise accessible through local `gh`
- the target base branch is clean before the run

Recommended Codex executable on the current Windows validation machine:

```text
D:\AI\Tools\CodexCLI\bin\codex.exe
```

## One-Command Target

The final V2.22 implementation should support a command in this shape:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -m autodev.document_run `
  --objective "Build an original retro platformer first level from the provided development document; preserve the engineering requirements but do not copy protected Nintendo characters, art, names, or exact level layouts." `
  --document .alchemy\super_mario_test_source\super_mario_level1_spec.md `
  --repository https://github.com/meta-xucong/-super-mario-test `
  --prepare-repository `
  --output .alchemy\external_docs_only_acceptance `
  --real-codex `
  --real-github `
  --no-github-ci `
  --codex-executable "D:\AI\Tools\CodexCLI\bin\codex.exe" `
  --max-worker-seconds 600 `
  --max-iterations 12 `
  --worktree-branch-prefix agent/external-docs-only
```

`--no-github-ci` is acceptable only because the current target repository has no
CI workflow. The final report must record this as an explicit no-CI waiver, not
as passed CI.

## Expected Planning Evidence

`document_run_report.json` must show:

```json
{
  "status": "done",
  "project_brief": {
    "primary_input_mode": "document_driven",
    "generated_from_one_liner": false,
    "source_confidence": "high"
  }
}
```

The context bundle must show:

- at least five document-derived requirements
- zero generated-one-line requirements
- source document IDs pointing at `super_mario_level1_spec.md`
- extracted themes for engine, physics, renderer, input, entity, tile-map,
  collision, game state, score, finish condition, and milestones

The task graph must include:

- architecture planning
- implementation tasks that preserve the document's engineering structure
- verification task
- browser/web artifact verification evidence for HTML/canvas output
- review task
- release task

## Expected Delivery Evidence

The final report must include:

- isolated execution worktree path
- real branch name
- commit SHA
- real PR URL under `https://github.com/meta-xucong/-super-mario-test/pull/`
- changed files
- GitHub command evidence
- CI status or explicit no-CI waiver
- final gate score at least `0.85`

No manual `git add`, `git commit`, `git push`, or `gh pr create` should be
needed after the command completes.

## Expected Product Evidence

For the platformer target, the generated product should include:

- original title and character naming
- local runnable web entrypoint
- canvas or equivalent browser-rendered game surface
- player movement and jump controls
- platform collision
- tile-map or level layout data
- coins or collectibles
- enemy or hazard behavior
- finish flag or completion trigger
- score, timer, state, and restart behavior

Browser verification evidence should include:

- served URL
- screenshot path
- console log summary
- nonblank pixel evidence
- detected canvas or root game surface

## Failure Classification

If this scenario does not reach `done`, the blocker must be classified as one of
the following:

- `B-DOC-COVERAGE`: document requirements were not extracted with enough
  coverage
- `B-PLANNER-FALLBACK`: document-driven planning incorrectly used generated
  one-line fallback
- `B-WORKER`: Codex worker failed or timed out
- `B-ARTIFACT-VERIFY`: generated web artifact failed browser verification
- `B-GITHUB`: branch, push, or PR creation failed
- `B-CI`: CI failed, remained pending, or was required but unavailable
- `B-ENV`: local git, gh, auth, Codex, or network environment was not ready

Each blocker must include exact command evidence and the next required action.

## Acceptance Checklist

Use this checklist before marking V2.22 complete:

- [ ] Document-derived requirements are extracted from the source spec.
- [ ] No generated-one-line requirement is used for the docs-only run.
- [ ] Task graph preserves the document's engineering modules.
- [ ] Real Codex edits the isolated worktree.
- [ ] Web artifact verification runs automatically.
- [ ] Real GitHub PR is created by the document-run command.
- [ ] CI or no-CI waiver is recorded explicitly.
- [ ] Final report contains enough evidence for user review.
- [ ] Source checkout remains clean outside the intended worktree/branch.
