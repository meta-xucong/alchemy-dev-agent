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

## 2026-06-27 V2.91 Follow-Up

After the 5:39 PM reset window, the Codex OK smoke passed and Billing Core was
relaunched through Alchemy. `run_attempt_028` correctly used a fresh attempt and
the inherited isolated worktree, but T001 stopped as an environment blocker.

That was a new Alchemy classifier false positive. The Codex subprocess exited
successfully; the raw JSONL merely contained historical repair evidence saying
that the previous usage-limit blocker had been resolved. V2.90 scanned the whole
JSONL stream for broad usage-limit substrings and therefore misclassified old
context as a live quota failure.

V2.91 narrows usage-limit detection:

- structured Codex `error`, `turn.failed`, and `response.failed` events still
  stop as environment blockers;
- explicit summaries, known issues, stderr, and plain non-JSON usage-limit
  errors still stop as environment blockers;
- ordinary successful JSONL command output that mentions historical usage-limit
  text no longer blocks the run.

`run_attempt_028` has a `supervisor_stop.json` marker so the next Billing Core
resume skips that false state. The execution chain remains correct: Codex
Desktop supervises, Alchemy real workers implement, and product code is edited
only inside the inherited run worktree.

## 2026-06-27 V2.92 Follow-Up

After V2.91, `run_attempt_029` proved the usage-limit false positive was fixed:
T001 completed, T002 completed, and T003 ran as a real frontend API cleanup
task.

T003 then exposed a different framework issue. The worker successfully narrowed
and tested the allowed API surface, but remaining direct retired API callers
were in `frontend/src/components/**`, `frontend/src/composables/**`, and
`frontend/src/constants/**`. `phase_repair_005.md` correctly asked the next
repair attempt to expand those files, but the rebuilt graph kept T003 on the
old API-only scope and put the needed paths into a later task. Because T003 can
stop the run before later tasks execute, this could replay the same blocker.

V2.92 expands the T003 "Clean frontend API service references" task so API
cleanup includes caller cleanup in components, composables, and constants. The
pre-fix `run_attempt_030` has a supervisor stop marker and should be skipped.
The next attempt should let T003 address the caller surface directly rather
than looping through the same non-partial blocker.

## 2026-06-27 V2.93 Follow-Up

`run_attempt_031` showed major forward progress after V2.92: T001 through T006
completed, including the previously difficult API-key/usage/admin workflow
area. T007 then hit the 900 second worker timeout.

The timeout guard itself behaved correctly. It killed the worker process tree,
recorded a non-partial technical blocker, and did not launch same-scope debug
work. But the next repair attempt, `run_attempt_032`, still rebuilt the broad
copy/i18n sweep instead of splitting it, even though `phase_repair_006.md`
explicitly said to checkpoint or split the workflow.

V2.93 addresses the timeout mechanism concern without simply raising the timer:
focused T007 timeout repairs now split the copy sweep into an i18n locale task
and a view/component/store/constants task. This should reduce the chance that a
worker making partial progress is repeatedly cut off by the same hard timeout.

Remaining timeout optimization: add real worker heartbeats/checkpoints and a
bounded grace policy so the supervisor can distinguish active progress from a
stuck worker near the timeout boundary.

## 2026-06-27 V2.94 Follow-Up

The next relaunch after V2.93 exposed one more recovery-chain issue.
`run_attempt_033` started at T001 and then activated T002 with the old broad
phase_010 graph. Starting at T001 is not automatically wrong because every
document run has a planning task, but this attempt was abnormal: it did not use
the existing `phase_repair_006.md` timeout brief and therefore did not generate
the split T007/T008 graph.

Root cause: the parent full-roadmap run had already written
`phase_repair_006.md`, but the persisted `phase_record.json` was still stale
and pointed at an older blocked attempt. The relaunch bootstrap path only used
the stale phase record or a newly generated resume brief, so it ignored the
newer disk repair document.

V2.94 fixes the handoff: if an ordinary `phase_repair_NNN.md` is newer than
`phase_record.json`, Alchemy passes the newest one to the next document runner.
The real phase_010 probe now selects `phase_repair_006.md` and generates
`T007 Sweep frontend i18n product copy`, `T008 Sweep frontend view and
component product copy`, and `T009 Complete remaining frontend closure
requirements`.

## 2026-06-27 V2.95 Follow-Up

`run_attempt_034` confirmed that V2.94 restored the correct repair brief and
split graph, but it also exposed remaining waste: after T001 completed, Alchemy
still dispatched T002 even though `phase_repair_006.md` said `Completed tasks
to preserve: T001, T002, T003, T004, T005, T006`.

