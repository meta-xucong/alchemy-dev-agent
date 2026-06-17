"""Repository indexing for v2 context bundles."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from intake.models import Blocker

from .models import RepositoryFile

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".alchemy",
    ".test-tmp",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
    ".next",
    "coverage",
    "target",
    ".venv",
    "venv",
}

LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".json": "json",
    ".md": "markdown",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".toml": "toml",
    ".txt": "text",
    ".css": "css",
    ".html": "html",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".sql": "sql",
}

SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".cs", ".rb", ".php"}
TEST_HINTS = ("test", "tests", "spec", "__tests__")
DOC_SUFFIXES = {".md", ".txt", ".rst"}
CONFIG_NAMES = {
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "Dockerfile",
    "docker-compose.yml",
    "Makefile",
}
PACKAGE_FILES = {"package.json", "pyproject.toml", "requirements.txt", "go.mod", "Cargo.toml", "pom.xml"}
CI_PREFIXES = (".github/workflows/", ".gitlab-ci.yml", "azure-pipelines.yml")


@dataclass(slots=True)
class RepositoryIndex:
    root_path: str
    files: list[RepositoryFile] = field(default_factory=list)
    package_files: list[str] = field(default_factory=list)
    ci_files: list[str] = field(default_factory=list)
    package_managers: list[str] = field(default_factory=list)
    test_commands: list[str] = field(default_factory=list)
    build_commands: list[str] = field(default_factory=list)
    lint_commands: list[str] = field(default_factory=list)
    coverage_unknown: bool = True
    blockers: list[Blocker] = field(default_factory=list)


class RepositoryIndexer:
    """Index a local repository without network access or external dependencies."""

    def __init__(self, *, max_files: int = 2000, max_file_size: int = 1_000_000) -> None:
        self.max_files = max_files
        self.max_file_size = max_file_size

    def index(self, root_path: str | Path) -> RepositoryIndex:
        root = Path(root_path)
        if not str(root_path):
            return RepositoryIndex(root_path="")
        if not root.exists():
            return RepositoryIndex(
                root_path=str(root),
                blockers=[
                    Blocker(
                        code="repository_path_missing",
                        message=f"Repository path does not exist: {root}",
                        severity="hard",
                    )
                ],
            )
        if not root.is_dir():
            return RepositoryIndex(
                root_path=str(root),
                blockers=[
                    Blocker(
                        code="repository_path_not_directory",
                        message=f"Repository path is not a directory: {root}",
                        severity="hard",
                    )
                ],
            )

        files: list[RepositoryFile] = []
        package_files: list[str] = []
        ci_files: list[str] = []

        for path in sorted(root.rglob("*")):
            if len(files) >= self.max_files:
                break
            if not path.is_file() or should_ignore(path, root):
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > self.max_file_size:
                continue
            relative_path = normalize_path(path.relative_to(root))
            kind = classify_file(relative_path, path)
            files.append(
                RepositoryFile(
                    path=relative_path,
                    kind=kind,
                    language=language_for(path),
                    size_bytes=size,
                )
            )
            if path.name in PACKAGE_FILES:
                package_files.append(relative_path)
            if is_ci_file(relative_path):
                ci_files.append(relative_path)

        return RepositoryIndex(
            root_path=str(root),
            files=files,
            package_files=sorted(package_files),
            ci_files=sorted(ci_files),
            package_managers=detect_package_managers(package_files),
            test_commands=detect_test_commands(root, package_files),
            build_commands=detect_script_commands(root, package_files, script_name="build"),
            lint_commands=detect_script_commands(root, package_files, script_name="lint"),
            coverage_unknown=not any(file.kind == "test" for file in files),
        )


def should_ignore(path: Path, root: Path) -> bool:
    try:
        relative_parts = path.relative_to(root).parts
    except ValueError:
        return True
    return any(part in IGNORED_DIRS for part in relative_parts)


def normalize_path(path: Path) -> str:
    return path.as_posix()


def classify_file(relative_path: str, path: Path) -> str:
    lowered = relative_path.lower()
    name = path.name
    if is_ci_file(relative_path):
        return "ci"
    if "migration" in lowered or path.suffix.lower() == ".sql":
        return "migration"
    if any(part in lowered for part in TEST_HINTS) and path.suffix.lower() in SOURCE_SUFFIXES | {".json", ".md"}:
        return "test"
    if path.suffix.lower() in DOC_SUFFIXES:
        return "doc"
    if name in CONFIG_NAMES or path.suffix.lower() in {".json", ".toml", ".yaml", ".yml"}:
        return "config"
    if path.suffix.lower() in SOURCE_SUFFIXES:
        return "source"
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico"}:
        return "asset"
    return "unknown"


def is_ci_file(relative_path: str) -> bool:
    lowered = relative_path.lower()
    return lowered.startswith(".github/workflows/") or lowered in CI_PREFIXES


def language_for(path: Path) -> str:
    return LANGUAGE_BY_SUFFIX.get(path.suffix.lower(), "")


def detect_package_managers(package_files: list[str]) -> list[str]:
    managers: list[str] = []
    if "package.json" in {Path(path).name for path in package_files}:
        managers.append("npm")
    if any(Path(path).name in {"pyproject.toml", "requirements.txt"} for path in package_files):
        managers.append("python")
    if "go.mod" in {Path(path).name for path in package_files}:
        managers.append("go")
    if "Cargo.toml" in {Path(path).name for path in package_files}:
        managers.append("cargo")
    if "pom.xml" in {Path(path).name for path in package_files}:
        managers.append("maven")
    return managers


def detect_test_commands(root: Path, package_files: list[str]) -> list[str]:
    commands: list[str] = []
    names = {Path(path).name for path in package_files}
    if "package.json" in names:
        scripts = read_package_json_scripts(root / "package.json")
        if "test" in scripts:
            commands.append("npm test")
    if "pyproject.toml" in names or "requirements.txt" in names:
        commands.append("python -m unittest discover -s tests")
    if "go.mod" in names:
        commands.append("go test ./...")
    if "Cargo.toml" in names:
        commands.append("cargo test")
    if "pom.xml" in names:
        commands.append("mvn test")
    return dedupe(commands)


def detect_script_commands(root: Path, package_files: list[str], *, script_name: str) -> list[str]:
    commands: list[str] = []
    names = {Path(path).name for path in package_files}
    if "package.json" in names:
        scripts = read_package_json_scripts(root / "package.json")
        if script_name in scripts:
            commands.append(f"npm run {script_name}")
    if script_name == "build" and "Cargo.toml" in names:
        commands.append("cargo build")
    if script_name == "build" and "go.mod" in names:
        commands.append("go build ./...")
    return dedupe(commands)


def read_package_json_scripts(path: Path) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    scripts = payload.get("scripts", {})
    return scripts if isinstance(scripts, dict) else {}


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
