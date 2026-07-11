# V2.186 Hard-Prune Governance For Copy-And-Cut Projects

## Relationship To V2.187

This document remains the specialized hard-prune and negative-requirement
contract. `docs/195_v2_187_goal_locked_autonomous_development.md` is the parent
architecture that generalizes the Billing Core lessons into objective
compilation, governed reference repositories, semantic inventory,
requirement-locked planning, independent verification, strategy-aware recovery,
proof-based progress, and coherent delivery.

Implementations must apply both documents for copy-and-cut projects. V2.187
defines the autonomous convergence loop; V2.186 defines the stricter absence
rules within that loop.

## Problem

Billing Core exposed a structural failure in Alchemy's full-roadmap execution
model.

The source document did not ask for a thin wrapper around the copied Sub2API
system. It required a new Billing Core product whose first version excludes API
gateway behavior, upstream account pools, model forwarding, proxies, channel
scheduling, subscription plans, platform quotas, and token relay operations.

The original requirements were explicit:

- the copied source is only material for pruning;
- the new project must not behave as Sub2API Lite;
- backend token relay/API gateway routes must not be registered;
- frontend account-pool, upstream-account, proxy, model-scheduling, relay
  monitor, and channel-monitor pages must not be exposed;
- first-version payment is balance recharge only, not subscription plans or
  model entitlement fulfillment;
- fresh migrations must not create relay-era tables such as `accounts`,
  `account_groups`, `proxies`, gateway `channels`, `channel_monitors`,
  `model_mappings`, `user_subscriptions`, `subscription_plans`,
  `platform_quotas`, or upstream credential tables.

Alchemy made useful progress on wallets, metering, payment, route allowlists,
and final-verification stop boundaries, but the execution model drifted toward
contract repair instead of hard product pruning. The final tail repeatedly
opened tasks such as `Repair final platform RPM capacity surface contracts`,
`Repair final admin settings RPM capacity contracts`, and route/settings
leftovers. Those tasks were symptoms of a deeper issue: old relay domains still
existed in schema, services, frontend API modules, router surfaces, tests, and
copy.

The failure mode was not a single bad worker. It was a mismatch between the
required transformation and Alchemy's planning/evaluation incentives.

## Incident Evidence

The following Billing Core facts must be treated as regression fixtures for
V2.186:

- Backend route registration partially converged: `/v1/**` and
  `/backend-api/codex/**` relay entry points were not registered in the checked
  server tests.
- Old domains were still present in source and generated schema surfaces,
  including Ent schemas such as `account.go`, `account_group.go`, `group.go`,
  `subscription_plan.go`, and `user_subscription.go`.
- Backend service code still contained OpenAI/Gemini/Antigravity/Codex,
  upstream account, provider, and gateway concepts.
- Frontend API/service files still existed for old domains such as admin
  accounts, channels, subscriptions, and channel monitor behavior.
- Frontend router still exposed `/admin/orders/plans`, conflicting with the
  first-version ban on subscription/payment plans.
- Final verification was blocked in residual RPM/platform-capacity tasks, which
  are themselves inherited relay entitlement concepts rather than Billing Core
  v1 concepts.
- `run_attempt_168` completed the user platform-capacity API repair but timed
  out on `Repair final admin settings RPM capacity contracts`.
- `run_attempt_169`, launched from the corrected split resume with a shortened
  600 second worker budget, timed out on
  `Repair final backend admin RPM capacity contracts`.
- Alchemy correctly stopped dispatch after non-partial blockers in these runs,
  proving the scheduler was safer than before; however, safe stopping did not
  solve the product-governance failure.

## Root Cause

Alchemy lacked a first-class negative-requirement and hard-prune model.

The planner and evaluator could read language such as "must remove" or "must not
create", but they did not convert it into a mandatory absence inventory with
hard fail semantics. As a result, the system accepted weaker transformations:

- hide a route instead of deleting or decommissioning the domain;
- rename a relay concept into CRM language while keeping old semantics;
- quarantine compatibility code without a formal waiver;
- pass route tests while old schema/service/API/router files remain;
- treat remaining old domains as contract leftovers instead of as primary
  product-boundary violations;
- report high completion percentages from phase/test progress even when negative
  requirements were still violated.

This is especially dangerous for copy-and-cut projects. When the source
repository is copied from a larger legacy product, the hardest work is often not
adding features. It is proving that forbidden inherited domains are gone.

## Design Rule

For copy-and-cut projects, absence requirements are first-class deliverables.

