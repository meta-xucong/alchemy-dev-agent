# V2.34 Delivery Readiness Gate

## Goal

V2.34 closes a readiness gap discovered while testing V2.33 artifact previews:

`status=done` and a numeric final gate score are not enough when later delivery evidence shows partial must-requirement coverage or failed browser probes.

The autonomous development system must not present a run as ready for human review unless the delivery evidence is internally consistent.

## Problem

Before V2.34, a run could reach `final_gate_score >= 0.85` while:

- must requirements were only partially covered,
- browser artifact verification failed,
- acceptance scenario probes failed,
- the development-cycle report was partial,
- the API job remained `running` when a run ended as `in_progress`.

That created two bad outcomes:

- The UI could show a delivery as ready even though evidence clearly requested more iteration.
- Async jobs could keep polling forever for runs that had actually finished below the delivery threshold.

## Contract

`ready_for_review` is true only when all conditions are true:

- runtime status is `done`;
- evaluator `done` is true;
- no evaluator hard failures exist;
- no blockers exist;
- requirement coverage status passed;
- no missing must requirements exist;
- no partial must requirements exist;
- static artifact verification is not failed;
- browser artifact verification is not failed;
- semantic browser probe is not failed;
- acceptance scenario browser probe is not failed;
- canvas-game gameplay probe completed;
- generated CI checks passed or are waived when generated CI is active.

## Runtime Gate

The evaluator now treats these evidence failures as hard failures:

- missing must coverage;
- partial must coverage;
- failed static artifact verification;
- failed browser artifact verification;
- failed semantic browser probe;
- failed acceptance scenario browser probe;
- missing or failed gameplay probe for canvas-game artifacts.

`DocumentRunPipeline` stores `artifact_report` in `runtime_state.repository` before re-evaluating the final gate, so the evaluator has access to the generated artifact evidence.

## Delivery Report Gate

`build_delivery_report` derives `readiness_issues` from runtime, coverage, artifact, browser, and CI evidence.

The report sets:

```json
{
  "ready_for_review": false,
  "readiness_issues": [
    "Must requirements have only partial coverage: REQ-001.",
    "Browser artifact verification failed."
  ]
}
```

The first readiness issue becomes the report summary, and all readiness issues are included in `next_actions`.

## API Job Status

An execution run with status `in_progress` is now mapped to project/job status:

```text
needs_iteration
```

This is a terminal API job status. It tells the UI to stop polling, fetch delivery evidence, and show the artifact previews plus readiness issues.

## Acceptance Criteria

- Partial must coverage blocks evaluator DONE.
- Failed browser or scenario probes block evaluator DONE.
- Delivery reports with partial must coverage or failed browser probes are not ready for review.
- Delivery reports surface readiness issues and next actions.
- Async API jobs ending as `in_progress` become `needs_iteration`, not perpetual `running`.
- The browser console renders artifact previews for `needs_iteration` runs so a reviewer can inspect evidence and decide the next repair step.
