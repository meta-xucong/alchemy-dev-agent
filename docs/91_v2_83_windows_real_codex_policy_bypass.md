# V2.83 Windows Real Codex Policy Bypass

## Problem

Billing Core phase_010 repair attempts reached the correct isolated worktree and
created fresh repair attempts, but real Codex workers still reported that the
workspace was read-only. A controlled real-worker smoke reproduced the problem:

- `codex exec --sandbox workspace-write` still rejected file patches as
  read-only on this Windows Codex CLI build.
- Adding `--ask-for-approval never` and explicit config overrides for
  `approval_policy` and `sandbox_mode` did not change the behavior.
- Shell verification commands such as `python ...` and `pnpm ...` were rejected
  by policy before execution.

This made autonomous repair attempts look like Billing Core implementation
blockers even though the repository worktree was writable.

## Fix

`runtime.codex_worker.CodexWorkerAdapter` now uses the Codex CLI
`--dangerously-bypass-approvals-and-sandbox` flag by default on Windows when the
requested sandbox is `workspace-write`.

Alchemy still constrains the blast radius through its own controls:

- real runs execute in the Alchemy-selected repository/worktree path;
- the Codex subprocess receives an explicit absolute `--cd` path;
- the worker package still includes `allowed_files` and task constraints;
- after the worker returns, Alchemy audits changed files and rolls back
  out-of-boundary changes;
- `ALCHEMY_DISABLE_CODEX_CLI_BYPASS=1` forces the older sandboxed argv when the
  local Codex CLI behavior is fixed or when a run intentionally needs that path.

The worker argv also disables Codex plugins with `--disable plugins`. Real
execution workers do not need desktop/document/browser plugins, and disabling
them prevents isolated `CODEX_HOME` startup from attempting remote plugin syncs
that can hit Windows long-path checkout failures.

## Verification

- Focused worker argv tests cover the Windows bypass path and opt-out path.
- `autodev.real_worker_smoke` failed with normal workspace-write policy and then
  passed after the bypass change.
- The passing smoke edited only `app.py` in a disposable fixture repository and
  verified `python -c "import app; assert app.add(2, 3) == 5"`.

## Operational Notes

This is a framework/runtime workaround, not a Billing Core code change. Billing
Core development should continue only through Alchemy, using the isolated
worktree recorded in the run artifacts. If future Codex CLI versions make
`workspace-write` reliable on Windows, set `ALCHEMY_DISABLE_CODEX_CLI_BYPASS=1`
and rerun the real-worker smoke before removing the bypass.
