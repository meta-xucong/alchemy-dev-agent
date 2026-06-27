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
    r"(?P<path>[\w./-]+\.(?:vue|tsx|jsx|yaml|yml|py|js|ts|go|rs|java|cs|rb|php|html|css|sql|md|json))(?![\w/-])"
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
    scope_controls: "ScopeControls" = field(default_factory=lambda: ScopeControls())


@dataclass(slots=True)
class ScopeControls:
    allowed_prefixes: list[str] = field(default_factory=list)
    protected_prefixes: list[str] = field(default_factory=list)
    target_files: list[str] = field(default_factory=list)
    boundary_mode: str = "strict"


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
        scope_controls = ScopeControls()

        for document in documents:
            doc_id = str(document["id"])
            role = str(document.get("role", "supplemental"))
            text = self._read_document_text(document)
            scope_controls = merge_scope_controls(scope_controls, extract_scope_controls(text))
            requirement_lines = extract_requirement_lines(text)
            acceptance_lines = extract_acceptance_lines(text)
            target_files = extract_target_files(text)
            if not requirement_lines and document.get("summary"):
                requirement_lines = [str(document["summary"])]
            acceptance_by_doc[doc_id] = acceptance_lines
            document_key_requirements[doc_id] = normalize_acceptance_lines(requirement_lines)
            for line in requirement_lines:
                priority = infer_priority(line, role)
                candidates.append((doc_id, role, line, priority, target_files))

        objective_text = str(payload.get("objective", "")).strip()
        if objective_text:
            scope_controls = merge_scope_controls(scope_controls, extract_scope_controls(objective_text))

        constraint_text = "\n".join(str(item) for item in payload.get("constraints", []) if str(item))
        if constraint_text:
            scope_controls = merge_scope_controls(scope_controls, extract_scope_controls(constraint_text))

        if not candidates:
            if objective_text:
                source = "generated_one_line" if payload.get("generated_from_one_liner") else "project_brief"
                priority = "should" if payload.get("generated_from_one_liner") else "must"
                candidates.append((source, "objective", objective_text, priority, []))

        explicit_acceptance = [str(item) for item in payload.get("acceptance_criteria", []) if str(item).strip()]
        acceptance_files_by_doc = {
            doc_id: explicit_paths_from_text("\n".join(lines))
            for doc_id, lines in acceptance_by_doc.items()
        }
        requirements: list[Requirement] = []
        seen: set[str] = set()
        for index, (doc_id, role, text, priority, target_files) in enumerate(candidates, start=1):
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
                preferred_files=dedupe_preserve_order([*acceptance_files_by_doc.get(doc_id, []), *target_files]),
                allowed_prefixes=scope_controls.allowed_prefixes,
                protected_prefixes=scope_controls.protected_prefixes,
                fallback_target_files=scope_controls.target_files,
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

        return RequirementExtraction(
            requirements=requirements,
            document_key_requirements=document_key_requirements,
            scope_controls=scope_controls,
        )

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


def extract_target_files(text: str) -> list[str]:
    selected: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        lowered = line.lower()
        if "target files" in lowered or "target file" in lowered or "目标文件" in line:
            selected.extend(explicit_paths_from_text(line))
    return dedupe_preserve_order(selected)


def extract_scope_controls(text: str) -> ScopeControls:
    allowed: list[str] = []
    protected: list[str] = []
    target_files: list[str] = []
    boundary_mode = detect_boundary_mode(text)
    mode = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        lowered = line.lower()
        if not line:
            continue
        control_line = strip_leading_marker(line).strip()
        control_lowered = control_line.lower()
        if line.startswith("#") and mode not in {"allowed_code", "protected_code"}:
            mode = ""
        if (
            "all implementation code and tests must live under" in control_lowered
            or ("only" in control_lowered and "may be changed" in control_lowered)
            or ("only" in control_lowered and "create or modify" in control_lowered)
            or control_lowered.startswith("allowed paths")
            or control_lowered.startswith("allowed scope")
            or control_lowered.startswith("allowed change scope")
            or control_lowered.startswith("allowed implementation scope")
            or (control_lowered.startswith("limited to") or control_lowered.endswith(" limited to:"))
            or "must live under" in control_lowered
            or (
                "build" in control_lowered
                and " under" in control_lowered
                and any(marker in control_lowered for marker in ("app/", "tests/", "alchemy_creative_agent_3_0"))
            )
        ):
            mode = "allowed"
        elif (
            control_lowered.startswith("do not edit any file under")
            or control_lowered.startswith("protected areas")
            or control_lowered.startswith("protected paths")
            or control_lowered.startswith("protected change scope")
            or control_lowered.startswith("reference material only")
        ):
            mode = "protected"
        elif lowered.startswith("target files"):
            inline_targets = explicit_paths_from_text(line)
            target_files.extend(inline_targets)
            mode = "target" if not inline_targets or line.endswith(":") else ""
        elif line.startswith("```"):
            if mode == "allowed":
                mode = "allowed_code"
            elif mode == "protected":
                mode = "protected_code"
            elif mode in {"allowed_code", "protected_code"}:
                mode = ""
            continue

        paths = scope_paths_from_line(line)
        if not paths:
            continue
        if mode in {"allowed", "allowed_code"}:
            allowed.extend(paths)
        elif mode in {"protected", "protected_code"}:
            protected.extend(paths)
        elif mode == "target":
            target_files.extend(explicit_paths_from_text(line))

    # The explicit target file list is also an implicit allowed scope.
    for target in target_files:
        parent = str(Path(target).parent).replace("\\", "/")
        if parent and parent != ".":
            allowed.append(parent + "/")
    apply_known_scope_heuristics(text, allowed, protected)
    return ScopeControls(
        allowed_prefixes=dedupe_preserve_order(normalize_scope_prefix(path) for path in allowed),
        protected_prefixes=dedupe_preserve_order(normalize_scope_prefix(path) for path in protected),
        target_files=dedupe_preserve_order(normalize_repo_path(path) for path in target_files),
        boundary_mode=boundary_mode,
    )


