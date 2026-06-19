"""Generate repository-native UI acceptance test drafts from scenario plans."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


NativeUITestFramework = Literal["playwright", "cypress", "none"]
NativeUITestStatus = Literal["generated", "skipped"]
NativeUITestWriteMode = Literal["report_only", "repository"]


@dataclass(slots=True)
class NativeUITestGeneration:
    status: NativeUITestStatus
    framework: NativeUITestFramework
    target_path: str = ""
    write_mode: NativeUITestWriteMode = "report_only"
    summary: str = ""
    files: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "framework": self.framework,
            "target_path": self.target_path,
            "write_mode": self.write_mode,
            "summary": self.summary,
            "files": list(self.files),
            "evidence": list(self.evidence),
        }


class NativeUITestGenerator:
    """Create Playwright or Cypress acceptance test drafts from browser scenarios."""

    def generate(
        self,
        *,
        repository_path: str | Path,
        output_dir: str | Path,
        acceptance_scenarios: dict[str, Any],
        artifact_profile: str = "unknown",
        write_to_repository: bool = False,
    ) -> NativeUITestGeneration:
        scenarios = _scenario_list(acceptance_scenarios.get("scenarios", []))
        if not scenarios:
            return NativeUITestGeneration(
                status="skipped",
                framework="none",
                summary="No generated acceptance scenarios were available for native UI tests.",
            )

        repo = Path(repository_path)
        output = Path(output_dir)
        framework, evidence = detect_ui_test_framework(repo)
        if framework == "none" and _is_static_browser_profile(repo, artifact_profile):
            framework = "playwright"
            evidence.append("No native UI framework detected; generated Playwright draft in report-only mode for static browser artifact.")
        if framework == "none":
            return NativeUITestGeneration(
                status="skipped",
                framework="none",
                summary="No supported native UI test framework or static browser artifact was detected.",
                evidence=evidence,
            )

        write_mode: NativeUITestWriteMode = "repository" if write_to_repository and framework != "none" else "report_only"
        if framework == "playwright":
            relative = "tests/alchemy_acceptance.spec.ts" if write_mode == "repository" else "generated_tests/playwright/alchemy_acceptance.spec.ts"
            content = playwright_test_text(scenarios)
        else:
            relative = "cypress/e2e/alchemy_acceptance.cy.js" if write_mode == "repository" else "generated_tests/cypress/alchemy_acceptance.cy.js"
            content = cypress_test_text(scenarios)

        target = (repo if write_mode == "repository" else output) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        summary = f"Generated {framework} native UI acceptance test {'in repository' if write_mode == 'repository' else 'draft in run output'}."
        return NativeUITestGeneration(
            status="generated",
            framework=framework,
            target_path=relative,
            write_mode=write_mode,
            summary=summary,
            files=[str(target)],
            evidence=[*evidence, f"{len(scenarios)} scenario(s) converted to native UI test code."],
        )


def detect_ui_test_framework(repository_path: str | Path) -> tuple[NativeUITestFramework, list[str]]:
    repo = Path(repository_path)
    evidence: list[str] = []
    package = read_package_json(repo / "package.json")
    package_text = json.dumps(package).lower() if package else ""
    if any((repo / name).exists() for name in ("playwright.config.js", "playwright.config.ts", "playwright.config.mjs")):
        evidence.append("Playwright config detected.")
        return "playwright", evidence
    if "@playwright/test" in package_text or "playwright" in _package_script_names(package):
        evidence.append("Playwright package or script detected.")
        return "playwright", evidence
    if any((repo / name).exists() for name in ("cypress.config.js", "cypress.config.ts", "cypress.config.mjs")):
        evidence.append("Cypress config detected.")
        return "cypress", evidence
    if (repo / "cypress").is_dir() or '"cypress"' in package_text or "cypress" in _package_script_names(package):
        evidence.append("Cypress package, script, or directory detected.")
        return "cypress", evidence
    return "none", evidence


def playwright_test_text(scenarios: list[dict[str, object]]) -> str:
    scenario_json = json.dumps(scenarios, indent=2, ensure_ascii=False)
    return f"""import {{ test, expect, type Page }} from '@playwright/test';

type AlchemyScenario = {{
  id?: string;
  title?: string;
  kind?: string;
  required_behaviors?: string[];
  [key: string]: unknown;
}};

const scenarios: AlchemyScenario[] = {scenario_json};

test.describe('Alchemy acceptance scenarios', () => {{
  for (const scenario of scenarios) {{
    test(`${{scenario.id || 'SCN'}} ${{scenario.title || 'acceptance scenario'}}`, async ({{ page }}) => {{
      await page.goto('/');
      await runScenario(page, scenario);
    }});
  }}
}});

