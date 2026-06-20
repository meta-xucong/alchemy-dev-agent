# V2.42 Real Environment Readiness Probe

V2.42 keeps the original goal unchanged: a user should be able to provide a
development package and have the agent system plan, implement, test, repair,
review, and deliver it. This phase does not add a new delivery feature. It adds
a non-mutating readiness probe for the real execution environment.

## Problem

The runtime now supports:

- dry-run unified execution;
- request-level preflight;
- one-line, document-only, local repository, and GitHub URL acceptance;
- opt-in real Codex and GitHub execution.

Before running a mutating real-worker or real-PR probe, operators need one
repeatable answer:

> Is this machine ready to run real Codex workers and GitHub PR delivery for a
> properly supplied project package?

Manual commands such as `git --version`, `gh auth status`, and `codex --version`
are useful, but they are not enough as a project artifact. V2.42 records those
checks together with unified request preflight results.

## Scope

The readiness probe is strictly non-mutating:

- no Codex worker is started;
- no repository files are modified;
- no branch is created;
- no clone/fetch is performed;
- no pull request is opened;
- no merge is attempted.

It may create local fixture files under the requested output directory and write
a JSON readiness report.

## Probe Inputs

Required:

- `output_dir`;
- `codex_executable`.

Optional:

- `require_browser`: treat browser automation as required;
- `include_private_github`: include an authenticated private-GitHub preflight
  request.

## Probe Checks

The probe combines:

1. `RealEnvironmentCheck`
   - `git --version`;
   - `gh --version`;
   - `gh auth status`;
   - `codex --version`;
   - optional browser automation import.

2. Unified request preflight for a local repository real-delivery request
   - local fixture repository path;
   - real Codex enabled;
   - real GitHub PR delivery enabled.

3. Optional unified request preflight for a private GitHub prepared-source
   request
   - private GitHub URL metadata;
   - `prepare_repository=true`;
   - real Codex and real GitHub enabled;
   - local `gh` authentication required by preflight.

## Report

The probe writes:

```text
output_dir/
  real_readiness_report.json
  environment/real_environment_report.json
  fixtures/
```

Top-level report shape:

```json
{
  "schema_version": "2.42",
  "status": "ready|blocked",
  "environment": {},
  "request_preflights": [],
  "blockers": [],
  "warnings": [],
  "output_dir": ""
}
```

`status=ready` means the machine is ready for a later controlled real-worker
probe. It does not mean a project has been delivered.

## CLI

```bash
python -m autodev.real_readiness_probe \
  --output .alchemy/real_readiness \
  --codex-executable codex \
  --summary
```

## Acceptance Criteria

V2.42 is accepted when:

- the probe writes `real_readiness_report.json`;
- fake-runner unit tests cover ready and blocked outcomes;
- a local non-mutating probe can be run on this machine;
- full regression tests pass.

## Non-Goals

V2.42 does not execute real workers, clone private repositories, create branches,
open PRs, wait for CI, or merge code. Those belong to a later controlled real
execution probe.
