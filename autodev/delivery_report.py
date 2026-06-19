"""Build reviewer-friendly delivery report summaries."""

from __future__ import annotations

from typing import Any


def build_delivery_report(
    *,
    status: str,
    runtime_state: dict[str, Any],
    artifact_report: dict[str, Any],
    requirement_coverage: dict[str, Any],
    generated_ci: dict[str, Any],
    workspace: dict[str, Any] | None = None,
    preflight: dict[str, Any] | None = None,
) -> dict[str, object]:
    evaluation = runtime_state.get("evaluation", runtime_state.get("evaluation_result", {}))
    github = runtime_state.get("github", {})
    blockers = runtime_state.get("blockers", [])
    browser = artifact_report.get("browser_verification", {})
    static = artifact_report.get("static_verification", {})
    profile = artifact_report.get("artifact_profile", {})
    gameplay_probe = browser.get("gameplay_probe", {}) if isinstance(browser, dict) else {}
    semantic_probe = browser.get("semantic_probe", {}) if isinstance(browser, dict) else {}
    coverage_entries = requirement_coverage.get("entries", [])
    report = {
        "status": status,
        "ready_for_review": status == "done" and not blockers,
        "summary": summary_for(status, evaluation, blockers),
        "final_gate": {
            "score": evaluation.get("final_gate_score", evaluation.get("final_score", 0)),
            "reason": evaluation.get("reason", ""),
            "hard_failures": list(evaluation.get("hard_failures", [])),
            "required_changes": list(evaluation.get("required_changes", [])),
        },
        "github": {
            "pull_request_url": github.get("pull_request_url", ""),
            "branch": github.get("branch", ""),
            "commit": github.get("commit", ""),
            "ci_status": github.get("ci_status", ""),
            "ci_details": list(github.get("ci_details", [])),
            "merge": dict(github.get("merge", {})),
        },
        "artifact": {
            "profile": profile.get("name", "unknown"),
            "static_status": static.get("status", ""),
            "browser_status": browser.get("status", ""),
            "semantic_status": semantic_probe.get("status", "") if isinstance(semantic_probe, dict) else "",
            "semantic_probe": dict(semantic_probe) if isinstance(semantic_probe, dict) else {},
            "gameplay_status": gameplay_probe.get("status", "") if isinstance(gameplay_probe, dict) else "",
            "gameplay_probe": dict(gameplay_probe) if isinstance(gameplay_probe, dict) else {},
            "screenshots": browser.get("screenshots", {}),
            "pixel_diff": browser.get("pixel_diff", {}),
            "artifact_files": list(artifact_report.get("artifact_files", [])),
        },
        "requirements": {
            "status": requirement_coverage.get("status", ""),
            "coverage_score": requirement_coverage.get("coverage_score", 0),
            "total": len(coverage_entries),
            "missing_must_requirement_ids": list(requirement_coverage.get("missing_must_requirement_ids", [])),
            "partial_must_requirement_ids": list(requirement_coverage.get("partial_must_requirement_ids", [])),
        },
        "generated_ci": dict(generated_ci),
        "blockers": list(blockers),
        "worker_lifecycle": list(runtime_state.get("worker_lifecycle", [])),
        "workspace": dict(workspace or {}),
        "preflight": dict(preflight or {}),
        "next_actions": next_actions(
            status,
            blockers,
            requirement_coverage,
            generated_ci,
            str(github.get("ci_status", "")),
        ),
    }
    return report


def summary_for(status: str, evaluation: dict[str, Any], blockers: list[dict[str, Any]]) -> str:
    if status == "done":
        return evaluation.get("reason", "Delivery is complete and ready for review.")
    if blockers:
        return str(blockers[0].get("description", "Delivery is blocked."))
    return evaluation.get("reason", "Delivery is not complete yet.")


def next_actions(
    status: str,
    blockers: list[dict[str, Any]],
    requirement_coverage: dict[str, Any],
    generated_ci: dict[str, Any],
    ci_status: str = "",
) -> list[str]:
    actions: list[str] = []
    if blockers:
        actions.append("Resolve blockers and resume the run.")
    if requirement_coverage.get("missing_must_requirement_ids"):
        actions.append("Implement missing must requirements before delivery.")
    if generated_ci.get("status") == "generated" and ci_status not in {"passed", "waived"}:
        actions.append("Wait for generated GitHub Actions checks to pass on the PR.")
    if status == "done" and not actions:
        actions.append("Review the PR, evidence, and generated artifact.")
    return actions
