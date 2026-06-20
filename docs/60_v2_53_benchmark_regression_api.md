# V2.53 Benchmark Regression API

## Objective

Expose the V2.52 benchmark regression gate through the local service/API layer.

The autonomous development controller should be able to compare a current benchmark against a baseline without shelling out to a CLI command.

## Contract

The service layer MUST provide:

`ProjectService.compare_benchmark_regression(payload)`

Required inputs:

- `baseline`: path to a baseline `benchmark_suite_report.json`;
- `current`: path to a current `benchmark_suite_report.json`.

Optional input:

- `output`: output directory for `benchmark_regression_report.json`; default is `<storage_root>/benchmark_regression`.

The HTTP layer MUST expose:

`POST /evidence/benchmark-regression`

## Behavior

The endpoint:

- returns the full `benchmark_regression_report`;
- writes `benchmark_regression_report.json`;
- returns HTTP 200 when the comparison executes, even if the report status is `blocked`;
- does not run benchmarks;
- does not run Codex;
- does not mutate GitHub.

Missing or invalid baseline/current reports are represented as report blockers, not HTTP 500 errors.

## Acceptance

V2.53 is complete when:

- service tests verify a passing comparison;
- HTTP route tests verify a blocked comparison with missing baseline;
- the full unit suite passes;
- JSON parsing, diff hygiene, state validation, and CI pass.
