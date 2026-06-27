# Billing Core CRM Supervision Assessment

## Operating Contract

Codex Desktop is the external supervisor for this project. It may inspect
artifacts, run smoke checks, fix Alchemy Dev Agent, write supervision documents,
and start or stop Alchemy runs. It must not directly implement CRM product code
inside Billing Core. Product code changes must be made by Alchemy real Codex
workers inside the isolated run worktree.

The Billing Core target is not "make sub2api nicer". The target is a reusable
CRM identity, recharge, wallet, billing, metering, charging, reconciliation,
statistics, admin, API, SDK, deployment, and observability core that can be
embedded into other projects and is no longer a token relay station.

## Current Evidence

Alchemy state as of 2026-06-27 12:40 +08:00:

- Alchemy repo is clean and pushed through `3eda150`.
- Minimal local Codex CLI smoke now passes again after the earlier usage-limit
  window.
- `interrupted_phase_resume_source()` returns no resume source for stale Billing
  Core `phase_010/run_attempt_020`, so the next run should create a fresh
  attempt instead of replaying `T002-DEBUG-1`.
- V2.86 package lockfile boundary expansion should prevent
  `frontend/pnpm-lock.yaml` from being treated as an out-of-scope edit when
  `frontend/package.json` is allowed.
- No stale Billing Core Alchemy worker process is currently running.

Billing Core roadmap evidence:

- Completed phases: `phase_001` through `phase_009`.
- Pending phases: `phase_010` frontend closure, `phase_011` schema pruning and
  build, `phase_012` demo smoke test.
- Latest usable full-roadmap report has 9 completed phase records and is still
  marked `running` because the roadmap has not reached final verification.
- `phase_010/run_attempt_015` stopped at T004 blockers before V2.81 repair
  support. Later attempts proved multiple Alchemy framework issues rather than
  final product readiness.
- `run_attempt_020` reached the correct inherited worktree and completed T002's
  Codex subprocess, but Alchemy discarded the result because of the lockfile
  boundary false failure fixed in V2.86.

## CRM Usability Assessment

Current CRM usability is partial and not yet deliverable.

What appears usable or close:

- The backend has meaningful CRM foundations: account identity work, wallet
  ledger/service/API pieces, metering route work, redeem-to-wallet integration,
  and balance-recharge-only payment behavior.
- Tests and route files show that user/admin wallet endpoints and CRM billing
  route surface were introduced.
- Payment behavior has been pushed toward balance recharge, with subscription
  plan catalog behavior retired or reduced in some layers.
- The project has an inherited worktree with accumulated product migration work
  that should be treated as the current integration surface.

What is not good enough yet:

- Frontend closure is incomplete. There are still user-facing payment/provider
  pages and compatibility paths such as Airwallex, Stripe, payment callbacks,
  admin payment plans, and subscription compatibility tests that must be
  intentionally removed, reframed, or proven harmless.
- Residual old-domain language remains in code and tests. Some "token" mentions
  are normal auth tokens, but many `gateway`, `provider`, `channel`, `model`,
  subscription, proxy, and upstream concepts still need classification.
- Schema pruning is not done. Ent schemas and generated code still include many
  old domain models, so the product is not yet a self-contained CRM core.
- Demo verification is not done. There is no final documented admin demo account
  plus deterministic smoke proving install, login, recharge, wallet ledger,
  metering, deduction, invoice/order, admin audit, and statistics flows.
- The original checkout at `D:\AI\SSH\sub2api-billing-core` is dirty. The active
  Alchemy worktree remains the safer execution surface, but final handoff must
  reconcile exactly which tree is authoritative.

## Alchemy Dev Agent Assessment

Alchemy is now suitable to continue the job, but it still needs close external
supervision.

Strengths after V2.78-V2.87:

- It can stop on non-partial blockers instead of dispatching unrelated next
  tasks.
- It can open phase repair attempts after autonomous technical blockers.
- It can skip stale terminal attempts and stale dead debug attempts.
- It can bootstrap Go safely with process-level environment variables.
- It can run Windows real Codex workers using the local Codex CLI path that
  actually writes in the isolated worktree.
- It now aligns package manifest boundaries with package-manager lockfiles.

Remaining Alchemy weaknesses:

- Long real-worker tasks still need strict budgets and stop rules to avoid
  expensive loops.
- Full-roadmap reports can remain `running` after manually stopped probes, so
  supervisor-side interpretation must prefer per-attempt state plus lifecycle
  records.
- Artifact directories contain large dependency caches and worktrees; Windows
  recursive scans can hit transient path/read errors. Supervisors should inspect
  precise state files instead of walking every artifact path.
- It has no first-class "product usability audit" phase for large migrations
  yet; this document is filling that gap manually.
- It does not yet enforce an authoritative target worktree/dirty-original
  handoff policy strongly enough for final delivery.

## Next Supervision Loop

The next run should use Alchemy only:

1. Re-run the minimal Codex OK smoke.
2. Launch Billing Core through `python -B -m autodev.run` with:
   - `--full-roadmap`
   - `--max-phases 1`
   - `--max-iterations 3` or `4`
   - `--max-worker-seconds 900`
   - process-local `ALCHEMY_GO_BIN`, `ALCHEMY_GOMODCACHE`,
     `GOTOOLCHAIN=auto`, and `GOFLAGS=-p=1`
