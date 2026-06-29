# V2.154 Final Frontend Admin Announcement Backup Promo Split

## Problem

After V2.153, Billing Core `final_verification/run_attempt_028` made real progress:

- T031 `Repair final frontend admin email template editor leaf file` completed.
- T032 `Repair final frontend admin compliance dialog file` completed.
- T033 `Repair final frontend admin settings support files` completed.

Alchemy then advanced to T034 `Repair final frontend admin announcement backup promo files`, which timed out at the
900 second worker boundary. The task still bundled announcement, backup, promo-code, announcement components, shared
styles, and shared types.

The regression test also exposed a second Alchemy issue: for deep final-frontend failures such as T034, some earlier
split-preservation ranges ended too early. A fresh graph could preserve completed task IDs against a compressed graph,
which risks task-ID drift and accidental replay or accidental completion of the wrong split node.

## Change

- `planner/task_graph_builder.py` now recognizes focused T034 timeouts on
  `Repair final frontend admin announcement backup promo files`.
- The next graph splits that task into:
  - `Repair final frontend admin announcements view file`
  - `Repair final frontend admin backup view file`
  - `Repair final frontend admin promo codes view file`
  - `Repair final frontend admin announcement components support files`
- Deep T034+ failures now force preservation of the relevant earlier final-frontend split chain, including
  view/component, admin view, settings/email, email-template leaf, user/create-edit, usage/payment, payment/refund, and
  announcement split surfaces.
- Preservation ranges for earlier split families now extend through the final-verification tail so completed task IDs
  are not applied to a compressed graph.

## Verification

- Focused announcement/backup/promo split regression.
- Six-layer focused final-frontend split regression.
- Full `tests/test_document_to_plan.py`.
- Full `tests/test_full_roadmap_execution.py`.

## Follow-Up

The next relaunch must confirm the real Billing Core graph preserves T001-T033 and starts the pending work at the
announcement split instead of replaying the old T034 bundle.
