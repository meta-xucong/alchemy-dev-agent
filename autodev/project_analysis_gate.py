"""Pre-development project analysis gate for autonomous runs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from .roadmap_extractor import (
    clean_title,
    document_priority,
    phase_title_from_line,
    phase_version_key,
    read_text,
    strip_list_marker,
)
from .roadmap_models import RoadmapExecutionPlan, RoadmapPhase


START_CONFIDENCE_THRESHOLD = 0.75
MAX_DEFAULT_PHASES = 20


@dataclass(slots=True)
class PhaseCandidate:
    text: str
    reason: str
    source_reference: str

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "reason": self.reason,
            "source_reference": self.source_reference,
        }


@dataclass(slots=True)
class ProjectAnalysisReport:
    root_objective: str
    completion_scope: str
    start_decision: str
    confidence: float
    valid_phases: list[dict[str, object]] = field(default_factory=list)
    ignored_phase_candidates: list[PhaseCandidate] = field(default_factory=list)
    duplicate_phase_candidates: list[PhaseCandidate] = field(default_factory=list)
    global_constraints: list[str] = field(default_factory=list)
    phase_local_constraints: list[str] = field(default_factory=list)
    external_blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    required_human_actions: list[str] = field(default_factory=list)
    ready_to_start: bool = False
    schema_version: str = "project_analysis_report_v1"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "root_objective": self.root_objective,
            "completion_scope": self.completion_scope,
            "start_decision": self.start_decision,
            "confidence": self.confidence,
            "valid_phases": list(self.valid_phases),
            "ignored_phase_candidates": [candidate.to_dict() for candidate in self.ignored_phase_candidates],
            "duplicate_phase_candidates": [candidate.to_dict() for candidate in self.duplicate_phase_candidates],
            "global_constraints": list(self.global_constraints),
            "phase_local_constraints": list(self.phase_local_constraints),
            "external_blockers": list(self.external_blockers),
            "warnings": list(self.warnings),
            "required_human_actions": list(self.required_human_actions),
            "ready_to_start": self.ready_to_start,
            "created_at": self.created_at,
        }


class ProjectAnalysisGate:
    """Decide whether a roadmap is safe enough for Codex workers to start."""

    def analyze(
        self,
        *,
        plan: RoadmapExecutionPlan,
        documents: Sequence[str | Path] = (),
        attachments: Sequence[str | Path] = (),
        max_default_phases: int = MAX_DEFAULT_PHASES,
    ) -> ProjectAnalysisReport:
        texts = readable_sources([*documents, *attachments])
        ignored, duplicates = scan_phase_candidates(texts, plan.phases)
        warnings: list[str] = []
        required_actions: list[str] = []
        if not plan.phases:
            required_actions.append("Provide at least one implementable development phase or a clearer objective.")
        if len(plan.phases) > max_default_phases:
            warnings.append(
                f"Roadmap contains {len(plan.phases)} phases, above the default safe limit of {max_default_phases}."
            )
            required_actions.append("Review source documents or narrow the roadmap before starting workers.")
        if plan.confidence < START_CONFIDENCE_THRESHOLD:
            warnings.append(
                f"Roadmap confidence {plan.confidence:.2f} is below start threshold {START_CONFIDENCE_THRESHOLD:.2f}."
            )
            required_actions.append("Add clearer development documents, acceptance criteria, or phase structure.")
        if plan.external_blockers:
            required_actions.append("Resolve external blockers before starting development.")
        if pseudo_phase_ratio(ignored, plan.phases) >= 1.5 and len(ignored) >= 6:
            warnings.append("Many phase-like headings were ignored; source documents may contain noisy prompt text.")
        start_decision = "start"
        if plan.external_blockers:
            start_decision = "blocked"
        elif required_actions:
            start_decision = "repair_roadmap"
        ready = start_decision == "start"
        return ProjectAnalysisReport(
            root_objective=plan.root_objective,
            completion_scope="full_roadmap" if plan.completion_policy == "full_roadmap" else "unknown",
            start_decision=start_decision,
            confidence=plan.confidence,
            valid_phases=[phase_summary(phase) for phase in plan.phases],
            ignored_phase_candidates=ignored,
            duplicate_phase_candidates=duplicates,
            global_constraints=list(plan.global_constraints),
            phase_local_constraints=dedupe(
                constraint
                for phase in plan.phases
                for constraint in phase.phase_local_constraints
            ),
            external_blockers=list(plan.external_blockers),
            warnings=warnings,
            required_human_actions=dedupe(required_actions),
            ready_to_start=ready,
        )


def readable_sources(paths: Sequence[str | Path]) -> list[tuple[Path, str]]:
    sources: list[tuple[Path, str]] = []
    for value in paths:
        path = Path(value)
        text = read_text(path)
        if text:
            sources.append((path, text))
    return sorted(sources, key=lambda item: document_priority(item[0]))


def scan_phase_candidates(
    sources: list[tuple[Path, str]],
    phases: Sequence[RoadmapPhase],
) -> tuple[list[PhaseCandidate], list[PhaseCandidate]]:
    ignored: list[PhaseCandidate] = []
    duplicates: list[PhaseCandidate] = []
    kept_versions = {phase_version_key(phase.title) for phase in phases if phase_version_key(phase.title)}
    seen_versions: set[str] = set()
    kept_titles = {clean_title(phase.title).lower() for phase in phases}
    for path, text in sources:
        for index, raw in enumerate(text.splitlines(), start=1):
            candidate_text = clean_candidate_text(raw)
            if not candidate_text:
                continue
            parsed = phase_title_from_line(raw)
            version = phase_version_key(parsed or candidate_text)
            source = f"{path}:{index}"
            if parsed:
                normalized = clean_title(parsed).lower()
                if version and version in seen_versions:
                    duplicates.append(PhaseCandidate(text=parsed, reason="duplicate_phase_version", source_reference=source))
                elif normalized in kept_titles:
                    seen_versions.add(version)
                elif version and version in kept_versions:
                    duplicates.append(PhaseCandidate(text=parsed, reason="duplicate_phase_version", source_reference=source))
                continue
            if looks_like_phase_candidate(candidate_text):
                ignored.append(
                    PhaseCandidate(
                        text=candidate_text,
                        reason=ignored_candidate_reason(candidate_text),
                        source_reference=source,
                    )
                )
    return dedupe_candidates(ignored), dedupe_candidates(duplicates)


def clean_candidate_text(line: str) -> str:
    value = strip_list_marker(line.strip().strip("` "))
    if not value or len(value) > 180:
        return ""
    return clean_title(value)


def looks_like_phase_candidate(text: str) -> bool:
    lower = text.lower()
    return lower.startswith(("v1", "v2", "v3", "v4", "v5", "phase ", "milestone ", "阶段", "里程碑"))


def ignored_candidate_reason(text: str) -> str:
    lower = text.lower()
    if "acceptance criteria" in lower:
        return "section_label_acceptance_criteria"
    if "out of scope" in lower:
        return "section_label_out_of_scope"
    if any(token in lower for token in ("must", "must not", "do not", "should", "can ", "may use", "keeps")):
        return "constraint_or_policy_sentence"
    if "concept" in lower:
        return "concept_reference"
    return "not_a_development_phase"


def phase_summary(phase: RoadmapPhase) -> dict[str, object]:
    return {
        "phase_id": phase.phase_id,
        "title": phase.title,
        "phase_type": phase.phase_type,
        "source_references": list(phase.source_references),
    }


def pseudo_phase_ratio(ignored: Sequence[PhaseCandidate], phases: Sequence[RoadmapPhase]) -> float:
    denominator = max(1, len(phases))
    return len(ignored) / denominator


def dedupe_candidates(candidates: Iterable[PhaseCandidate]) -> list[PhaseCandidate]:
    result: list[PhaseCandidate] = []
    seen: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        key = (candidate.text, candidate.reason, candidate.source_reference)
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value).strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def write_project_analysis_report(path: str | Path, report: ProjectAnalysisReport) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target

