# V2.55 Evidence Console Redesign

## Purpose

V2.55 turns the browser console delivery area into an operator-ready evidence workbench. The runtime already exposes evidence indexing, packaging, benchmark regression, and readiness gates; the console must make those gates visible and actionable without changing execution semantics.

This phase supports the original autonomous development goal by making final review closer to the manual engineering loop:

1. read the generated delivery evidence,
2. inspect requirements, probes, artifacts, and blockers,
3. run evidence index/package/readiness checks from one place,
4. decide whether the system is ready for human acceptance or needs another iteration.

## Scope

In scope:

- Redesign `server/static/index.html` delivery panel into a compact evidence command center.
- Add a one-click English/Chinese language switch for the console chrome and evidence workbench.
- Add tabbed delivery views for overview, artifacts, evidence gate, and raw JSON.
- Wire browser controls to existing APIs:
  - `POST /evidence/index`
  - `POST /evidence/package`
  - `POST /evidence/readiness`
- Render readiness checks, blockers, and output paths in the UI.
- Preserve existing project creation, run execution, polling, SSE, graph, coverage, artifact preview, and feedback reopen flows.
- Add static asset tests that pin the new evidence workbench contract.

Out of scope:

- No new runtime execution behavior.
- No new agents, schedulers, or evaluator rules.
- No mutating GitHub benchmark run.
- No redesign of the full application shell beyond the delivery/evidence surface.

## UX Contract

The delivery panel must expose four operator views:

| View | Purpose |
| --- | --- |
| Overview | Final status, gate score, high-signal delivery metrics, evidence cards, and detailed review sections. |
| Artifacts | Generated evidence artifacts and requirement coverage visualization. |
| Evidence Gate | Evidence root/path inputs plus index, package, and readiness actions. |
| Raw JSON | Full delivery payload for debugging and audit traceability. |

The visual style should be:

- high-end, minimal, and technical,
- dense enough for repeated engineering review,
- readable on desktop and mobile,
- consistent with the existing single-page console structure.

## API Binding Contract

Evidence Index action:

```json
{
  "roots": [
    ".alchemy/v2_47_real_unified_delivery",
    ".alchemy/v2_48_pr_lifecycle_inspect",
    ".alchemy/v2_50_benchmark_suite",
    ".alchemy/v2_52_benchmark_regression"
  ],
  "output": ".alchemy/ui_evidence_index.json"
}
```

Evidence Package action:

```json
{
  "roots": [
    ".alchemy/v2_47_real_unified_delivery",
    ".alchemy/v2_48_pr_lifecycle_inspect",
    ".alchemy/v2_50_benchmark_suite",
    ".alchemy/v2_52_benchmark_regression"
  ],
  "output": ".alchemy/ui_evidence_package",
  "clean_output": true
}
```

Evidence Readiness action:

```json
{
  "evidence_index": ".alchemy/ui_evidence_index.json",
  "evidence_package": ".alchemy/ui_evidence_package/evidence_package_manifest.json",
  "benchmark_regression": ".alchemy/v2_52_benchmark_regression/benchmark_regression_report.json",
  "output": ".alchemy/ui_evidence_readiness"
}
```

The UI may update path inputs after successful index/package actions so the next gate can run without manual copying.

Evidence roots should be curated to the current review package. Scanning the entire historical `.alchemy` cache is allowed for forensic inspection, but it can surface stale failed or blocked reports and should not be the default final-readiness gate input.

## Acceptance Criteria

- Browser console contains a delivery header, readiness badge, gate score, tab controls, and evidence workbench controls.
- Browser console can switch between English and Chinese without reloading, including evidence gate labels, status text, and file-upload chrome.
- Existing delivery evidence still renders when a run completes or a deep link is loaded.
- Evidence index/package/readiness actions call the existing APIs and render their outputs.
- New UI identifiers and JavaScript functions are pinned by `tests.test_api_server.ApiServerTests.test_http_api_serves_console_static_assets`.
- `tests.test_evidence_api` continues to pass.
- Full unit test suite passes.
- Long-running task state validates.
