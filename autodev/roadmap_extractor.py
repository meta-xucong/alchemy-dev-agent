"""Extract full-roadmap execution plans from development inputs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Sequence

from context.requirement_extractor import ScopeControls, extract_scope_controls, merge_scope_controls

from .roadmap_models import RoadmapExecutionPlan, RoadmapPhase


PHASE_HEADING_PATTERN = re.compile(
    r"^(?P<marker>#+\s*)?(?P<title>(?:V\d+(?:\.\d+)?|Phase\s+\d+(?:\.\d+)?|阶段\s*\d+(?:\.\d+)?|Milestone\s+\d+(?:\.\d+)?|里程碑\s*\d+(?:\.\d+)?)[^#\n]*)",
    re.IGNORECASE,
)
SUMMARY_VERSION_PATTERN = re.compile(
    r"^\s*(?P<title>V\d+(?:\.\d+)?\s+(?:[A-Z][A-Za-z0-9+/&().:-]*\s*){1,10})$",
    re.IGNORECASE,
)
PHASE_TITLE_HINTS = (
    "foundation",
    "brand",
    "consistency",
    "generation",
    "loop",
    "mvp",
    "rendering",
    "conditioning",
    "sidecar",
    "api",
    "ux",
    "ui",
    "frontend",
    "scenario",
    "vertical",
    "agent",
    "specialization",
    "workspace",
    "runtime",
    "flow",
    "delivery",
    "hardening",
    "core",
    "memory",
    "scoring",
    "refine",
    "product",
    "phase",
    "wave",
    "里程碑",
    "阶段",
    "基础",
    "生成",
)
NON_PHASE_TITLE_HINTS = (
    "acceptance criteria",
    "out of scope",
    "should ",
    "can ",
    "must",
    "must not",
    "do not",
    "does not need",
    "may use",
    "keeps",
    "code must",
    "concept",
    "owned layer",
    "runtime modules",
    "only as historical",
    "should allow",
    "should make",
    "foundation should",
)
GLOBAL_CONSTRAINT_MARKERS = (
    "do not import",
    "do not call",
    "must not import",
    "must not call",
    "must not expose",
    "must not leak",
    "do not route",
    "do not couple",
    "no v1/v2",
    "fully independent",
    "protected branch",
    "no automatic merge",
    "不要",
    "不得",
    "不能",
)
PHASE_LOCAL_MARKERS = (
    "in this task",
    "in this phase",
    "foundation",
    "v3.0",
    "first task",
    "first-pass",
    "当前阶段",
    "本阶段",
    "本任务",
)
EXTERNAL_BLOCKER_MARKERS = (
    "api key",
    "credential",
    "login",
    "paid",
    "gpu",
    "comfyui",
    "controlnet",
    "ip-adapter",
    "instantstyle",
    "真实生图",
    "账号",
    "密钥",
    "付费",
    "显卡",
)
NON_BLOCKING_RESOURCE_MARKERS = (
    "do not",
    "does not",
    "should not",
    "shouldn't",
    "must not expose",
    "must not leak",
    "not expose",
    "not leak",
    "not need",
    "not required",
    "no ",
    "unless",
    "without",
    "skip",
    "out of scope",
    "first implementation",
    "foundation",
    "不要",
    "不需要",
    "无需",
    "不用",
    "不应",
    "不得",
    "不能",
)
MIGRATION_WORK_MARKERS = (
    "remove",
    "delete",
    "prune",
    "trim",
    "replace",
    "whitelist",
    "legacy",
    "migration",
    "route registration",
    "router",
    "menu",
    "fresh migration",
    "目标系统",
    "最终 demo",
    "删除",
    "移除",
    "裁剪",
    "收口",
    "改成",
    "白名单",
    "不注册",
    "不能保留",
    "不能继续",
    "不能创建",
)
SCHEMA_FIELD_PATTERN = re.compile(
    r"^[`\"']?[a-zA-Z_][\w.-]*[`\"']?\s*:\s*"
    r"(?:bool|boolean|string|str|int|integer|float|number|array|object|dict|list|null|none)"
    r"(?:\b|$)",
    re.IGNORECASE,
)


class RoadmapExtractor:
    """Build a deterministic full-roadmap execution plan."""

    def extract(
        self,
        *,
        objective: str,
        documents: Sequence[str | Path] = (),
        attachments: Sequence[str | Path] = (),
        source_mode: str = "uploaded_docs",
        delivery_policy: dict[str, object] | None = None,
    ) -> RoadmapExecutionPlan:
        refs = [Path(path) for path in [*documents, *attachments]]
        texts = [(path, read_text(path)) for path in refs if path.exists()]
        global_constraints, phase_local_constraints, external_blockers = classify_constraints(text for _path, text in texts)
        global_scope_controls = extract_combined_scope_controls(text for _path, text in texts)
        phases = self._extract_phases(texts)
        if not phases:
            phases = [
                RoadmapPhase(
                    phase_id="phase_001",
                    title="Complete root objective",
                    source_references=[str(path) for path, _text in texts],
                    phase_type="feature",
                    requirements=[objective],
                    global_constraints=list(global_constraints),
                    phase_local_constraints=[],
                )
            ]
        for phase in phases:
            phase.global_constraints = list(global_constraints)
            phase.scope_controls = scope_controls_payload(
                merge_scope_controls(global_scope_controls, scope_controls_from_payload(phase.scope_controls))
            )
            phase.phase_local_constraints = [
                value
                for value in phase.phase_local_constraints
                if value not in global_constraints
            ] or [value for value in phase_local_constraints if phase_key(phase.title) in value.lower()]
            if not phase.promotion_gate:
                phase.promotion_gate = {
                    "required_score": 0.85,
                    "required_tests_pass": True,
                    "central_review_decision": "handoff_for_phase",
                }
            if not phase.verification:
                phase.verification = {"commands": [], "probes": [], "review_checks": ["central_phase_review"]}
        return RoadmapExecutionPlan(
            root_objective=objective,
            source_mode=source_mode,
            completion_policy="full_roadmap",
            global_constraints=list(global_constraints),
            external_blockers=list(external_blockers),
            phases=phases,
            final_acceptance={
                "all_required_phases_complete": True,
                "final_system_audit_passes": True,
                "no_hard_blockers": True,
            },
            delivery_policy=delivery_policy
            or {
                "mode": "local",
                "requires_user_approval_for_merge": True,
                "allow_public_repository": True,
                "allow_destructive_actions": False,
            },
            confidence=confidence_for_plan(phases, texts),
        )

    def _extract_phases(self, texts: list[tuple[Path, str]]) -> list[RoadmapPhase]:
        phases: list[RoadmapPhase] = []
        seen_titles: set[str] = set()
        version_seen: set[str] = set()
        candidates: list[tuple[int, Path, int, str, list[str]]] = []
        for path, text in sorted(texts, key=lambda item: document_priority(item[0])):
            lines = text.splitlines()
            for index, line, in_fence in iter_phase_lines(lines):
                title = phase_title_from_line(line)
                if not title:
                    continue
                priority = 2 if in_fence else 0
                candidates.append((priority, path, index, title, lines))
        has_versioned_phase = any(phase_version_key(title).startswith("v") for _priority, _path, _index, title, _lines in candidates)
        for priority, path, index, title, lines in sorted(candidates, key=lambda item: (item[0], document_priority(item[1]), item[2])):
            if should_skip_reference_phase(path, title, has_versioned_phase=has_versioned_phase):
                continue
            key = normalize_phase_title(title)
            version_key = phase_version_key(title)
            if version_key and version_key in version_seen:
                continue
            if key in seen_titles:
                continue
            seen_titles.add(key)
            if version_key:
                version_seen.add(version_key)
            block = phase_block(lines, index)
            phases.append(
                RoadmapPhase(
                    phase_id=f"phase_{len(phases) + 1:03d}",
                    title=title,
                    source_references=[f"{path}:{index + 1}"],
                    phase_type=infer_phase_type(title),
                    requirements=extract_phase_requirements(block, fallback=title),
                    scope_controls=scope_controls_payload(extract_scope_controls("\n".join(block))),
                    phase_local_constraints=phase_local_constraints_from_block(block),
                    optional=is_optional_phase(title, block),
                )
            )
        return phases


def read_text(path: Path) -> str:
    if path.suffix.lower() not in {".md", ".txt", ".json", ".yaml", ".yml"}:
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def phase_title_from_line(line: str) -> str:
    stripped = line.strip().strip("` ")
    if not stripped:
        return ""
    markdown_heading = stripped.startswith("#")
    if markdown_heading:
        stripped = strip_list_marker(stripped.lstrip("#").strip())
    match = PHASE_HEADING_PATTERN.match(stripped)
    if match and is_valid_phase_title(match.group("title"), markdown_heading=bool(match.group("marker"))):
        return clean_title(match.group("title"))
    list_candidate = strip_list_marker(stripped)
    summary = SUMMARY_VERSION_PATTERN.match(list_candidate)
    if summary:
        title = clean_title(summary.group("title"))
        return title if is_valid_phase_title(title, markdown_heading=False) else ""
    return ""


def is_valid_phase_title(title: str, *, markdown_heading: bool) -> bool:
    clean = clean_title(title)
    lower = clean.lower()
    if not re.match(r"^(?:v\d+(?:\.\d+)?|phase\s+\d+(?:\.\d+)?|阶段\s*\d+(?:\.\d+)?|milestone\s+\d+(?:\.\d+)?|里程碑\s*\d+(?:\.\d+)?)\b", lower):
        return False
    if any(hint in lower for hint in NON_PHASE_TITLE_HINTS):
        return False
    if re.match(r"^v\d+\b(?!\.)", lower):
        return False
    if markdown_heading:
        return True
    return any(hint in lower for hint in PHASE_TITLE_HINTS)


def clean_title(value: str) -> str:
    title = re.sub(r"\s+", " ", value.strip().strip("#:- "))
    prompt_match = re.search(r"\bprompt\s*:\s*(V\d+(?:\.\d+)?\s+.+)$", title, flags=re.IGNORECASE)
    if prompt_match:
        title = prompt_match.group(1)
    return title[:120]


def normalize_phase_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.lower()).strip()


def phase_version_key(title: str) -> str:
    match = re.match(r"^(v\d+(?:\.\d+)?|phase\s+\d+(?:\.\d+)?|阶段\s*\d+(?:\.\d+)?|milestone\s+\d+(?:\.\d+)?|里程碑\s*\d+(?:\.\d+)?)\b", title.lower())
    return match.group(1) if match else ""


def document_priority(path: Path) -> tuple[int, str]:
    name = path.name.lower()
    if "13_step_by_step_delivery_plan" in name:
        return (0, str(path))
    if "05_development_roadmap" in name:
        return (1, str(path))
    if "14_codex_task_prompts" in name:
        return (2, str(path))
    if name == "readme.md":
        return (3, str(path))
    return (4, str(path))


def iter_phase_lines(lines: list[str]) -> Iterable[tuple[int, str, bool]]:
    in_fence = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        yield index, line, in_fence


def phase_block(lines: list[str], start: int) -> list[str]:
    block: list[str] = []
    in_fence = False
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
        if not in_fence and phase_title_from_line(line):
            break
        block.append(line)
    return block[:120]


def should_skip_reference_phase(path: Path, title: str, *, has_versioned_phase: bool) -> bool:
    version = phase_version_key(title)
    if not has_versioned_phase or not version.startswith("phase "):
        return False
    path_hint = str(path).lower().replace("\\", "/")
    if "reference" in path_hint or "参考" in path_hint:
        return True
    return False


def extract_phase_requirements(block: list[str], *, fallback: str) -> list[str]:
    requirements: list[str] = []
    in_section = False
    for raw in block:
        line = raw.strip()
        if not line:
            continue
        heading = line.strip("# ").lower()
        if line.startswith("#"):
            in_section = any(word in heading for word in ("goal", "requirements", "acceptance", "deliverables", "scope", "目标", "需求", "验收"))
            continue
        if is_list_item(line):
            clean = strip_list_marker(line)
            if clean:
                requirements.append(clean)
        elif in_section and len(line) <= 180:
            requirements.append(line)
    return dedupe(requirements[:30] or [fallback])


def phase_local_constraints_from_block(block: list[str]) -> list[str]:
    constraints: list[str] = []
    for raw in block:
        line = strip_list_marker(raw.strip())
        lower = line.lower()
        if any(marker in lower for marker in ("do not", "not required", "out of scope", "不要", "不需要", "不得", "不能")):
            constraints.append(line)
    return dedupe(constraints)


def classify_constraints(texts: Iterable[str]) -> tuple[list[str], list[str], list[str]]:
    global_constraints: list[str] = []
    phase_local_constraints: list[str] = []
    external_blockers: list[str] = []
    for text in texts:
        in_non_blocking_resource_section = False
        for raw in text.splitlines():
            stripped = raw.strip()
            if stripped.startswith("#"):
                heading = stripped.strip("# ").lower()
                in_non_blocking_resource_section = any(
                    marker in heading
                    for marker in ("not included", "out of scope", "not required", "non-goals", "不包含", "范围外")
                )
                continue
            if not stripped:
                in_non_blocking_resource_section = False
                continue
            line = strip_list_marker(stripped)
            if not line or len(line) > 220:
                continue
            lower = line.lower()
            if in_non_blocking_resource_section and any(marker in lower for marker in EXTERNAL_BLOCKER_MARKERS):
                phase_local_constraints.append(line)
                continue
            if is_external_blocker_line(lower):
                external_blockers.append(line)
            if is_migration_work_constraint(lower):
                global_constraints.append(line)
            elif any(marker in lower for marker in GLOBAL_CONSTRAINT_MARKERS):
                if any(marker in lower for marker in PHASE_LOCAL_MARKERS) and "v1/v2" not in lower:
                    phase_local_constraints.append(line)
                else:
                    global_constraints.append(line)
            elif any(marker in lower for marker in ("not included", "out of scope", "do not implement yet", "later")):
                phase_local_constraints.append(line)
    return dedupe(global_constraints), dedupe(phase_local_constraints), dedupe(external_blockers)


def extract_combined_scope_controls(texts: Iterable[str]) -> ScopeControls:
    controls = ScopeControls()
    for text in texts:
        controls = merge_scope_controls(controls, extract_scope_controls(text))
    return controls


def scope_controls_from_payload(payload: dict[str, object] | None) -> ScopeControls:
    payload = dict(payload or {})
    return ScopeControls(
        allowed_prefixes=[str(item) for item in payload.get("allowed_prefixes", []) or []],
        protected_prefixes=[str(item) for item in payload.get("protected_prefixes", []) or []],
        target_files=[str(item) for item in payload.get("target_files", []) or []],
        boundary_mode=str(payload.get("boundary_mode", "strict") or "strict"),
    )


def scope_controls_payload(controls: ScopeControls) -> dict[str, object]:
    return {
        "allowed_prefixes": list(controls.allowed_prefixes),
        "protected_prefixes": list(controls.protected_prefixes),
        "target_files": list(controls.target_files),
        "boundary_mode": str(controls.boundary_mode or "strict"),
    }


def is_external_blocker_line(lower: str) -> bool:
    if SCHEMA_FIELD_PATTERN.match(lower.strip().strip("-*+ ")):
        return False
    if not any(marker in lower for marker in EXTERNAL_BLOCKER_MARKERS):
        return False
    if any(marker in lower for marker in MIGRATION_WORK_MARKERS):
        return False
    if any(marker in lower for marker in NON_BLOCKING_RESOURCE_MARKERS):
        return False
    return any(gate in lower for gate in ("require", "requires", "required", "need ", "needs ", "需要", "must", "必须"))


def is_migration_work_constraint(lower: str) -> bool:
    return any(marker in lower for marker in MIGRATION_WORK_MARKERS) and any(
        gate in lower for gate in ("must", "必须", "不能", "不得", "should", "要")
    )


def infer_phase_type(title: str) -> str:
    lower = title.lower()
    if any(token in lower for token in ("documentation", "document", "docs", "freeze", "文档", "冻结")):
        return "documentation"
    if any(token in lower for token in ("foundation", "skeleton", "core", "基础")):
        return "foundation"
    if any(token in lower for token in ("ui", "ux", "frontend", "interface", "界面")):
        return "ui"
    if any(token in lower for token in ("generation", "provider", "image", "生成")):
        return "generation"
    if any(token in lower for token in ("api", "integration", "adapter", "集成")):
        return "integration"
    if any(token in lower for token in ("delivery", "pr", "release", "交付")):
        return "delivery"
    if any(token in lower for token in ("hardening", "test", "audit", "验收", "测试")):
        return "hardening"
    return "feature"


def is_optional_phase(title: str, block: list[str]) -> bool:
    joined = f"{title}\n" + "\n".join(block[:12])
    lower = joined.lower()
    return any(
        token in lower
        for token in (
            "optional idea",
            "optional unless explicitly requested",
            "nice to have",
            "may expose",
            "future vertical",
            "future pack",
            "future expansion",
            "future specialization",
            "v3.8+",
            "可选想法",
            "后续可选",
        )
    )


def is_list_item(line: str) -> bool:
    return bool(re.match(r"^\s*(?:[-*+]|\d+[.)、])\s+", line))


def strip_list_marker(line: str) -> str:
    return re.sub(r"^\s*(?:[-*+]|\d+[.)、])\s+", "", line).strip()


def phase_key(title: str) -> str:
    match = re.search(r"v\d+(?:\.\d+)?|phase\s+\d+(?:\.\d+)?|阶段\s*\d+(?:\.\d+)?", title.lower())
    return match.group(0) if match else title.lower()[:24]


def confidence_for_plan(phases: list[RoadmapPhase], texts: list[tuple[Path, str]]) -> float:
    if not phases:
        return 0.35
    if len(phases) >= 3 and texts:
        return 0.86
    if len(phases) >= 2 and texts:
        return 0.80
    if texts:
        return 0.72
    return 0.55


def dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value).strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result