async function runScenario(page: Page, scenario: AlchemyScenario) {{
  const behaviors = Array.isArray(scenario.required_behaviors) ? scenario.required_behaviors : [];
  if (scenario.kind === 'crud') {{
    const editable = page.locator('input:not([type="hidden"]):not([type="file"]), textarea, select').first();
    await expect(editable).toBeVisible();
    const create = page.getByRole('button', {{ name: /add|create|new|save|submit|新增|添加|创建|保存/i }}).first();
    await expect(create).toBeVisible();
    await expect(page.locator('li, tr, article, [data-item], [data-record], table, ul, ol').first()).toBeVisible();
    return;
  }}
  if (scenario.kind === 'auth') {{
    await expect(page.locator('input[type="email"], input[type="text"], input[name*="user"], input[name*="email"]').first()).toBeVisible();
    if (behaviors.includes('login')) {{
      await expect(page.locator('input[type="password"], input[name*="password"]').first()).toBeVisible();
    }}
    await expect(page.getByRole('button', {{ name: /login|sign in|register|submit|登录|注册/i }}).first()).toBeVisible();
    return;
  }}
  if (scenario.kind === 'file_upload') {{
    const upload = page.locator('input[type="file"], [data-upload], [aria-label*="upload"], [aria-label*="上传"]').first();
    await expect(upload).toBeVisible();
    return;
  }}
  if (scenario.kind === 'dashboard') {{
    await expect(page.locator('canvas, svg, table, [data-metric], [data-chart], [data-dashboard]').first()).toBeVisible();
    if (behaviors.includes('filter')) {{
      await expect(page.locator('input[type="search"], input, select, [data-filter], [aria-label*="filter"], [aria-label*="搜索"]').first()).toBeVisible();
    }}
    return;
  }}
  throw new Error(`Unsupported Alchemy scenario kind: ${{scenario.kind}}`);
}}
"""


def cypress_test_text(scenarios: list[dict[str, object]]) -> str:
    scenario_json = json.dumps(scenarios, indent=2, ensure_ascii=False)
    return f"""const scenarios = {scenario_json};

describe('Alchemy acceptance scenarios', () => {{
  for (const scenario of scenarios) {{
    it(`${{scenario.id}} ${{scenario.title}}`, () => {{
      cy.visit('/');
      runScenario(scenario);
    }});
  }}
}});

function runScenario(scenario) {{
  if (scenario.kind === 'crud') {{
    cy.get('input:not([type="hidden"]):not([type="file"]), textarea, select').first().should('be.visible');
    cy.contains('button, [role="button"], input[type="submit"]', /add|create|new|save|submit|新增|添加|创建|保存/i).should('be.visible');
    cy.get('li, tr, article, [data-item], [data-record], table, ul, ol').first().should('be.visible');
    return;
  }}
  if (scenario.kind === 'auth') {{
    cy.get('input[type="email"], input[type="text"], input[name*="user"], input[name*="email"]').first().should('be.visible');
    if ((scenario.required_behaviors || []).includes('login')) {{
      cy.get('input[type="password"], input[name*="password"]').first().should('be.visible');
    }}
    cy.contains('button, [role="button"], input[type="submit"]', /login|sign in|register|submit|登录|注册/i).should('be.visible');
    return;
  }}
  if (scenario.kind === 'file_upload') {{
    cy.get('input[type="file"], [data-upload], [aria-label*="upload"], [aria-label*="上传"]').first().should('be.visible');
    return;
  }}
  if (scenario.kind === 'dashboard') {{
    cy.get('canvas, svg, table, [data-metric], [data-chart], [data-dashboard]').first().should('be.visible');
    if ((scenario.required_behaviors || []).includes('filter')) {{
      cy.get('input[type="search"], input, select, [data-filter], [aria-label*="filter"], [aria-label*="搜索"]').first().should('be.visible');
    }}
    return;
  }}
  throw new Error(`Unsupported Alchemy scenario kind: ${{scenario.kind}}`);
}}
"""


def read_package_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _package_script_names(package: dict[str, object]) -> str:
    scripts = package.get("scripts", {})
    if not isinstance(scripts, dict):
        return ""
    values: list[str] = []
    for key, value in scripts.items():
        values.append(str(key).lower())
        values.append(str(value).lower())
    return " ".join(values)


def _scenario_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _is_static_browser_profile(repo: Path, artifact_profile: str) -> bool:
    return artifact_profile in {"static_web_app", "canvas_game"} or (repo / "index.html").is_file()
