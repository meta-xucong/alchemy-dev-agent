# V2.58 Beginner-First Console Simplification

## Objective

Alchemy Dev Agent must feel like a one-click software generation tool for non-technical users.

The default UI is not an engineering dashboard. It is a guided flow:

1. Prepare this computer
2. Choose one input source
3. Start auto development
4. Watch progress
5. Review the result

Engineering controls remain available, but only behind Advanced Details.

## User Model

Primary user:

- Does not understand task graphs, CI, workers, JSON, PR lifecycle, or evidence packaging.
- Wants to upload an idea, documents, or a GitHub URL.
- Wants to know whether the system is working, stuck, done, or needs attention.
- Wants a clear result entry point after completion.

Advanced user:

- May inspect raw state, events, task graph, evidence gate, preflight, and manual run controls.
- Can open Advanced Details explicitly.

## Required Default Screen

The first screen must expose only:

- Language switch
- API status
- Advanced Details toggle
- Environment readiness check
- Three mutually exclusive input cards:
  - one-sentence idea
  - local development documents
  - GitHub repository
- Start Auto Development
- Development Progress
- Review The Result

## Hidden By Default

The following must not appear in the normal path:

- Codex executable path
- model provider details
- CI wait and poll fields
- real worker / real GitHub / auto merge switches
- Plan / Run / Pause / Resume / Stop controls
- intake JSON
- task graph JSON
- event stream
- evidence gate workbench
- raw delivery JSON

They may be shown only when Advanced Details is enabled or a nested advanced section is opened.

## Acceptance Criteria

- A non-technical user can understand the main flow in under 30 seconds.
- The default visible controls are action-oriented, not implementation-oriented.
- The start button cannot be confused with Plan, Preflight, or Run.
- Result review has a visible main entry point after completion.
- Advanced Details never blocks the happy path.
- Switching language updates beginner-facing and advanced labels consistently.

## Implementation Notes

V2.58 keeps the existing backend contract unchanged.

Changes are limited to the console information architecture:

- `server/static/index.html` keeps existing element IDs for compatibility.
- `server/static/app.js` adds an `advancedVisible` UI state persisted in local storage.
- `server/static/styles.css` makes the default layout a single-column guided flow.
- Existing engineering panels are preserved and conditionally revealed.

## Non-Goals

- No new orchestration features.
- No backend contract changes.
- No redesign of the automation engine.
- No removal of advanced capabilities.
