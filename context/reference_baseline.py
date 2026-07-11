"""Repository role governance for V2.187 goal-locked runs."""

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

RepoRole = Literal["target", "reference", "orchestrator", "artifact", "external"]


@dataclass(slots=True)
class RepositoryRole:
    id: str
    path: str
    role: RepoRole
    writable: bool
    purpose: list[str] = field(default_factory=list)
    head: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "role": self.role,
            "writable": self.writable,
            "purpose": list(self.purpose),
            "head": self.head,
        }


@dataclass(slots=True)
class ReferenceBaseline:
    target: RepositoryRole
    references: list[RepositoryRole] = field(default_factory=list)
    orchestrator: RepositoryRole | None = None
    artifacts: list[RepositoryRole] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "2.187",
            "target": self.target.to_dict(),
            "references": [item.to_dict() for item in self.references],
            "orchestrator": self.orchestrator.to_dict() if self.orchestrator else {},
            "artifacts": [item.to_dict() for item in self.artifacts],
            "validation_errors": list(self.validation_errors),
        }


def build_reference_baseline(
    *,
    target_path: Path | str,
    reference_paths: list[Path | str] | None = None,
    orchestrator_path: Path | str | None = None,
    artifact_paths: list[Path | str] | None = None,
) -> ReferenceBaseline:
    target = _role("target", target_path, "target", True, ["product_edits"])
    references = [
        _role(f"reference-{index}", path, "reference", False, ["structural_repair", "transplant_source"])
        for index, path in enumerate(reference_paths or [], start=1)
    ]
    orchestrator = _role("orchestrator", orchestrator_path, "orchestrator", False, ["framework_development"]) if orchestrator_path else None
    artifacts = [
        _role(f"artifact-{index}", path, "artifact", True, ["run_output"])
        for index, path in enumerate(artifact_paths or [], start=1)
    ]
    baseline = ReferenceBaseline(target=target, references=references, orchestrator=orchestrator, artifacts=artifacts)
    baseline.validation_errors = validate_reference_baseline(baseline)
    return baseline


def validate_reference_baseline(baseline: ReferenceBaseline) -> list[str]:
    errors: list[str] = []
    target_path = Path(baseline.target.path).resolve()
    if not target_path.is_dir():
        errors.append("Target repository path does not exist or is not a directory.")
    if not baseline.target.writable:
        errors.append("Target repository must be writable.")
    seen_paths = {_normalized_path(target_path)}
    for reference in baseline.references:
        reference_path = Path(reference.path).resolve()
        normalized_reference = _normalized_path(reference_path)
        if not reference_path.is_dir():
            errors.append(f"Reference repository {reference.id} does not exist or is not a directory.")
        if reference.writable:
            errors.append(f"Reference repository {reference.id} must be read-only.")
        if _same_or_child(reference_path, target_path) or _same_or_child(target_path, reference_path):
            errors.append(f"Reference repository {reference.id} overlaps target path.")
        if normalized_reference in seen_paths:
            errors.append(f"Repository role path is declared more than once: {reference_path}")
        seen_paths.add(normalized_reference)
    if baseline.orchestrator and baseline.orchestrator.writable:
        errors.append("Orchestrator repository is not writable for product tasks.")
    if baseline.orchestrator:
        orchestrator_path = Path(baseline.orchestrator.path).resolve()
        if _same_or_child(orchestrator_path, target_path) or _same_or_child(target_path, orchestrator_path):
            errors.append("Orchestrator repository overlaps target path; omit the orchestrator role for framework self-development.")
    return errors


def assert_write_allowed(baseline: ReferenceBaseline, changed_paths: list[Path | str]) -> None:
    target = Path(baseline.target.path).resolve()
    protected = [Path(item.path).resolve() for item in baseline.references]
    if baseline.orchestrator:
        protected.append(Path(baseline.orchestrator.path).resolve())
    for changed in changed_paths:
        resolved = Path(changed).resolve()
        if not _same_or_child(resolved, target):
            raise ValueError(f"Changed path is outside target repository: {resolved}")
        if any(_same_or_child(resolved, root) for root in protected):
            raise ValueError(f"Changed path overlaps a non-writable repository role: {resolved}")


def _role(id: str, path: Path | str | None, role: RepoRole, writable: bool, purpose: list[str]) -> RepositoryRole:
    resolved = Path(path or "").resolve()
    return RepositoryRole(id=id, path=str(resolved), role=role, writable=writable, purpose=purpose, head=_fingerprint(resolved))


def _fingerprint(path: Path) -> str:
    if not path.exists():
        return "missing"
    try:
        head = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        status = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain=v1", "--untracked-files=all"],
            capture_output=True,
            text=True,
            check=False,
        )
        if head.returncode == 0 and status.returncode == 0:
            identity = f"{head.stdout.strip()}\n{status.stdout}"
            return "git-sha256:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
    except OSError:
        pass
    digest = hashlib.sha256(str(path).encode("utf-8"))
    if path.is_dir():
        for child in sorted(item for item in path.rglob("*") if item.is_file() and ".git" not in item.parts):
            try:
                digest.update(child.relative_to(path).as_posix().encode("utf-8"))
                with child.open("rb") as stream:
                    while chunk := stream.read(64 * 1024):
                        digest.update(chunk)
            except OSError:
                continue
    return "sha256:" + digest.hexdigest()


def _same_or_child(path: Path, root: Path) -> bool:
    normalized_path = _normalized_path(path)
    normalized_root = _normalized_path(root)
    try:
        common = os.path.commonpath([normalized_path, normalized_root])
    except ValueError:
        return False
    return common == normalized_root


def _normalized_path(path: Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))
