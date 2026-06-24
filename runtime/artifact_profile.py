"""Artifact profile detection for generated project outputs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

MAX_CANDIDATE_FILES = 500
EXCLUDED_PATH_PARTS = {
    ".git",
    ".alchemy",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
}


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

        if _is_python_project_selection(selected):
            evidence.append("Python source or test artifact files selected.")
            return ArtifactProfile("python_project", "medium", evidence)

        if _is_documentation_only(selected):
            evidence.append("Only documentation files are selected.")
            return ArtifactProfile("documentation_only", "high", evidence)

        has_html = any(path.endswith(".html") for path in selected) or _has_file(repo, "index.html")
        if has_html and _has_canvas_game_context(combined):
            evidence.append("HTML target and game-specific markers detected.")
            return ArtifactProfile("canvas_game", "medium", evidence)

        if has_html and ("<canvas" in combined or "requestanimationframe" in combined):
            evidence.append("HTML canvas and animation loop markers detected.")
            if _has_canvas_game_context(combined):
                evidence.append("Game-specific markers detected.")
                return ArtifactProfile("canvas_game", "high", evidence)
            return ArtifactProfile("static_web_app", "medium", evidence)

        if has_html:
            evidence.append("HTML entrypoint detected.")
            return ArtifactProfile("static_web_app", "medium", evidence)

        return ArtifactProfile("unknown", "low", ["No known artifact profile markers were detected."])


def _candidate_files(repo: Path, files: list[str] | None) -> list[str]:
    if files:
        return _expand_file_patterns(repo, files)
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


def _contains_any_game_marker(text: str, markers: tuple[str, ...]) -> bool:
    return any(_contains_game_marker(text, marker) for marker in markers)


def _has_canvas_game_context(text: str) -> bool:
    chinese_game_markers = ("游戏", "关卡", "玩家", "敌人", "金币", "物理", "碰撞")
    if any(marker in text for marker in chinese_game_markers):
        return True

    explicit_game_phrases = (
        "canvas game",
        "platform game",
        "video game",
        "game loop",
        "gameplay",
        "platformer",
        "tilemap",
        "side scroller",
        "side-scroller",
        "arcade",
    )
    if any(phrase in text for phrase in explicit_game_phrases):
        return True

    strong_markers = (
        "enemy",
        "coin",
        "collision",
        "physics",
        "projectile",
        "sprite",
        "tile",
    )
    weak_markers = ("player", "level", "renderer", "score", "jump")
    strong_count = sum(1 for marker in strong_markers if _contains_game_marker(text, marker))

    if strong_count >= 2:
        return True
    return False


def _contains_game_marker(text: str, marker: str) -> bool:
    if any("\u4e00" <= char <= "\u9fff" for char in marker):
        return marker in text
    pattern = rf"(?<![a-z0-9_]){re.escape(marker)}s?(?![a-z0-9_])"
    return re.search(pattern, text) is not None


def _is_documentation_only(files: list[str]) -> bool:
    return bool(files) and all(Path(file).suffix.lower() in {".md", ".txt", ".rst"} for file in files)


def _is_python_project_selection(files: list[str]) -> bool:
    if not files:
        return False
    web_like_suffixes = {".html", ".css", ".js", ".mjs", ".cjs", ".jsx", ".tsx", ".ts"}
    if any(Path(file).suffix.lower() in web_like_suffixes for file in files):
        return False
    python_like = [
        file
        for file in files
        if Path(file).suffix.lower() == ".py" or "/tests/" in file.replace("\\", "/") or file.replace("\\", "/").startswith("tests/")
    ]
    return bool(python_like)


def _expand_file_patterns(repo: Path, files: list[str]) -> list[str]:
    repo = repo.resolve()
    resolved: list[str] = []
    seen: set[str] = set()
    for value in files:
        clean = str(value).replace("\\", "/").strip()
        if not clean:
            continue
        matches = _matches_for_pattern(repo, clean)
        if not matches and _has_glob_chars(clean):
            continue
        if not matches:
            matches = [clean]
        for match in matches:
            normalized = match.replace("\\", "/").strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                resolved.append(normalized)
            if len(resolved) >= MAX_CANDIDATE_FILES:
                return resolved
    return resolved


def _has_glob_chars(pattern: str) -> bool:
    return any(char in pattern for char in "*?[]")


def _matches_for_pattern(repo: Path, pattern: str) -> list[str]:
    path = Path(pattern)
    if path.is_absolute():
        try:
            path = path.resolve().relative_to(repo)
        except ValueError:
            return []
        pattern = str(path).replace("\\", "/")

    target = repo / pattern
    if target.is_file() and _include_candidate_file(target, repo):
        return [str(target.relative_to(repo)).replace("\\", "/")]
    if target.is_dir():
        return _files_under(target, repo)
    for suffix in ("/**", "/**/*"):
        if pattern.endswith(suffix):
            base = repo / pattern[: -len(suffix)]
            if base.is_dir():
                return _files_under(base, repo)
    if any(char in pattern for char in "*?[]"):
        matches = [
            candidate
            for candidate in repo.glob(pattern)
            if candidate.is_file() and _include_candidate_file(candidate, repo)
        ]
        return sorted(str(candidate.relative_to(repo)).replace("\\", "/") for candidate in matches)[:MAX_CANDIDATE_FILES]
    return []


def _files_under(directory: Path, repo: Path) -> list[str]:
    matches = [
        candidate
        for candidate in directory.rglob("*")
        if candidate.is_file() and _include_candidate_file(candidate, repo)
    ]
    return sorted(str(candidate.relative_to(repo)).replace("\\", "/") for candidate in matches)[:MAX_CANDIDATE_FILES]


def _include_candidate_file(path: Path, repo: Path) -> bool:
    try:
        relative = path.relative_to(repo)
    except ValueError:
        return False
    if any(part in EXCLUDED_PATH_PARTS for part in relative.parts):
        return False
    if path.stat().st_size > 2_000_000:
        return False
    return True