def detect_boundary_mode(text: str) -> str:
    lowered = text.lower()
    normalized = lowered.replace("_", " ").replace("-", " ")
    markers = (
        "large refactor",
        "whole-repository",
        "whole repository",
        "product-scale",
        "standalone service",
        "standalone system",
        "整仓",
        "大型重构",
        "整体改造",
        "独立运行",
        "独立程序",
        "脱胎换骨",
    )
    return "large_refactor" if any(marker in normalized or marker in lowered or marker in text for marker in markers) else "strict"


def scope_paths_from_line(line: str) -> list[str]:
    clean = line.strip().strip("`").strip()
    if not clean:
        return []
    paths: list[str] = []
    if (clean.endswith("/") or clean.endswith("/**")) and not any(char.isspace() for char in clean):
        paths.append(clean)
    paths.extend(explicit_paths_from_text(clean))
    return dedupe_preserve_order(paths)


def merge_scope_controls(left: ScopeControls, right: ScopeControls) -> ScopeControls:
    return ScopeControls(
        allowed_prefixes=dedupe_preserve_order([*left.allowed_prefixes, *right.allowed_prefixes]),
        protected_prefixes=dedupe_preserve_order([*left.protected_prefixes, *right.protected_prefixes]),
        target_files=dedupe_preserve_order([*left.target_files, *right.target_files]),
        boundary_mode="large_refactor" if "large_refactor" in {left.boundary_mode, right.boundary_mode} else "strict",
    )


def apply_known_scope_heuristics(text: str, allowed: list[str], protected: list[str]) -> None:
    lowered = text.lower()
    if "alchemy_creative_agent_3_0" not in lowered:
        return
    has_independence_rule = any(marker in lowered for marker in ("v1/v2", "v1 or v2", "v1/v2 runtime", "independent"))
    if not has_independence_rule:
        return
    allowed.append("alchemy_creative_agent_3_0/")
    if "alchemy_creative_agent_3_0/app" in lowered:
        allowed.append("alchemy_creative_agent_3_0/app/")
    if "alchemy_creative_agent_3_0/tests" in lowered:
        allowed.append("alchemy_creative_agent_3_0/tests/")
    protected.extend(
        [
            "custom_media_agent_2_0/",
            "custom_media_agent_2_0_docs/",
            "src_skeleton/",
            "docs/prompt-transform-conjure/",
            "docs/alchemy_lab/",
        ]
    )


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
    if role == "feedback":
        return "must"
    lowered = text.lower()
    for priority, markers in PRIORITY_MARKERS.items():
        if any(marker in lowered or marker in text for marker in markers):
            return priority
    if role == "primary_requirements":
        return "must"
    if role == "test_plan":
        return "should"
    return "should"


def related_files_for_requirement(
    text: str,
    repository_files: list[RepositoryFile],
    *,
    preferred_files: list[str] | None = None,
    allowed_prefixes: list[str] | None = None,
    protected_prefixes: list[str] | None = None,
    fallback_target_files: list[str] | None = None,
) -> list[str]:
    explicit = explicit_paths_from_text(text)
    preferred = [path for path in list(preferred_files or []) if path not in explicit]
    if preferred and not explicit:
        filtered_preferred = filter_scope_paths(
            dedupe_preserve_order(preferred),
            allowed_prefixes=allowed_prefixes or [],
            protected_prefixes=protected_prefixes or [],
        )
        if filtered_preferred:
            return filtered_preferred
        if fallback_target_files:
            return list(fallback_target_files)
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
    if preferred and not explicit and not any(path for path in related if path not in preferred):
        related = list(preferred)
    filtered = filter_scope_paths(
        dedupe_preserve_order(related),
        allowed_prefixes=allowed_prefixes or [],
        protected_prefixes=protected_prefixes or [],
    )
    if not filtered and fallback_target_files:
        return list(fallback_target_files)
    return filtered


def explicit_paths_from_text(text: str) -> list[str]:
    return dedupe_preserve_order([match.group("path") for match in PATH_PATTERN.finditer(text)])


def filter_scope_paths(
    paths: list[str],
    *,
    allowed_prefixes: list[str],
    protected_prefixes: list[str],
) -> list[str]:
    result: list[str] = []
    for path in paths:
        normalized = normalize_repo_path(path)
        if protected_prefixes and any(path_matches_prefix(normalized, prefix) for prefix in protected_prefixes):
            continue
        if allowed_prefixes and not any(path_matches_prefix(normalized, prefix) for prefix in allowed_prefixes):
            continue
        result.append(normalized)
    return dedupe_preserve_order(result)


def path_matches_prefix(path: str, prefix: str) -> bool:
    clean_prefix = normalize_scope_prefix(prefix)
    if clean_prefix.endswith("/"):
        return path.startswith(clean_prefix)
    return path == clean_prefix or path.startswith(clean_prefix + "/")


def normalize_scope_prefix(path: str) -> str:
    clean = normalize_repo_path(path)
    if clean.endswith("/**"):
        clean = clean[:-3]
    if clean and not Path(clean).suffix and not clean.endswith("/"):
        clean += "/"
    return clean


def normalize_repo_path(path: str) -> str:
    clean = str(path).replace("\\", "/").strip().strip("`").strip()
    if clean.endswith("."):
        clean = clean[:-1]
    return clean.strip("/")


def dedupe_preserve_order(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value).strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result
