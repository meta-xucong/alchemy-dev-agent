# V2.48 Pull Request Lifecycle Controls

V2.48 keeps the original goal unchanged: Alchemy should autonomously develop,
test, verify, and deliver software from user documents and repositories. After
V2.46 and V2.47, the system can create and audit real GitHub PR evidence. The
next production gap is lifecycle control for those PRs.

## Purpose

V2.48 answers:

> After Alchemy creates a validation or delivery pull request, can operators
> inspect it, plan state transitions, and perform safe explicit cleanup without
> relying on ad hoc `gh` commands?

## Safety Model

Default behavior is non-mutating:

```bash
python -m autodev.github_pr_lifecycle \
  --selector 3 \
  --action inspect \
  --output .alchemy/github_pr_lifecycle \
  --summary
```

Mutating actions require `--confirm`:

```bash
python -m autodev.github_pr_lifecycle \
  --selector 3 \
  --action ready \
  --confirm
```

```bash
python -m autodev.github_pr_lifecycle \
  --selector 3 \
  --action close \
  --delete-branch \
  --confirm
```

Without `--confirm`, `ready` and `close` return `status=planned` and do not
call the mutating GitHub command.

## Supported Actions

- `inspect`: read PR state, draft flag, branch names, merge state, and checks.
- `ready`: mark a draft PR ready for review, only with `--confirm`.
- `close`: close a PR, only with `--confirm`.
- `close --delete-branch`: close the PR and ask GitHub to delete the remote
  branch, only with `--confirm`.

## Report Contract

The control writes:

```text
.alchemy/github_pr_lifecycle/github_pr_lifecycle_report.json
```

The report includes:

- `schema_version = 2.48`;
- selected action;
- PR selector;
- repository path;
- pull request metadata;
- PR check metadata;
- exact `gh` commands and outputs;
- warnings for planned-but-not-confirmed actions;
- blockers for failed inspection or mutation.

## Relationship To Delivery

V2.48 does not replace `runtime.github_flow`. Creation and delivery still happen
through the normal document-run/orchestrator path. This module starts after a PR
exists and controls review/cleanup state.

That separation prevents accidental merge, close, or branch deletion during the
main development loop.

## Acceptance Criteria

V2.48 is accepted when:

- `inspect` reports PR metadata without mutation;
- `ready` without `--confirm` is planned and non-mutating;
- `close --delete-branch --confirm` issues the expected GitHub command;
- lifecycle summary is compact and human-readable;
- `real_probe_index` can index `github_pr_lifecycle_report.json`;
- a non-mutating real inspect can run against the current validation PR;
- full unit tests, JSON parsing, diff hygiene, and state validation pass.

