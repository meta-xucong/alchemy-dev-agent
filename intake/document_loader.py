"""File cataloging and role inference for project intake."""

from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path

from .models import Blocker, FileRole, ParseStatus, ProjectFile

SUPPORTED_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml"}
REFERENCE_CODE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".cs", ".rb", ".php"}


class DocumentLoader:
    """Create deterministic file metadata for ProjectBrief inputs."""

    def load(
        self,
        path: str | Path,
        *,
        role: FileRole | None = None,
        required: bool = False,
        primary: bool = False,
    ) -> tuple[ProjectFile, list[Blocker]]:
        file_path = Path(path)
        inferred_role = role or self.infer_role(file_path, primary=primary)
        media_type = guess_media_type(file_path)
        blockers: list[Blocker] = []

        try:
            data = file_path.read_bytes()
            content_hash = sha256_digest(data)
            parse_status = self.parse_status(file_path)
            summary = summarize_bytes(data, file_path)
        except OSError as exc:
            content_hash = "sha256:unreadable"
            parse_status = "failed"
            summary = ""
            blockers.append(
                Blocker(
                    code="unreadable_file",
                    message=f"Cannot read required intake file '{file_path}': {exc}",
                    severity="hard" if required else "warning",
                )
            )

        if required and parse_status == "unsupported":
            blockers.append(
                Blocker(
                    code="unsupported_required_file",
                    message=f"Required intake file '{file_path}' has unsupported type '{file_path.suffix}'.",
                    severity="hard",
                )
            )

        project_file = ProjectFile(
            id=stable_file_id(file_path, content_hash),
            name=file_path.name,
            path=str(file_path),
            media_type=media_type,
            role=inferred_role,
            required=required,
            content_hash=content_hash,
            parse_status=parse_status,
            summary=summary,
        )
        return project_file, blockers

    def infer_role(self, path: Path, *, primary: bool = False) -> FileRole:
        if primary:
            return "primary_requirements"

        name = path.name.lower()
        suffix = path.suffix.lower()
        if "api" in name or "openapi" in name or "swagger" in name:
            return "api_spec"
        if "database" in name or "schema" in name or "migration" in name or name.startswith("db"):
            return "database_schema"
        if "design" in name or "wireframe" in name or "ui" in name or "ux" in name:
            return "design"
        if "test" in name or "qa" in name or "verification" in name:
            return "test_plan"
        if "sample" in name or "fixture" in name or "data" in name:
            return "data_sample"
        if suffix in REFERENCE_CODE_SUFFIXES:
            return "reference_code"
        return "supplemental"

    def parse_status(self, path: Path) -> ParseStatus:
        if path.suffix.lower() in SUPPORTED_SUFFIXES:
            return "parsed"
        return "unsupported"


def sha256_digest(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def stable_file_id(path: Path, content_hash: str) -> str:
    seed = f"{path.as_posix()}\0{content_hash}".encode("utf-8")
    return f"file_{hashlib.sha256(seed).hexdigest()[:12]}"


def guess_media_type(path: Path) -> str:
    mimetypes.add_type("text/markdown", ".md")
    mimetypes.add_type("application/yaml", ".yaml")
    mimetypes.add_type("application/yaml", ".yml")
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def summarize_bytes(data: bytes, path: Path) -> str:
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        return ""

    text = data.decode("utf-8", errors="replace")
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if len(first_line) > 160:
        return first_line[:157] + "..."
    return first_line
