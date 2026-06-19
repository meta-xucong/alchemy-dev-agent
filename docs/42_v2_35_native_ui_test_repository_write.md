# V2.35 Native UI Test Repository Write

## Goal

V2.35 adds a controlled path for turning generated browser acceptance scenarios into repository-native UI tests.

V2.30 introduced generated Playwright/Cypress test drafts. V2.33 made those drafts previewable as delivery artifacts. V2.35 allows the system to write them into the target repository only when it is safe to do so.

## Default Behavior

The default remains:

```text
report_only
```

Generated UI tests are written under the run output directory and surfaced through `native_ui_tests.files` and `artifact_manifest`.

## Repository Write Switch

Repository writes happen only when the caller explicitly sets:

```json
{
  "write_native_ui_tests": true
}
```

or, on the CLI:

```bash
python -m autodev.document_run ... --write-native-ui-tests
```

The browser console exposes the same setting as `Write native UI tests`.

## Safety Rule

Even when the switch is enabled, the generator writes into the repository only if a supported native UI test framework is already detected:

- Playwright config,
- `@playwright/test` package evidence,
- Playwright script evidence,
- Cypress config,
- Cypress package/script/directory evidence.

If no framework is detected but the artifact is a static browser artifact, the system still generates a report-only Playwright draft and records:

```text
Repository write skipped because no Playwright or Cypress dependency/configuration was detected.
```

This prevents the runtime from adding test files that the repository cannot run.

## Paths

When repository write is allowed:

- Playwright target: `tests/alchemy_acceptance.spec.ts`
- Cypress target: `cypress/e2e/alchemy_acceptance.cy.js`

When repository write is not allowed:

- Playwright draft: `generated_tests/playwright/alchemy_acceptance.spec.ts`
- Cypress draft: `generated_tests/cypress/alchemy_acceptance.cy.js`

## Reporting

The result remains visible in:

- `native_ui_tests`
- `artifact_report.native_ui_tests`
- `runtime_state.repository.native_ui_tests`
- `delivery_report.artifact.native_ui_tests`
- `requirement_coverage` evidence
- `artifact_manifest`

## Acceptance Criteria

- Default native UI test generation is still report-only.
- Static browser artifacts without Playwright/Cypress dependencies stay report-only even when repository write is requested.
- Repositories with Playwright evidence can receive `tests/alchemy_acceptance.spec.ts`.
- Repositories with Cypress evidence can receive `cypress/e2e/alchemy_acceptance.cy.js`.
- API, CLI, and browser console all expose the same `write_native_ui_tests` control.
