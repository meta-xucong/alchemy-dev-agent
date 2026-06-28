# V2.139 Final Frontend Admin Component Timeout Split

## Problem

After V2.138, Billing Core `final_verification/run_attempt_013` preserved T001-T009, completed
T010 `Repair final frontend account component contracts`, and then timed out on T011
`Repair final frontend admin operation component contracts`.

T011 still bundled several unrelated admin component families in one worker:

- `frontend/src/components/admin/account/**`
- `frontend/src/components/admin/user/**`
- `frontend/src/components/admin/channel/**`
- `frontend/src/components/admin/monitor/**`
- `frontend/src/components/admin/payment/**`
- `frontend/src/components/admin/usage/**`
- `frontend/src/components/channels/**`

The timeout boundary was correct: Alchemy recorded `B-T011-1`, stopped the run, did not launch a same-scope
debug worker, and did not dispatch downstream tasks. The remaining controller problem was the next resume graph:
it must preserve T001-T010 and split T011 instead of replaying the broad admin component worker.

## Change

`planner/task_graph_builder.py` now detects final-verification T011 admin component timeout context and preserves
the prior frontend split shape while splitting T011 into narrower serial tasks:

- `Repair final frontend admin account identity components`
- `Repair final frontend admin connector channel components`
- `Repair final frontend admin monitor components`
- `Repair final frontend admin usage payment components`

The downstream final frontend tasks continue after those split admin scopes:

- `Repair final frontend analytics and shared component contracts`
- `Repair final frontend view page contracts`
- `Repair final frontend state composable utility contracts`
- `Repair final frontend test and fixture contracts`

`autodev/full_roadmap_executor.py` also raises the final-verification minimum iteration budget from 12 to 24.
This protects the newly split serial tail from stopping at the iteration limit after useful progress.

## Verification

- Focused document-to-plan regression for T011 admin component timeout splitting.
- Focused full-roadmap regression for writing `final_verification_repair_resume_009.md`.
- Existing V2.137/V2.138 frontend timeout split regressions remain in place.
- The next real Billing Core probe should generate `final_verification_repair_resume_009.md`, preserve T001-T010,
  and start at `Repair final frontend admin account identity components`.
