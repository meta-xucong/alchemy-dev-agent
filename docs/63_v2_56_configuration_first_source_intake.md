# V2.56 Configuration-First Source Intake

## Purpose

V2.56 aligns the browser console with the intended autonomous development entrypoint:

1. verify the local execution environment,
2. choose exactly one development source,
3. start the agent development loop only after the source contract is complete.

This phase preserves the original goal: a user should be able to provide a sufficiently detailed development package and let the agent system analyze, implement, test, review, iterate, and deliver. One-line input remains supported as a fallback path, but document-driven and repository-driven development are the primary paths.

## Source Modes

The console exposes three mutually exclusive source cards.

| Source | User input | Runtime route | Required before start |
| --- | --- | --- | --- |
| Idea prompt | A paragraph or one-line objective | generated requirements document + `document_driven` | Non-empty objective |
| Local documents | One or more uploaded files from the browser | `document_driven` | At least one uploaded primary document |
| GitHub repository | A GitHub repository URL | `document_driven` with `source_mode=github_public` | Non-empty repository URL and verified GitHub CLI login |

When one source is selected, the other two cards are disabled until the operator chooses `Change Source`. This prevents mixed truth sources such as an idea prompt plus a stale repository URL.

The idea prompt is no longer sent directly to the legacy one-line fallback from the browser console. The console marks it with `expand_one_line=true`; the API writes a generated development brief into server storage, attaches that document to the request, and routes the run through the same document-driven execution pipeline used by uploaded development documents. The CLI one-line fallback remains available for deterministic compatibility tests and lightweight local demos, but it is not the default browser development flow.

## Configuration Gate

The development source panel is locked until `POST /environment/check` returns `status=ready`.

The gate checks:

- `git`
- GitHub CLI availability
- GitHub CLI authentication
- Codex CLI availability
- model access configuration
- optional browser automation availability when automatic browser verification is enabled

If any required check fails, only the configuration area remains operable. The source panel, run controls, and evidence actions stay disabled.

The console should load safe local defaults from `GET /environment/defaults` before the operator edits anything. Defaults are detection-based, not hard-coded:

- `codex_executable` comes from the current machine's `codex` command resolution.
- `github_cli` comes from the current machine's `gh` command resolution.
- model mode defaults to `codex_cli`, because the normal user path is to use the already authenticated Codex CLI worker rather than manually filling API keys.

## Model Access Contract

Model configuration is part of the same preflight gate because the orchestrator, document expansion, reviewer, and Codex worker path depend on it.

Supported provider modes:

| Provider | Required configuration |
| --- | --- |
| `codex_cli` | Codex CLI executable must pass `--version`; model access is delegated to Codex CLI |
| `openai` | API key environment variable, default `OPENAI_API_KEY` |
| `anthropic` | API key environment variable, default `ANTHROPIC_API_KEY` |
| `custom` | API key environment variable plus base URL |

The browser console records model choices for operator traceability. Runtime execution currently enforces model readiness through the environment check and passes model configuration through the run payload for future adapters.

The UI must make the recommended model path obvious:

- Show `Recommended: Codex CLI login` as the default mode.
- Explain that no API key is needed in the recommended path.
- Hide API key and base URL fields behind `Advanced model settings`.
- When an advanced API provider is selected, open the advanced settings and clearly show whether the expected environment variable is detected.

## Local Document Upload Flow

The local document path flow must not require users to type local filesystem paths.

Required browser sequence:

1. User selects the `Local documents` card.
2. User selects one or more files with the file picker.
3. Console creates a project with `primary_input_mode=document_driven`.
4. Console uploads files through `POST /projects/{project_id}/files`.
5. Uploaded files become primary development documents.
6. Console starts `POST /projects/{project_id}/runs`.

Preflight for this source must also create/load the project and upload selected files first, so backend validation sees real stored document paths.

## GitHub URL Flow

GitHub repository mode accepts a repository URL directly. The environment gate must verify GitHub CLI authentication before this source can start.

When this source is selected, the console defaults `prepare_repository=true` for run and preflight payloads. The user should not need to manually provide a local checkout path; the runtime should prepare or inspect the repository through the GitHub source flow.

Default behavior treats repositories as public because the current product direction allows public test repositories. Private repositories remain possible through authenticated `gh` and future visibility controls, but the UI does not force private mode as the default.

## Acceptance Criteria

- Configuration panel includes Codex CLI, GitHub-related options, browser verification options, and model access fields.
- Configuration panel pre-fills detected local defaults through `GET /environment/defaults`.
- Model access defaults to Codex CLI recommended mode and hides API key fields under advanced settings.
- Development source panel is disabled before environment readiness.
- Three source cards are mutually exclusive.
- Local document mode uses browser multi-file upload, not typed paths.
- GitHub mode uses a URL and relies on the environment gate for `gh auth status`.
- Start and preflight buttons require a selected source plus source-specific required input.
- Static page tests pin the configuration-first source contract.
- Environment tests cover model provider readiness checks.
- Existing unified run, project run, evidence, and feedback workflows continue to pass.
