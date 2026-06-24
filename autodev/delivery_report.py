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
    native_ui_tests: dict[str, Any] | None = None,
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
    scenario_probe = browser.get("scenario_probe", {}) if isinstance(browser, dict) else {}
    scenario_plan = artifact_report.get("acceptance_scenarios", {})
    native_tests = native_ui_tests or artifact_report.get("native_ui_tests", {})
    coverage_entries = requirement_coverage.get("entries", [])
    readiness_issues = delivery_readiness_issues(
        status=status,
        evaluation=evaluation if isinstance(evaluation, dict) else {},
        blockers=blockers if isinstance(blockers, list) else [],
        artifact_report=artifact_report,
        requirement_coverage=requirement_coverage,
        generated_ci=generated_ci,
        ci_status=str(github.get("ci_status", "")),
    )
    report = {
        "status": status,
        "ready_for_review": not readiness_issues,
        "summary": summary_for(status, evaluation, blockers, readiness_issues),
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
            "scenario_status": scenario_probe.get("status", "") if isinstance(scenario_probe, dict) else "",
            "scenario_probe": dict(scenario_probe) if isinstance(scenario_probe, dict) else {},
            "acceptance_scenarios": dict(scenario_plan) if isinstance(scenario_plan, dict) else {},
            "native_ui_tests": dict(native_tests) if isinstance(native_tests, dict) else {},
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
        "readiness_issues": readiness_issues,
        "worker_lifecycle": list(runtime_state.get("worker_lifecycle", [])),
        "workspace": dict(workspace or {}),
        "preflight": dict(preflight or {}),
        "next_actions": next_actions(
            status,
            blockers,
            requirement_coverage,
            generated_ci,
            str(github.get("ci_status", "")),
            readiness_issues,
        ),
    }
    return report


def delivery_readiness_issues(
    *,
    status: str,
    evaluation: dict[str, Any],
    blockers: list[dict[str, Any]],
    artifact_report: dict[str, Any],
    requirement_coverage: dict[str, Any],
    generated_ci: dict[str, Any],
    ci_status: str,
) -> list[str]:
    issues: list[str] = []
    if status != "done" or not evaluation.get("done", False):
        issues.append(str(evaluation.get("reason", "Final gate did not reach DONE.")))
    for failure in evaluation.get("hard_failures", []):
        _append_unique(issues, str(failure))
    for blocker in blockers:
        if isinstance(blocker, dict):
            _append_unique(issues, str(blocker.get("description", blocker.get("message", "Unresolved blocker exists."))))
        else:
            _append_unique(issues, str(blocker))
    if requirement_coverage.get("status") not in {"passed", ""}:
        _append_unique(issues, "Requirement coverage did not pass.")
    missing_must = [str(item) for item in requirement_coverage.get("missing_must_requirement_ids", [])]
    partial_must = [str(item) for item in requirement_coverage.get("partial_must_requirement_ids", [])]
    if missing_must:
        _append_unique(issues, "Must requirements are missing coverage: " + ", ".join(missing_must) + ".")
    if partial_must:
        _append_unique(issues, "Must requirements have only partial coverage: " + ", ".join(partial_must) + ".")
    for failure in artifact_readiness_issues(artifact_report):
        _append_unique(issues, failure)
    if generated_ci.get("status") == "generated" and ci_status not in {"passed", "waived"}:
        _append_unique(issues, "Generated GitHub Actions checks have not passed.")
    return issues


def artifact_readiness_issues(artifact_report: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    static = artifact_report.get("static_verification", {})
    browser = artifact_report.get("browser_verification", {})
    profile = artifact_report.get("artifact_profile", {})
    profile_name = str(profile.get("name", "")) if isinstance(profile, dict) else ""
    if profile_name in {"canvas_game", "static_web_app"} and isinstance(static, dict) and static.get("status") == "failed":
        issues.append("Static artifact verification failed.")
    if not isinstance(browser, dict) or not browser:
        return issues
    if browser.get("status") == "failed":
        issues.append("Browser artifact verification failed.")
    semantic = browser.get("semantic_probe", {})
    if isinstance(semantic, dict) and semantic.get("status") == "failed":
        issues.append("Semantic browser probe failed.")
    scenario = browser.get("scenario_probe", {})
    if isinstance(scenario, dict) and scenario.get("status") == "failed":
        issues.append("Acceptance scenario browser probe failed.")
    gameplay = browser.get("gameplay_probe", {})
    gameplay_status = str(gameplay.get("status", "")) if isinstance(gameplay, dict) else ""
    if profile_name == "canvas_game" and gameplay_status != "completed":
        issues.append("Canvas gameplay probe did not complete.")
    elif gameplay_status == "failed":
        issues.append("Gameplay browser probe failed.")
    return issues


def summary_for(
    status: str,
    evaluation: dict[str, Any],
    blockers: list[dict[str, Any]],
    readiness_issues: list[str] | None = None,
) -> str:
    readiness_issues = readiness_issues or []
    if status == "done" and not readiness_issues:
        return evaluation.get("reason", "Delivery is complete and ready for review.")
    if readiness_issues:
        return readiness_issues[0]
    if blockers:
        return str(blockers[0].get("description", "Delivery is blocked."))
    return evaluation.get("reason", "Delivery is not complete yet.")


def next_actions(
    status: str,
    blockers: list[dict[str, Any]],
    requirement_coverage: dict[str, Any],
    generated_ci: dict[str, Any],
    ci_status: str = "",
    readiness_issues: list[str] | None = None,
) -> list[str]:
    actions: list[str] = []
    readiness_issues = readiness_issues or []
    if blockers:
        actions.append("Resolve blockers and resume the run.")
    if requirement_coverage.get("missing_must_requirement_ids"):
        actions.append("Implement missing must requirements before delivery.")
    if requirement_coverage.get("partial_must_requirement_ids"):
        actions.append("Improve partial must requirement coverage before delivery.")
    for issue in readiness_issues:
        if issue and issue not in actions:
            actions.append(issue)
    if generated_ci.get("status") == "generated" and ci_status not in {"passed", "waived"}:
        actions.append("Wait for generated GitHub Actions checks to pass on the PR.")
    if status == "done" and not actions:
        actions.append("Review the PR, evidence, and generated artifact.")
    return actions


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)
