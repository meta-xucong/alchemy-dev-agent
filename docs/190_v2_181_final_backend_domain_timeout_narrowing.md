# V2.181 Final Backend Domain Timeout Narrowing

## Problem

Billing Core `final_verification/run_attempt_055` correctly consumed the V2.180 repair graph and started in the inherited worktree, but T004 `Repair final backend domain and repository contracts` timed out after the 900 second worker budget.

The generated `_056` resume captured the non-partial timeout, but the planner still rebuilt the same broad `backend/internal/domain/**` plus `backend/internal/repository/**` task. The resume also risked dropping unresolved repair surfaces that were carried by the previous `_055` resume, such as README/deploy/relay delivery artifacts.

## Fix

`autodev/full_roadmap_executor.py` now promotes focused timeout task IDs into the top-level repair scope. It also carries forward the previous final-verification repair context when a newer timeout resume is generated from an attempt that referenced an earlier repair resume.

`planner/task_graph_builder.py` now narrows a focused T004 timeout to `Repair final backend domain repository contract leftovers` without changing the task ID. The narrowed task uses concrete files:

- `backend/internal/domain/constants.go`
- `backend/internal/repository/account_repo.go`
- `backend/internal/repository/channel_repo.go`
- `backend/internal/repository/http_upstream.go`
- `backend/internal/repository/proxy_repo.go`
- `backend/go.mod`
- `backend/go.sum`

## Verification

- `python -m pytest tests/test_document_to_plan.py -k "backend_domain_repository_timeout_is_narrowed or backend_service_handler_timeout_is_narrowed or final_audit_focus_adds_delivery_artifact_repair"`
- `python -m pytest tests/test_document_to_plan.py`
- `python -m pytest tests/test_full_roadmap_execution.py -k "final_verification_resume_preserves_supervisor_stopped_progress or final_verification_resume_uses_latest_non_stopped_failed_state"`
- `python -m compileall autodev planner tests -q`
- Real helper probe generated `final_verification_repair_resume_057.md`
- Real graph probe using `_057`

The real `_057` graph has 64 nodes. T004 is narrowed to exact backend domain/repository leftovers, T005 waits for T004, the frontend repair chain remains open, T060 delivery artifact repair is preserved, and final audit waits at T061.

## Next Step

Relaunch Billing Core through the existing supervised probe and monitor that `run_attempt_056` starts with narrowed T004 in the inherited worktree.
