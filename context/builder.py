"""Build ContextBundle inputs from ProjectBrief payloads."""

from __future__ import annotations

from typing import Any

from intake.models import Blocker, ProjectBrief

from .models import ContextBundle, DocumentSummary, Requirement, Risk
from .repository_indexer import RepositoryIndexer
from .requirement_extractor import RequirementExtractor

PROTECTED_GAME_TERMS = ("超级玛丽", "super mario", "mario", "mushroom kingdom", "goomba", "koopa")


class ContextBundleBuilder:
    """Create deterministic planner context from a ProjectBrief."""

    def __init__(
        self,
        repository_indexer: RepositoryIndexer | None = None,
        requirement_extractor: RequirementExtractor | None = None,
    ) -> None:
        self.repository_indexer = repository_indexer or RepositoryIndexer()
        self.requirement_extractor = requirement_extractor or RequirementExtractor()

    def build(self, project_brief: ProjectBrief | dict[str, Any]) -> ContextBundle:
        payload = project_brief.to_dict() if isinstance(project_brief, ProjectBrief) else project_brief
        objective = str(payload["objective"])
        blockers = [
            Blocker(code=str(blocker["code"]), message=str(blocker["message"]), severity=blocker.get("severity", "hard"))
            for blocker in payload.get("blockers", [])
        ]

        repository = payload.get("repository")
        root_path = str(repository.get("local_path", "")) if isinstance(repository, dict) else ""
        repository_index = self.repository_indexer.index(root_path) if root_path else None
        if repository_index:
            blockers.extend(repository_index.blockers)
        repository_files = repository_index.files if repository_index else []

        documents = [self._document_summary(document) for document in payload.get("documents", [])]
        documents.extend(self._document_summary(attachment) for attachment in payload.get("attachments", []))

        if self._should_use_generated_artifact_fallback(payload):
            requirements = self._requirements_from_payload(payload, objective)
        else:
            extraction = self.requirement_extractor.extract(payload, repository_files)
            key_requirements_by_doc = extraction.document_key_requirements
            documents = [
                self._document_summary(document, key_requirements_by_doc=key_requirements_by_doc)
                for document in payload.get("documents", [])
            ]
            documents.extend(
                self._document_summary(attachment, key_requirements_by_doc=key_requirements_by_doc)
                for attachment in payload.get("attachments", [])
            )
            requirements = enrich_requirements_with_scaffold_hints(extraction.requirements, objective, repository_files)
        risks = self._risks_for_objective(objective)

        return ContextBundle(
            project_id=str(payload["project_id"]),
            objective=objective,
            documents=documents,
            repository_files=repository_files,
            package_files=repository_index.package_files if repository_index else [],
            ci_files=repository_index.ci_files if repository_index else [],
            requirements=requirements,
            risks=risks,
            blockers=blockers,
            root_path=root_path,
            package_managers=repository_index.package_managers if repository_index else [],
            test_commands=repository_index.test_commands if repository_index else ["static artifact inspection"],
            build_commands=repository_index.build_commands if repository_index else [],
            lint_commands=repository_index.lint_commands if repository_index else [],
            coverage_unknown=repository_index.coverage_unknown if repository_index else True,
        )

    def _document_summary(
        self,
        payload: dict[str, Any],
        *,
        key_requirements_by_doc: dict[str, list[str]] | None = None,
    ) -> DocumentSummary:
        summary = str(payload.get("summary", ""))
        key_requirements = (key_requirements_by_doc or {}).get(str(payload["id"]), [])
        if not key_requirements and summary:
            key_requirements = [summary]
        return DocumentSummary(
            id=str(payload["id"]),
            path=str(payload["path"]),
            role=str(payload["role"]),
            content_hash=str(payload["content_hash"]),
            parse_status=str(payload["parse_status"]),
            summary=summary,
            key_requirements=key_requirements,
            confidence="high" if payload.get("parse_status") == "parsed" else "low",
        )

    def _requirements_from_payload(self, payload: dict[str, Any], objective: str) -> list[Requirement]:
        acceptance = list(payload.get("acceptance_criteria", []))
        if self._is_retro_platformer_request(objective):
            safe_acceptance = [
                "Game is a playable original retro side-scrolling platformer.",
                "Game uses canvas-rendered original pixel-style shapes and no external copyrighted assets.",
                "Player can move, jump, collide with platforms, collect coins, avoid enemies, and reach a finish flag.",
                "A first-stage level is present with ground, blocks, gaps, coins, enemies, timer, score, and restart.",
                "The generated artifact can run locally by opening index.html.",
            ]
            return [
                Requirement(
                    id="REQ-001",
                    source_document_id="generated_one_line",
                    text="Create an original retro side-scrolling platform game from the user's one-line objective.",
                    priority="must",
                    acceptance_criteria=safe_acceptance,
                    related_files=["index.html"],
                    planned_task_ids=["T001", "T002", "T003", "T004"],
                )
            ]

        fallback_acceptance = acceptance or [
            "Generate a local runnable artifact.",
            "Record implementation and verification evidence.",
        ]
        return [
            Requirement(
                id="REQ-001",
                source_document_id="generated_one_line" if payload.get("generated_from_one_liner") else "project_brief",
                text=objective,
                priority="should" if payload.get("generated_from_one_liner") else "must",
                acceptance_criteria=fallback_acceptance,
                planned_task_ids=["T001", "T002", "T003", "T004"],
            )
        ]

    def _risks_for_objective(self, objective: str) -> list[Risk]:
        risks: list[Risk] = []
        lowered = objective.lower()
        if any(term in lowered or term in objective for term in PROTECTED_GAME_TERMS):
            risks.append(
                Risk(
                    id="RISK-001",
                    type="copyright_safety",
                    severity="high",
                    description="The user requested close imitation of a protected commercial game.",
                    mitigation="Generate an original retro platformer with original shapes, names, colors, layout, and mechanics inspired only by the broad genre.",
                )
            )
        return risks

    def _is_retro_platformer_request(self, objective: str) -> bool:
        lowered = objective.lower()
        platform_terms = ("platform", "platformer", "横版", "闯关", "关卡", "游戏", "game")
        return any(term in lowered or term in objective for term in platform_terms)

    def _should_use_generated_artifact_fallback(self, payload: dict[str, Any]) -> bool:
        if not payload.get("generated_from_one_liner"):
            return False
        documents = [*payload.get("documents", []), *payload.get("attachments", [])]
        parsed_primary = [
            document
            for document in documents
            if document.get("required") and document.get("role") == "primary_requirements" and document.get("parse_status") == "parsed"
        ]
        return not parsed_primary


