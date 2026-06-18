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
https://github.com/example/saas-dashboard
```

Target branch:

```text
main
```

Repository access:

```text
Public repository; no gh login required.
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
    "url": "https://github.com/example/saas-dashboard",
    "owner": "example",
    "name": "saas-dashboard",
    "target_branch": "main",
    "base_branch": "main",
    "local_path": ".alchemy/projects/proj_workspace_support/repo",
    "visibility": "public",
    "gh_auth_required": false,
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
          "Must add workspace API support in src/api/workspaces.ts.",
          "Must add dashboard workspace switching in src/pages/dashboard.tsx.",
          "Should add workspace permission tests in tests/workspaces.test.ts."
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
        "text": "Must add workspace API support in src/api/workspaces.ts.",
        "priority": "must",
        "acceptance_criteria": [
          "Users can create a workspace.",
          "Users can invite members by email.",
          "Users can switch active workspace.",
          "Workspace permissions are enforced on backend APIs.",
          "Existing dashboard tests still pass."
        ],
        "related_files": [
          "src/api/workspaces.ts"
        ],
        "planned_task_ids": [
          "T002",
          "T005",
          "T006"
        ]
      },
      {
        "id": "REQ-002",
        "source_document_id": "doc_primary_requirements",
        "text": "Must add dashboard workspace switching in src/pages/dashboard.tsx.",
        "priority": "must",
        "acceptance_criteria": [
          "Users can switch active workspace.",
          "Existing dashboard tests still pass."
        ],
        "related_files": [
          "src/pages/dashboard.tsx"
        ],
        "planned_task_ids": [
          "T003",
          "T005",
          "T006"
        ]
      },
      {
        "id": "REQ-003",
        "source_document_id": "doc_primary_requirements",
        "text": "Should add workspace permission tests in tests/workspaces.test.ts.",
        "priority": "should",
        "acceptance_criteria": [
          "Existing dashboard tests still pass."
        ],
        "related_files": [
          "tests/workspaces.test.ts"
        ],
        "planned_task_ids": [
          "T004",
          "T005",
          "T006"
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
      "title": "Plan implementation from requirements",
      "type": "architecture",
      "assigned_agent": "architect",
      "dependencies": [],
      "completion_criteria": [
        "All requirements are assigned to implementation tasks.",
        "Known blockers and risks are reflected in task scope."
      ]
    },
    {
      "id": "T002",
      "title": "Implement backend requirement: Must add workspace API support in src/api/workspaces.ts.",
      "type": "backend",
      "assigned_agent": "backend",
      "dependencies": [
        "T001"
      ],
      "completion_criteria": [
        "Users can create a workspace.",
        "Users can invite members by email.",
        "Users can switch active workspace.",
        "Workspace permissions are enforced on backend APIs.",
        "Existing dashboard tests still pass."
      ],
      "relevant_files": [
        "src/api/workspaces.ts"
      ]
    },
    {
      "id": "T003",
      "title": "Implement frontend requirement: Must add dashboard workspace switching in src/pages/dashboard.tsx.",
      "type": "frontend",
      "assigned_agent": "frontend",
      "dependencies": [
        "T001"
      ],
      "completion_criteria": [
        "Users can switch active workspace.",
        "Existing dashboard tests still pass."
      ],
      "relevant_files": [
        "src/pages/dashboard.tsx"
      ]
    },
    {
      "id": "T004",
      "title": "Implement verification requirement: Should add workspace permission tests in tests/workspaces.test.ts.",
      "type": "test",
      "assigned_agent": "test",
      "dependencies": [
        "T001"
      ],
      "completion_criteria": [
        "Existing dashboard tests still pass."
      ],
      "relevant_files": [
        "tests/workspaces.test.ts"
      ]
    },
    {
      "id": "T005",
      "title": "Verify implementation against project checks",
      "type": "test",
      "assigned_agent": "test",
      "dependencies": [
        "T002",
        "T003",
        "T004"
      ],
      "completion_criteria": [
        "Detected verification commands pass or produce documented blockers.",
        "Every must requirement has implementation evidence."
      ],
      "commands_to_run": [
        "npm test",
        "npm run build",
        "npm run lint"
      ]
    },
    {
      "id": "T006",
      "title": "Review delivery readiness",
      "type": "review",
      "assigned_agent": "reviewer",
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
