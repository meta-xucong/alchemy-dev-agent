"""Requirement coverage matrix for document-driven delivery reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class RequirementCoverageEntry:
    requirement_id: str
    priority: str
    text: str
    planned_task_ids: list[str] = field(default_factory=list)
    implementation_files: list[str] = field(default_factory=list)
    verification_evidence: list[str] = field(default_factory=list)
    coverage_status: str = "missing"
    gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "requirement_id": self.requirement_id,
            "priority": self.priority,
            "text": self.text,
            "planned_task_ids": list(self.planned_task_ids),
            "implementation_files": list(self.implementation_files),
            "verification_evidence": list(self.verification_evidence),
            "coverage_status": self.coverage_status,
            "gaps": list(self.gaps),
        }


@dataclass(slots=True)
class RequirementCoverageReport:
    status: str
    summary: str
    coverage_score: float
    entries: list[RequirementCoverageEntry] = field(default_factory=list)
    missing_must_requirement_ids: list[str] = field(default_factory=list)
    partial_must_requirement_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "summary": self.summary,
            "coverage_score": self.coverage_score,
            "entries": [entry.to_dict() for entry in self.entries],
            "missing_must_requirement_ids": list(self.missing_must_requirement_ids),
            "partial_must_requirement_ids": list(self.partial_must_requirement_ids),
        }


class RequirementCoverageBuilder:
    """Build a per-requirement coverage report from runtime and artifact evidence."""

    def build(
        self,
        *,
        repository_path: str | Path,
        context_bundle: dict[str, Any],
        task_graph: dict[str, Any],
        runtime_state: dict[str, Any] | None = None,
        artifact_report: dict[str, Any] | None = None,
    ) -> RequirementCoverageReport:
        repo = Path(repository_path)
        requirements = list(context_bundle.get("requirement_map", {}).get("requirements", []))
        nodes = {str(node.get("id", "")): node for node in task_graph.get("nodes", [])}
        runtime_nodes = {
            str(node.get("id", "")): node
            for node in (runtime_state or {}).get("task_graph", {}).get("nodes", [])
        }
        if runtime_nodes:
            nodes.update(runtime_nodes)
        completed = set(str(task_id) for task_id in (runtime_state or {}).get("completed_tasks", []))
        entries: list[RequirementCoverageEntry] = []

        for requirement in requirements:
            entry = self._entry_for_requirement(
                repo=repo,
                requirement=requirement,
                nodes=nodes,
                completed=completed,
                artifact_report=artifact_report or {},
            )
            entries.append(entry)

        missing_must = [entry.requirement_id for entry in entries if entry.priority == "must" and entry.coverage_status == "missing"]
        partial_must = [entry.requirement_id for entry in entries if entry.priority == "must" and entry.coverage_status == "partial"]
        score = _coverage_score(entries)
        status = "passed" if entries and not missing_must and score >= 0.8 else "failed"
        if not entries:
            status = "not_applicable"
        summary = (
            f"{len(entries)} requirements analyzed; score {score:.2f}."
            if entries
            else "No requirements were available for coverage analysis."
        )
        return RequirementCoverageReport(
            status=status,
            summary=summary,
            coverage_score=score,
            entries=entries,
            missing_must_requirement_ids=missing_must,
            partial_must_requirement_ids=partial_must,
        )

    def _entry_for_requirement(
        self,
        *,
        repo: Path,
        requirement: dict[str, Any],
        nodes: dict[str, dict[str, Any]],
        completed: set[str],
        artifact_report: dict[str, Any],
    ) -> RequirementCoverageEntry:
        planned = [str(task_id) for task_id in requirement.get("planned_task_ids", []) if str(task_id)]
        related_files = [str(file) for file in requirement.get("related_files", []) if str(file)]
        task_files = _files_from_tasks(nodes, planned)
        implementation_files = _dedupe([*related_files, *task_files])
        existing_files = [file for file in implementation_files if (repo / file).exists()]
        verification = _verification_evidence(nodes, planned, artifact_report)
        gaps: list[str] = []
        implementation_done = bool(planned) and any(task_id in completed or nodes.get(task_id, {}).get("status") == "completed" for task_id in planned)
        if not planned:
            gaps.append("Requirement has no planned task ids.")
        if implementation_files and not existing_files:
            gaps.append("No implementation files exist for this requirement.")
        if not implementation_files:
            gaps.append("Requirement has no mapped implementation files.")
        if not verification:
            gaps.append("Requirement has no verification evidence.")
        if not implementation_done:
            gaps.append("No planned task is completed for this requirement.")

        if not planned or (implementation_files and not existing_files) or not implementation_done:
            status = "missing"
        elif gaps:
            status = "partial"
        else:
            status = "covered"

        return RequirementCoverageEntry(
            requirement_id=str(requirement.get("id", "")),
            priority=str(requirement.get("priority", "should")),
            text=str(requirement.get("text", "")),
            planned_task_ids=planned,
            implementation_files=implementation_files,
            verification_evidence=verification,
            coverage_status=status,
            gaps=gaps,
        )


def _files_from_tasks(nodes: dict[str, dict[str, Any]], task_ids: list[str]) -> list[str]:
    files: list[str] = []
    for task_id in task_ids:
        node = nodes.get(task_id, {})
        if node.get("type") in {"architecture", "review", "release"}:
            continue
        files.extend(str(file) for file in node.get("relevant_files", []) if str(file))
    return files


def _verification_evidence(nodes: dict[str, dict[str, Any]], task_ids: list[str], artifact_report: dict[str, Any]) -> list[str]:
    evidence: list[str] = []
    for task_id in task_ids:
        node = nodes.get(task_id, {})
        if node.get("status") == "completed":
            evidence.append(f"Task {task_id} completed.")
        for item in node.get("evidence", []):
            summary = item.get("summary") if isinstance(item, dict) else ""
            if summary:
                evidence.append(str(summary))
    static_status = artifact_report.get("static_verification", {}).get("status")
    if static_status:
        evidence.append(f"Static artifact verification: {static_status}.")
    browser_status = artifact_report.get("browser_verification", {}).get("status")
    if browser_status:
        evidence.append(f"Browser artifact verification: {browser_status}.")
    gameplay_status = artifact_report.get("browser_verification", {}).get("gameplay_probe", {}).get("status")
    if gameplay_status:
        evidence.append(f"Gameplay probe: {gameplay_status}.")
    semantic_status = artifact_report.get("browser_verification", {}).get("semantic_probe", {}).get("status")
    if semantic_status and semantic_status != gameplay_status:
        evidence.append(f"Semantic probe: {semantic_status}.")
    return _dedupe(evidence)


def _coverage_score(entries: list[RequirementCoverageEntry]) -> float:
    if not entries:
        return 0.0
    weights = {"must": 2.0, "should": 1.0, "could": 0.5}
    values = {"covered": 1.0, "partial": 0.5, "missing": 0.0}
    total_weight = sum(weights.get(entry.priority, 1.0) for entry in entries)
    if not total_weight:
        return 0.0
    score = sum(weights.get(entry.priority, 1.0) * values.get(entry.coverage_status, 0.0) for entry in entries)
    return round(score / total_weight, 4)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value).strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result
