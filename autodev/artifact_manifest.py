"""Build safe preview manifests for generated delivery artifacts."""

from __future__ import annotations

import hashlib
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote


TEXT_EXTENSIONS = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mjs",
    ".spec.ts",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}


@dataclass(frozen=True, slots=True)
class ArtifactContent:
    artifact_id: str
    path: Path
    media_type: str
    filename: str

    @property
    def data(self) -> bytes:
        return self.path.read_bytes()


def build_artifact_manifest(
    *,
    project_id: str,
    run_id: str,
    run: dict[str, Any],
    project_dir: str | Path,
    repository_path: str | Path | None = None,
    include_internal: bool = False,
) -> dict[str, object]:
    """Return a manifest for files explicitly referenced by a run report."""

    project_root = Path(project_dir).resolve()
    run_root = (project_root / "runs" / run_id).resolve()
    repository_roots = _repository_roots(run, repository_path)
    allowed_roots = _dedupe_paths([project_root, run_root, *repository_roots])
    items: list[dict[str, object]] = []

    artifact_report = _dict(run.get("artifact_report"))
    delivery_report = _dict(run.get("delivery_report"))
    delivery_artifact = _dict(delivery_report.get("artifact"))
    browser = _dict(artifact_report.get("browser_verification"))

    screenshots = _dict(delivery_artifact.get("screenshots")) or _dict(browser.get("screenshots"))
    for name, value in screenshots.items():
        _add_item(
            items,
            kind="screenshot",
            label=f"{name} screenshot",
            path_value=str(value),
            base_roots=[run_root],
            allowed_roots=allowed_roots,
            project_id=project_id,
            run_id=run_id,
        )

    native = (
        _dict(artifact_report.get("native_ui_tests"))
        or _dict(delivery_artifact.get("native_ui_tests"))
        or _dict(_dict(run.get("runtime_state")).get("repository")).get("native_ui_tests", {})
    )
    native = _dict(native)
    for value in _list(native.get("files")):
        _add_item(
            items,
            kind="native_ui_test",
            label="Native UI test draft",
            path_value=str(value),
            base_roots=[run_root, *repository_roots],
            allowed_roots=allowed_roots,
            project_id=project_id,
            run_id=run_id,
        )
    target_path = str(native.get("target_path", "") or "")
    if target_path:
        _add_item(
            items,
            kind="native_ui_test",
            label="Native UI test target",
            path_value=target_path,
            base_roots=[run_root, *repository_roots],
            allowed_roots=allowed_roots,
            project_id=project_id,
            run_id=run_id,
        )

    artifact_files = _list(artifact_report.get("artifact_files")) or _list(delivery_artifact.get("artifact_files"))
    for value in artifact_files:
        _add_item(
            items,
            kind="artifact_file",
            label=f"Artifact file: {Path(str(value)).name or value}",
            path_value=str(value),
            base_roots=repository_roots,
            allowed_roots=allowed_roots,
            project_id=project_id,
            run_id=run_id,
        )

    generated_ci = _dict(run.get("generated_ci")) or _dict(_dict(run.get("runtime_state")).get("repository")).get("generated_ci", {})
    generated_ci = _dict(generated_ci)
    ci_paths = _list(generated_ci.get("evidence"))
    workflow_path = str(generated_ci.get("workflow_path", "") or "")
    if workflow_path:
        ci_paths.append(workflow_path)
    for value in ci_paths:
        _add_item(
            items,
            kind="generated_ci",
            label=f"Generated CI: {Path(str(value)).name or value}",
            path_value=str(value),
            base_roots=repository_roots,
            allowed_roots=allowed_roots,
            project_id=project_id,
            run_id=run_id,
        )

    public_items = _dedupe_items(items)
    if not include_internal:
        public_items = [_public_item(item) for item in public_items]
    return {
        "project_id": project_id,
        "run_id": run_id,
        "items": public_items,
    }


