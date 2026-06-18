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

## Original Result

The original V2.13 check used the default `codex` command resolved from
WindowsApps. On this machine:

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

## V2.14 Resolution Path

V2.14 installs the standalone Codex CLI to an explicit tool path:

```text
D:\AI\Tools\CodexCLI\bin\codex.exe
```

Use:

```bash
python -m autodev.real_env_check \
  --output .alchemy/real_env_check \
  --codex-executable "D:\AI\Tools\CodexCLI\bin\codex.exe"
```

The local API also accepts the same path through:

```text
POST /environment/check
```

See `docs/23_codex_cli_api_integration.md`.

## Required Resolution

Real Codex worker validation needs a launchable Codex CLI entry point.

Acceptable fixes include:

- repairing the installed Codex Desktop/CLI package so `codex --version` works from PowerShell
- installing a separate Codex CLI executable available on `PATH`
- providing an alternate executable path via `--codex-executable`

Until a real target repository run is completed, the system has validated local
CLI launchability and `codex exec` smoke execution, but not arbitrary external
repository delivery.
