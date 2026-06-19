"""Acceptance scenario planning for document-driven browser verification."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal


ScenarioKind = Literal["crud", "auth", "file_upload", "dashboard"]


@dataclass(slots=True)
class AcceptanceScenario:
    id: str
    kind: ScenarioKind
    title: str
    source_requirement_id: str
    required_behaviors: list[str] = field(default_factory=list)
    evidence_terms: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "source_requirement_id": self.source_requirement_id,
            "required_behaviors": list(self.required_behaviors),
            "evidence_terms": list(self.evidence_terms),
        }


@dataclass(slots=True)
class AcceptanceScenarioPlan:
    status: str
    summary: str
    scenarios: list[AcceptanceScenario] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "summary": self.summary,
            "scenarios": [scenario.to_dict() for scenario in self.scenarios],
        }


class AcceptanceScenarioPlanner:
    """Derive deterministic browser scenarios from requirements and acceptance criteria."""

    def build(self, context_bundle: dict[str, Any]) -> AcceptanceScenarioPlan:
        requirements = list(context_bundle.get("requirement_map", {}).get("requirements", []))
        scenarios: list[AcceptanceScenario] = []
        seen: set[tuple[str, str]] = set()
        for requirement in requirements:
            source_id = str(requirement.get("id", "") or f"REQ-{len(scenarios) + 1:03d}")
            text = _requirement_text(requirement)
            for kind in ("crud", "auth", "file_upload", "dashboard"):
                if not _matches_kind(text, kind):
                    continue
                key = (source_id, kind)
                if key in seen:
                    continue
                seen.add(key)
                scenarios.append(
                    AcceptanceScenario(
                        id=f"SCN-{len(scenarios) + 1:03d}",
                        kind=kind,  # type: ignore[arg-type]
                        title=_title_for(kind),
                        source_requirement_id=source_id,
                        required_behaviors=_required_behaviors(text, kind),
                        evidence_terms=_matched_terms(text, kind),
                    )
                )
        status = "generated" if scenarios else "skipped"
        summary = (
            f"{len(scenarios)} browser acceptance scenario(s) generated from requirements."
            if scenarios
            else "No domain-specific browser acceptance scenarios were inferred."
        )
        return AcceptanceScenarioPlan(status=status, summary=summary, scenarios=scenarios)


def _requirement_text(requirement: dict[str, Any]) -> str:
    parts = [str(requirement.get("text", ""))]
    parts.extend(str(item) for item in requirement.get("acceptance_criteria", []) if str(item).strip())
    return " ".join(parts).lower()


def _matches_kind(text: str, kind: str) -> bool:
    return bool(_matched_terms(text, kind))


def _matched_terms(text: str, kind: str) -> list[str]:
    terms = KIND_TERMS[kind]
    matched: list[str] = []
    for term in terms:
        if re.search(term, text, flags=re.IGNORECASE):
            matched.append(_display_term(term))
    return _dedupe(matched)


def _required_behaviors(text: str, kind: str) -> list[str]:
    if kind == "crud":
        behaviors = []
        if re.search(r"\b(create|add|new|submit|save)\b|新增|添加|创建|保存", text, flags=re.IGNORECASE):
            behaviors.append("create")
        if re.search(r"\b(edit|update|modify)\b|编辑|修改|更新", text, flags=re.IGNORECASE):
            behaviors.append("update")
        if re.search(r"\b(delete|remove|archive)\b|删除|移除", text, flags=re.IGNORECASE):
            behaviors.append("delete")
        if re.search(r"\b(list|table|item|record|todo|task)\b|列表|记录|任务|待办", text, flags=re.IGNORECASE):
            behaviors.append("list")
        return _dedupe(behaviors or ["create"])
    if kind == "auth":
        behaviors = []
        if re.search(r"\b(login|sign in|signin)\b|登录", text, flags=re.IGNORECASE):
            behaviors.append("login")
        if re.search(r"\b(register|sign up|signup)\b|注册", text, flags=re.IGNORECASE):
            behaviors.append("register")
        if re.search(r"\b(logout|sign out|session)\b|退出|会话", text, flags=re.IGNORECASE):
            behaviors.append("session")
        return _dedupe(behaviors or ["login"])
    if kind == "file_upload":
        return ["upload"]
    if kind == "dashboard":
        behaviors = []
        if re.search(r"\b(chart|graph|metric|kpi|analytics|dashboard)\b|图表|指标|统计|仪表盘", text, flags=re.IGNORECASE):
            behaviors.append("metrics")
        if re.search(r"\b(filter|search|sort)\b|筛选|搜索|排序", text, flags=re.IGNORECASE):
            behaviors.append("filter")
        if re.search(r"\b(table|report|list)\b|表格|报表|列表", text, flags=re.IGNORECASE):
            behaviors.append("table")
        return _dedupe(behaviors or ["metrics"])
    return []


def _title_for(kind: str) -> str:
    return {
        "crud": "CRUD acceptance scenario",
        "auth": "Authentication acceptance scenario",
        "file_upload": "File upload acceptance scenario",
        "dashboard": "Dashboard acceptance scenario",
    }.get(kind, "Acceptance scenario")


def _display_term(pattern: str) -> str:
    return pattern.replace("\\b", "").replace("|", "/")


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value).strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


KIND_TERMS: dict[str, tuple[str, ...]] = {
    "crud": (
        r"\bcrud\b",
        r"\b(create|add|new|edit|update|delete|remove)\b",
        r"\b(todo|task|item|record)\b",
        r"新增|添加|创建|编辑|修改|更新|删除|移除|待办|任务|记录",
    ),
    "auth": (
        r"\b(login|signin|sign in|register|signup|sign up|logout|password|session)\b",
        r"登录|注册|密码|退出|会话",
    ),
    "file_upload": (
        r"\b(upload|import|attachment|file picker|dropzone)\b",
        r"上传|导入|附件|文件选择|拖拽上传",
    ),
    "dashboard": (
        r"\b(dashboard|analytics|metric|kpi|chart|graph|table|report|filter|search)\b",
        r"仪表盘|看板|统计|指标|图表|报表|表格|筛选|搜索",
    ),
}
