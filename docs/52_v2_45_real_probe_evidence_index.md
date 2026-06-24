# V2.45 Real Probe Evidence Index

V2.45 keeps the original goal unchanged. The project now has several real or
near-real probes:

- V2.42 real environment readiness;
- V2.43 controlled real Codex worker smoke;
- V2.44 controlled real document-run local smoke.

Those reports prove important milestones, but their evidence is spread across
different output directories. V2.45 adds a non-mutating evidence index.

## Purpose

The evidence index answers:

> Which real-readiness and real-worker probes have been run, where are their
> reports, what passed, and what blockers remain?

## Scope

The indexer:

- scans one or more roots for known probe report files;
- reads JSON reports;
- normalizes each report into a compact evidence entry;
- records key fields such as status, worker status, verification status,
  preflight status, lifecycle count, blocker count, and report path;
- writes a single `real_probe_index.json`.

It does not run probes, modify repositories, call Codex, call GitHub, or open
network connections.

## Known Report Types

```text
real_readiness_report.json
real_worker_smoke_report.json
real_document_run_smoke_report.json
real_worker_probe_report.json
```

`real_worker_probe_report.json` is diagnostic evidence. A partial diagnostic probe is indexed and
shown to reviewers, but it does not block the overall index when all non-diagnostic evidence is
ready or passed. Failed or blocked diagnostic probes should still be investigated before a release
claim is made.

## CLI

```bash
python -m autodev.real_probe_index \
  --root .alchemy \
  --output .alchemy/real_probe_index.json \
  --summary
```

## Acceptance Criteria

V2.45 is accepted when:

- indexer tests cover readiness, worker smoke, document-run smoke, and unknown
  report resilience;
- the local index can discover V2.42/V2.43/V2.44 reports;
- full regression tests pass.

## Boundary

After V2.45, the remaining major unproven path is a mutating GitHub branch/PR
probe. That should require explicit human approval because it creates remote
state.
