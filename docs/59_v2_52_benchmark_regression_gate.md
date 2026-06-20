# V2.52 Benchmark Regression Gate

## Objective

Add a machine-checkable comparison gate for repeated benchmark runs.

V2.50 proves the system can run deterministic benchmark scenarios. V2.52 answers the next automation question:

> Did the new run regress compared with a previous accepted benchmark?

This supports the original long-running development loop:

```text
implement -> test -> audit -> compare with prior evidence -> iterate or advance
```

## Scope

V2.52 compares two `benchmark_suite_report.json` files:

- a baseline report from a previously accepted run;
- a current report from the latest run.

It produces a `benchmark_regression_report.json`.

## Regression Rules

A current run MUST be blocked when:

- a baseline-passed scenario is missing from the current report;
- a baseline-passed scenario now has any non-`passed` status;
- the current summary has more failed scenarios than the baseline;
- the current overall status is not `passed`.

A current run MAY still pass when:

- durations change;
- stdout/stderr differ;
- new scenarios are added and pass;
- baseline failures are fixed.

## Report Shape

```json
{
  "schema_version": "2.52",
  "status": "passed|blocked",
  "baseline_path": "",
  "current_path": "",
  "scenario_changes": [],
  "summary": {
    "baseline_total": 0,
    "current_total": 0,
    "resolved_failures": [],
    "new_failures": [],
    "missing_baseline_passes": [],
    "added_scenarios": []
  },
  "blockers": []
}
```

## CLI

```bash
python -m autodev.benchmark_regression \
  --baseline .alchemy/benchmark_suite_previous/benchmark_suite_report.json \
  --current .alchemy/benchmark_suite/benchmark_suite_report.json \
  --output .alchemy/benchmark_regression \
  --summary
```

## Integration

The regression report is evidence, not an executor. It MUST NOT:

- run benchmark scenarios itself;
- run Codex;
- mutate GitHub;
- rewrite either input report.

It SHOULD be indexable by `real_probe_index` and packageable by `evidence_package`.

## Acceptance

V2.52 is complete when:

- unit tests cover passed, regressed, missing baseline, and CLI summary paths;
- `real_probe_index` recognizes `benchmark_regression_report.json`;
- `evidence_package` includes `benchmark_regression_report.json`;
- a local regression comparison against the current benchmark passes;
- the full unit suite, JSON parsing, diff hygiene, state validation, and CI pass.