That was not the old "broad T007" loop, but it was still unnecessary repeat
work. A human supervisor would naturally remember not to rerun completed
chapters; V2.95 makes that explicit in Alchemy. The planner now marks task IDs
listed in `Completed tasks to preserve` as completed in the rebuilt graph, with
preservation evidence attached. The real phase_010 graph probe now shows T001
through T006 completed and T007/T008/T009 pending.

This means the next controlled resume should skip the repeated T002-T006
frontend work and start from the split copy/i18n repair boundary.

## 2026-06-27 V2.96 Follow-Up

The V2.95 relaunch confirmed that completed-task preservation worked. In
`run_attempt_035`, T001 through T008 were all completed or preserved, and the
new split copy tasks T007 and T008 both finished. The remaining broad T009
frontend closure task then hit the 900 second timeout.

The next launch, `run_attempt_036`, did not go back to T002-T006; that part was
fixed. But it still recreated the same broad T009 task from `frontend/**`
instead of following `phase_repair_007.md`'s instruction to split or checkpoint
before replay. I stopped that run before it spent the full worker window.

V2.96 splits focused T009 timeout repair into shell/route, state/API, and
view/component closure tasks. The real phase_010 graph probe now shows T001
through T008 completed and T009 through T011 pending as narrower work packages.

Current token-cost judgment: many T001 nodes are normal because each attempt
has a planning task, but the recent high cost is not the expected mature
Alchemy baseline. It came from bootstrapping Alchemy's resume, repair-brief,
completed-task preservation, usage-limit detection, Windows worker, and timeout
split behavior while using a large legacy project as the integration test.
Those fixes are exactly the work needed to make later Alchemy development
cheaper than manual chapter-by-chapter Codex supervision.

## 2026-06-27 V2.97 Follow-Up

After V2.96, `run_attempt_037` proved the run no longer resumed the old broad
T009 task, but it exposed a subtler recovery problem. The relaunch passed only
`phase_repair_007.md`, not the earlier `phase_repair_006.md` that had split
the broad copy task into T007 and T008.

That caused task IDs to drift. `Completed tasks to preserve: T008` was applied
to a newly generated shell/route closure task, even though the real completed
T008 was the previous view/component copy task. I stopped `run_attempt_037`
before Alchemy could continue on a falsely completed graph.

V2.97 changes the full-roadmap bootstrap to pass recent ordinary repair briefs
up to the configured repair-document limit. The real phase_010 probe now passes
both `phase_repair_006.md` and `phase_repair_007.md`, preserving T001 through
T008 correctly and leaving T009 through T011 pending as the three remaining
frontend closure tasks.

This is a newly discovered issue from the interrupted/restarted supervision
cycle. It reinforces the main conclusion: the token overrun has come from
making Alchemy remember and reuse context that a human supervisor would keep in
working memory, not from an inherent impossibility of agentic development.

## 2026-06-27 V2.98 Follow-Up

After V2.97, `run_attempt_038` finally resumed on the correct cumulative graph.
It preserved T001 through T008, completed T009 shell/route closure, then hit
the 900 second timeout on T010 state/API closure.

The timeout behavior itself was correct: no debug task, no same-scope retry,
and a non-partial `technical_limit` blocker. The new framework issue was that
the parent did not write `phase_repair_008.md`, because the two historical
repair context docs consumed the same count as newly generated repair docs.

V2.98 separates those concepts. Historical repair context no longer consumes
the current parent run's new-repair budget, and blocked-phase resume briefs
also include recent ordinary repair context even when `phase_record.json` is
newer. The next relaunch should be able to carry 006/007 context, generate a
focused T010 repair, and split the state/API closure task instead of losing
the graph again.

## 2026-06-27 V2.99 Follow-Up

The V2.98 relaunch wrote `phase_repair_resume_004.md` and rebuilt the graph
with 006/007/resume context, preserving T001 through T009 correctly. It still
activated the same T010 state/API closure task that had already timed out.

I stopped `run_attempt_039` before it spent another full worker window. V2.99
now splits focused T010 timeout repair into API service, store/composable, and
constants/type closure tasks. The real phase_010 graph probe now preserves
T001 through T009 and leaves T010 through T013 pending as smaller closure
tasks.

## 2026-06-27 V2.100 Follow-Up

`run_attempt_040` confirmed that V2.99 was effective. The graph preserved
T001 through T009, completed the new narrow T010 API service closure task, and
advanced to T011. This is not a T001 loop and not a full restart.

The same T010 worker exposed a separate token-cost issue. It completed the
task, but the Codex worker turn carried very large command output and raw event
evidence from broad searches and a dirty large worktree. Alchemy already
truncated final raw output before saving it, but that happens after the worker
model has spent tokens reading command output.

V2.100 adds prompt-level output-budget rules for real Codex workers and caps
structured text fields in parsed worker results. This should reduce both live
worker token burn and later repair-context pollution. It does not eliminate the
need for progress-aware heartbeats/checkpoints, which remains the next
controller optimization.

