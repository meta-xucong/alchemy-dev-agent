"""Artifact profile detection for generated project outputs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


ArtifactProfileName = Literal[
    "canvas_game",
    "static_web_app",
    "node_project",
    "python_project",
    "documentation_only",
    "unknown",
]


@dataclass(slots=True)
class ArtifactProfile:
    name: ArtifactProfileName
    confidence: str
    evidence: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
        }


class ArtifactProfileDetector:
    """Infer a coarse artifact profile from files, docs, and task evidence."""

    def detect(
        self,
        repository_path: str | Path,
        files: list[str] | None = None,
        *,
        objective: str = "",
        requirements: list[str] | None = None,
    ) -> ArtifactProfile:
        repo = Path(repository_path)
        selected = _candidate_files(repo, files)
        text = _combined_text(repo, selected)
        combined = "\n".join([objective, *list(requirements or []), text]).lower()
        evidence: list[str] = []

        if _has_file(repo, "package.json"):
            evidence.append("package.json detected.")
            return ArtifactProfile("node_project", "high", evidence)

        if _has_any(repo, ["pyproject.toml", "requirements.txt", "setup.py"]):
            evidence.append("Python project marker detected.")
            return ArtifactProfile("python_project", "high", evidence)

        if _is_documentation_only(selected):
            evidence.append("Only documentation files are selected.")
            return ArtifactProfile("documentation_only", "high", evidence)

        has_html = any(path.endswith(".html") for path in selected) or _has_file(repo, "index.html")
        web_game_markers = (
            "canvas",
            "tilemap",
            "platformer",
            "player",
            "enemy",
            "coin",
            "level",
            "physics",
            "renderer",
            "游戏",
            "关卡",
            "玩家",
            "敌人",
            "金币",
            "物理",
            "渲染",
        )
        if has_html and any(marker in combined for marker in web_game_markers):
            evidence.append("HTML target and game requirement markers detected.")
            return ArtifactProfile("canvas_game", "medium", evidence)

        if has_html and ("<canvas" in combined or "requestanimationframe" in combined):
            evidence.append("HTML canvas and animation loop markers detected.")
            if any(marker in combined for marker in ("game", "player", "enemy", "coin", "level", "tile", "游戏", "玩家", "敌人", "关卡")):
                evidence.append("Game-specific markers detected.")
                return ArtifactProfile("canvas_game", "high", evidence)
            return ArtifactProfile("static_web_app", "medium", evidence)

        if has_html:
            evidence.append("HTML entrypoint detected.")
            return ArtifactProfile("static_web_app", "medium", evidence)

        return ArtifactProfile("unknown", "low", ["No known artifact profile markers were detected."])


def _candidate_files(repo: Path, files: list[str] | None) -> list[str]:
    if files:
        return [str(file).replace("\\", "/") for file in files]
    if (repo / "index.html").exists():
        return ["index.html"]
    return [str(path.relative_to(repo)).replace("\\", "/") for path in repo.glob("*.md")]


def _combined_text(repo: Path, files: list[str]) -> str:
    chunks: list[str] = []
    for file_path in files:
        target = repo / file_path
        if target.exists() and target.is_file() and target.stat().st_size < 2_000_000:
            chunks.append(target.read_text(encoding="utf-8", errors="replace"))
    if (repo / "package.json").exists():
        try:
            chunks.append(json.dumps(json.loads((repo / "package.json").read_text(encoding="utf-8")), sort_keys=True))
        except json.JSONDecodeError:
            chunks.append((repo / "package.json").read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def _has_file(repo: Path, relative: str) -> bool:
    return (repo / relative).is_file()


def _has_any(repo: Path, relatives: list[str]) -> bool:
    return any(_has_file(repo, relative) for relative in relatives)


def _is_documentation_only(files: list[str]) -> bool:
    return bool(files) and all(Path(file).suffix.lower() in {".md", ".txt", ".rst"} for file in files)
