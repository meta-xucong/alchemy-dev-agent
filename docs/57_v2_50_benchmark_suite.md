# V2.50 Benchmark Suite

V2.50 keeps the original goal unchanged: Alchemy should become a reliable
automatic programming and product-building agent. Reliability requires stable
benchmarks, not only one-off successful demos.

## Purpose

V2.50 answers:

> Can the project repeatedly prove that the main user-facing dry-run paths still
> work after each implementation chapter?

## Benchmark Scope

The benchmark suite runs public CLI contracts:

- one-line fallback app generation;
- document-only generated repository delivery;
- document plus local repository delivery;
- V2.47 real-unified-delivery dry-run gate report;
- unified acceptance harness;
- V2.49 evidence package export.

Real Codex and real GitHub delivery remain outside the default benchmark because
they can consume external resources and create remote state. They should be
added as explicitly approved benchmark profiles later.

## CLI

```bash
python -m autodev.benchmark_suite \
  --output .alchemy/benchmark_suite \
  --summary
```

For a faster local check:

```bash
python -m autodev.benchmark_suite \
  --output .alchemy/benchmark_suite \
  --skip-unified-acceptance \
  --summary
```

## Report Contract

The suite writes:

```text
.alchemy/benchmark_suite/benchmark_suite_report.json
```

The report contains:

- `schema_version = 2.50`;
- benchmark status;
- per-scenario command;
- output directory;
- duration;
- stdout/stderr snapshot;
- check results;
- summary counts and failed scenario names.

## Acceptance Criteria

V2.50 is accepted when:

- fake-runner tests cover passing and failing benchmark behavior;
- CLI summary runs a lightweight benchmark successfully;
- benchmark report is generated locally;
- `real_probe_index` can index `benchmark_suite_report.json`;
- full unit tests, JSON parsing, diff hygiene, and state validation pass.