WEB_GAME_SCAFFOLD_FILES = [
    "index.html",
    "src/main.js",
    "src/engine.js",
    "src/input.js",
    "src/physics.js",
    "src/tilemap.js",
    "src/entities.js",
    "src/renderer.js",
    "tests/static_checks.js",
]


SCAFFOLD_HINTS = {
    "index.html": ("canvas", "html", "browser", "页面", "入口", "可运行", "60 fps"),
    "src/main.js": ("game engine", "初始化", "完整跑通", "level 1", "第一关", "main"),
    "src/engine.js": ("engine", "game engine", "游戏核心", "状态机", "关卡"),
    "src/input.js": ("input", "输入", "键盘", "控制"),
    "src/physics.js": ("physics", "物理", "跳跃", "碰撞", "aabb", "tile collision"),
    "src/tilemap.js": ("tilemap", "tile map", "关卡定义", "关卡系统", "level"),
    "src/entities.js": ("entity", "entities", "player", "enemy", "金币", "敌人", "旗帜", "goomba"),
    "src/renderer.js": ("renderer", "render", "渲染", "canvas", "60 fps"),
    "tests/static_checks.js": ("test", "测试", "验收", "验证", "完成标准"),
}


def enrich_requirements_with_scaffold_hints(
    requirements: list[Requirement],
    objective: str,
    repository_files: list[Any],
) -> list[Requirement]:
    if not should_apply_web_game_scaffold(requirements, objective, repository_files):
        return requirements
    for requirement in requirements:
        related = list(requirement.related_files)
        text = requirement.text.lower()
        if "文件结构" in requirement.text or "file structure" in text or "project structure" in text:
            related.extend(WEB_GAME_SCAFFOLD_FILES)
        for file_path, markers in SCAFFOLD_HINTS.items():
            if any(marker in text or marker in requirement.text for marker in markers):
                related.append(file_path)
        if not related:
            related.append("index.html")
        requirement.related_files = dedupe_preserve_order(related)
    return requirements


def should_apply_web_game_scaffold(requirements: list[Requirement], objective: str, repository_files: list[Any]) -> bool:
    if not requirements:
        return False
    source_files = [file for file in repository_files if getattr(file, "kind", "") == "source"]
    if source_files:
        return False
    combined = "\n".join([objective, *[requirement.text for requirement in requirements]]).lower()
    platform_markers = ("platform", "platformer", "横版", "关卡", "游戏", "game", "tilemap", "canvas", "player")
    return any(marker in combined or marker in objective for marker in platform_markers)


def dedupe_preserve_order(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value).strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result
