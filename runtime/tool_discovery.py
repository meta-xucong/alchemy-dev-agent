"""Shared executable discovery for preflight and runtime workers."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Mapping


CODEX_OVERRIDE_VARIABLES = ("ALCHEMY_CODEX_CLI_PATH", "CODEX_CLI_PATH")


def resolve_codex_executable(
    requested: str = "codex",
    *,
    env: Mapping[str, str] | None = None,
) -> str:
    for candidate in codex_executable_candidates(requested, env=env):
        if candidate.is_file():
            return str(candidate)
        resolved = shutil.which(str(candidate), path=(env or os.environ).get("PATH"))
        if resolved:
            return resolved
    return ""


def codex_executable_candidates(
    requested: str = "codex",
    *,
    env: Mapping[str, str] | None = None,
) -> list[Path]:
    values = env or os.environ
    candidates: list[Path] = []
    for variable in CODEX_OVERRIDE_VARIABLES:
        override = str(values.get(variable, "")).strip()
        if override:
            candidates.append(Path(override))

    requested_path = Path(requested)
    explicit_path = requested_path.is_absolute() or requested_path.parent != Path(".")
    if explicit_path:
        candidates.append(requested_path)
        return _dedupe_paths(candidates)

    if os.name == "nt" and is_codex_command(requested):
        local_appdata = str(values.get("LOCALAPPDATA", "")).strip()
        if local_appdata:
            base = Path(local_appdata) / "OpenAI" / "Codex" / "bin"
            if base.is_dir():
                versioned = sorted(
                    (path / "codex.exe" for path in base.iterdir() if path.is_dir()),
                    key=_candidate_mtime,
                    reverse=True,
                )
                candidates.extend(versioned)
            candidates.append(base / "codex.exe")
    resolved = shutil.which(requested, path=values.get("PATH"))
    if resolved:
        candidates.append(Path(resolved))
    candidates.append(requested_path)
    return _dedupe_paths(candidates)


def is_codex_command(executable: str) -> bool:
    return Path(str(executable)).name.lower() in {"codex", "codex.exe", "codex.cmd", "codex.bat"}


def _candidate_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _dedupe_paths(values: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for value in values:
        key = os.path.normcase(os.path.abspath(str(value))) if value.parent != Path(".") else str(value).lower()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result
