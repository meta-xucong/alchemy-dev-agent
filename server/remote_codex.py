"""Small, token-free bridge to the Remote Codex Worker Web application.

Alchemy stores only the Worker Web address.  Authentication stays inside the
Worker Web process, where the Remote Codex project already owns it.  This
keeps the browser and Alchemy storage free of Remote Codex credentials while
allowing a project card to start a conversation and read its live progress.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .project_service import ApiError


class RemoteCodexTransport(Protocol):
    """Future adapters only need these three conversation operations."""

    def get_json(self, path: str) -> dict[str, Any]: ...
    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(slots=True)
class WorkerWebTransport:
    base_url: str
    timeout_seconds: float = 8.0

    def get_json(self, path: str) -> dict[str, Any]:
        return self._request("GET", path, None)

    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", path, payload)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json"} if body is not None else {},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # nosec B310 - user-configured local bridge.
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ApiError(502, "remote_codex_rejected", f"Remote Codex rejected the request: {detail[:240]}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ApiError(503, "remote_codex_unavailable", f"Cannot reach Remote Codex: {exc}") from exc
        if not isinstance(data, dict):
            raise ApiError(502, "remote_codex_invalid_response", "Remote Codex returned an invalid response.")
        return data


class RemoteCodexBridge:
    """Persisted endpoint configuration and a stable project-facing API."""

    def __init__(self, storage_root: str | Path, *, transport_factory=WorkerWebTransport) -> None:
        self.path = Path(storage_root) / "integrations" / "remote_codex.json"
        self.transport_factory = transport_factory

    def configuration(self) -> dict[str, object]:
        value = self._read()
        base_url = str(value.get("base_url", ""))
        if not base_url:
            return {"configured": False, "connected": False, "base_url": "", "message": "Connect Remote Codex when you need a remote conversation."}
        try:
            config = self._transport(base_url).get_json("/ui/config")
        except ApiError as exc:
            return {"configured": True, "connected": False, "base_url": base_url, "message": exc.message}
        binding = config.get("binding", {}) if isinstance(config.get("binding"), dict) else {}
        return {
            "configured": True,
            "connected": bool(config.get("logged_in")) and str(binding.get("state", "")) == "bound",
            "base_url": base_url,
            "worker_name": str(config.get("display_name", "Remote Codex")),
            "binding_state": str(binding.get("state", "unknown")),
            "message": "Remote Codex is ready for conversations." if bool(config.get("logged_in")) else "Remote Codex needs a local login first.",
        }

    def configure(self, payload: dict[str, Any]) -> dict[str, object]:
        base_url = normalise_base_url(str(payload.get("base_url", "")))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"base_url": base_url}, indent=2) + "\n", encoding="utf-8")
        return self.configuration()

    def submit_conversation(self, payload: dict[str, Any]) -> dict[str, object]:
        message = str(payload.get("message", "")).strip()
        if not message:
            raise ApiError(400, "remote_codex_message_required", "Please describe what you want to develop.")
        base_url = self._configured_url()
        parent_task_id = str(payload.get("parent_task_id", "")).strip()
        remote_payload: dict[str, Any] = {"message": message}
        if parent_task_id:
            remote_payload["parent_task_id"] = parent_task_id
        task = self._transport(base_url).post_json("/ui/tasks", remote_payload)
        return {"project_id": str(payload.get("project_id", "")), "provider": "remote_codex", "task": task}

    def task_detail(self, task_id: str) -> dict[str, object]:
        return self._transport(self._configured_url()).get_json(f"/ui/tasks/{safe_task_id(task_id)}")

    def _configured_url(self) -> str:
        base_url = str(self._read().get("base_url", ""))
        if not base_url:
            raise ApiError(409, "remote_codex_not_connected", "Connect Remote Codex before starting a remote conversation.")
        return base_url

    def _transport(self, base_url: str) -> RemoteCodexTransport:
        return self.transport_factory(base_url)

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}


def normalise_base_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ApiError(400, "invalid_remote_codex_url", "Use a plain http(s) Remote Codex Worker Web address.")
    return value.strip().rstrip("/")


def safe_task_id(value: str) -> str:
    clean = value.strip()
    if not clean or any(character in clean for character in "/\\?&#"):
        raise ApiError(400, "invalid_remote_codex_task", "Invalid Remote Codex task id.")
    return clean
