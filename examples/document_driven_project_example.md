# Document-Driven Project Example

## User Input Package

The user wants to implement a real feature in an existing repository.

Objective:

> Add team workspace support to the existing SaaS dashboard.

Primary development document:

```text
workspace_feature_spec.md
```

Supporting files:

```text
api_contract.yaml
database_migration_notes.md
billing_constraints.md
workspace_ui_requirements.md
test_plan.md
```

GitHub repository:

```text
https://github.com/example/private-saas-dashboard
```

Target branch:

```text
main
```

Repository access:

```text
Use local gh authentication.
```

## Intake Result

The intake layer creates a `ProjectBrief`.

```json
{
  "schema_version": "2.0",
  "project_id": "proj_workspace_support",
  "objective": "Add team workspace support to the existing SaaS dashboard.",
  "primary_input_mode": "document_driven",
  "documents": [
    {
      "id": "doc_primary_requirements",
      "name": "workspace_feature_spec.md",
      "path": "uploads/workspace_feature_spec.md",
      "media_type": "text/markdown",
      "role": "primary_requirements",
      "required": true,
      "content_hash": "sha256:primary",
      "summary": "Defines workspace membership, invitation, switching, and permission requirements.",
      "parse_status": "parsed"
    }
  ],
  "attachments": [
    {
      "id": "doc_api_contract",
      "name": "api_contract.yaml",
      "path": "uploads/api_contract.yaml",
      "media_type": "application/yaml",
      "role": "api_spec",
      "required": true,
      "content_hash": "sha256:api",
      "parse_status": "parsed"
    },
    {
      "id": "doc_ui",
      "name": "workspace_ui_requirements.md",
      "path": "uploads/workspace_ui_requirements.md",
      "media_type": "text/markdown",
      "role": "design",
      "required": true,
      "content_hash": "sha256:ui",
      "parse_status": "parsed"
    }
  ],
  "repository": {
    "provider": "github",
    "url": "https://github.com/example/private-saas-dashboard",
    "owner": "example",
    "name": "private-saas-dashboard",
    "target_branch": "main",
    "base_branch": "main",
    "local_path": ".alchemy/projects/proj_workspace_support/repo",
    "visibility": "private",
    "gh_auth_required": true,
    "access_status": "available"
  },
  "constraints": [
    "Do not break existing single-user accounts.",
    "Use the repository's existing test runner.",
    "No token or secret may be stored in the Alchemy UI."
  ],
  "acceptance_criteria": [
    "Users can create a workspace.",
    "Users can invite members by email.",
    "Users can switch active workspace.",
    "Workspace permissions are enforced on backend APIs.",
    "Existing dashboard tests still pass."
  ],
  "generated_from_one_liner": false,
  "source_confidence": "high",
  "blockers": [],
  "created_at": "2026-06-18T00:00:00Z"
}
```

## Context Bundle Excerpt

The context builder indexes documents and repository evidence.

