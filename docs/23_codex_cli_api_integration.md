# V2.14 Codex CLI API Integration

## Purpose

V2.14 removes the previous real-worker blocker by installing and validating a
standalone Codex CLI entry point that the Alchemy API can call directly.

The desktop app remains the interactive operator surface. The CLI is the
non-interactive worker surface used by the runtime.

## Installation Model

Install the standalone CLI outside this repository and pass its executable path
to the API or CLI runtime:

```powershell
$env:CODEX_NON_INTERACTIVE = "1"
$env:CODEX_INSTALL_DIR = "D:\AI\Tools\CodexCLI\bin"
irm https://chatgpt.com/codex/install.ps1 | iex
```

Validated local executable:

```text
D:\AI\Tools\CodexCLI\bin\codex.exe
```

This avoids relying on the WindowsApps desktop package path, which previously
failed with access denied from PowerShell.

## Desktop App Isolation

The Codex desktop app and Codex CLI are separate entry points over the same
Codex product family:

- The desktop app is for interactive planning, review, and operator control.
- The CLI is for terminal and automation workflows.
- Installing a standalone CLI does not overwrite this repository or the active
  desktop thread.
- The CLI may reuse local Codex authentication and configuration under the
  user's Codex state directory.

Do not delete or overwrite the user's Codex state directory during setup.

## Runtime Contract

Real worker execution uses:

```text
codex exec --json --sandbox workspace-write
```

The runtime passes a bounded `codex_worker_result_v1` task package through
stdin and expects the final agent message or JSONL stream to contain:

```json
{
  "task_id": "string",
  "status": "completed|partial|failed|blocked",
  "summary": "string",
  "files_changed": [],
  "commands_run": [],
  "tests_passed": [],
  "tests_failed": [],
  "evidence": [],
  "known_issues": [],
  "follow_up_tasks": [],
  "confidence": 0.0
}
```

`workspace-write` is required for implementation tasks because the default
`codex exec` sandbox is read-only.

## API Integration

The local API can validate the machine environment:

```http
POST /environment/check
Content-Type: application/json

{
  "codex_executable": "D:\\AI\\Tools\\CodexCLI\\bin\\codex.exe"
}
```

The response is the same environment report written by:

```powershell
python -m autodev.real_env_check `
  --output .alchemy\real_env_check `
  --codex-executable "D:\AI\Tools\CodexCLI\bin\codex.exe"
```

Execution runs can also pass the same executable:

```http
POST /projects/{project_id}/runs
Content-Type: application/json

{
  "async": true,
  "real_codex": true,
  "codex_executable": "D:\\AI\\Tools\\CodexCLI\\bin\\codex.exe"
}
```

The browser console exposes the same field as `Codex CLI executable`.

## Safety Boundary

Dry-run mode remains the default.

Real Codex execution only starts when the caller explicitly sets:

```json
{
  "real_codex": true
}
```

Real GitHub mutation only starts when the caller explicitly sets:

```json
{
  "real_github": true
}
```

For first real validation, use a disposable public repository or dedicated test
branch. The runtime may edit files in the target checkout and, when real GitHub
mode is enabled, create commits, push branches, and open pull requests.

## Verification

Minimum local verification:

```powershell
D:\AI\Tools\CodexCLI\bin\codex.exe --version

python -B -m autodev.real_env_check `
  --output .alchemy\real_env_check `
  --codex-executable "D:\AI\Tools\CodexCLI\bin\codex.exe"

python -B -m unittest discover -s tests
```

CLI smoke verification:

```powershell
@'
Return exactly this JSON object and no extra prose:
{"task_id":"smoke","status":"completed","summary":"ok","files_changed":[],"commands_run":[],"tests_passed":[],"tests_failed":[],"evidence":["cli smoke"],"known_issues":[],"follow_up_tasks":[],"confidence":1.0}
'@ | D:\AI\Tools\CodexCLI\bin\codex.exe exec --json --ephemeral --sandbox read-only --skip-git-repo-check -
```

## Current Status

V2.14 is ready when:

- standalone CLI version check passes
- `codex exec --json` smoke test passes
- API environment check accepts an explicit executable path
- full unit test suite passes