3. Confirm a fresh `phase_010/run_attempt_021` or later is created.
4. Confirm the worker runs in the inherited isolated worktree, not the original
   checkout.
5. If T002 or T004 now fails on real product tests, let Alchemy create repair
   attempts. If it fails because the controller behaves incorrectly, stop and
   fix Alchemy.
6. After each attempt, inspect worker lifecycle, task graph status, blockers,
   changed files, and test output before continuing.

## Delivery Gates

Do not consider the CRM deliverable until all gates below pass:

- Alchemy full-roadmap reaches final audit, not just phase-local success.
- Frontend has no direct old token-relay/API-gateway/provider-channel pages.
- Backend runtime route surface excludes token relay/provider/channel/model
  routing behavior from the CRM product.
- Ent schema and migrations are pruned or explicitly wrapped as generic CRM
  infrastructure.
- Go targeted tests pass for identity, wallet, payment recharge, metering,
  redeem, admin audit, and route surface.
- Frontend tests pass for router/menu/payment/recharge/wallet/usage/admin
  workflows.
- A deterministic demo smoke documents admin credentials or setup steps and
  proves the CRM can be installed and used by another project.
- Final handoff identifies the authoritative worktree and avoids silently
  mixing dirty original checkout state with Alchemy run artifacts.

## 2026-06-27 Follow-Up

The supervised V2.88 probe reached `phase_010/run_attempt_023` and stopped
cleanly. There are no live Billing Core parent or worker processes left from
that run.

Current execution state:

- T001-T005 are completed in the inherited isolated worktree.
- T006 is blocked by `B-T006-2` after retry exhaustion.
- T006's targeted/task-local frontend checks passed, but the full frontend
  suite and typecheck still expose failures outside the previous allowed scope.
- The remaining product work should be split into focused Alchemy tasks around
  the failing frontend files and route/sidebar wiring, not replayed as a broad
  phase restart.

New Alchemy issues found and addressed:

- Resuming a blocked phase did not automatically carry the prior blocker
  evidence into the first new phase attempt.
- Repair documents were too generic and did not preserve the concrete failed
  task, completed tasks, out-of-scope test failures, or timeout/splitting
  guidance.
- Bare `api key` and `auth` blocker marker matching could misclassify CRM
  identity/API-key product work as a non-repairable credential problem.

V2.88 adds focused `phase_repair_resume_NNN.md` generation and narrows the
credential markers. The next Billing Core resume should therefore enter
`phase_010` with a T006-focused repair brief.

## 2026-06-27 V2.89 Follow-Up

The supervised V2.88 relaunch proved that the repair brief was focused, but the
planner still produced the wrong task graph in `run_attempt_024` and
`run_attempt_025`.

New Alchemy issues found and addressed:

- Repair narrative containing phrases like "in allowed scope" could be parsed
  as a global allowed-scope contract, causing later "previous relevant files"
  evidence to narrow the whole phase to old task files.
- Frontend `large_refactor` planning was short-circuited by scoped file
  evidence before it reached the frontend task decomposition logic.
- `.vue` paths in repair evidence were not extracted, weakening the handoff for
  Vue frontend failures.
- A manually stopped bad attempt needed an explicit terminal marker so later
  resumes would not reuse it.

V2.89 fixes those issues. Rebuilding current `phase_010` inputs now produces
seven frontend `large_refactor` implementation tasks, including a usage/API-key
task scoped to `AccountUsageCell`, `UsageTable`, `EmailVerifyView`,
`usePersistedPageSize`, `DashboardView`, router, and sidebar files.

The timeout concern remains recorded as a follow-up rather than a reason to
blindly raise worker budgets. The next optimization should make timeout
handling progress-aware through heartbeats/checkpoints/bounded grace, while
keeping hard stops for stuck workers.

## 2026-06-27 V2.90 Follow-Up

The V2.89 relaunch answered the "is it looping?" question with concrete state:
`run_attempt_026` completed T001, T002, T003, and T004, then stopped at T005.
That is forward progress, not a from-scratch loop.

The T005 blocker was not a CRM product failure. Raw Codex JSONL showed the local
Codex CLI account hit a usage limit and reported a reset time of 5:39 PM. Before
V2.90, Alchemy collapsed that into "worker did not return parseable JSON", which
caused one debug task and one retry before the non-partial blocker stopped the
run.

V2.90 classifies this as an environment blocker:

- Codex CLI usage-limit JSONL is parsed before generic worker-output failure.
- Orchestrator records local model availability as `type=environment`.
- Full-roadmap auto-repair will not create CRM product repair attempts for
  usage-limit descriptions.

The correct next action is to wait for the usage window to reset, then resume
through Alchemy. Do not edit Billing Core product files from Codex Desktop to
work around an account quota blocker.

## Stop Rules

Continue iterating while Alchemy makes forward progress or exposes fixable
framework issues. Stop only if:

- local model access is unavailable and no approved provider path exists;
- required credentials or external payment/provider accounts are needed;
- the target worktree becomes unrecoverably inconsistent with no safe baseline;
- repeated Alchemy repairs produce no meaningful progress and the remaining
  system is less useful than restarting from a cleaner CRM scaffold.
