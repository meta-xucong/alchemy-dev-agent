"""Generate a development document package for one-sentence objectives."""

from __future__ import annotations

import json
from pathlib import Path


class GeneratedDevelopmentPackage:
    """Create a machine-auditable document package before coding from a short idea."""

    def write(self, *, objective: str, output_dir: str | Path) -> dict[str, object]:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        files = {
            "00_objective.md": objective_doc(objective),
            "01_product_requirements.md": requirements_doc(objective),
            "02_architecture.md": architecture_doc(objective),
            "03_roadmap.md": roadmap_doc(objective),
            "04_acceptance_criteria.md": acceptance_doc(objective),
            "05_test_plan.md": test_plan_doc(objective),
            "06_delivery_policy.md": delivery_policy_doc(),
        }
        written: list[str] = []
        for filename, content in files.items():
            path = output / filename
            path.write_text(content, encoding="utf-8")
            written.append(str(path))
        plan = {
            "schema_version": "generated_development_package_v1",
            "objective": objective,
            "documents": written,
            "roadmap_hint": [
                "V1.0 Foundation and architecture",
                "V1.1 Core implementation",
                "V1.2 Verification, polish, and delivery",
            ],
        }
        plan_path = output / "roadmap_execution_plan.json"
        plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(str(plan_path))
        return {
            "status": "generated",
            "objective": objective,
            "output_dir": str(output),
            "documents": written,
        }


def objective_doc(objective: str) -> str:
    return f"""# Objective

Build the complete requested software product:

```text
{objective}
```

This generated package is the execution contract for full-roadmap mode.
"""


def requirements_doc(objective: str) -> str:
    return f"""# Product Requirements

## Requirements

- Must turn the objective into a usable software deliverable: {objective}
- Must implement the core user workflow end to end.
- Must include sensible defaults for users who provided only a short idea.
- Must produce a reviewable local result.
- Must include tests or deterministic verification evidence.

## Acceptance Criteria

- A user can run or open the generated result.
- The primary workflow works without manual code edits.
- Verification evidence is recorded.
- The final handoff is blocked if critical requirements are missing.
"""


def architecture_doc(objective: str) -> str:
    return f"""# Architecture

The system should choose the smallest practical architecture that can satisfy:

```text
{objective}
```

## Requirements

- Must keep implementation simple and inspectable.
- Must separate source files, tests, and delivery artifacts when practical.
- Must avoid unnecessary external services unless the objective requires them.
"""


def roadmap_doc(objective: str) -> str:
    return f"""# Roadmap

## V1.0 Foundation

### Goal

Create the project foundation for: {objective}

### Requirements

- Define the project structure.
- Implement the minimum working shell.
- Add deterministic verification.

## V1.1 Core Implementation

### Goal

Implement the main user-facing behavior.

### Requirements

- Build all required product logic.
- Connect the main workflow end to end.
- Preserve simple local execution.

## V1.2 Verification, Polish, and Delivery

### Goal

Make the result reviewable and ready for handoff.

### Requirements

- Run tests or static checks.
- Fix critical issues found by review.
- Produce final delivery evidence.
"""


def acceptance_doc(objective: str) -> str:
    return f"""# Acceptance Criteria

- Must satisfy the root objective: {objective}
- Must complete every required roadmap phase.
- Must not stop after an internal phase if later required phases remain.
- Must provide final result access and evidence.
"""


def test_plan_doc(objective: str) -> str:
    return f"""# Test Plan

## Required Verification

- Run available unit tests or static checks.
- If the result is a web artifact, verify the openable page.
- If no formal test runner exists, produce deterministic smoke evidence.

Objective under test:

```text
{objective}
```
"""


def delivery_policy_doc() -> str:
    return """# Delivery Policy

- Local result generation is allowed.
- Pull request creation is allowed only when GitHub delivery is configured.
- Auto-merge is disabled unless explicitly authorized.
- Destructive cleanup is forbidden by default.
"""
