# V2.49 Evidence Package Export

V2.49 keeps the original goal unchanged: Alchemy should produce autonomous
software delivery that can be trusted and reviewed. After V2.47 and V2.48, the
runtime can create total-control reports and PR lifecycle reports, but evidence
is still spread across `.alchemy` directories.

## Purpose

V2.49 answers:

> Can Alchemy export a compact, reviewable evidence package for a run or probe
> series without manually hunting through JSON files?

## CLI

```bash
python -m autodev.evidence_package \
  --root .alchemy/v2_47_real_unified_delivery \
  --root .alchemy/v2_48_pr_lifecycle_inspect \
  --output .alchemy/v2_49_evidence_package \
  --summary
```

The exporter is read-only with respect to source evidence. It copies known JSON
reports into a package directory and writes:

```text
evidence_package_manifest.json
summary.md
reports/
```

## Included Reports

By default, only known Alchemy evidence reports are included:

- `unified_run_report.json`
- `document_run_report.json`
- `delivery_report.json`
- `development_cycle.json`
- `real_unified_delivery_report.json`
- `real_probe_index.json`
- `github_pr_lifecycle_report.json`
- `real_delivery_validation_report.json`
- `real_readiness_report.json`
- `real_worker_smoke_report.json`
- `real_document_run_smoke_report.json`

Unknown JSON can be included only with `--include-unknown-json`.

## Manifest Contract

The package manifest records:

- `schema_version = 2.49`;
- package status;
- source roots;
- copied files;
- package-relative file paths;
- report status;
- schema version;
- SHA-256 hash;
- byte size;
- compact per-report summary;
- package-level status counts, blocker counts, and failed required gates.

## Safety Model

The exporter:

- does not call Codex;
- does not call GitHub;
- does not inspect arbitrary non-JSON files;
- ignores unknown JSON by default;
- reports invalid JSON or missing roots as blockers.

## Acceptance Criteria

V2.49 is accepted when:

- known reports are copied into a package directory;
- unknown JSON is ignored unless explicitly included;
- missing roots produce blockers;
- `summary.md` and `evidence_package_manifest.json` are written;
- `real_probe_index` can index `evidence_package_manifest.json`;
- a package can be generated from current V2.47/V2.48 evidence;
- full unit tests, JSON parsing, diff hygiene, and state validation pass.

