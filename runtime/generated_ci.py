"""Generate lightweight CI workflows for docs-only static web artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class GeneratedCIResult:
    status: str
    workflow_path: str = ""
    summary: str = ""
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "workflow_path": self.workflow_path,
            "summary": self.summary,
            "evidence": list(self.evidence),
        }


class StaticWebCIGenerator:
    """Create a minimal GitHub Actions workflow when a static web repo has none."""

    workflow_path = ".github/workflows/alchemy-static-checks.yml"

    def generate_if_needed(
        self,
        repository_path: str | Path,
        *,
        artifact_profile: str,
        collect_ci: bool,
        explicit_no_ci: bool = False,
    ) -> GeneratedCIResult:
        repo = Path(repository_path)
        if explicit_no_ci or not collect_ci:
            return GeneratedCIResult(
                status="skipped",
                summary="CI generation skipped because CI collection is disabled.",
            )
        if artifact_profile not in {"canvas_game", "static_web_app"}:
            return GeneratedCIResult(
                status="skipped",
                summary=f"CI generation skipped for artifact profile {artifact_profile}.",
            )
        existing = list((repo / ".github" / "workflows").glob("*.yml")) + list((repo / ".github" / "workflows").glob("*.yaml"))
        if existing:
            return GeneratedCIResult(
                status="skipped",
                summary="Existing GitHub Actions workflow detected.",
                evidence=[str(path.relative_to(repo)).replace("\\", "/") for path in existing],
            )
        if not (repo / "index.html").exists():
            return GeneratedCIResult(
                status="skipped",
                summary="Static web CI generation skipped because index.html is missing.",
            )

        target = repo / self.workflow_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(static_web_workflow_text(), encoding="utf-8")
        return GeneratedCIResult(
            status="generated",
            workflow_path=self.workflow_path,
            summary="Generated lightweight static web artifact CI workflow.",
            evidence=[self.workflow_path],
        )


def static_web_workflow_text() -> str:
    return """name: Alchemy Static Checks

on:
  pull_request:
  push:
    branches:
      - main
      - master

jobs:
  static-web:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Run static artifact checks
        run: |
          if [ -f tests/static_checks.js ]; then
            node tests/static_checks.js
          else
            node -e "const fs=require('fs'); if(!fs.existsSync('index.html')) { throw new Error('index.html missing'); } const html=fs.readFileSync('index.html','utf8'); if(!/<canvas|<main|id=['\\\"]app['\\\"]/.test(html)) { throw new Error('No browser artifact root detected'); }"
          fi
"""
