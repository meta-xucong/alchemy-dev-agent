# V2.46 Controlled Real GitHub PR Probe

V2.46 keeps the original Alchemy Dev Agent objective unchanged:

> A user can provide a development objective, detailed documents, supporting
> files, and an optional local or GitHub repository. The agent system should
> plan, implement, test, repair, verify, and deliver the result with evidence.

The remaining gap after V2.45 was not local execution. V2.42, V2.43, and V2.44
already proved real environment readiness, a real Codex worker smoke, and a
real document-run local smoke. The missing latest evidence was a controlled
mutating GitHub branch and pull request probe in the unified evidence chain.

## Purpose

V2.46 answers:

> Can this checkout create real remote GitHub delivery evidence on an approved
> repository, and can that evidence be indexed with the other real probes?

## Approved Scope

The probe may:

- create an isolated git worktree from a clean source checkout;
- create a disposable validation branch;
- write one validation marker file;
- commit the marker;
- push the branch to `origin`;
- open a draft pull request;
- collect PR check status through `gh pr checks`;
- write `real_delivery_validation_report.json`;
- include that report in `real_probe_index.json`.

The probe must not:

- merge the PR unless a separate explicit `--auto-merge` request is provided;
- delete remote branches automatically;
- rewrite the base branch;
- treat missing or failed CI as a successful CI-backed delivery;
- expose or store GitHub tokens.

## Runtime Contract

The controlled probe reuses the existing real GitHub delivery harness:

```bash
python -m autodev.real_delivery_validation \
  --repository-path . \
  --output .alchemy/v2_46_real_github_pr_probe \
  --branch agent/alchemy-v2-46-pr-probe \
  --base-branch master \
  --ci-wait-seconds 120 \
  --ci-poll-interval-seconds 10
```

The harness is intentionally small. It validates delivery plumbing, not product
quality for a generated app. Product quality remains enforced by document-run,
browser verification, requirement coverage, reviewer gates, and CI in the main
runtime.

## Evidence Contract

The report path is:

```text
.alchemy/v2_46_real_github_pr_probe/real_delivery_validation_report.json
```

Required evidence fields:

- `status`: `passed` only when branch, commit, push, PR, and enabled CI policy
  complete without blockers;
- `branch`: the disposable validation branch;
- `base_branch`: the target base branch;
- `github.status`: expected `pushed`;
- `github.commit`: pushed head commit;
- `github.pull_request_url`: real GitHub PR URL;
- `github.ci_status`: `passed`, `failed`, `pending`, `unknown`, or `waived`;
- `github.ci_details`: raw normalized PR check details;
- `github.merge.status`: expected `skipped` for this probe;
- `workspace.status`: isolated worktree lifecycle state;
- `blockers`: empty for a passing probe.

## Evidence Index Integration

V2.46 extends `autodev.real_probe_index` to recognize:

```text
real_delivery_validation_report.json -> real_github_pr_probe
```

The indexed entry records:

- branch and base branch;
- commit;
- PR URL;
- GitHub flow status;
- CI status;
- merge status;
- worktree status;
- blocker count.

This makes the real evidence chain one inspectable object:

1. environment readiness;
2. real Codex worker smoke;
3. real document-run local smoke;
4. real GitHub PR probe.

## Acceptance Criteria

V2.46 is accepted when:

- `tests.test_real_probe_index` covers `real_github_pr_probe` indexing;
- `tests.test_real_delivery_validation` still covers branch, PR, CI pass,
  failed CI, unknown CI, and CI waiver behavior;
- the real probe creates a draft PR on an explicitly approved repository;
- the real probe report is indexed by `real_probe_index`;
- full unit tests pass;
- JSON specs parse, diff hygiene passes, and long-running state validates.

## Operator Cleanup

The created draft PR is intentional evidence. Operators may close or merge it
after review. This phase does not auto-close the PR because the PR URL itself is
part of the auditable proof that the GitHub delivery path worked.

