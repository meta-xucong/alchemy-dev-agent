"""Deterministic V2.187 objective compiler."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable

from .objective_models import ObjectiveContract, ObjectiveRequirement, RequirementClass, RequirementSource

ABSENT_SOURCE_MARKERS = (
    "delete", "remove", "absent", "forbidden", "must not remain", "must not contain",
    "删除", "移除", "清理", "不得保留", "禁止", "不能存在", "不应存在", "不属于",
)
ABSENT_RUNTIME_MARKERS = ("route", "runtime", "reachable", "endpoint", "page", "路由", "运行时", "端点", "页面", "入口")
FRESH_SCHEMA_MARKERS = ("fresh", "migration", "schema", "table", "ent", "全新", "迁移", "数据库", "表", "数据模型")
PUBLIC_CONTRACT_MARKERS = (
    "api", "ui", "copy", "docs", "public", "frontend", "sdk", "接口", "前端", "文案", "菜单", "组件", "服务",
)
SOURCE_SCOPE_MARKERS = ("source", "source code", "codebase", "源码", "源代码", "代码文件")
REFERENCE_MARKERS = (
    "reference", "read-only", "read only", "original", "transplant", "compare",
    "参考", "只读", "原版", "原始", "对照", "移植",
    "参考", "只读", "原版", "原始", "对照", "移植",
)
EXTERNAL_REFERENCE_MARKERS = (
    "read-only",
    "read only",
    "reference repository",
    "reference repo",
    "structural reference",
    "transplant",
    "compare against",
    "只读",
    "移植",
    "对照",
    "鍙",
    "绉绘",
    "瀵圭収",
)
VERIFY_MARKERS = (
    "test", "verify", "build", "smoke", "startup", "probe", "acceptance",
    "测试", "验证", "构建", "启动", "冒烟", "验收", "检查",
)
DECIDE_MARKERS = ("decide", "choice", "resolve", "must_decide", "决定", "决策", "选择", "明确方案")
PRESERVE_MARKERS = ("preserve", "remain valid", "retain", "keep", "保留", "保持", "不得破坏", "继续有效")
MUST_MARKERS = ("must", "required", "shall", "need to", "必须", "需要", "应当", "需", "务必")
NON_GOAL_SECTIONS = ("non-goal", "non goal", "out of scope", "不做", "非目标", "范围外", "不属于")
REQUIREMENT_SECTIONS = (
    "requirement", "acceptance", "scope", "goal", "deliverable", "responsibilit", "constraint", "proof", "verify",
    "需求", "要求", "验收", "范围", "目标", "交付", "职责", "约束", "证明", "验证", "必须", "禁止",
)

DOMAIN_SEEDS = {
    "rpm_capacity": ("rpm", "capacity", "容量"),
    "platform_quota": ("platform quota", "platform capacity", "quota", "平台配额", "平台容量"),
    "subscription": ("subscription", "plan", "订阅", "套餐"),
    "gateway": ("gateway", "proxy", "relay", "网关", "代理", "中转"),
    "upstream_account": (
        "upstream account", "account pool", "channel scheduling", "model routing",
        "上游账号", "账号池", "渠道调度", "模型路由",
    ),
    "billing_core": (
        "identity", "wallet", "recharge", "redeem", "metering", "usage", "payment", "audit",
        "身份", "钱包", "充值", "兑换", "计量", "用量", "支付", "审计",
    ),
}

DOMAIN_ALIASES = {
    alias: domain
    for domain, aliases in DOMAIN_SEEDS.items()
    for alias in aliases
}


class ObjectiveCompiler:
    """Compile detailed documents into a validated objective contract.

    This first implementation is deterministic and conservative. It preserves
    source spans and classifies explicit requirement language without relying on
    task completion or worker summaries.
    """

    def compile(
        self,
        objective: str,
        documents: Iterable[Path | str],
        *,
        acceptance_criteria: Iterable[str] = (),
    ) -> ObjectiveContract:
        requirements: list[ObjectiveRequirement] = []
        source_documents: list[str] = []
        for document in documents:
            path = Path(document)
            source_documents.append(str(path))
            text = path.read_text(encoding="utf-8", errors="replace")
            requirements.extend(self._requirements_from_text(path, text, start_index=len(requirements) + 1))
        synthetic = [str(item).strip() for item in acceptance_criteria if str(item).strip()]
        if not requirements and objective.strip():
            synthetic.insert(0, objective.strip())
        for statement in synthetic:
            requirements.append(
                self._build_requirement(
                    statement,
                    requirement_id=f"REQ-{len(requirements) + 1:03d}",
                    source=RequirementSource(
                        document="project_brief",
                        section="Acceptance Criteria" if acceptance_criteria else "Objective",
                        line_start=1,
                        line_end=1,
                        quote_hash=_quote_hash(statement),
                    ),
                )
            )
        contract = ObjectiveContract(objective=objective, requirements=requirements, source_documents=source_documents)
        contract.validation_errors = validate_objective_contract(contract)
        contract.revision = contract.compute_revision()
        return contract

    def _requirements_from_text(self, path: Path, text: str, *, start_index: int) -> list[ObjectiveRequirement]:
        requirements: list[ObjectiveRequirement] = []
        section = ""
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#"):
                section = line.strip("# ").strip()
                continue
            if not _looks_requirement_like(line, section=section):
                continue
            statement = _strip_marker(line)
            requirements.append(
                self._build_requirement(
                    statement,
                    requirement_id=f"REQ-{start_index + len(requirements):03d}",
                    source=RequirementSource(
                        document=str(path),
                        section=section,
                        line_start=line_number,
                        line_end=line_number,
                        quote_hash=_quote_hash(statement),
                    ),
                )
            )
        return requirements

    def _build_requirement(
        self,
        statement: str,
        *,
        requirement_id: str,
        source: RequirementSource,
    ) -> ObjectiveRequirement:
        class_name = classify_requirement(statement, section=source.section)
        domain = infer_domain(statement)
        subjects = infer_subjects(statement, domain)
        if class_name.startswith("must_absent") and not subjects:
            subjects = infer_negative_subjects(statement, domain)
        return ObjectiveRequirement(
            id=requirement_id,
            source=source,
            statement=statement,
            strength="may" if class_name in {"may_reframe", "may_waive"} else "must",
            class_name=class_name,
            domain=domain,
            subjects=subjects,
            scope=infer_scope(statement, class_name),
            allowed_exceptions=infer_allowed_exceptions(statement),
            proof_obligations=infer_proof_obligations(class_name),
        )


def classify_requirement(statement: str, *, section: str = "") -> RequirementClass:
    lowered = statement.lower()
    section_lower = section.lower()
    if "waive" in lowered or "exception" in lowered:
        return "may_waive"
    if "reframe" in lowered or "changed semantics" in lowered:
        return "may_reframe"
    negative = (
        any(marker in lowered for marker in ABSENT_SOURCE_MARKERS)
        or any(marker in section_lower for marker in NON_GOAL_SECTIONS)
        or "must not" in lowered
        or "shall not" in lowered
        or "不得" in statement
        or "不能" in statement
        or "不应" in statement
    )
    if negative:
        if any(marker in lowered for marker in FRESH_SCHEMA_MARKERS):
            return "must_absent_fresh_schema"
        if any(marker in lowered or marker in statement for marker in SOURCE_SCOPE_MARKERS):
            return "must_absent_source"
        if any(marker in lowered for marker in PUBLIC_CONTRACT_MARKERS):
            return "must_absent_public_contract"
        if any(marker in lowered for marker in ABSENT_RUNTIME_MARKERS):
            return "must_absent_runtime"
        return "must_absent_source"
    if any(marker in lowered or marker in statement for marker in PRESERVE_MARKERS):
        return "must_preserve"
    if _has_external_reference_intent(statement):
        return "must_reference"
    if any(marker in lowered or marker in statement for marker in DECIDE_MARKERS):
        return "must_decide"
    if any(marker in lowered or marker in statement for marker in VERIFY_MARKERS):
        return "must_verify"
    return "must_implement"


def infer_domain(statement: str) -> str:
    lowered = statement.lower()
    matched = [domain for domain, seeds in DOMAIN_SEEDS.items() if any(seed in lowered for seed in seeds)]
    if len(matched) == 1:
        return matched[0]
    if len(matched) > 1:
        return "multi_domain"
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_]+", lowered)
    return words[0] if words else "general"


def infer_subjects(statement: str, domain: str) -> list[str]:
    subjects = [domain] if domain and domain != "general" else []
    lowered = statement.lower()
    subjects.extend(alias for alias in DOMAIN_ALIASES if alias in lowered)
    for code in re.findall(r"`([^`]+)`", statement):
        subjects.append(code)
    for word in re.findall(r"\b[A-Z][A-Za-z0-9_]{3,}\b", statement):
        subjects.append(word)
    return _dedupe(subjects)


def infer_negative_subjects(statement: str, domain: str) -> list[str]:
    lowered = statement.lower()
    protected_terms = [
        "rom",
        "logo",
        "brand",
        "branding",
        "sprite",
        "sprites",
        "music",
        "audio",
        "asset",
        "assets",
        "layout",
        "route",
        "api",
    ]
    subjects = [term for term in protected_terms if term in lowered]
    if subjects:
        return _dedupe(subjects)
    if domain and domain not in {"general", "multi_domain"}:
        return [domain]
    return ["prohibited_content"]


def infer_scope(statement: str, class_name: RequirementClass) -> list[str]:
    paths = re.findall(r"[\w./-]+\.(?:go|ts|tsx|vue|sql|json|yaml|yml|md)", statement)
    if paths:
        return _dedupe(paths)
    if class_name == "must_absent_fresh_schema":
        return ["backend/migrations/**", "backend/ent/**"]
    if class_name == "must_absent_public_contract":
        return ["frontend/**", "docs/**", "backend/internal/server/**"]
    if class_name == "must_absent_runtime":
        return ["backend/internal/server/**", "frontend/src/router/**"]
    if class_name == "must_reference":
        return []
    lowered = statement.lower()
    inferred: list[str] = []
    if any(marker in lowered or marker in statement for marker in ("frontend", "ui", "page", "component", "前端", "页面", "组件")):
        inferred.append("frontend/**")
    if any(marker in lowered or marker in statement for marker in ("backend", "service", "server", "后端", "服务")):
        inferred.append("backend/**")
    if any(marker in lowered or marker in statement for marker in ("migration", "schema", "database", "迁移", "数据库", "数据表")):
        inferred.extend(["backend/migrations/**", "backend/ent/**"])
    if inferred:
        return _dedupe(inferred)
    return ["**"]


def infer_proof_obligations(class_name: RequirementClass) -> list[str]:
    return {
        "must_absent_source": ["static_inventory_zero"],
        "must_absent_runtime": ["runtime_route_inventory_zero"],
        "must_absent_fresh_schema": ["fresh_schema_inventory_zero", "fresh_migration_smoke"],
        "must_absent_public_contract": ["public_contract_inventory_zero"],
        "must_reference": ["reference_baseline_declared", "decision_record_references_source"],
        "must_verify": ["named_verification_passes"],
        "must_decide": ["decision_record_present"],
        "must_preserve": ["preserved_behavior_passes"],
        "must_implement": ["implementation_evidence_present", "behavior_verification_passes"],
        "may_reframe": ["waiver_or_semantic_change_recorded"],
        "may_waive": ["waiver_recorded"],
    }[class_name]


def infer_allowed_exceptions(statement: str) -> list[str]:
    lowered = statement.lower()
    if not any(marker in lowered or marker in statement for marker in ("except", "exception", "permitted archive", "除外", "例外", "允许保留")):
        return []
    paths = re.findall(r"`([^`]+)`", statement)
    exceptions = [path for path in paths if "/" in path or "*" in path]
    if any(marker in lowered or marker in statement for marker in ("archive", "archived", "归档")):
        exceptions.extend(["archive/**", "**/archive/**", "**/legacy_archive/**"])
    return _dedupe(exceptions)


def validate_objective_contract(contract: ObjectiveContract) -> list[str]:
    errors: list[str] = []
    seen_subjects: dict[tuple[str, str], str] = {}
    for requirement in contract.requirements:
        if not requirement.proof_obligations:
            errors.append(f"{requirement.id} has no proof obligations.")
        if requirement.class_name.startswith("must_absent") and (not requirement.scope or not requirement.subjects):
            errors.append(f"{requirement.id} negative requirement lacks scope or subject seeds.")
        if requirement.class_name == "must_reference" and not requirement.subjects:
            errors.append(f"{requirement.id} reference requirement lacks a named reference subject.")
        for subject in requirement.subjects:
            key = (requirement.domain, subject.lower())
            previous = seen_subjects.get(key)
            if previous and _classes_conflict(previous, requirement.class_name, requirement.domain, subject):
                errors.append(f"{requirement.id} conflicts with another requirement for {requirement.domain}:{subject}.")
            seen_subjects[key] = requirement.class_name
    if not contract.requirements:
        errors.append("No objective requirements were compiled.")
    return errors


def _classes_conflict(left: str, right: str, domain: str, subject: str) -> bool:
    if domain.lower() in {"general", "ui", "frontend", "backend", "source", "code", "id", "tile", "level", "layoutrevision"} and subject.lower() in {
        domain.lower(),
        "ui",
        "prohibited_content",
        "id",
        "tile",
        "level",
        "layoutrevision",
    }:
        return False
    return (left.startswith("must_absent") and right in {"must_implement", "must_preserve"}) or (
        right.startswith("must_absent") and left in {"must_implement", "must_preserve"}
    )


def _has_external_reference_intent(statement: str) -> bool:
    lowered = statement.lower()
    if not any(marker in lowered or marker in statement for marker in REFERENCE_MARKERS):
        return False
    if any(marker in lowered or marker in statement for marker in EXTERNAL_REFERENCE_MARKERS):
        return True
    return False


def _looks_requirement_like(line: str, *, section: str = "") -> bool:
    lowered = line.lower()
    explicit = any(marker in lowered or marker in line for marker in (*MUST_MARKERS, *ABSENT_SOURCE_MARKERS, *VERIFY_MARKERS, *REFERENCE_MARKERS, *PRESERVE_MARKERS))
    if explicit:
        return True
    is_list = bool(re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", line))
    section_lower = section.lower()
    return is_list and any(marker in section_lower or marker in section for marker in (*REQUIREMENT_SECTIONS, *NON_GOAL_SECTIONS))


def _strip_marker(line: str) -> str:
    return re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line).strip()


def _quote_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
