"""Expand development documents referenced by entry-point prompts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence


SUPPORTED_DOCUMENT_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml"}
PATH_CANDIDATE_PATTERN = re.compile(
    r"(?P<path>(?:[A-Za-z]:[\\/])?[\w .()@~+\-\\/]+?\.(?:md|txt|json|yaml|yml))(?![\w/\\.-])",
    re.IGNORECASE,
)


@dataclass(slots=True)
class DocumentReferenceExpansion:
    documents: list[str]
    added_documents: list[str] = field(default_factory=list)
    unresolved_references: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "documents": list(self.documents),
            "added_documents": list(self.added_documents),
            "unresolved_references": list(self.unresolved_references),
        }


def expand_development_documents(
    documents: Sequence[str | Path],
    *,
    repository_path: str | Path | None = None,
    max_documents: int = 80,
) -> DocumentReferenceExpansion:
    """Return documents plus readable docs referenced inside them.

    Entry prompts often contain a "read these documents first" list. The full
    roadmap executor must treat those files as part of the source package, or
    it may incorrectly collapse the job into a low-confidence one-phase task.
    """

    repo_root = Path(repository_path).resolve() if repository_path else None
    original_paths = [
        resolved
        for resolved in (
            resolve_existing_path(Path(path), base_dir=None, repository_path=repo_root)
            for path in documents
        )
        if resolved is not None
    ]
    expansion_roots = infer_expansion_roots(original_paths, repository_path=repo_root)
    original_keys = {canonical_key(path) for path in original_paths}
    queue = list(original_paths)
    resolved_documents: list[str] = []
    added_documents: list[str] = []
    unresolved: list[str] = []
    seen: set[str] = set()

    while queue and len(resolved_documents) < max_documents:
        current = resolve_existing_path(queue.pop(0), base_dir=None, repository_path=repo_root)
        if current is None:
            continue
        key = canonical_key(current)
        if key in seen:
            continue
        seen.add(key)
        resolved_documents.append(str(current))

        text = read_supported_text(current)
        if not text:
            continue
        for reference in referenced_document_paths(text):
            resolved = resolve_existing_path(
                reference,
                base_dir=current.parent,
                repository_path=repo_root,
                allowed_roots=expansion_roots,
            )
            if resolved is None:
                unresolved.append(reference)
                continue
            ref_key = canonical_key(resolved)
            if ref_key in seen or any(canonical_key(path) == ref_key for path in queue if Path(path).exists()):
                continue
            queue.append(resolved)
            if str(resolved) not in added_documents and canonical_key(resolved) not in original_keys:
                added_documents.append(str(resolved))

    return DocumentReferenceExpansion(
        documents=resolved_documents,
        added_documents=added_documents,
        unresolved_references=dedupe(unresolved),
    )


def resolve_existing_path(
    candidate: str | Path,
    *,
    base_dir: Path | None,
    repository_path: Path | None,
    allowed_roots: Sequence[Path] | None = None,
) -> Path | None:
    raw = str(candidate).strip().strip("`").strip()
    if not raw:
        return None
    path = Path(raw)
    candidates: list[Path] = []
    if path.is_absolute():
        candidates.append(path)
    else:
        if base_dir is not None:
            candidates.append(base_dir / path)
            candidates.append(base_dir.parent / path)
        if repository_path is not None:
            candidates.append(repository_path / path)
        candidates.append(path)
    for item in candidates:
        try:
            resolved = item.resolve()
        except OSError:
            resolved = item
        if (
            resolved.exists()
            and resolved.is_file()
            and resolved.suffix.lower() in SUPPORTED_DOCUMENT_SUFFIXES
            and is_allowed_expansion_path(resolved, allowed_roots)
        ):
            return resolved
    return None


def infer_expansion_roots(paths: Sequence[Path], *, repository_path: Path | None) -> list[Path]:
    roots: list[Path] = []
    for path in paths:
        root = path.parent
        if repository_path is not None:
            try:
                relative = path.resolve().relative_to(repository_path)
            except ValueError:
                relative = None
            if relative is not None and len(relative.parts) > 1:
                first = relative.parts[0]
                if first.lower() not in {".github", "docs", "specs", "tests"}:
                    root = repository_path / first
                else:
                    root = repository_path / first
        roots.append(root.resolve())
    return dedupe_paths(roots)


def is_allowed_expansion_path(path: Path, allowed_roots: Sequence[Path] | None) -> bool:
    if not allowed_roots:
        return True
    resolved = path.resolve()
    for root in allowed_roots:
        try:
            resolved.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def referenced_document_paths(text: str) -> list[str]:
    candidates: list[str] = []
    for line in text.splitlines():
        clean = line.strip().strip("`").strip()
        if not clean or clean.startswith(("http://", "https://")):
            continue
        for match in PATH_CANDIDATE_PATTERN.finditer(clean):
            value = match.group("path").strip()
            if looks_like_repository_document(value):
                candidates.append(value.replace("\\", "/"))
    return dedupe(candidates)


def looks_like_repository_document(value: str) -> bool:
    suffix = Path(value).suffix.lower()
    if suffix not in SUPPORTED_DOCUMENT_SUFFIXES:
        return False
    lowered = value.lower()
    if any(marker in lowered for marker in ("node_modules/", ".git/", "__pycache__/")):
        return False
    return "/" in value or "\\" in value or Path(value).name.lower() in {"readme.md"}


def read_supported_text(path: Path) -> str:
    if path.suffix.lower() not in SUPPORTED_DOCUMENT_SUFFIXES:
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def canonical_key(path: str | Path) -> str:
    try:
        return str(Path(path).resolve()).lower()
    except OSError:
        return str(path).replace("\\", "/").lower()


def dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value).strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def dedupe_paths(values: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for value in values:
        try:
            resolved = value.resolve()
        except OSError:
            resolved = value
        key = canonical_key(resolved)
        if key in seen:
            continue
        seen.add(key)
        result.append(resolved)
    return result
