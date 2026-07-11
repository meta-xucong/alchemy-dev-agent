"""Semantic repository inventory for V2.187 contracts."""

from __future__ import annotations

import fnmatch
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .objective_models import ObjectiveContract, ObjectiveRequirement

SURFACE_BY_PATH = (
    ("generated", ("generated/", "gen/", ".generated.", "_generated.")),
    ("schema", ("backend/ent/", "schema/", "migrations/")),
    ("runtime_route", ("route", "router", "server")),
    ("frontend_public_contract", ("frontend/", "src/api/", "src/views/", "src/router/", "i18n")),
    ("public_documentation", ("docs/", "readme", "openapi", "swagger")),
    ("config_deploy", ("docker", "deploy", ".env", "config", "compose", "k8s")),
    ("test", ("test", "spec")),
)

SKIP_DIRECTORIES = {
    ".git",
    ".alchemy",
    ".codex-longrun",
    ".test-tmp",
    ".venv",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "coverage",
    "__pycache__",
}


@dataclass(slots=True)
class InventoryHit:
    requirement_id: str
    domain: str
    subject: str
    path: str
    surface_class: str
    production_relevance: str
    generated: bool
    status: str
    proposed_action: str
    polarity: str = "forbidden"
    evidence_fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "domain": self.domain,
            "subject": self.subject,
            "path": self.path,
            "surface_class": self.surface_class,
            "production_relevance": self.production_relevance,
            "generated": self.generated,
            "status": self.status,
            "proposed_action": self.proposed_action,
            "polarity": self.polarity,
            "evidence_fingerprint": self.evidence_fingerprint,
        }


@dataclass(slots=True)
class RepositoryInventory:
    root_path: str
    hits: list[InventoryHit] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "2.187",
            "root_path": self.root_path,
            "hits": [hit.to_dict() for hit in self.hits],
            "summary": inventory_summary(self.hits),
        }


class SemanticInventoryBuilder:
    def build(self, root: Path | str, objective_contract: ObjectiveContract) -> RepositoryInventory:
        root_path = Path(root).resolve()
        file_paths = list(_inventory_files(root_path))
        hits: list[InventoryHit] = []
        negative_requirements = [
            requirement for requirement in objective_contract.requirements if requirement.class_name.startswith("must_absent")
        ]
        for requirement in negative_requirements:
            seeds = _search_seeds(requirement)
            for path in file_paths:
                relative = path.relative_to(root_path).as_posix()
                if _is_allowed_exception(relative, requirement.allowed_exceptions):
                    continue
                surface = classify_surface(relative)
                if not _surface_applies(requirement.class_name, surface):
                    continue
                if not _path_in_scope(relative, requirement.scope):
                    continue
                text = _safe_read(path)
                haystack = f"{relative}\n{text}".lower()
                for seed in seeds:
                    if seed and _contains_seed(haystack, seed):
                        relevance = classify_relevance(relative)
                        hits.append(
                            InventoryHit(
                                requirement_id=requirement.id,
                                domain=requirement.domain,
                                subject=seed,
                                path=relative,
                                surface_class=surface,
                                production_relevance=relevance,
                                generated=is_generated(relative),
                                status="active" if relevance == "production" else "test_or_archive",
                                proposed_action="delete" if relevance == "production" else "waive_or_delete",
                                evidence_fingerprint=_file_fingerprint(path),
                            )
                        )
                        break
        positive_requirements = [
            requirement
            for requirement in objective_contract.requirements
            if requirement.class_name in {"must_implement", "must_preserve"}
        ]
        for requirement in positive_requirements:
            seeds = _search_seeds(requirement)
            for path in file_paths:
                relative = path.relative_to(root_path).as_posix()
                if classify_relevance(relative) != "production" or not _path_in_scope(relative, requirement.scope):
                    continue
                text = _safe_read(path)
                haystack = f"{relative}\n{text}".lower()
                matched = next((seed for seed in seeds if _contains_seed(haystack, seed)), "")
                if not matched:
                    continue
                hits.append(
                    InventoryHit(
                        requirement_id=requirement.id,
                        domain=requirement.domain,
                        subject=matched,
                        path=relative,
                        surface_class=classify_surface(relative),
                        production_relevance="production",
                        generated=is_generated(relative),
                        status="present_signal",
                        proposed_action="verify_or_repair",
                        polarity="required_signal",
                        evidence_fingerprint=_file_fingerprint(path),
                    )
                )
        return RepositoryInventory(root_path=str(root_path.resolve()), hits=_dedupe_hits(hits))


