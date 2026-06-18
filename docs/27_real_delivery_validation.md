# V2.18 Real Delivery Validation

## Purpose

V2.18 turns real GitHub delivery validation into a repeatable harness instead
of a one-off manual check.

The goal is to prove that Alchemy can create real GitHub delivery evidence:

- a validation branch
- a commit
- a pushed branch
- a pull request
- PR check or CI status evidence when workflows exist

## Implemented Scope

### GitHub Flow

`runtime/github_flow.py` now supports:

- idempotent PR handling through `gh pr view`
- PR creation with explicit `--head`
- optional draft PR creation
- PR check collection through `gh pr checks --json`
- CI status normalization to `passed`, `failed`, `pending`, or `unknown`
- configurable CI collection and waiting through runtime, document-run, API, and
  browser console run payloads
- persisted `ci_details` evidence in runtime state

### Validation Harness

Run the controlled validation harness:

```bash
python -m autodev.real_delivery_validation \
  --repository-path . \
  --output .alchemy/real_delivery_validation \
  --branch agent/alchemy-real-delivery-validation \
  --base-branch master
```

By default, the harness uses an isolated git worktree so the source checkout is
not directly mutated. It writes:

```text
.alchemy/real_delivery_validation/real_delivery_validation_report.json
```

The report includes:

- repository path
- branch and base branch
- worktree setup evidence
- git and gh command evidence
- PR URL
- commit SHA
- CI status and raw check details
- blockers, if validation could not complete

If CI check collection returns `failed`, remains `pending`, or cannot produce a
known status after the configured wait, the validation report is `blocked`. A
pushed branch and PR are necessary delivery evidence, but they are not
sufficient when the quality gate is not healthy.

### CI Workflow

The repository now includes a minimal GitHub Actions workflow:

```text
.github/workflows/ci.yml
```

It runs:

- `python -B -m unittest discover -s tests`
- JSON parsing for all files under `specs/`

This gives real PR validation a concrete CI signal instead of leaving
`ci_status` permanently `unknown`.

### CI Waiting

The validation CLI waits for PR checks by default:

```bash
python -m autodev.real_delivery_validation \
  --repository-path . \
  --output .alchemy/real_delivery_validation \
  --branch agent/alchemy-real-delivery-validation \
  --base-branch master \
  --ci-wait-seconds 120 \
  --ci-poll-interval-seconds 10
```

This prevents the common race where GitHub Actions has accepted the PR but has
not yet reported any checks. The final report records a terminal CI state when
checks finish within the configured timeout. Failed checks, timed-out pending
checks, and missing check status block the validation result when CI collection
is enabled.

## Boundaries

This phase validates GitHub branch/PR/CI plumbing. It does not merge PRs, delete
branches, or claim production autonomous delivery quality by itself.

The harness creates validation artifacts intentionally. Operators should review
and close or merge the validation PR according to project policy.

## Verification

V2.18 is verified by:

- fake-runner GitHub flow tests for PR creation, PR reuse, and CI status parsing
- fake-runner real delivery validation harness tests
- full repository unit tests
- local acceptance harness
- a controlled real GitHub validation run when credentials and repository access
  are available

## Validation Evidence

The current public repository was validated with a controlled draft PR:

- PR: https://github.com/meta-xucong/alchemy-dev-agent/pull/2
- Branch: `agent/alchemy-real-delivery-validation-20260618170706128436`
- Head commit: `3a2dbeb0705b037998ad6612325bbb9c8668b4ab`
- CI workflow: `CI / tests`
- CI result: `SUCCESS`

The first CI run exposed an async job-state race in `server/jobs.py`; the fix
was committed to `master` and the validation PR branch was rebased onto the
fixed commit before CI passed.
