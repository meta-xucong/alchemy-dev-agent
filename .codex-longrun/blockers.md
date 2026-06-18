# Blockers

## 2026-06-18 B-ENV-CODEX

- Status: active
- Type: environment
- Summary: Real Codex worker validation is blocked because `codex --version` fails from PowerShell with Windows access denied.
- Evidence: `.alchemy/real_env_check/real_environment_report.json`
- Impact: Local dry-run acceptance, API/UI flow, GitHub CLI auth, public/private source preparation, and deterministic tests pass. Real Codex worker execution cannot be validated until a launchable Codex CLI is available.
- Required resolution: Repair the installed Codex Desktop/CLI package, install a separate Codex CLI executable available on `PATH`, or provide a working executable path via `--codex-executable`.

## 2026-06-18 B-ENV-CODEX

- Status: resolved by V2.14.
- Resolution: Installed standalone Codex CLI to `D:\AI\Tools\CodexCLI\bin\codex.exe` and validated it through `autodev.real_env_check`, the runtime worker adapter, and the HTTP API real_codex smoke.
- Remaining boundary: Full external repository delivery is not yet proven; next phase must run a controlled real repository or dedicated branch validation.
