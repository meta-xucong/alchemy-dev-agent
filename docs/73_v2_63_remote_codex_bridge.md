# Remote Codex Project Bridge

The Lab can connect to a Remote Codex **Worker Web** address without storing its token. The Worker Web remains the authentication boundary; Alchemy only stores the endpoint and proxies a small conversation contract.

The stable adapter surface is intentionally small:

- configure/status: `GET|POST /integrations/remote-codex`
- start a project-scoped conversation: `POST /projects/{project_id}/remote-codex/tasks`
- read the current conversation and its friendly progress: `GET /projects/{project_id}/remote-codex/tasks/{task_id}`

`RemoteCodexTransport` is the extension point for a future direct assistant bridge. Any new transport must retain these three user-facing operations and must not put Remote Codex credentials in the browser or Alchemy project storage.
