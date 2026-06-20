"""Unified entrypoint acceptance harness."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from server import ProjectService


@dataclass(slots=True)
class UnifiedScenarioResult:
    name: str
    status: str
    checks: list[dict[str, object]] = field(default_factory=list)
    preflight: dict[str, object] = field(default_factory=dict)
    run: dict[str, object] = field(default_factory=dict)
    delivery: dict[str, object] = field(default_factory=dict)
    artifacts: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "checks": list(self.checks),
            "preflight": dict(self.preflight),
            "run": dict(self.run),
            "delivery": dict(self.delivery),
            "artifacts": dict(self.artifacts),
        }


@dataclass(slots=True)
class UnifiedAcceptanceResult:
    status: str
    scenarios: list[UnifiedScenarioResult] = field(default_factory=list)
    output_dir: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "scenarios": [scenario.to_dict() for scenario in self.scenarios],
            "output_dir": self.output_dir,
        }


class UnifiedAcceptanceHarness:
    """Exercise unified request preflight, start, and evidence retrieval."""

    def run(self, *, output_dir: str | Path = ".alchemy/unified_acceptance", keep: bool = False) -> UnifiedAcceptanceResult:
        output = Path(output_dir)
        if output.exists() and not keep:
            shutil.rmtree(output)
        output.mkdir(parents=True, exist_ok=True)

        service = ProjectService(storage_root=output / "server")
        fixtures = write_fixtures(output / "fixtures")
        scenarios = [
            self._run_one_line(service, output),
            self._run_document_only(service, output, fixtures["spec"]),
            self._run_local_repository(service, output, fixtures["spec"], fixtures["repo"]),
            self._run_github_url_dry_run(service, output, fixtures["spec"]),
        ]
        status = "passed" if all(scenario.status == "passed" for scenario in scenarios) else "failed"
        result = UnifiedAcceptanceResult(status=status, scenarios=scenarios, output_dir=str(output))
        (output / "unified_acceptance_report.json").write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return result

    def _run_one_line(self, service: ProjectService, output: Path) -> UnifiedScenarioResult:
        payload = {
            "objective": "Build a small retro platform game",
            "async": False,
        }
        preflight = service.preflight_unified_request(payload)
        run = service.run_unified_request(payload)
        project_id = str(run.get("project_id", ""))
        run_id = str(run.get("run_id", ""))
        artifacts = service.get_run_artifacts(project_id, run_id)
        checks = [
            check("preflight_passed", preflight.get("status") == "passed", preflight.get("status", "")),
            check("route_one_line", run.get("route") == "one_line_fallback", run.get("route", "")),
            check("run_done", run.get("status") == "done", run.get("status", "")),
            check("artifact_generated", has_artifact_path(artifacts, "index.html"), artifacts.get("items", [])),
        ]
        return scenario("one_line_fallback", checks, preflight=preflight, run=run, artifacts=artifacts)

    def _run_document_only(self, service: ProjectService, output: Path, spec: Path) -> UnifiedScenarioResult:
        payload = {
            "objective": "Build from the primary development document",
            "documents": [str(spec)],
            "output_dir": str(output / "document_only_run"),
            "async": False,
        }
        preflight = service.preflight_unified_request(payload)
        run = service.run_unified_request(payload)
        project_id = str(run.get("project_id", ""))
        delivery = service.get_delivery(project_id)
        artifacts = service.get_run_artifacts(project_id, str(run.get("run_id", "")))
        generated_repo = Path(str(run.get("run", {}).get("output_dir", ""))) / "generated_repository" if isinstance(run.get("run"), dict) else Path("")
        checks = [
            check("preflight_passed", preflight.get("status") == "passed", preflight.get("status", "")),
            check("planned_generated_repository", str(preflight.get("planned_repository_path", "")).endswith("generated_repository"), preflight.get("planned_repository_path", "")),
            check("route_document_run", run.get("route") == "document_run", run.get("route", "")),
            check("run_done", run.get("status") == "done", run.get("status", "")),
            check("generated_repository_exists", generated_repo.exists() and any(generated_repo.iterdir()), str(generated_repo)),
            check("delivery_ready", bool(delivery.get("delivery_report", {}).get("ready_for_review")), delivery.get("delivery_report", {})),
            check("artifacts_available", len(artifacts.get("items", [])) > 0, len(artifacts.get("items", []))),
        ]
        return scenario("document_only_generated_repository", checks, preflight=preflight, run=run, delivery=delivery, artifacts=artifacts)

    def _run_local_repository(self, service: ProjectService, output: Path, spec: Path, repo: Path) -> UnifiedScenarioResult:
        payload = {
            "objective": "Deliver the local repository package",
            "documents": [str(spec)],
            "repository_path": str(repo),
            "output_dir": str(output / "local_repo_run"),
            "async": True,
        }
        preflight = service.preflight_unified_request(payload)
        started = service.run_unified_request(payload)
        project_id = str(started.get("project_id", ""))
        run_id = str(started.get("run_id", ""))
        job = wait_for_job(service, project_id, run_id)
        run = service.get_run(project_id, run_id)
        events = service.get_run_events(project_id, run_id)
        delivery = service.get_delivery(project_id)
        artifacts = service.get_run_artifacts(project_id, run_id)
        checks = [
            check("preflight_passed", preflight.get("status") == "passed", preflight.get("status", "")),
            check("source_local", started.get("source_mode") == "local", started.get("source_mode", "")),
            check("async_started", started.get("async") is True, started.get("async", "")),
            check("job_done", job.get("status") == "done", job.get("status", "")),
            check("run_done", run.get("status") == "done", run.get("status", "")),
            check("events_recorded", len(events.get("events", [])) > 0, len(events.get("events", []))),
            check("delivery_done", delivery.get("status") == "done", delivery.get("status", "")),
            check("delivery_ready", bool(delivery.get("delivery_report", {}).get("ready_for_review")), delivery.get("delivery_report", {})),
        ]
        return scenario("local_repository_package", checks, preflight=preflight, run=run, delivery=delivery, artifacts=artifacts)

    def _run_github_url_dry_run(self, service: ProjectService, output: Path, spec: Path) -> UnifiedScenarioResult:
        payload = {
            "objective": "Inspect public GitHub source metadata in dry-run mode",
            "documents": [str(spec)],
            "repository_url": "https://github.com/example/saas-dashboard",
            "repository_visibility": "public",
            "source_mode": "github_public",
            "output_dir": str(output / "github_url_run"),
            "async": False,
        }
        preflight = service.preflight_unified_request(payload)
        warnings = preflight.get("warnings", [])
        created = service.create_project(
            {
                "objective": payload["objective"],
                "documents": payload["documents"],
                "repository_url": payload["repository_url"],
                "repository_visibility": payload["repository_visibility"],
            }
        )
        repository = created.get("brief", {}).get("repository", {}) if isinstance(created.get("brief"), dict) else {}
        project = created.get("project", {}) if isinstance(created.get("project"), dict) else {}
        checks = [
            check("preflight_passed", preflight.get("status") == "passed", preflight.get("status", "")),
            check("unprepared_github_warning", has_issue(warnings, "github_source_not_prepared"), warnings),
            check("project_created", bool(project.get("project_id")), project),
            check("repository_metadata_recorded", repository.get("provider") == "github", repository),
            check("no_remote_mutation_required", preflight.get("delivery_mode") == "report_only", preflight.get("delivery_mode", "")),
        ]
        return scenario("github_url_dry_run_metadata", checks, preflight=preflight, run={"project": project, "brief": created.get("brief", {})})


def scenario(
    name: str,
    checks: list[dict[str, object]],
    *,
    preflight: dict[str, object],
    run: dict[str, object],
    delivery: dict[str, object] | None = None,
    artifacts: dict[str, object] | None = None,
) -> UnifiedScenarioResult:
    status = "passed" if all(item["passed"] for item in checks) else "failed"
    return UnifiedScenarioResult(
        name=name,
        status=status,
        checks=checks,
        preflight=preflight,
        run=run,
        delivery=delivery or {},
        artifacts=artifacts or {},
    )


def check(name: str, passed: bool, detail: object) -> dict[str, object]:
    return {
        "name": name,
        "passed": passed,
        "detail": detail,
    }


def has_issue(issues: object, code: str) -> bool:
    return any(isinstance(item, dict) and item.get("code") == code for item in issues if isinstance(issues, list))


def has_artifact_path(manifest: dict[str, object], filename: str) -> bool:
    items = manifest.get("items", [])
    return any(isinstance(item, dict) and str(item.get("path", "")).replace("\\", "/").endswith(filename) for item in items if isinstance(items, list))


def wait_for_job(service: ProjectService, project_id: str, run_id: str, timeout_seconds: float = 15.0) -> dict[str, object]:
    deadline = time.time() + timeout_seconds
    last: dict[str, object] = {}
    while time.time() < deadline:
        last = service.get_run_job(project_id, run_id)
        if str(last.get("status", "")) not in {"queued", "running", "paused"}:
            return last
        time.sleep(0.05)
    raise TimeoutError(f"Timed out waiting for unified acceptance run {run_id}; last={last}")


def write_fixtures(root: Path) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    repo = root / "local-repo"
    spec = root / "development_spec.md"
    write_fixture_repo(repo)
    write_spec(spec)
    return {"repo": repo, "spec": spec}


def write_fixture_repo(root: Path) -> None:
    (root / "src" / "api").mkdir(parents=True)
    (root / "src" / "pages").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "api" / "workspaces.ts").write_text("export const api = true;\n", encoding="utf-8")
    (root / "src" / "pages" / "dashboard.tsx").write_text("export const ui = true;\n", encoding="utf-8")
    (root / "tests" / "workspaces.test.ts").write_text("test('workspace', () => {});\n", encoding="utf-8")
    (root / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")


def write_spec(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# Unified Acceptance Development Spec",
                "",
                "## Objective",
                "Add workspace support.",
                "",
                "## Requirements",
                "- Must add workspace API support in src/api/workspaces.ts.",
                "- Must add dashboard workspace switching in src/pages/dashboard.tsx.",
                "- Must keep the app reviewable through delivery evidence.",
                "",
                "## Acceptance Criteria",
                "- Users can create a workspace.",
                "- Users can switch active workspace.",
                "- Delivery evidence includes artifacts or generated repository files.",
            ]
        ),
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run unified entrypoint acceptance checks.")
    parser.add_argument("--output", default=".alchemy/unified_acceptance")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--summary", action="store_true", help="Print a compact scenario summary instead of the full report.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = UnifiedAcceptanceHarness().run(output_dir=args.output, keep=args.keep)
    payload = result.to_dict()
    if args.summary:
        payload = {
            "status": payload["status"],
            "output_dir": payload["output_dir"],
            "scenarios": [
                {
                    "name": scenario["name"],
                    "status": scenario["status"],
                    "failed_checks": [
                        check["name"]
                        for check in scenario.get("checks", [])
                        if isinstance(check, dict) and not check.get("passed", False)
                    ],
                }
                for scenario in payload["scenarios"]
                if isinstance(scenario, dict)
            ],
        }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if result.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
