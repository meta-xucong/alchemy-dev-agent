# V2.54 Evidence Readiness Gate

## Objective

Add one final machine-readable evidence gate for the long-running autonomous development loop.

Earlier phases produce separate evidence:

- `real_probe_index.json` from V2.45/V2.51;
- `evidence_package_manifest.json` from V2.49/V2.51;
- `benchmark_regression_report.json` from V2.52/V2.53.

V2.54 combines these into one report:

```text
evidence inputs -> evidence readiness gate -> ready|blocked
```

## Contract

The gate reads existing JSON reports. It MUST NOT:

- run Codex;
- run benchmark scenarios;
- mutate GitHub;
- rewrite input evidence.

It writes:

```text
evidence_readiness_report.json
```

## Required Inputs

- `evidence_index`: path to `real_probe_index.json`;
- `evidence_package`: path to `evidence_package_manifest.json`;
- `benchmark_regression`: optional path to `benchmark_regression_report.json`.

## Readiness Rules

The report is `ready` only when:

- evidence index status is `passed`;
- evidence index has at least one entry;
- diagnostic probe entries may be present, but only non-diagnostic entries count toward
  `blocked_or_failed`;
- evidence package status is `passed`;
- evidence package has at least one file;
- benchmark regression is absent or status `passed`;
- no blockers appear in any provided input.

The report is `blocked` when any required input is missing, invalid, failed, blocked, empty, or has blockers.

## CLI

```bash
python -m autodev.evidence_readiness \
  --evidence-index .alchemy/real_probe_index.json \
  --evidence-package .alchemy/evidence_package/evidence_package_manifest.json \
  --benchmark-regression .alchemy/benchmark_regression/benchmark_regression_report.json \
  --output .alchemy/evidence_readiness \
  --summary
```

## Service/API

The service layer should expose:

```text
ProjectService.evaluate_evidence_readiness(payload)
POST /evidence/readiness
```

The HTTP endpoint returns `200` with a `ready` or `blocked` evidence payload.

## Acceptance

V2.54 is complete when:

- unit tests cover ready, blocked, missing input, and CLI summary paths;
- service/API tests cover `POST /evidence/readiness`;
- local current evidence produces `status=ready`;
- full tests, JSON parsing, diff hygiene, state validation, and CI pass.
