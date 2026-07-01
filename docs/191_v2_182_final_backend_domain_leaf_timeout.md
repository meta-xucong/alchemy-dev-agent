# V2.182 Final Backend Domain Leaf Timeout

## Problem

Billing Core `final_verification/run_attempt_056` consumed the V2.181 graph correctly: T004 ran in the inherited worktree with concrete backend domain/repository files and T005 was not dispatched early. The worker still exhausted the 900 second budget.

The controller behavior was safe, but the next resume needed a smaller checkpoint. Replaying the same seven-file T004 scope would repeat the timeout.

## Fix

`autodev/full_roadmap_executor.py` now writes top-level focused timeout task titles into repair resumes and can recover previous final-verification repair documents from report project/context documents, not only from top-level repair-document fields.

`planner/task_graph_builder.py` now treats a repeated timeout of `Repair final backend domain repository contract leftovers` as a second-level split while keeping task ID T004 stable:

- `backend/internal/domain/constants.go`
- `backend/internal/repository/account_repo.go`
- `backend/go.mod`
- `backend/go.sum`

## Verification

- `python -m pytest tests/test_document_to_plan.py -k "backend_domain_repository"`
- `python -m pytest tests/test_document_to_plan.py`
- `python -m pytest tests/test_full_roadmap_execution.py -k "final_verification_resume_preserves_supervisor_stopped_progress or final_verification_resume_uses_latest_non_stopped_failed_state"`
- `python -m compileall autodev planner tests -q`
- Real helper probe generated `final_verification_repair_resume_059.md`
- Real graph probe using `_059`

The real `_059` graph keeps T004 stable, narrows it to the domain/account-repository leaf, preserves T005/frontend/delivery repairs, and keeps final audit behind T060.
