"""ProjectBrief generation for document-driven intake."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

from .document_loader import DocumentLoader
from .github_source import parse_github_source
from .models import Blocker, FileRole, InputMode, ProjectBrief, ProjectFile, SourceConfidence, Visibility, utc_now_iso
from .models import RepositorySource
from .schema_validation import validate_project_brief_contract


class ProjectBriefBuilder:
    """Build a schema-compatible ProjectBrief from local intake inputs."""

    def __init__(self, document_loader: DocumentLoader | None = None) -> None:
        self.document_loader = document_loader or DocumentLoader()

    def build(
        self,
        *,
        objective: str,
        documents: Sequence[str | Path] = (),
        attachments: Sequence[str | Path] = (),
        primary_input_mode: InputMode = "document_driven",
        repository_url: str = "",
        repository_path: str | Path = "",
        target_branch: str = "main",
        base_branch: str = "",
        repository_visibility: Visibility = "public",
        constraints: Sequence[str] = (),
        acceptance_criteria: Sequence[str] = (),
        file_roles: dict[str, FileRole] | None = None,
        required_attachments: Sequence[str | Path] = (),
        created_at: str | None = None,
    ) -> ProjectBrief:
        clean_objective = objective.strip()
        blockers: list[Blocker] = []
        roles = {str(Path(key)): value for key, value in (file_roles or {}).items()}
        required_attachment_paths = {str(Path(path)) for path in required_attachments}

        if not clean_objective:
            blockers.append(Blocker(code="missing_objective", message="Project objective is required.", severity="hard"))

        document_files: list[ProjectFile] = []
        for index, document_path in enumerate(documents):
            path = Path(document_path)
            role = roles.get(str(path))
            project_file, file_blockers = self.document_loader.load(
                path,
                role=role,
                required=True,
                primary=index == 0,
            )
            document_files.append(project_file)
            blockers.extend(file_blockers)

        attachment_files: list[ProjectFile] = []
        for attachment_path in attachments:
            path = Path(attachment_path)
            required = str(path) in required_attachment_paths
            project_file, file_blockers = self.document_loader.load(
                path,
                role=roles.get(str(path)),
                required=required,
            )
            attachment_files.append(project_file)
            blockers.extend(file_blockers)

        if primary_input_mode == "document_driven" and not document_files:
            blockers.append(
                Blocker(
                    code="missing_primary_document",
                    message="Document-driven intake requires at least one primary development document.",
                    severity="hard",
                )
            )

        project_id = stable_project_id(
            clean_objective,
            document_files,
            attachment_files,
            repository_url or str(repository_path),
        )

        repository = None
        if repository_url:
            repository = parse_github_source(
                repository_url,
                project_id=project_id,
                target_branch=target_branch,
                base_branch=base_branch,
                visibility=repository_visibility,
            )
            if repository is None:
                blockers.append(
                    Blocker(
                        code="invalid_github_url",
                        message=f"Repository URL is not a supported GitHub URL: {repository_url}",
                        severity="hard",
                    )
                )
        elif repository_path:
            repository = build_local_repository_source(
                repository_path,
                target_branch=target_branch,
                base_branch=base_branch,
                visibility=repository_visibility,
            )

        generated_from_one_liner = primary_input_mode == "one_line_fallback"
        source_confidence = self.source_confidence(primary_input_mode, document_files, blockers)

        brief = ProjectBrief(
            project_id=project_id,
            objective=clean_objective,
            primary_input_mode=primary_input_mode,
            documents=document_files,
            attachments=attachment_files,
            repository=repository,
            constraints=list(constraints),
            acceptance_criteria=list(acceptance_criteria),
            generated_from_one_liner=generated_from_one_liner,
            blockers=blockers,
            source_confidence=source_confidence,
            created_at=created_at or utc_now_iso(),
        )
        return brief

    def source_confidence(
        self,
        primary_input_mode: InputMode,
        documents: Sequence[ProjectFile],
        blockers: Sequence[Blocker],
    ) -> SourceConfidence:
        if any(blocker.severity == "hard" for blocker in blockers):
            return "low"
        if primary_input_mode == "one_line_fallback":
            return "low"
        if documents:
            return "high"
        return "medium"


def stable_project_id(
    objective: str,
    documents: Sequence[ProjectFile],
    attachments: Sequence[ProjectFile],
    repository_url: str,
) -> str:
    digest = hashlib.sha256()
    digest.update(objective.encode("utf-8"))
    digest.update(b"\0")
    digest.update(repository_url.encode("utf-8"))
    for project_file in [*documents, *attachments]:
        digest.update(b"\0")
        digest.update(project_file.content_hash.encode("utf-8"))
        digest.update(b"\0")
        digest.update(project_file.path.encode("utf-8"))
    return f"proj_{digest.hexdigest()[:12]}"


def build_local_repository_source(
    repository_path: str | Path,
    *,
    target_branch: str = "main",
    base_branch: str = "",
    visibility: Visibility = "public",
) -> RepositorySource:
    path = Path(repository_path)
    return RepositorySource(
        provider="local",
        url="",
        owner="",
        name=path.name or "local-repository",
        target_branch=target_branch,
        base_branch=base_branch,
        local_path=str(path),
        visibility=visibility,
        gh_auth_required=False,
        access_status="available" if path.exists() else "unchecked",
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a v2 ProjectBrief from local intake inputs.")
    parser.add_argument("--objective", required=True)
    parser.add_argument("--mode", choices=["document_driven", "one_line_fallback"], default="document_driven")
    parser.add_argument("--document", action="append", default=[])
    parser.add_argument("--attachment", action="append", default=[])
    parser.add_argument("--required-attachment", action="append", default=[])
    parser.add_argument("--repository")
    parser.add_argument("--repository-path", default="")
    parser.add_argument("--target-branch", default="main")
    parser.add_argument("--base-branch", default="")
    parser.add_argument("--repository-visibility", choices=["public", "private", "unknown"], default="public")
    parser.add_argument("--constraint", action="append", default=[])
    parser.add_argument("--acceptance", action="append", default=[])
    parser.add_argument("--validate", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    brief = ProjectBriefBuilder().build(
        objective=args.objective,
        documents=args.document,
        attachments=args.attachment,
        primary_input_mode=args.mode,
        repository_url=args.repository or "",
        repository_path=args.repository_path,
        target_branch=args.target_branch,
        base_branch=args.base_branch,
        repository_visibility=args.repository_visibility,
        constraints=args.constraint,
        acceptance_criteria=args.acceptance,
        required_attachments=args.required_attachment,
    )
    payload = brief.to_dict()
    if args.validate:
        errors = validate_project_brief_contract(payload)
        if errors:
            print(json.dumps({"errors": errors, "project_brief": payload}, indent=2, sort_keys=True))
            return 1

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