Current judgment on token use: the many T001 labels are mostly normal per-run
planning nodes, but the historical token overrun was not normal mature
Alchemy behavior. It came from using a very large legacy migration to harden
Alchemy's resume, timeout, repair-context, preservation, and now worker-output
controls. Ordinary Alchemy development should be cheaper after these fixes,
but large repositories still need strict output budgets and task slicing.

## 2026-06-27 V2.101 Follow-Up

While applying V2.100 supervision, I wrote `run_attempt_040/supervisor_stop.json`
after T010 completed. T011 then completed, but the still-running parent
dispatched T012 anyway. This exposed a live-control bug: the marker file was
used by future resume selection but not by the running document-run controller.

I stopped the clearly scoped `run_attempt_040` process tree to avoid further
pre-V2.100 worker token burn. V2.101 adds a marker-file execution controller
and wires it into `DocumentRunPipeline` by default. From now on,
`supervisor_stop.json` and `operator_stop.json` should stop dispatch before the
next task and request cancellation while a worker is running.

Current phase_010 state after this supervised stop: T010 and T011 completed;
T012 is active only as stale state because its process was terminated. The next
Alchemy relaunch must skip `run_attempt_040` as supervisor-stopped and must not
blindly resume stale T012.

## 2026-06-27 V2.102 Follow-Up

After V2.101, the next risk was losing good work from `run_attempt_040`.
`phase_record.json` still pointed at older `run_attempt_038`, so a naive
bootstrap would only know that broad T010 had timed out. It would not know that
the V2.99 split T010 and T011 had already completed.

The first graph probe confirmed the danger: T010/T011 could be preserved
against the wrong task titles if the prior T010 split context was not kept.
V2.102 fixes this by generating/reusing a supervisor-stopped context brief from
newer stopped attempts. The brief preserves completed task IDs from the stopped
attempt and keeps the T010 timeout split context active so task IDs do not
drift.

The real phase_010 graph now rebuilds to the correct continuation boundary:
T001 through T011 completed, T012 constants/type closure pending, T013 view
workflow closure pending, then verification/review. This is now safe to relaunch
through Alchemy without replaying T010/T011.

## 2026-06-27 V2.103 Follow-Up

After V2.102, Alchemy resumed phase_010 and completed the remaining frontend
closure nodes through T016. The product-side progress is now high, but the phase
still did not promote: `run_attempt_041` scored 0.425 because frontend build
failed, and later repair attempts reached 0.70 without fixing the actual build
blocker.

The concrete CRM blocker was not hidden in the product code. T014 recorded it
clearly: `pnpm --dir frontend run build` could not resolve the raw Markdown
imports used by `frontend/src/components/admin/AdminComplianceDialog.vue`.
The expected files are `docs/legal/admin-compliance.zh.md` and
`docs/legal/admin-compliance.en.md`.

The Alchemy bug was in evidence handoff. Because T014 itself was marked
`completed`, the repair document preserved T001 through T016 but did not carry
the failing command, known issue, follow-up task, or target file paths into the
next planner pass. V2.103 fixes that handoff and recovers historical
verification issue evidence from prior run attempt state files, so the next
Alchemy relaunch should create a new focused repair task beyond the preserved
T001-T016 range.

Current delivery estimate remains roughly 85%-88% complete. The remaining work
is to let Alchemy repair this phase_010 build blocker, promote phase_010, then
run phase_011 schema/build cleanup and phase_012 demo smoke/final handoff.

## 2026-06-28 V2.104 Follow-Up

The V2.103 relaunch entered the correct worktree and proved the execution chain
is now healthy: T017 was dispatched to an Alchemy real worker in the inherited
isolated worktree, not to the original checkout. The worker added
`docs/legal/admin-compliance.zh.md` and `docs/legal/admin-compliance.en.md`.
Frontend install, tests, production build, and lint passed.

The phase still blocked because the regenerated repair graph no longer carried
coverage nodes for some old frontend closure requirements after suppressing the
broad fallback task. That was an Alchemy traceability issue, not a failed CRM
product fix.

V2.104 adds a completed `Preserve completed frontend closure coverage` node for
these fully preserved repair resumes. The node maps unmatched original
requirements to preserved completion evidence without opening another broad
`frontend/**` worker. The next relaunch should keep T017 as the only product
repair task, carry preserved coverage through T018, then verify/review with
T019/T020.

## Stop Rules

Continue iterating while Alchemy makes forward progress or exposes fixable
framework issues. Stop only if:

- local model access is unavailable and no approved provider path exists;
- required credentials or external payment/provider accounts are needed;
- the target worktree becomes unrecoverably inconsistent with no safe baseline;
- repeated Alchemy repairs produce no meaningful progress and the remaining
  system is less useful than restarting from a cleaner CRM scaffold.
