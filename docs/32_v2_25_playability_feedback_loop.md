# V2.25 Playability Feedback Loop

## Purpose

V2.25 keeps the original Alchemy Dev Agent objective unchanged: a user can provide a development objective, detailed documents, supporting files, and a GitHub repository, then the agent system plans, implements, tests, fixes, delivers, and verifies the result.

The gap found after the V2.24 external game rerun was not basic execution. The generated browser game could open, render, and respond to input, but manual testing still found product-level bugs. The previous gates proved that the page was alive, not that the game loop was semantically playable.

V2.25 turns that manual playtest feedback into a machine-checkable acceptance layer.

## Relationship To Earlier Documents

- V2.23 made browser artifact evidence first-class with screenshots, console errors, blank-screen checks, and pixel diff.
- V2.24 made the human long-task SOP machine-checkable through `development_cycle`.
- V2.25 adds semantic behavior checks for generated interactive artifacts, starting with canvas games.

These documents are cumulative. V2.25 does not replace V2.23 or V2.24; it tightens the same delivery goal.

## Problem Observed In Practice

The V2.24 generated game passed:

- static artifact inspection
- local browser launch
- screenshot capture
- nonblank canvas check
- keyboard interaction pixel diff
- console-error check
- generated static CI
- PR merge evidence

Those checks still miss bugs such as:

- player does not move according to game state even if pixels change
- jump input is wired but ineffective
- level cannot reach a victory state
- restart resets the screen but not the underlying state
- game soft-locks after win, death, or retry
- implementation hides problems behind animation without exposing testable state

## New Contract

Generated canvas games must expose a deterministic browser-test hook:

```js
window.__ALCHEMY_GAME_TEST__ = {
  snapshot() {
    return {
      player_x: 0,
      player_y: 0,
      state: "playing",
      won: false
    };
  },
  step(dt) {},
  advanceToVictory() {},
  restart() {}
};
```

Required semantics:

- `snapshot()` returns numeric `player_x`, numeric `player_y`, `state`, and `won`.
- `step(dt)` advances deterministic game simulation for automated probes.
- `advanceToVictory()` moves the game into a reachable win state without requiring fragile pixel automation.
- `restart()` returns the game to a playable state.
- The hook must not require external assets, network calls, secret state, or user credentials.

## Runtime Behavior

For `canvas_game` artifacts, automatic browser verification now performs:

1. Load the generated artifact in a local static server.
2. Capture initial screenshot and console errors.
3. Verify the canvas is nonblank.
4. Dispatch right-move input and check that `snapshot().player_x` increases.
5. Dispatch jump input and check that `snapshot().player_y` changes.
6. Call `advanceToVictory()` and require a win/complete state.
7. Call `restart()` and require a playable state.
8. Capture post-interaction screenshot and compute pixel diff.
9. Fail the browser artifact gate when gameplay probe evidence is missing or failed.

The browser verification result includes:

```json
{
  "gameplay_probe": {
    "status": "completed",
    "tests_passed": [],
    "tests_failed": [],
    "evidence": [],
    "snapshots": {}
  }
}
```

## Static Gate

Static web artifact verification now rejects `canvas_game` artifacts that omit:

- `window.__ALCHEMY_GAME_TEST__`
- `snapshot()`
- `advanceToVictory()`
- `restart()`

Generated static CI also checks for the hook when a fallback static workflow is created for canvas/game-like artifacts.

## Worker Prompt Requirement

Codex worker prompts must explicitly instruct generated canvas games to include the deterministic gameplay hook. This keeps the contract available before browser automation runs and makes failures repairable by the debug loop.

## Development Cycle Impact

The `development_cycle.testing` step now treats a canvas game as incomplete unless:

- evaluator test health is present
- static verification passes
- browser verification does not fail
- gameplay probe status is `completed`
- CI is passed, waived, or not requested

This moves the system closer to the user's manual engineering loop:

```text
read docs -> refine -> implement -> audit -> test -> play/accept -> fix -> repeat -> deliver
```

## Delivery Report Impact

Delivery reports expose:

- `artifact.gameplay_status`
- `artifact.gameplay_probe`

The browser console also displays Gameplay in the delivery summary so manual review can immediately see whether semantic playability passed.

## User Feedback Loop

When a user reports "it runs, but still has bugs", the next runtime iteration should:

1. Convert the feedback into acceptance checks.
2. Add or tighten deterministic probes.
3. Re-run static, browser, gameplay, CI, and development-cycle gates.
4. Only mark delivery complete after the new probes pass.

This preserves the original autonomous-development target while making each real-world test result strengthen the system.

## Remaining Follow-Up

- Generalize semantic probes beyond canvas games to forms, dashboards, CRUD apps, and API services.
- Add a structured user-feedback intake document type that turns reported bugs into requirement deltas and debug tasks.
- Add richer browser-console views for gameplay probe snapshots and failed interaction traces.
- Store short replay traces for failed browser probes.
- Add optional Playwright scenario generation from development documents when a project already contains its own UI test framework.
