# V2.51 Evidence API Service

## Objective

Expose the real-probe evidence index and evidence package exporter through the local service/API layer so a reviewer or future UI can inspect delivery readiness without running ad hoc CLI commands.

This phase does not add new execution behavior. It turns the existing V2.45-V2.50 evidence contracts into service methods and HTTP endpoints.

## Contract

The service layer MUST expose:

- a read-only evidence index operation;
- an evidence package export operation;
- stable output paths under the service storage root by default;
- the same evidence semantics as `autodev.real_probe_index` and `autodev.evidence_package`.

The service layer MUST NOT:

- mutate GitHub state;
- run Codex workers;
- rerun delivery pipelines;
- reinterpret evidence statuses differently from the CLI modules.

## Service Methods

`ProjectService.get_evidence_index(payload=None)`:

- Inputs:
  - `roots`: optional list of evidence roots; default is the configured evidence root.
  - `output`: optional JSON output path; default is `<storage_root>/evidence/real_probe_index.json`.
- Output: full `real_probe_index` payload.

`ProjectService.export_evidence_package(payload=None)`:

- Inputs:
  - `roots`: optional list of evidence roots; default is the configured evidence root.
  - `output`: optional package directory; default is `<storage_root>/evidence_package`.
  - `include_unknown_json`: optional boolean; default `false`.
  - `clean_output`: optional boolean; default `true`.
- Output: full `evidence_package_manifest` payload.

## HTTP Endpoints

`GET /evidence/index`

- Returns the current evidence index for the configured evidence root.
- Writes the generated index to the service storage root.
- Does not mutate any target repository.

`POST /evidence/index`

- Same as `GET`, but accepts `roots` and `output` overrides.

`POST /evidence/package`

- Exports a review package from the requested evidence roots.
- Writes `evidence_package_manifest.json` and `summary.md`.
- Returns the full manifest payload.

## Review Semantics

The endpoint output is review evidence, not a delivery decision by itself.

Delivery readiness remains controlled by:

- evaluator DONE gate;
- delivery report `ready_for_review`;
- browser/static/semantic/scenario/gameplay probes where applicable;
- GitHub CI evidence where applicable;
- benchmark and real-probe reports.

## Acceptance

V2.51 is complete when:

- service methods are covered by unit tests;
- HTTP route tests verify `/evidence/index` and `/evidence/package`;
- missing evidence roots return a blocked evidence package instead of crashing;
- the full unit suite passes;
- JSON parsing, diff hygiene, and long-running state validation pass.
