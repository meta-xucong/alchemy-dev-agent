# V2.59 Five-Issue Experience Audit

## Purpose

V2.59 audits the browser console against the five product issues raised after the first real beginner run.

The goal remains unchanged: Alchemy Dev Agent should let a non-technical user provide an idea, documents, or a GitHub repository, then automatically plan, implement, test, iterate, and deliver a reviewable program.

This phase does not add new orchestration features. It tightens the user-facing contract so the existing autonomous loop is understandable and controllable.

## Audit Origin

The five original issues:

1. Completed runs need an obvious result entry point.
2. Development needs visible progress and status.
3. Large tasks should not be killed by a short default timeout.
4. GitHub actions must be separated by source type and delivery mode.
5. The default frontend must be simple enough for users with no coding background.

## Findings

### 1. Result Entry Point

Status: solved.

The delivery area exposes artifact-aware actions:

- open generated browser result,
- open result folder,
- open GitHub PR only when real PR evidence exists.

### 2. Progress Visibility

Status: solved with one V2.59 improvement.

The run status panel shows phase, percent, task count, elapsed time, last activity, and stalled state.

V2.59 adds a beginner-facing Stop Development button that appears only while a run is queued, running, or paused. Advanced pause/resume controls remain hidden by default.

### 3. Worker Time Limit

Status: solved.

Product flows default `max_worker_seconds` to `0`, and worker runtime treats `0` or `None` as unlimited. Stalled detection is reporting-only and does not kill large tasks.

### 4. GitHub Action Isolation

Status: improved.

Backend evidence may still include disabled future GitHub actions for advanced inspection, but the default frontend now shows only enabled delivery actions. A local-only run therefore does not present a disabled GitHub button to beginner users.

Advanced Details can reveal the full action set for operators.

### 5. Beginner Frontend Simplicity

Status: improved.

The default console is a four-step guided flow:

1. prepare the computer,
2. choose one source,
3. watch development progress,
4. review the result.

V2.59 further reduces first-screen noise by hiding source-specific form fields until the user selects a source card. Advanced Details can reveal all source fields for operator inspection.

## Acceptance Criteria

- The default page hides advanced configuration, run controls, graph, events, evidence gate, raw JSON, and disabled delivery actions.
- Source cards show only title and description until selected.
- Selecting an idea, documents, or GitHub card reveals only that source's required fields.
- Running jobs expose a simple Stop Development action in the progress panel.
- Local-only delivery does not show a disabled GitHub publish action in the beginner view.
- Advanced Details still reveals engineering controls and complete evidence.
- Existing tests continue to pass.

## Implementation Notes

- `server/static/app.js` filters disabled delivery actions outside Advanced Details.
- `server/static/app.js` binds `progressStopRun` to the existing stop control path.
- `server/static/styles.css` hides source-specific fields until a card is selected.
- Backend contracts remain unchanged so advanced evidence consumers keep full data.
