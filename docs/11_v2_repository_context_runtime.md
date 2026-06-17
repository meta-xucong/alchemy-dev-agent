# V2.2 Repository Context Runtime

## Purpose

V2.2 moves the system from document-only intake toward real repository-aware planning.

The goal is to convert a linked or local repository into planner-ready evidence inside `ContextBundle`:

```text
ProjectBrief.repository.local_path
  -> RepositoryIndexer
  -> repository_map
  -> test_profile
  -> ContextBundle
```

This stage is still local and deterministic. It does not clone repositories or call GitHub. It indexes an already available local checkout path.

## Implemented Scope

V2.2 implements:

- Local repository path validation.
- Repository file discovery.
- Ignored directory filtering.
- File kind classification.
- Language detection by suffix.
- Package file detection.
- CI workflow detection.
- Package manager detection.
- Test command detection.
- Build command detection.
- Lint command detection.
- ContextBundle enrichment from repository evidence.
- Blockers for missing or invalid repository paths.

## File Classification

The repository indexer classifies files into:

- `source`
- `test`
- `doc`
- `config`
- `ci`
- `asset`
- `migration`
- `unknown`

Ignored paths include:

- `.git`
- `.alchemy`
- `.test-tmp`
- `node_modules`
- build outputs
- cache directories
- virtual environments

## Test Profile Detection

The current detector supports common signals:

| Signal | Package Manager | Test Command | Build Command | Lint Command |
| --- | --- | --- | --- | --- |
| `package.json` | `npm` | `npm test` when `scripts.test` exists | `npm run build` when `scripts.build` exists | `npm run lint` when `scripts.lint` exists |
| `pyproject.toml` or `requirements.txt` | `python` | `python -m unittest discover -s tests` | | |
| `go.mod` | `go` | `go test ./...` | `go build ./...` | |
| `Cargo.toml` | `cargo` | `cargo test` | `cargo build` | |
| `pom.xml` | `maven` | `mvn test` | | |

This is intentionally conservative. It records likely commands; it does not execute them.

## ContextBundle Integration

When `ProjectBrief.repository.local_path` is set, `ContextBundleBuilder` now indexes the local repository and fills:

- `repository_map.root_path`
- `repository_map.files`
- `repository_map.package_files`
- `repository_map.ci_files`
- `test_profile.package_managers`
- `test_profile.test_commands`
- `test_profile.build_commands`
- `test_profile.lint_commands`
- `test_profile.coverage_unknown`
- `blockers`

## Blockers

V2.2 records hard blockers for:

- Repository path does not exist.
- Repository path is not a directory.

These blockers are added to the ContextBundle. Planning should not execute live repository mutation while hard context blockers exist.

## Non-Goals

V2.2 does not yet implement:

- `gh auth status`.
- GitHub clone.
- GitHub fetch.
- Branch checkout.
- Remote repository visibility checks.
- Deep code summarization.
- Semantic requirement-to-file mapping.
- Running detected tests.

Those belong to V2.3 and later runtime stages.

## Implementation Files

```text
context/
  repository_indexer.py
  builder.py

tests/
  test_repository_context.py
```

## Verification

V2.2 is verified with a synthetic local repository containing:

- TypeScript source.
- TypeScript tests.
- `package.json`.
- GitHub Actions workflow.
- README.

The test asserts that repository evidence is included in a schema-valid ContextBundle.
