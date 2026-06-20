# V2.43 Controlled Real Codex Worker Smoke

V2.43 keeps the original autonomous-development goal unchanged. V2.42 proved
the local machine is ready for real Codex/GitHub execution without mutating
anything. V2.43 adds the next smallest real-execution proof:

> Can a real Codex CLI worker complete one bounded task inside a disposable
> local fixture repository and return structured worker evidence?

## Scope

This smoke is intentionally narrow and local:

- creates a disposable fixture repository under `output_dir`;
- initializes git locally only for diff/boundary tracking;
- permits edits to exactly one file;
- runs one real Codex worker task;
- runs a local Python assertion as verification;
- records lifecycle, file changes, structured worker output, and blockers;
- does not clone, push, create branches on a remote, open PRs, or merge.

## Worker Task

The fixture repository contains:

```text
app.py
```

The real worker receives:

- `task_id`: `T-REAL-SMOKE-001`;
- `allowed_files`: `["app.py"]`;
- `commands_to_run`: `python -c "import app; assert app.add(2, 3) == 5"`;
- acceptance criteria requiring `add(a, b)` to return a numeric sum.

## Report

The smoke writes:

```text
output_dir/
  real_worker_smoke_report.json
  repo/
  workers/
```

Top-level report shape:

```json
{
  "schema_version": "2.43",
  "status": "passed|failed|blocked",
  "preflight": {},
  "worker_result": {},
  "verification": {},
  "repository": {},
  "blockers": [],
  "output_dir": ""
}
```

## CLI

```bash
python -m autodev.real_worker_smoke \
  --output .alchemy/real_worker_smoke \
  --codex-executable codex \
  --timeout-seconds 300 \
  --summary
```

Use `--dry-run-worker` to verify the harness without invoking real Codex.

## Acceptance Criteria

V2.43 is accepted when:

- dry/fake tests verify report shape and blocked behavior;
- if readiness is available, a local real smoke can run without touching GitHub;
- full regression tests pass;
- failure modes produce a report and blocker instead of crashing.

## Non-Goals

V2.43 does not test multi-task orchestration, GitHub PR delivery, CI waiting, or
merge behavior. Those belong to later controlled probes.
