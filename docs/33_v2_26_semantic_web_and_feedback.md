# V2.26 Semantic Web And Feedback Loop

## Purpose

V2.26 extends the V2.25 playability gate beyond games. The original target remains unchanged: a detailed development document plus supporting files and a GitHub repository should drive autonomous planning, coding, testing, review, delivery, and iterative repair.

V2.25 proved that a rendered canvas game is not enough; the system must verify semantic behavior. V2.26 applies the same idea to ordinary product surfaces such as forms, dashboards, CRUD screens, and static web apps.

## Relationship To Earlier Work

- V2.23: browser screenshots, console errors, pixel diff, generated CI, requirement coverage.
- V2.24: machine-checkable development-cycle SOP.
- V2.25: semantic gameplay probe for canvas games.
- V2.26: semantic web interaction probe plus structured user-feedback intake.

## Problem

For non-game products, screenshot and DOM existence checks can miss critical bugs:

- a form renders but cannot accept input
- a submit button exists but does not update state
- dashboard filters do not change visible data
- empty-state, create, reset, or retry actions are broken
- manual reviewer feedback is not converted into the next debug iteration

## Static Web Contract

`static_web_app` artifacts are verified differently from `canvas_game` artifacts.

Static checks should confirm:

- an HTML entrypoint exists
- the page has an app root such as `<main>`, `<form>`, `<section>`, or `id="app"`
- interactive controls are detected when the app claims to support interaction
- no protected commercial game terms leak into generated artifacts

The canvas-game requirements for tile maps, physics, enemies, and gameplay hooks do not apply to ordinary web apps.

## Semantic Browser Probe

Automatic browser verification now records a `semantic_probe` object.

For `static_web_app`, the probe should:

1. Inspect the page for input, textarea, select, button, link, and clickable role controls.
2. Fill up to three text-like inputs with deterministic test values.
3. Toggle checkboxes or selects when present.
4. Click the first safe button or clickable control.
5. Compare before/after DOM summaries.
6. Record whether controls existed, whether input filling worked, whether clicking worked, and whether the visible state changed.

Expected result shape:

```json
{
  "semantic_probe": {
    "status": "completed",
    "kind": "static_web_app",
    "tests_passed": [],
    "tests_failed": [],
    "evidence": [],
    "snapshots": {}
  }
}
```

For static pages with no controls, the probe can complete with evidence that no interactive controls were present. It should not fail purely because an informational page has no form.

For `canvas_game`, `semantic_probe` aliases the existing gameplay probe so reports can consume one field across artifact types.

## Feedback Intake Contract

Manual testing feedback becomes first-class input through `feedback` role files.

Feedback files are Markdown, text, JSON, YAML, or uploaded notes whose filename or role indicates bug feedback, for example:

- `feedback.md`
- `bug_report.md`
- `playtest_notes.md`
- `验收反馈.md`

The context builder should normalize feedback into requirement-like deltas:

- each actionable bug becomes a `must` requirement
- the source document id points to the feedback file
- related files are inferred from explicit paths or existing repository context
- task planning routes feedback items to implementation, verification, and review tasks

## Done Criteria

V2.26 is complete when:

- static web app verification no longer uses canvas-game rules
- automatic browser verification records semantic probes for static web apps
- delivery reports and UI summaries surface semantic probe status
- feedback files become requirement deltas and planned debug/fix work
- unit tests, acceptance harness, JSON parsing, diff hygiene, state validation, and GitHub CI pass

## Remaining Follow-Up

- Generate Playwright scenarios from detailed acceptance documents.
- Add domain-specific semantic probes for CRUD tables, auth flows, dashboards, file uploaders, and API-backed forms.
- Persist short replay traces for failed semantic probes.
- Let user feedback reopen a delivered run and automatically create a recovery/debug branch.