```json
{
  "schema_version": "2.0",
  "project_id": "proj_workspace_support",
  "objective": "Add team workspace support to the existing SaaS dashboard.",
  "document_index": {
    "documents": [
      {
        "id": "doc_primary_requirements",
        "path": "uploads/workspace_feature_spec.md",
        "role": "primary_requirements",
        "content_hash": "sha256:primary",
        "parse_status": "parsed",
        "summary": "Workspace membership, invitations, workspace switching, and permission model.",
        "key_requirements": [
          "Create workspace data model.",
          "Invite members by email.",
          "Switch active workspace in dashboard.",
          "Enforce workspace permissions on API requests."
        ],
        "confidence": "high"
      }
    ]
  },
  "repository_map": {
    "root_path": ".alchemy/projects/proj_workspace_support/repo",
    "files": [
      {
        "path": "src/api/workspaces.ts",
        "kind": "source",
        "language": "typescript",
        "size_bytes": 3200
      },
      {
        "path": "src/pages/dashboard.tsx",
        "kind": "source",
        "language": "typescript",
        "size_bytes": 8700
      },
      {
        "path": "tests/workspaces.test.ts",
        "kind": "test",
        "language": "typescript",
        "size_bytes": 2100
      }
    ],
    "package_files": [
      "package.json"
    ],
    "ci_files": [
      ".github/workflows/ci.yml"
    ]
  },
  "requirement_map": {
    "requirements": [
      {
        "id": "REQ-001",
        "source_document_id": "doc_primary_requirements",
        "text": "Users can create a workspace.",
        "priority": "must",
        "acceptance_criteria": [
          "Workspace creation API exists.",
          "Workspace appears in dashboard after creation."
        ],
        "related_files": [
          "src/api/workspaces.ts",
          "src/pages/dashboard.tsx"
        ],
        "planned_task_ids": [
          "T002",
          "T004"
        ]
      }
    ]
  },
  "test_profile": {
    "package_managers": [
      "npm"
    ],
    "test_commands": [
      "npm test"
    ],
    "build_commands": [
      "npm run build"
    ],
    "lint_commands": [
      "npm run lint"
    ],
    "ci_files": [
      ".github/workflows/ci.yml"
    ],
    "coverage_unknown": false
  },
  "risk_profile": {
    "risks": [
      {
        "id": "RISK-001",
        "type": "authorization",
        "severity": "high",
        "description": "Workspace permissions must be enforced across all existing dashboard APIs.",
        "mitigation": "Reviewer Agent must verify backend checks and Test Agent must add permission tests."
      }
    ]
  },
  "blockers": [],
  "created_at": "2026-06-18T00:00:00Z"
}
```

## Generated Task Graph

```json
{
  "nodes": [
    {
      "id": "T001",
      "title": "Design workspace implementation plan",
      "type": "architecture",
      "agent": "architect",
      "dependencies": [],
      "completion_criteria": [
        "Data model, API, UI, tests, and migration approach are mapped to requirements."
      ]
    },
    {
      "id": "T002",
      "title": "Implement workspace backend model and APIs",
      "type": "backend",
      "agent": "backend",
      "dependencies": [
        "T001"
      ],
      "completion_criteria": [
        "Workspace create, invite, member list, and switch endpoints exist.",
        "Workspace permission checks are enforced."
      ]
    },
    {
      "id": "T003",
      "title": "Add database migration for workspace tables",
      "type": "backend",
      "agent": "backend",
      "dependencies": [
        "T001"
      ],
      "completion_criteria": [
        "Migration creates workspace, membership, and invitation records."
      ]
    },
    {
      "id": "T004",
      "title": "Implement workspace dashboard UI",
      "type": "frontend",
      "agent": "frontend",
      "dependencies": [
        "T002",
        "T003"
      ],
      "completion_criteria": [
        "Users can create, invite, and switch workspaces from the dashboard."
      ]
    },
    {
      "id": "T005",
      "title": "Add workspace tests",
      "type": "test",
      "agent": "test",
      "dependencies": [
        "T002",
        "T003",
        "T004"
      ],
      "completion_criteria": [
        "Backend permission tests pass.",
        "Frontend workspace workflow tests pass."
      ]
    },
    {
      "id": "T006",
      "title": "Review workspace delivery",
      "type": "review",
      "agent": "reviewer",
      "dependencies": [
        "T005"
      ],
      "completion_criteria": [
        "All must requirements are traced to completed tasks.",
        "Final gate score is at least 0.85."
      ]
    }
  ]
}
```

## Agent Execution Flow

| Step | Owner | Output |
| --- | --- | --- |
| Intake | System service | ProjectBrief |
| Context build | System service | ContextBundle |
| Planning | Architect Agent | Task graph |
| Backend implementation | Backend Agent through Codex Worker | Backend diff, tests |
| Frontend implementation | Frontend Agent through Codex Worker | UI diff, tests |
| Verification | Test Agent through Codex Worker | Test evidence |
| Failure recovery | Debug Agent through Codex Worker | Fix diff, rerun logs |
| Final review | Reviewer Agent | Approval or blockers |
| Delivery | Orchestrator | Branch, PR, report, final state |

## One-Line Fallback Variant

If the user only enters:

```text
Build workspace support for my SaaS app.
```

The system may expand the sentence into a draft `ProjectBrief`, but:

- `primary_input_mode` must be `one_line_fallback`.
- `generated_from_one_liner` must be `true`.
- `source_confidence` should be `low` or `medium`.
- Requirements must be shown for user review before execution.
