# Intake And Context Contract

## Purpose

The intake and context layer converts user-provided project material into structured runtime inputs.

It is responsible for turning:

- Detailed development documents.
- Uploaded supporting files.
- GitHub repository links.
- Branch, issue, pull request, or release references.
- User constraints and acceptance criteria.

Into:

- `ProjectBrief`
- `ContextBundle`
- Task graph planning inputs

The runtime must not ask agents to infer the project from scattered raw files when a structured brief and context bundle can be produced first.

## Supported Input Types

### Objective

A short description of the desired project, feature, migration, or system.

Required fields:

- `objective`
- `primary_input_mode`

Allowed modes:

- `document_driven`
- `one_line_fallback`

### Primary Development Document

The primary document is the highest-priority source of requirements.

Supported planned file types:

- Markdown: `.md`
- Plain text: `.txt`
- JSON: `.json`
- YAML: `.yaml`, `.yml`
- PDF: `.pdf`
- Word: `.docx`

The initial implementation may support a subset, but unsupported file types must produce explicit blockers instead of silent omissions.

### Supporting Files

Supporting files may include:

- API specifications.
- Database schemas.
- Architecture notes.
- UI wireframes or design notes.
- Test plans.
- Existing bug reports.
- Logs.
- Reference snippets.
- Migration notes.
- Data samples.

Every supporting file must be assigned a role:

- `primary_requirements`
- `supplemental`
- `api_spec`
- `database_schema`
- `design`
- `test_plan`
- `reference_code`
- `data_sample`
- `other`

### GitHub Repository Link

Repository input may include:

- Repository URL.
- Target branch.
- Base branch.
- Issue reference.
- Pull request reference.
- Local checkout path, when already present.

Repository inspection must record:

- Provider.
- Owner.
- Repository name.
- Visibility if known.
- Branch or commit reference.
- Local path.
- Authentication requirement.
- Retrieval status.

## GitHub Source Retrieval

Public GitHub repositories are the primary supported source path. They must not require `gh` login or stored tokens.

The system must support:

- URL normalization.
- Owner and repository name parsing.
- Branch validation.
- Clone when no local checkout exists.
- Fetch when a local checkout already exists.
- Deterministic checkout of the requested target branch.
- Clean separation between user repository code and Alchemy runtime code.

The retrieval result must be added to the `ProjectBrief.repository` object.

## Optional GitHub CLI Authentication

Private repository support is an optional authenticated extension path delegated to local GitHub CLI authentication.

The system must check:

```bash
gh --version
gh auth status
```

Required behavior:

- If `gh` is missing, record a blocker.
- If `gh` is unauthenticated, record a blocker with a login instruction.
- If `gh` is authenticated but cannot access the repository, record a repository access blocker.
- If the repository is public, `gh` is not required for source retrieval.
- No GitHub token may be collected or stored by the application UI.

## ProjectBrief Generation

`ProjectBrief` is the normalized intake output.

It must contain:

- Objective.
- Input mode.
- Primary document metadata.
- Supporting file metadata.
- Repository metadata.
- User constraints.
- Acceptance criteria.
- Generated-from-one-liner flag.
- Source confidence.

Rules:

- User-provided documents override model-generated assumptions.
- Explicit acceptance criteria override inferred acceptance criteria.
- Repository evidence must not override the user's stated objective without reviewer approval.
- Any unsupported or unreadable file must be recorded as a blocker.

## ContextBundle Generation

`ContextBundle` is the planner-ready evidence package.

It must contain:

- Document index.
- Repository map.
- Requirement map.
- Test profile.
- Risk profile.
- Blockers.
- Traceability links.

The context bundle is created from `ProjectBrief`, uploaded files, and repository inspection.

## Document Index

The document index stores:

- Document ID.
- Path.
- Role.
- Content hash.
- Summary.
- Key requirements.
- Confidence.
- Parse status.

The planner must preserve source references so reviewer checks can trace each task back to user-provided material.

## Repository Map

The repository map stores:

- File paths.
- File kind.
- Language.
- Size.
- Package files.
- Test files.
- CI files.
- Configuration files.
- Migration files.
- Documentation files.

The repository indexer should identify common signals:

- `package.json`
- `pyproject.toml`
- `requirements.txt`
- `go.mod`
- `Cargo.toml`
- `pom.xml`
- `.github/workflows/*`
- `Dockerfile`
- `docker-compose.yml`

## Requirement Map

Each requirement must contain:

- Stable requirement ID.
- Requirement text.
- Source document ID.
- Priority.
- Acceptance criteria.
- Related repository files.
- Planned task IDs once a graph is generated.

Priority values:

- `must`
- `should`
- `could`

Rules:

- Requirements from the primary development document default to `must` unless marked otherwise.
- Requirements from supporting files default to `should` unless they are explicit acceptance criteria.
- Generated fallback requirements default to `should`.
- V2.4 extracts requirements deterministically from structured document sections and priority markers.
- V2.4 links requirements to repository files through explicit file paths, filenames, and file-stem matches.
- V2.4 fills `planned_task_ids` after task graph generation.

## Test Profile

The test profile must record:

- Detected package managers.
- Test commands.
- Build commands.
- Lint commands.
- CI workflow files.
- Coverage signals.
- Unknown verification gaps.

The Test Agent uses this profile as its starting point. It may refine commands during execution, but changes must be recorded in runtime state.

## Blocker Handling

The intake layer must produce blockers for:

- Missing primary development document in document-driven mode.
- Unsupported required file types.
- Unreadable uploaded files.
- Invalid GitHub URL.
- Public repository clone or fetch failure.
- Missing `gh` when private repository access is required.
- Failed `gh auth status`.
- Repository access denied.
- Missing target branch.
- Contradictory hard requirements.

Blockers must be visible before execution begins.

## Determinism

The intake layer must be deterministic for the same input package when model-generated fallback is not used.

Deterministic fields:

- File IDs derived from stable hashes.
- Document role classification when explicitly provided.
- Repository metadata from GitHub URL and checkout state.
- Requirement IDs generated from normalized source order.

When model expansion is used, the resulting `ProjectBrief` must record that generated content was used.

## Handoff To Runtime

The planner receives:

- `ProjectBrief`
- `ContextBundle`

The planner produces:

- Task graph nodes.
- Dependencies.
- Agent assignment candidates.
- Completion criteria.
- Required context files.
- Verification commands.

The runtime then uses the existing v1 execution contract.
