# V2.180 Final Audit Delivery Repair Scope

## Problem

Billing Core `final_verification/run_attempt_054` proved the V2.179 launch recovery worked: T005 and T054 completed in the inherited worktree. The next blocker was T060 final audit evidence.

The generated repair resume initially preserved T005 even though the audit named `backend/internal/handler/admin/account_data.go` and an undefined `service.AccountTypeUpstream` reference. The graph also did not create an editable task for delivery artifacts such as `README.md`, `deploy/docker-compose*.yml`, `deploy/config.example.yaml`, and `deploy/relay`.

Launching the next worker from that graph would have repaired only part of the T060 findings.

## Fix

`autodev/full_roadmap_executor.py` now treats `AccountTypeUpstream` and `account_data.go` audit evidence as concrete backend repair targets. That reopens the backend domain/service/handler repair path instead of preserving it as complete.

`planner/task_graph_builder.py` now adds `Repair final delivery artifact contracts` when final-verification repair evidence names README/deploy/docker delivery artifacts together with retired relay, gateway, proxy, or old-domain findings.

## Verification

- `python -m pytest tests/test_document_to_plan.py -k "final_audit_focus_adds_delivery_artifact_repair or final_audit_focus_keeps_deep_tail_shape_when_tail_tasks_reopen"`
- `python -m pytest tests/test_document_to_plan.py`
- `python -m pytest tests/test_full_roadmap_execution.py -k "final_verification_resume_preserves_supervisor_stopped_progress or final_verification_resume_uses_latest_non_stopped_failed_state"`
- `python -m compileall autodev planner tests -q`
- Real helper probe generated `final_verification_repair_resume_055.md` from `run_attempt_054`
- Real graph probe using `_055`

The real `_055` graph has 64 nodes. It reopens backend repair work, keeps the frontend T060 evidence repair chain editable, adds T060 `Repair final delivery artifact contracts`, and moves final audit to T061 so it waits for the product and delivery repairs.

## Next Step

Relaunch Billing Core through the existing supervised probe. The expected next worker should start from the reopened backend repair chain in the inherited worktree, then continue to frontend and delivery repairs before rerunning final audit.
