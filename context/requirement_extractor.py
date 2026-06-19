"""Deterministic requirement extraction for document-driven planning."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import RepositoryFile, Requirement

PRIORITY_MARKERS = {
    "must": ("must", "required", "shall", "need to", "needs to", "必须", "需要", "应当"),
    "should": ("should", "建议", "应该", "最好"),
    "could": ("could", "nice to have", "optional", "可选", "可以"),
}

ACCEPTANCE_HEADINGS = (
    "acceptance",
    "acceptance criteria",
    "验收",
    "完成标准",
    "done criteria",
)

REQUIREMENT_HEADINGS = (
    "requirements",
    "functional requirements",
    "需求",
    "功能需求",
    "user stories",
    "内容说明",
    "本次提交包含",
    "技术目标",
    "该文档用于指导实现",
    "适用范围",
    "下一步计划",
    "建议下一阶段实现",
    "开发里程碑",
    "里程碑",
    "文件结构",
    "架构",
    "系统设计",
    "实现计划",
    "scope",
    "technical goals",
    "goals",
    "contents",
    "content",
    "architecture",
    "milestones",
    "next steps",
    "file structure",
    "feedback",
    "bug",
    "bugs",
    "bug report",
    "issues",
    "playtest",
    "playtest notes",
    "manual feedback",
    "验收反馈",
    "反馈",
    "问题",
)

PATH_PATTERN = re.compile(
    r"(?P<path>[\w./-]+\.(?:tsx|jsx|yaml|yml|py|js|ts|go|rs|java|cs|rb|php|html|css|sql|md|json))(?![\w.-])"
)
LEADING_MARKER_PATTERN = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
PROTECTED_TERM_REWRITES = (
    ("超级玛丽类横版游戏", "原创复古横版平台游戏"),
    ("超级玛丽类", "原创复古平台类"),
    ("超级玛丽", "原创复古平台游戏"),
    ("mushroom kingdom", "original whimsical game world"),
    ("super mario", "original retro platformer"),
    ("nintendo", "protected commercial game reference"),
    ("goomba", "basic walking enemy"),
    ("koopa", "basic patrol enemy"),
    ("luigi", "alternate original helper character"),
    ("peach", "original goal character"),
    ("bowser", "original boss obstacle"),
    ("toad", "original helper character"),
    ("mario", "original player hero"),
)


@dataclass(slots=True)
class RequirementExtraction:
    requirements: list[Requirement] = field(default_factory=list)
    document_key_requirements: dict[str, list[str]] = field(default_factory=dict)


class RequirementExtractor:
    """Extract planner-ready requirements from ProjectBrief documents.

    The extractor is intentionally deterministic. It handles well-structured
    Markdown/plain text and degrades to summaries/objective text when deeper
    parsing is unavailable.
    """

    def extract(self, payload: dict[str, Any], repository_files: list[RepositoryFile]) -> RequirementExtraction:
        documents = [*payload.get("documents", []), *payload.get("attachments", [])]
        acceptance_by_doc: dict[str, list[str]] = {}
        candidates: list[tuple[str, str, str, str]] = []
        document_key_requirements: dict[str, list[str]] = {}

        for document in documents:
            doc_id = str(document["id"])
            role = str(document.get("role", "supplemental"))
            text = self._read_document_text(document)
            requirement_lines = extract_requirement_lines(text)
            acceptance_lines = extract_acceptance_lines(text)
            if not requirement_lines and document.get("summary"):
                requirement_lines = [str(document["summary"])]
            acceptance_by_doc[doc_id] = acceptance_lines
            document_key_requirements[doc_id] = normalize_acceptance_lines(requirement_lines)
            for line in requirement_lines:
                priority = infer_priority(line, role)
                candidates.append((doc_id, role, line, priority))

        if not candidates:
            objective = str(payload.get("objective", "")).strip()
            if objective:
                source = "generated_one_line" if payload.get("generated_from_one_liner") else "project_brief"
                priority = "should" if payload.get("generated_from_one_liner") else "must"
                candidates.append((source, "objective", objective, priority))

        explicit_acceptance = [str(item) for item in payload.get("acceptance_criteria", []) if str(item).strip()]
        acceptance_files_by_doc = {
            doc_id: explicit_paths_from_text("\n".join(lines))
            for doc_id, lines in acceptance_by_doc.items()
        }
        requirements: list[Requirement] = []
        seen: set[str] = set()
        for index, (doc_id, role, text, priority) in enumerate(candidates, start=1):
            clean_text = normalize_requirement_text(text)
            if not clean_text:
                continue
            dedupe_key = clean_text.lower()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            acceptance = acceptance_by_doc.get(doc_id, []) or explicit_acceptance
            acceptance = normalize_acceptance_lines(acceptance)
            if not acceptance and role == "test_plan":
                acceptance = [clean_text]
            if not acceptance:
                acceptance = [f"Requirement is implemented and verified: {clean_text}"]
            related_files = related_files_for_requirement(
                clean_text,
                repository_files,
                preferred_files=acceptance_files_by_doc.get(doc_id, []),
            )
            requirements.append(
                Requirement(
                    id=f"REQ-{len(requirements) + 1:03d}",
                    source_document_id=doc_id,
                    text=clean_text,
                    priority=priority,
                    acceptance_criteria=dedupe_preserve_order(acceptance),
                    related_files=related_files,
                    planned_task_ids=[],
                    source_role=role,
                )
            )

        return RequirementExtraction(requirements=requirements, document_key_requirements=document_key_requirements)

    def _read_document_text(self, document: dict[str, Any]) -> str:
        path = Path(str(document.get("path", "")))
        if document.get("parse_status") != "parsed":
            return ""
        if path.suffix.lower() not in {".md", ".txt", ".json", ".yaml", ".yml"}:
            return ""
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return str(document.get("summary", ""))


def extract_requirement_lines(text: str) -> list[str]:
    lines = text.splitlines()
    selected: list[str] = []
    in_requirement_section = False
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        heading = normalized_heading(line)
        if heading:
            in_requirement_section = any(marker in heading for marker in REQUIREMENT_HEADINGS)
            if any(marker in heading for marker in ACCEPTANCE_HEADINGS):
                in_requirement_section = False
            continue
        if is_requirement_line(line, in_requirement_section):
            selected.append(strip_leading_marker(line))
    return dedupe_preserve_order(selected)


def extract_acceptance_lines(text: str) -> list[str]:
    lines = text.splitlines()
    selected: list[str] = []
    in_acceptance_section = False
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        heading = normalized_heading(line)
        if heading:
            in_acceptance_section = any(marker in heading for marker in ACCEPTANCE_HEADINGS)
            if in_acceptance_section:
                continue
            if heading.startswith("#"):
                in_acceptance_section = False
            continue
        if in_acceptance_section and is_list_like(line):
            selected.append(strip_leading_marker(line))
    return dedupe_preserve_order(selected)


def normalized_heading(line: str) -> str:
    if line.startswith("#"):
        return line.strip("# ").lower()
    if line.endswith(":") and len(line) <= 80:
        return line.rstrip(":").lower()
    if line.endswith("：") and len(line) <= 80:
        return line.rstrip("：").lower()
    return ""


def is_requirement_line(line: str, in_requirement_section: bool) -> bool:
    lowered = line.lower()
    if in_requirement_section and is_list_like(line):
        return True
    if in_requirement_section and re.match(r"^\s*\d+[.、]\s+", line):
        return True
    return any(marker in lowered for marker in [*PRIORITY_MARKERS["must"], *PRIORITY_MARKERS["should"], *PRIORITY_MARKERS["could"]])


def is_list_like(line: str) -> bool:
    return bool(LEADING_MARKER_PATTERN.match(line) or re.match(r"^\s*\d+[.、]\s+", line))


def strip_leading_marker(line: str) -> str:
    clean = LEADING_MARKER_PATTERN.sub("", line).strip()
    return re.sub(r"^\s*\d+[.、]\s+", "", clean).strip()


def normalize_requirement_text(text: str) -> str:
    clean = strip_leading_marker(text).strip()
    clean = re.sub(r"\s+", " ", clean)
    clean = rewrite_protected_game_terms(clean)
    return clean.rstrip(".") + "." if clean and not clean.endswith((".", "!", "?", "。")) else clean


def normalize_acceptance_lines(lines: list[str]) -> list[str]:
    normalized: list[str] = []
    for line in lines:
        clean = re.sub(r"\s+", " ", strip_leading_marker(str(line)).strip())
        if clean:
            normalized.append(rewrite_protected_game_terms(clean))
    return dedupe_preserve_order(normalized)


def rewrite_protected_game_terms(text: str) -> str:
    clean = text
    for source, replacement in PROTECTED_TERM_REWRITES:
        if any("\u4e00" <= char <= "\u9fff" for char in source):
            clean = clean.replace(source, replacement)
        else:
            clean = re.sub(rf"\b{re.escape(source)}\b", replacement, clean, flags=re.IGNORECASE)
    return clean


def infer_priority(text: str, role: str) -> str:
    lowered = text.lower()
    for priority, markers in PRIORITY_MARKERS.items():
        if any(marker in lowered or marker in text for marker in markers):
            return priority
    if role == "primary_requirements":
        return "must"
    if role == "feedback":
        return "must"
    if role == "test_plan":
        return "should"
    return "should"


def related_files_for_requirement(
    text: str,
    repository_files: list[RepositoryFile],
    *,
    preferred_files: list[str] | None = None,
) -> list[str]:
    explicit = explicit_paths_from_text(text)
    preferred = [path for path in list(preferred_files or []) if path not in explicit]
    if preferred and not explicit:
        return dedupe_preserve_order(preferred)
    paths_by_name = {Path(file.path).name.lower(): file.path for file in repository_files}
    paths_by_stem = {Path(file.path).stem.lower(): file.path for file in repository_files if Path(file.path).stem}
    lowered = text.lower()
    related = [*explicit, *preferred]
    for name, path in paths_by_name.items():
        if name in lowered:
            related.append(path)
    for stem, path in paths_by_stem.items():
        if stem and len(stem) >= 4 and stem in lowered:
            related.append(path)
    return dedupe_preserve_order(related)


def explicit_paths_from_text(text: str) -> list[str]:
    return dedupe_preserve_order([match.group("path") for match in PATH_PATTERN.finditer(text)])


def dedupe_preserve_order(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value).strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result
