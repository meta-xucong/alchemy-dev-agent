"""Safe, beginner-facing availability signals for local development modes."""

from __future__ import annotations

import os
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Any, Callable


CommandRunner = Callable[..., subprocess.CompletedProcess[bytes]]


class RuntimeStatusProbe:
    """Read only the non-secret connection facts that the Lab can display."""

    def __init__(
        self,
        *,
        command_runner: CommandRunner = subprocess.run,
        codex_config_path: Path | None = None,
    ) -> None:
        self.command_runner = command_runner
        codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        self.codex_config_path = codex_config_path or codex_home / "config.toml"

    def local_status(self) -> dict[str, object]:
        codex = self._command_status("codex", ["codex", "--version"])
        codex["model"] = read_toml_model(self.codex_config_path) or "未固定（使用 Codex CLI 默认模型）"
        github = self._command_status("gh", ["gh", "auth", "status"])
        return {"codex_cli": codex, "github": github}

    def _command_status(self, executable: str, command: list[str]) -> dict[str, object]:
        if not shutil.which(executable):
            return {"connected": False, "state": "missing", "label": f"未找到 {executable}"}
        try:
            result = self.command_runner(command, capture_output=True, check=False, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return {"connected": False, "state": "unavailable", "label": f"无法检查 {executable}"}
        output = (result.stdout or b"").decode("utf-8", errors="replace").strip()
        first_line = next((line.strip() for line in output.splitlines() if line.strip()), "")
        return {
            "connected": result.returncode == 0,
            "state": "ready" if result.returncode == 0 else "needs_attention",
            "label": first_line or (f"{executable} 已连接" if result.returncode == 0 else f"{executable} 需要登录或授权"),
        }


def read_toml_model(path: Path) -> str:
    """Extract only the model selector; credentials are never read into a response."""

    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return ""
    model = value.get("model", "") if isinstance(value, dict) else ""
    if not model and isinstance(value, dict) and isinstance(value.get("codex"), dict):
        model = value["codex"].get("model", "")
    return str(model).strip() if isinstance(model, str) else ""
