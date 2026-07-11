# Remote Codex Project Bridge

The Lab can connect to a Remote Codex **Worker Web** address without storing its token. The Worker Web remains the authentication boundary; Alchemy only stores the endpoint and proxies a small conversation contract.

The stable adapter surface is intentionally small:

- configure/status: `GET|POST /integrations/remote-codex`
- start a project-scoped conversation: `POST /projects/{project_id}/remote-codex/tasks`
- read the current conversation and its friendly progress: `GET /projects/{project_id}/remote-codex/tasks/{task_id}`

`RemoteCodexTransport` is the extension point for a future direct assistant bridge. Any new transport must retain these three user-facing operations and must not put Remote Codex credentials in the browser or Alchemy project storage.

## Development modes and status

The Lab presents two user-selectable modes:

- **Local mode** starts an Alchemy run through the local Codex CLI. `GET /runtime/status`
  reports only the safe availability state of the CLI and GitHub CLI plus the selected
  local Codex model. It never returns credentials or configuration contents.
- **Remote mode** submits a structured conversation through Worker Web. Its status is
  derived from `/ui/config`: login, worker-to-commander binding, and synchronization.
  A Worker Web can optionally expose `codex_model` (or a bound commander capability
  named `codex_model:<name>`). For a loopback Worker Web, the bridge also supports the
  current commander's local model configuration as a compatibility fallback.

The default local Worker Web address is `http://127.0.0.1:18766`. A response to
`/ui/config` that requires unrelated authentication is reported as an invalid endpoint,
not as a Remote Codex login failure.

Before `POST /projects/{project_id}/remote-codex/tasks`, the bridge refreshes the
Worker Web readiness state. This prevents a stale login or unbound worker from creating
a failed conversation request.
