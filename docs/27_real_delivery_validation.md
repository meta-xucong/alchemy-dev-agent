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
