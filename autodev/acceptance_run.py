"""Local acceptance harness for the document-driven autonomous runtime."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from server import ProjectService


@dataclass(slots=True)
class AcceptanceResult:
    status: str
    checks: list[dict[str, object]] = field(default_factory=list)
    project: dict[str, object] = field(default_factory=dict)
    run: dict[str, object] = field(default_factory=dict)
    delivery: dict[str, object] = field(default_factory=dict)
    output_dir: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "checks": list(self.checks),
            "project": dict(self.project),
            "run": dict(self.run),
            "delivery": dict(self.delivery),
            "output_dir": self.output_dir,
        }


class AcceptanceHarness:
    """Exercise the current local product path end to end."""

    def run(self, *, output_dir: str | Path = ".alchemy/acceptance", keep: bool = False) -> AcceptanceResult:
        output = Path(output_dir)
        if output.exists() and not keep:
            shutil.rmtree(output)
        output.mkdir(parents=True, exist_ok=True)
        repo = output / "repo"
        spec = output / "workspace_feature_spec.md"
        api = output / "api_contract.yaml"
        write_fixture_repo(repo)
        write_spec(spec)
        write_api_contract(api)

        service = ProjectService(storage_root=output / "server")
        created = service.create_project(
            {
                "objective": "Add workspace support",
                "documents": [str(spec)],
                "attachments": [str(api)],
                "repository": "https://github.com/example/saas-dashboard",
                "repository_path": str(repo),
            }
        )
        project_id = str(created["project"]["project_id"])
        plan = service.build_plan(project_id)
        started = service.start_run(project_id, {})
        run_id = str(started["run_id"])
        job = wait_for_job(service, project_id, run_id)
        run = service.get_run(project_id, run_id)
        events = service.get_run_events(project_id, run_id)
        delivery = service.get_delivery(project_id)

        checks = [
            check("project_created", bool(project_id), project_id),
            check("intake_ready", created["project"]["status"] == "intake_ready", created["project"]["status"]),
            check("task_graph_generated", len(plan["task_graph"]["nodes"]) >= 5, len(plan["task_graph"]["nodes"])),
            check("async_job_done", job["status"] == "done", job["status"]),
            check("run_done", run["status"] == "done", run["status"]),
            check("events_recorded", len(events["events"]) > 0, len(events["events"])),
            check("delivery_done", delivery["status"] == "done", delivery["status"]),
            check("final_gate_passed", run["runtime_state"]["done"] is True, run["runtime_state"]["evaluation"]["reason"]),
        ]
        status = "passed" if all(item["passed"] for item in checks) else "failed"
        result = AcceptanceResult(
            status=status,
            checks=checks,
            project=service.get_project(project_id),
            run=run,
            delivery=delivery,
            output_dir=str(output),
        )
        (output / "acceptance_report.json").write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result


def check(name: str, passed: bool, detail: object) -> dict[str, object]:
    return {
        "name": name,
        "passed": passed,
        "detail": detail,
    }


def wait_for_job(service: ProjectService, project_id: str, run_id: str, timeout_seconds: float = 10.0) -> dict[str, object]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        job = service.get_run_job(project_id, run_id)
        if job["status"] not in {"queued", "running", "paused"}:
            return job
        time.sleep(0.05)
    raise TimeoutError(f"Timed out waiting for run {run_id}")


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
                "# Workspace Feature",
                "## Requirements",
                "- Must add workspace API support in src/api/workspaces.ts.",
                "- Must add dashboard workspace switching in src/pages/dashboard.tsx.",
                "## Acceptance Criteria",
                "- Users can create a workspace.",
                "- Users can switch active workspace.",
            ]
        ),
        encoding="utf-8",
    )


def write_api_contract(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "openapi: 3.0.0",
                "info:",
                "  title: Workspace API",
                "paths:",
                "  /workspaces:",
                "    post:",
                "      summary: Create workspace",
            ]
        ),
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run local Alchemy acceptance checks.")
    parser.add_argument("--output", default=".alchemy/acceptance")
    parser.add_argument("--keep", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = AcceptanceHarness().run(output_dir=args.output, keep=args.keep)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
