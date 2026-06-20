# V2.44 Real Document-Run Local Smoke

V2.44 keeps the original goal unchanged: detailed development documents and
repository context should drive the agent system through planning, execution,
testing, repair, review, and delivery evidence.

V2.43 proved a single real Codex worker can edit a disposable local fixture.
V2.44 proves the next larger loop:

> Can the document-driven pipeline plan work from a development document,
> dispatch real Codex for local implementation tasks, run verification, and
> produce delivery evidence without mutating GitHub?

## Scope

The smoke is local and controlled:

- creates a disposable local fixture repository under `output_dir`;
- writes a small development document;
- runs `DocumentRunPipeline` with `real_codex=true` and `real_github=false`;
- keeps GitHub delivery in dry-run evidence mode;
- records preflight, worker lifecycle, runtime state, delivery report, and
  repository diff;
- does not clone, push, create remote branches, open PRs, wait for CI, or merge.

## Fixture

The fixture repository contains:

```text
app.py
```

The development document requires:

- implement `add(a, b)` in `app.py`;
- verify `python -c "import app; assert app.add(2, 3) == 5"`.

## Report

The smoke writes:

```text
output_dir/
  real_document_run_smoke_report.json
  repo/
  run/
```

The report includes:

- top-level status;
- document-run result summary;
- worker lifecycle evidence;
- delivery readiness;
- repository diff;
- blockers, if any.

## CLI

```bash
python -m autodev.real_document_run_smoke \
  --output .alchemy/real_document_run_smoke \
  --codex-executable codex \
  --timeout-seconds 300 \
  --summary
```

## Acceptance Criteria

V2.44 is accepted when:

- fake-runner tests cover passed and blocked report behavior;
- a real local document-run smoke passes when readiness is available;
- full regression tests pass;
- any failure is captured as a report blocker instead of an unhandled crash.

## Non-Goals

This does not test real GitHub PR creation, CI waiting, auto-merge, or private
repository cloning. Those remain separate controlled probes.