If a source document says a capability, table, route, page, API module, service,
or product concept must be removed, Alchemy must treat continued presence as a
hard failure until one of these is true:

1. The artifact is deleted.
2. The artifact is rebuilt with a new source-approved semantic contract and the
   source document explicitly permits that new meaning.
3. The artifact is isolated behind an explicit waiver with owner, rationale,
   expiry, and proof that it cannot affect fresh install, runtime behavior,
   public API, frontend navigation, or delivered documentation.

Generic "not exposed as product behavior", "quarantined", "CRM-renamed", or
"route not registered" evidence is insufficient for a must-remove item.

## Negative Requirement Classes

The intake and context layers must classify each negative requirement into one
of these classes:

| Class | Meaning | Delivery rule |
| --- | --- | --- |
| `must_absent_runtime` | Route, command, daemon, menu, or reachable page must not be available. | Runtime and navigation probes must fail closed. |
| `must_absent_source` | Source files, modules, services, schemas, or generated clients must not remain in production source. | Inventory must show zero unwaived hits. |
| `must_absent_fresh_schema` | Fresh install/migration must not create a table, column, enum, index, or seed. | Fresh database contract must prove absence. |
| `must_absent_public_contract` | API payloads, DTOs, SDK types, docs, or i18n copy must not expose the concept. | Public contract and text probes must show zero unwaived hits. |
| `may_reframe` | A legacy name may remain only with new documented semantics. | Requires explicit source-approved semantic mapping and tests. |
| `may_waive_temporarily` | Temporary compatibility is allowed. | Requires waiver file and hard expiry; cannot count as final clean delivery. |

Unclassified negative requirements default to `must_absent_source` plus
`must_absent_runtime`.

## Required Artifacts

Hard-prune runs must produce these machine-readable artifacts:

```text
.alchemy/<run>/negative_requirements.json
.alchemy/<run>/forbidden_inventory.json
.alchemy/<run>/prune_manifest.json
.alchemy/<run>/absence_evidence.json
.alchemy/<run>/waivers.json
```

`negative_requirements.json` records each forbidden domain with source document
line references, class, examples, and allowed exceptions.

`forbidden_inventory.json` records every matching path/symbol/route/table/copy
hit before work starts. It must include categories:

- backend route registration;
- backend handlers, services, repositories, jobs, commands, config;
- Ent schema and generated clients;
- root migrations and embedded migrations;
- frontend router and navigation;
- frontend API/service modules;
- frontend views/components/composables/stores/types/tests;
- i18n and product copy;
- docs, deploy files, seed data, examples, and CI scripts.

`prune_manifest.json` records planned deletes, rewrites, reframes, and waivers.

`absence_evidence.json` records final probes proving zero unwaived hits.

`waivers.json` must be empty for projects whose source document requires final
demo absence with no compatibility exception.

## Hard-Prune Workflow

Copy-and-cut projects must use this workflow before normal feature completion
can be considered deliverable:

```text
source document
  -> negative requirement extraction
  -> forbidden inventory
  -> prune manifest
  -> deletion/rewrite waves
  -> compile and test repair
  -> absence probes
  -> normal acceptance tests
  -> final handoff
```

The first worker task must be read-only inventory, not implementation. The
second task must create a prune manifest. Implementation tasks must then follow
the manifest by category. Alchemy must not start broad final test convergence
until the inventory has either zero hits or explicit waivers.

## Planner Requirements

The planner must not convert a must-remove domain into a vague contract repair.

Bad task titles:

- `Repair final platform RPM capacity surface contracts`
- `Repair final admin settings RPM capacity contracts`
- `Repair final backend production source-boundary leftovers`
- `Repair final frontend retired source-boundary leftovers`

Acceptable task titles:

- `Delete forbidden fresh-migration relay tables`
- `Delete backend upstream account services and repositories`
- `Delete frontend admin account-pool API modules`
- `Remove subscription plan routes and router entries`
- `Remove channel monitor pages, composables, and tests`
- `Repair compile errors after account-pool deletion`
- `Prove forbidden relay inventory is zero`

Repair tasks may exist, but they must be downstream of concrete delete/rewrite
tasks. A timeout in a hard-prune task must split by inventory category and exact
path groups, not by semantic leftovers.

## Worker Prompt Requirements

Hard-prune worker prompts must say:

- deletion is expected when a file only supports a forbidden domain;
- tests may need to be deleted or rewritten when they assert forbidden behavior;
- generated code may need regeneration after schema deletion;
- route unregistration alone is not enough when source absence is required;
- keeping code with renamed labels is not enough unless the manifest marks the
  item `may_reframe`;
