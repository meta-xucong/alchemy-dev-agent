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
    ".appdata",
    ".appdata-local",
    ".cache",
    ".entc",
    ".gocache",
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

SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".cs", ".rb", ".php", ".html", ".css"}
TEST_HINTS = ("test", "tests", "spec", "__tests__")
DOC_SUFFIXES = {".md", ".txt", ".rst"}
CONFIG_NAMES = {
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lockb",
    "pyproject.toml",
    "requirements.txt",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "Dockerfile",
    "docker-compose.yml",
    "Makefile",
}
NODE_LOCK_FILES = {
    "pnpm-lock.yaml": "pnpm",
    "yarn.lock": "yarn",
    "bun.lockb": "bun",
    "package-lock.json": "npm",
}
PACKAGE_FILES = {
    "package.json",
    *NODE_LOCK_FILES.keys(),
    "pyproject.toml",
    "requirements.txt",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
}
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

        representative_files: dict[str, RepositoryFile] = {}
        saw_test_file = False

        for path in sorted(root.rglob("*")):
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
            repository_file = RepositoryFile(
                path=relative_path,
                kind=kind,
                language=language_for(path),
                size_bytes=size,
            )
            representative_files.setdefault(top_level_key(relative_path), repository_file)
            if len(files) < self.max_files:
                files.append(repository_file)
            if path.name in PACKAGE_FILES:
                package_files.append(relative_path)
            if is_ci_file(relative_path):
                ci_files.append(relative_path)
            if kind == "test":
                saw_test_file = True

        return RepositoryIndex(
            root_path=str(root),
            files=include_representative_files(files, representative_files),
            package_files=sorted(package_files),
            ci_files=sorted(ci_files),
            package_managers=detect_package_managers(package_files),
            test_commands=detect_test_commands(root, package_files),
            build_commands=detect_script_commands(root, package_files, script_name="build"),
            lint_commands=detect_script_commands(root, package_files, script_name="lint"),
            coverage_unknown=not saw_test_file,
        )


def should_ignore(path: Path, root: Path) -> bool:
    try:
        relative_parts = path.relative_to(root).parts
    except ValueError:
        return True
    return any(part in IGNORED_DIRS or part.startswith(".gocache") for part in relative_parts)


def normalize_path(path: Path) -> str:
    return path.as_posix()


def top_level_key(relative_path: str) -> str:
    return relative_path.split("/", 1)[0]


def include_representative_files(files: list[RepositoryFile], representatives: dict[str, RepositoryFile]) -> list[RepositoryFile]:
    selected = {file.path for file in files}
    result = list(files)
    for file in representatives.values():
        if file.path not in selected:
            result.append(file)
            selected.add(file.path)
    return result


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
    for package_file in package_files:
        if Path(package_file).name == "package.json":
            managers.append(node_package_manager_for(package_file, package_files))
    if not managers:
        managers.extend(
            manager
            for path in package_files
            for lock_name, manager in NODE_LOCK_FILES.items()
            if Path(path).name == lock_name
        )
    if any(Path(path).name in {"pyproject.toml", "requirements.txt"} for path in package_files):
        managers.append("python")
    if "go.mod" in {Path(path).name for path in package_files}:
        managers.append("go")
    if "Cargo.toml" in {Path(path).name for path in package_files}:
        managers.append("cargo")
    if "pom.xml" in {Path(path).name for path in package_files}:
        managers.append("maven")
    return dedupe(managers)


def detect_test_commands(root: Path, package_files: list[str]) -> list[str]:
    commands: list[str] = []
    for package_file in package_files:
        if Path(package_file).name != "package.json":
            continue
        scripts = read_package_json_scripts(root / package_file)
        if "test" in scripts:
            commands.append(node_script_command(package_file, "test", package_files))
    for package_file in package_files:
        name = Path(package_file).name
        if name in {"pyproject.toml", "requirements.txt"}:
            commands.append(directory_command(package_file, "python -m unittest discover -s tests"))
        if name == "go.mod":
            commands.append(directory_command(package_file, "go test ./..."))
        if name == "Cargo.toml":
            commands.append(directory_command(package_file, "cargo test"))
        if name == "pom.xml":
            commands.append(directory_command(package_file, "mvn test"))
    return dedupe(commands)


def detect_script_commands(root: Path, package_files: list[str], *, script_name: str) -> list[str]:
    commands: list[str] = []
    for package_file in package_files:
        if Path(package_file).name != "package.json":
            continue
        scripts = read_package_json_scripts(root / package_file)
        if script_name in scripts:
            commands.append(node_script_command(package_file, script_name, package_files, run_script=True))
    if script_name == "build":
        for package_file in package_files:
            name = Path(package_file).name
            if name == "Cargo.toml":
                commands.append(directory_command(package_file, "cargo build"))
            if name == "go.mod":
                commands.append(directory_command(package_file, "go build ./..."))
    return dedupe(commands)


def npm_command(package_file: str, script_name: str, *, run_script: bool = False) -> str:
    return node_script_command(package_file, script_name, [package_file], run_script=run_script)


def node_script_command(
    package_file: str,
    script_name: str,
    package_files: list[str],
    *,
    run_script: bool = False,
) -> str:
    manager = node_package_manager_for(package_file, package_files)
    parent = package_parent(package_file)
    action = f"run {script_name}" if run_script else script_name
    if manager == "pnpm":
        return f"pnpm --dir {parent} {action}" if parent else f"pnpm {action}"
    if manager == "yarn":
        return f"yarn --cwd {parent} {action}" if parent else f"yarn {action}"
    if manager == "bun":
        bun_action = f"run {script_name}"
        return f"bun --cwd {parent} {bun_action}" if parent else f"bun {bun_action}"
    if not parent:
        return f"npm {action}"
    return f"npm --prefix {parent} {action}"


def node_install_command(package_file: str, package_files: list[str]) -> str:
    manager = node_package_manager_for(package_file, package_files)
    parent = package_parent(package_file)
    if manager == "pnpm":
        return f"pnpm --dir {parent} install --frozen-lockfile" if parent else "pnpm install --frozen-lockfile"
    if manager == "yarn":
        return f"yarn --cwd {parent} install --frozen-lockfile" if parent else "yarn install --frozen-lockfile"
    if manager == "bun":
        return f"bun --cwd {parent} install" if parent else "bun install"
    return f"npm --prefix {parent} install" if parent else "npm install"


def node_package_manager_for(package_file: str, package_files: list[str]) -> str:
    known_files = {_normalize_package_path(path) for path in package_files}
    package_dir = Path(package_file).parent
    for directory in _package_manager_search_dirs(package_dir):
        prefix = "" if directory.as_posix() == "." else directory.as_posix().rstrip("/") + "/"
        for lock_name, manager in NODE_LOCK_FILES.items():
            if f"{prefix}{lock_name}" in known_files:
                return manager
    return "npm"


def _package_manager_search_dirs(package_dir: Path) -> list[Path]:
    current = package_dir if package_dir.as_posix() else Path(".")
    dirs = [current]
    while current.as_posix() not in {"", "."}:
        current = current.parent
        dirs.append(current if current.as_posix() else Path("."))
    if Path(".") not in dirs:
        dirs.append(Path("."))
    return dirs


def _normalize_package_path(path: str) -> str:
    normalized = Path(path).as_posix().strip("/")
    return "" if normalized == "." else normalized


def directory_command(package_file: str, command: str) -> str:
    parent = package_parent(package_file)
    if not parent:
        return command
    return f"cd {parent} && {command}"


def package_parent(package_file: str) -> str:
    parent = Path(package_file).parent.as_posix()
    return "" if parent == "." else parent


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
