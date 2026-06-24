"""Subprocess helpers shared by runtime adapters."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Callable


def hidden_subprocess_startup_kwargs(*, new_process_group: bool = False) -> dict[str, Any]:
    """Return Windows startup kwargs that avoid flashing console windows."""

    if os.name != "nt":
        return {}

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if new_process_group:
        creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    kwargs: dict[str, Any] = {"creationflags": creationflags}

    startupinfo_class = getattr(subprocess, "STARTUPINFO", None)
    if startupinfo_class is not None:
        startupinfo = startupinfo_class()
        startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
        startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        kwargs["startupinfo"] = startupinfo
    return kwargs


def run_hidden(
    runner: Callable[..., subprocess.CompletedProcess[Any]],
    args: list[str],
    **kwargs: Any,
) -> subprocess.CompletedProcess[Any]:
    """Run with hidden Windows startup flags when using the real subprocess.run."""

    if runner is subprocess.run:
        kwargs = {**kwargs, **hidden_subprocess_startup_kwargs()}
    return runner(args, **kwargs)


def clean_git_env(cwd: str | Path | None = None) -> dict[str, str]:
    """Return a non-interactive Git environment isolated from parent worktrees."""

    env = os.environ.copy()
    for name in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    ):
        env.pop(name, None)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "Never"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    if cwd is not None:
        try:
            env["GIT_CEILING_DIRECTORIES"] = str(Path(cwd).resolve().parent)
        except OSError:
            pass
    return env