- broad verification is not part of deletion tasks; workers should run narrow
  compile/static checks and return precise remaining inventory.

Workers must return:

- deleted files;
- rewritten files;
- remaining forbidden hits;
- waived hits;
- narrow checks attempted;
- compile/test failures caused by the deletion wave.

## Evaluation Changes

The final gate must hard fail when any unwaived `must_absent_*` requirement has
remaining hits. Numeric score cannot override this rule.

For hard-prune projects, completion percentages must be capped:

- maximum 60% before a forbidden inventory exists;
- maximum 75% while any `must_absent_fresh_schema` hit remains;
- maximum 85% while any `must_absent_source` hit remains;
- maximum 90% while any `must_absent_runtime` or `must_absent_public_contract`
  hit remains;
- 100% only after absence probes, normal tests, final audit, simulation, and real
  checks all pass.

This prevents a run from reporting 99%+ while core "must remove" requirements
are still violated.

## Billing Core Regression Fixture

V2.186 must add a regression fixture based on Billing Core:

Input document facts:

- Billing Core is not a token relay or Sub2API Lite.
- Fresh migration must not create `accounts`, `account_groups`,
  `user_subscriptions`, `subscription_plans`, `platform_quotas`, proxy/channel
  tables, or upstream credential tables.
- Backend must not register or require gateway/upstream/proxy/model/channel
  routing behavior.
- Frontend must not expose account pools, upstream OAuth import, proxies, model
  settings, API relay monitoring, channel monitor pages, subscription plan
  purchase/management, or old product copy.

Fixture repository facts:

- Ent schema contains forbidden account/group/subscription files.
- Backend service layer contains upstream account/provider/gateway terms.
- Frontend API modules contain accounts/channels/subscriptions/channel monitor
  files.
- Router contains `/admin/orders/plans`.
- Route allowlist tests pass.

Expected Alchemy behavior:

- route allowlist pass does not pass final gate;
- planner emits hard-prune inventory and deletion tasks, not RPM contract repair;
- final evaluation contains hard failures for every unwaived forbidden inventory
  category;
- completion estimate remains below 85% until source/schema inventory is clean;
- no handoff is allowed even if existing tests pass.

## Implementation Plan

V2.186 should be implemented in these layers:

1. Intake/context:
   - extract negative requirements with source line references;
   - classify them into `must_absent_*`, `may_reframe`, or
     `may_waive_temporarily`;
   - seed default forbidden term/path patterns from explicit document examples.

2. Repository indexing:
   - add hard-prune inventory probes for routes, schemas, migrations, services,
     frontend APIs, router, pages, i18n, docs, and deploy files;
   - distinguish auth token/session terms from relay token terms using nearby
     context.

3. Planning:
   - insert inventory and prune-manifest tasks before implementation;
   - create delete-first tasks from inventory categories;
   - prevent generic "contract leftovers" tasks from replacing must-remove
     tasks.

4. Runtime/evaluator:
   - load `absence_evidence.json`;
   - add hard failures for unwaived forbidden hits;
   - cap progress percentages according to inventory state.

5. Final verification:
   - rerun absence probes after every repair wave;
   - fail final audit when "route not registered" is the only evidence for a
     source-absence requirement.

6. Evidence UI/reporting:
   - show forbidden inventory counts by category;
   - show deleted/reframed/waived counts separately;
   - require explicit user review for waivers.

## Non-Goals

V2.186 does not require Alchemy to delete code blindly. It requires the system to
make deletion obligations explicit, auditable, and impossible to hide behind
passing tests or renamed contracts.

It also does not ban compatibility code in all projects. It bans implicit
compatibility in final delivery when the source document says the copied legacy
domain must be removed.

## Acceptance Criteria

- A document that says "must remove X" creates a negative requirement and a
  forbidden inventory probe for X.
- Remaining unwaived forbidden inventory creates evaluator hard failures.
- Route allowlist success cannot satisfy source/schema absence requirements.
- Hard-prune task graphs start with inventory and prune manifest tasks.
- Timeout recovery splits hard-prune work by inventory category and exact files.
- Billing Core fixture fails final delivery while forbidden Ent schemas,
  services, frontend API modules, router entries, or fresh migration tables
  remain.
- Progress reporting cannot exceed the hard-prune caps.
- Waivers are explicit, reviewable, and cannot silently produce 100% delivery.
