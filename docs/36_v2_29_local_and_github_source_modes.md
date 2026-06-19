# V2.29 Local And GitHub Source Modes

## Purpose

V2.29 closes a product gap found during repeated external delivery tests:

The system must support both:

- local repository import
- GitHub repository import

These are source acquisition modes, not separate execution systems.

Both modes must converge into the same contract:

```text
ProjectBrief -> ContextBundle -> TaskGraph -> RuntimeState -> DeliveryReport
```

## Problem

Earlier versions could pass `repository_path` into execution, but a project with
only a local repository path and no GitHub URL did not always carry an explicit
repository source in `ProjectBrief`.

That created a contract ambiguity:

- GitHub projects had a first-class `repository` object.
- Local-only projects could still execute, but the local source mode was not
  explicit enough for intake, context, reporting, and acceptance evidence.

The user workflow requires local import to be first class because a project may
be prepared locally before any remote repository exists.

## Source Mode Contract

`ProjectBrief.repository.provider` supports:

```json
"github"
"local"
```

### GitHub Mode

GitHub mode starts from a GitHub repository URL.

The system may:

- inspect repository metadata
- clone or fetch the repository
- use local `gh` authentication only for explicitly private repositories
- record branch, PR, CI, and merge evidence when real GitHub delivery is enabled

After retrieval, GitHub mode must still produce a local checkout path. The rest
of the runtime consumes that local path.

### Local Mode

Local mode starts from an existing repository directory.

The system must:

- accept `repository_path` without requiring a GitHub URL
- record `provider = local`
- preserve the local path in `ProjectBrief.repository.local_path`
- index files from that path into `ContextBundle.repository_map`
- execute dry-run and real Codex workers against that local source path or an
  isolated worktree derived from it
- skip real GitHub delivery unless `real_github` is explicitly enabled and the
  repository has usable git remotes

## Feedback Reopen Contract

Feedback reopen must work in both source modes.

For a delivered run, the system must:

1. accept feedback files as `role = feedback`
2. preserve feedback files as attachments, not primary development documents
3. extract feedback-derived requirements with `source_role = feedback`
4. route those requirements to Debug Agent tasks
5. start a new run, normally `run_002`, using the same source mode as the
   original project
6. record `feedback_reopen` metadata with source run, feedback files, repair
   branch prefix, and task graph

## Local Simulation Acceptance

V2.29 adds a local acceptance harness:

```bash
python -m autodev.local_repository_acceptance \
  --output .alchemy/local_repository_acceptance
```

The harness creates a fixture local repository and verifies:

- local repository source is recorded as `provider = local`
- repository path is preserved
- context indexing sees local files
- initial delivery reaches `done`
- feedback reopen creates `run_002`
- feedback requirements remain `source_role = feedback`
- at least one Debug Agent task is planned
- dry-run GitHub evidence is recorded without requiring a remote repository
- final delivery is ready for review

Optional browser verification can be enabled locally:

```bash
python -m autodev.local_repository_acceptance \
  --output .alchemy/local_repository_acceptance \
  --auto-browser-verify
```

Unit tests do not require Playwright. Browser verification remains an optional
local acceptance check so CI can stay deterministic.

## Updated Product Meaning

The product now supports two practical entry points:

```text
Detailed docs + local repository path
Detailed docs + GitHub repository URL
```

Both support the same downstream agent loop:

```text
read docs
index source
extract requirements
plan graph
dispatch agents
execute worker tasks
test
review
evaluate
reopen from feedback when needed
deliver
```

## Remaining Work

V2.29 does not add a new execution model. Remaining product hardening still
belongs to later phases:

- richer UI distinction between local and GitHub source modes
- repository picker or directory chooser in desktop UI contexts
- native generated Playwright/Cypress test output when projects already include
  a UI test framework
- source-run versus repair-run evidence comparison reports
- true live event streaming beyond persisted polling