def resolve_artifact_content(
    *,
    project_id: str,
    run_id: str,
    artifact_id: str,
    run: dict[str, Any],
    project_dir: str | Path,
    repository_path: str | Path | None = None,
) -> ArtifactContent | None:
    manifest = build_artifact_manifest(
        project_id=project_id,
        run_id=run_id,
        run=run,
        project_dir=project_dir,
        repository_path=repository_path,
        include_internal=True,
    )
    for item in _list(manifest.get("items")):
        if not isinstance(item, dict) or item.get("artifact_id") != artifact_id:
            continue
        path = Path(str(item.get("_absolute_path", "")))
        if not path.is_file():
            return None
        return ArtifactContent(
            artifact_id=artifact_id,
            path=path,
            media_type=str(item.get("media_type", "application/octet-stream")),
            filename=Path(str(item.get("path", path.name))).name or path.name,
        )
    return None


def _add_item(
    items: list[dict[str, object]],
    *,
    kind: str,
    label: str,
    path_value: str,
    base_roots: list[Path],
    allowed_roots: list[Path],
    project_id: str,
    run_id: str,
) -> None:
    path = _resolve_reported_file(path_value, base_roots, allowed_roots)
    if path is None:
        return
    media_type = _media_type(path)
    preview = "image" if media_type.startswith("image/") else "text" if media_type.startswith("text/") else "download"
    display_path = _display_path(path, base_roots or allowed_roots)
    artifact_id = _artifact_id(kind, label, display_path, path)
    items.append(
        {
            "artifact_id": artifact_id,
            "kind": kind,
            "label": label,
            "path": display_path,
            "media_type": media_type,
            "size_bytes": path.stat().st_size,
            "preview": preview,
            "url": f"/projects/{quote(project_id)}/runs/{quote(run_id)}/artifacts/{quote(artifact_id)}",
            "_absolute_path": str(path),
        }
    )


def _resolve_reported_file(path_value: str, base_roots: list[Path], allowed_roots: list[Path]) -> Path | None:
    if not path_value:
        return None
    raw = Path(path_value)
    candidates: list[Path] = []
    if raw.is_absolute():
        candidates.append(raw)
    for root in base_roots:
        candidates.append(root / raw)
    for root in allowed_roots:
        candidates.append(root / raw)
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if not resolved.is_file():
            continue
        if _is_under_any(resolved, allowed_roots):
            return resolved
    return None


def _repository_roots(run: dict[str, Any], repository_path: str | Path | None) -> list[Path]:
    values: list[str] = []
    if repository_path:
        values.append(str(repository_path))
    runtime_repository = _dict(_dict(run.get("runtime_state")).get("repository"))
    workspace = _dict(run.get("workspace"))
    project_brief = _dict(run.get("project_brief"))
    brief_repository = _dict(project_brief.get("repository"))
    context_repository = _dict(_dict(run.get("context_bundle")).get("repository_map"))
    for key in ("path",):
        value = str(runtime_repository.get(key, "") or "")
        if value:
            values.append(value)
    for key in ("execution_path", "worktree_path", "source_path"):
        value = str(workspace.get(key, "") or "")
        if value:
            values.append(value)
    for key in ("local_path",):
        value = str(brief_repository.get(key, "") or context_repository.get("root_path", "") or "")
        if value:
            values.append(value)
    return _dedupe_paths([Path(value).resolve() for value in values if value])


def _is_under_any(path: Path, roots: list[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _display_path(path: Path, roots: list[Path]) -> str:
    for root in roots:
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            continue
    return path.name


def _media_type(path: Path) -> str:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if name.endswith(".spec.ts"):
        return "text/plain; charset=utf-8"
    if suffix in TEXT_EXTENSIONS:
        return "text/plain; charset=utf-8"
    media_type, _ = mimetypes.guess_type(str(path))
    return media_type or "application/octet-stream"


def _artifact_id(kind: str, label: str, display_path: str, path: Path) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", f"{kind}_{label}_{Path(display_path).name}".lower()).strip("_")
    digest = hashlib.sha256(f"{kind}:{label}:{display_path}:{path}".encode("utf-8")).hexdigest()[:10]
    return f"{slug[:48]}_{digest}"


def _dedupe_items(items: list[dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (str(item.get("kind", "")), str(item.get("_absolute_path", "")))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _public_item(item: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in item.items() if not key.startswith("_")}


def _dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        result.append(path.resolve())
    return result