def classify_surface(path: str) -> str:
    lowered = path.lower()
    for surface, markers in SURFACE_BY_PATH:
        if any(marker in lowered for marker in markers):
            return surface
    return "source"


def classify_relevance(path: str) -> str:
    lowered = path.lower()
    if any(marker in lowered for marker in ("archive", "legacy_archive", "docs/")):
        return "archived"
    if any(marker in lowered for marker in ("test", ".spec.", "_test.")):
        return "test"
    return "production"


def inventory_summary(hits: list[InventoryHit]) -> dict[str, Any]:
    by_requirement: dict[str, int] = {}
    by_surface: dict[str, int] = {}
    by_polarity: dict[str, int] = {}
    for hit in hits:
        by_requirement[hit.requirement_id] = by_requirement.get(hit.requirement_id, 0) + 1
        by_surface[hit.surface_class] = by_surface.get(hit.surface_class, 0) + 1
        by_polarity[hit.polarity] = by_polarity.get(hit.polarity, 0) + 1
    return {
        "total_hits": len(hits),
        "by_requirement": by_requirement,
        "by_surface": by_surface,
        "by_polarity": by_polarity,
    }


def _search_seeds(requirement: ObjectiveRequirement) -> list[str]:
    seeds = [requirement.domain.replace("_", " "), requirement.domain, *requirement.subjects]
    return _dedupe_text(seed for seed in seeds if seed and seed not in {"general", "multi_domain"})


def _is_allowed_exception(path: str, allowed_exceptions: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) or path.startswith(pattern.rstrip("*")) for pattern in allowed_exceptions)


def _safe_read(path: Path) -> str:
    try:
        if path.stat().st_size > 512_000:
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def is_generated(path: str) -> bool:
    lowered = path.lower()
    if "/ent/schema/" in f"/{lowered}" or lowered.startswith("ent/schema/"):
        return False
    return bool(
        re.search(r"(^|/)(generated|gen)(/|$)", lowered)
        or ("/ent/" in f"/{lowered}" and any(marker in lowered for marker in ("ent/client", "ent/predicate", "ent/mutation")))
    )


def _dedupe_hits(hits: list[InventoryHit]) -> list[InventoryHit]:
    result: list[InventoryHit] = []
    seen: set[tuple[str, str, str]] = set()
    for hit in hits:
        key = (hit.requirement_id, hit.subject.lower(), hit.path)
        if key not in seen:
            seen.add(key)
            result.append(hit)
    return result


def _inventory_files(root: Path):
    if not root.is_dir():
        return
    for path in root.rglob("*"):
        try:
            relative_parts = path.relative_to(root).parts
        except ValueError:
            continue
        if any(part in SKIP_DIRECTORIES for part in relative_parts):
            continue
        try:
            if path.is_file() and not path.is_symlink():
                yield path
        except OSError:
            continue


def _surface_applies(class_name: str, surface: str) -> bool:
    if class_name == "must_absent_runtime":
        return surface in {"runtime_route", "frontend_public_contract", "config_deploy"}
    if class_name == "must_absent_fresh_schema":
        return surface in {"schema", "generated"}
    if class_name == "must_absent_public_contract":
        return surface in {"frontend_public_contract", "runtime_route", "public_documentation"}
    return True


def _path_in_scope(path: str, scope: list[str]) -> bool:
    if not scope or scope == ["**"]:
        return True
    return any(fnmatch.fnmatch(path, pattern) or path.startswith(pattern.rstrip("*")) for pattern in scope)


def _contains_seed(haystack: str, seed: str) -> bool:
    normalized = seed.strip().lower()
    if not normalized:
        return False
    variants = {
        normalized,
        normalized.replace(" ", "_"),
        normalized.replace(" ", "-"),
        normalized.replace("_", " "),
    }
    return any(variant and variant in haystack for variant in variants)


def _file_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(64 * 1024):
                digest.update(chunk)
    except OSError:
        return "unreadable"
    return "sha256:" + digest.hexdigest()


def _dedupe_text(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value).strip()
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            result.append(clean)
    return result
