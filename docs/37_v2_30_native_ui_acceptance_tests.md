# V2.30 Native UI Acceptance Tests

## Purpose

V2.30 turns generated browser acceptance scenarios into repository-native UI test
artifacts.

The browser probe introduced in V2.27 answers:

```text
Did this run pass the inferred acceptance scenarios now?
```

Native UI test generation answers:

```text
Can the delivered repository keep re-running those acceptance scenarios later?
```

This moves the system closer to product-grade autonomous delivery because the
final artifact can include reusable tests, not only one-time runtime evidence.

## Scope

V2.30 supports deterministic test generation for:

- Playwright
- Cypress

Generated scenarios are derived from the existing
`artifact_report.acceptance_scenarios` contract.

This phase does not introduce a new scenario planner. It reuses the existing
scenario kinds:

- `crud`
- `auth`
- `file_upload`
- `dashboard`

## Source Contract

Input:

```json
{
  "acceptance_scenarios": {
    "status": "generated",
    "scenarios": []
  },
  "repository_path": "",
  "artifact_profile": "static_web_app|node_project|canvas_game|..."
}
```

Output:

```json
{
  "status": "generated|skipped",
  "framework": "playwright|cypress|none",
  "target_path": "",
  "write_mode": "report_only|repository",
  "summary": "",
  "files": [],
  "evidence": []
}
```

## Framework Detection

The generator chooses a framework in this order:

1. Existing Playwright markers:
   - `playwright.config.js`
   - `playwright.config.ts`
   - `@playwright/test` in `package.json`
2. Existing Cypress markers:
   - `cypress.config.js`
   - `cypress.config.ts`
   - `cypress/` directory
   - `cypress` in `package.json`
3. Static HTML fallback:
   - `index.html` exists and the artifact profile is `static_web_app` or
     `canvas_game`
   - Generate a Playwright draft in report-only mode

## Write Modes

### Repository Mode

When the repository already has a Playwright or Cypress setup, the generator may
write test files into the repository:

```text
tests/alchemy_acceptance.spec.ts
cypress/e2e/alchemy_acceptance.cy.js
```

Repository mode is intended for real Codex/GitHub delivery runs where generated
tests should be committed with the feature.

### Report-Only Mode

When no native UI test framework exists, the generator writes test drafts under
the run output directory:

```text
generated_tests/playwright/alchemy_acceptance.spec.ts
generated_tests/cypress/alchemy_acceptance.cy.js
```

Report-only mode avoids changing arbitrary repositories while still producing a
reviewable acceptance-test artifact.

## Test Semantics

Generated tests are intentionally broad and resilient. They should verify the
presence of domain behaviors without assuming exact UI implementation details.

Examples:

- CRUD: input exists, create button exists, list/table/item surface exists.
- Auth: credential input exists, password/session field exists when login is
  required, submit control exists.
- File upload: file input or visible upload control exists.
- Dashboard: metric/table/report surface exists and filter/search exists when
  required.

The generator should not produce brittle pixel-level assertions. Visual
inspection remains the browser artifact verifier's job.

## Runtime Integration

`document_run` includes a new report field:

```json
"native_ui_tests": {}
```

`delivery_report.artifact.native_ui_tests` surfaces the same summary.

`requirement_coverage` may use native test generation evidence as verification
support for requirements associated with generated scenarios.

## Acceptance Criteria

V2.30 is complete when:

- generated acceptance scenarios can be converted into a Playwright test draft
- existing Playwright repositories are detected
- existing Cypress repositories are detected
- report-only generation works for local static-web repositories
- document-run output includes `native_ui_tests`
- delivery report exposes `artifact.native_ui_tests`
- tests cover generator behavior and document-run report wiring

## Non-Goals

This phase does not:

- install Playwright or Cypress
- run generated repository-native tests
- replace the browser probe gate
- require every repository to accept generated tests automatically
- create a separate acceptance scenario schema
