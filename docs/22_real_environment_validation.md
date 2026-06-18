# V2.13 Real Environment Validation

## Purpose

V2.13 records whether this machine can run real external repository validation.

Local deterministic acceptance already passes. Real validation requires:

- `git`
- `gh`
- authenticated GitHub CLI
- launchable Codex CLI
- a representative target repository and development document

## Command

```bash
python -m autodev.real_env_check --output .alchemy/real_env_check
```

The command writes:

```text
.alchemy/real_env_check/real_environment_report.json
```

## Current Result

On this machine:

- `git` passed.
- `gh` passed.
- `gh auth status` passed.
- `codex --version` failed with Windows access denied.

Status:

```text
blocked
```

Blocker:

```text
B-ENV-CODEX
```

## Required Resolution

Real Codex worker validation needs a launchable Codex CLI entry point.

Acceptable fixes include:

- repairing the installed Codex Desktop/CLI package so `codex --version` works from PowerShell
- installing a separate Codex CLI executable available on `PATH`
- providing an alternate executable path via `--codex-executable`

Until then, the system can run deterministic dry-run acceptance and GitHub preflight, but not real Codex worker execution.
