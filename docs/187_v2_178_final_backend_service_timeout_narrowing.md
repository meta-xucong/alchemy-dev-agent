# V2.178 Final Backend Service Timeout Narrowing

## Problem

Billing Core `final_verification/run_attempt_052` made real progress: T002 completed and T005 ran with progress detected. After the 900 second worker timeout plus one 300 second progress grace window, T005 still did not return and Alchemy correctly stopped at a non-partial timeout blocker.

The generated repair resume `_052` identified that T005 should be split, but the planner still rebuilt the same broad service/handler/server/cmd task under T005. Relaunching would likely spend another long worker window on the same scope.

## Fix

`planner/task_graph_builder.py` now narrows a focused final-verification T005 timeout without changing task IDs.

When a final-verification repair resume focuses T005, contains timeout evidence, and references the backend service/handler/server contract scope, T005 becomes `Repair final backend service contract leftovers` with a smaller file scope:

- `backend/internal/service/**`
- `backend/internal/domain/**`
- `backend/internal/repository/**`
- `backend/go.mod`
- `backend/go.sum`

Handler, server, command wiring, and broad verification remain for later audit-driven follow-up instead of being bundled into the same timed-out worker.

## Verification

- `python -m pytest tests/test_document_to_plan.py -k "backend_service_handler_timeout_is_narrowed or repair_context_builds_editable_repair_task"`
- `python -m pytest tests/test_document_to_plan.py`
- `python -m pytest tests/test_full_roadmap_execution.py`
- `python -m py_compile planner\task_graph_builder.py tests\test_document_to_plan.py`
- Real graph probe using `final_verification_repair_resume_052.md`

The real graph probe keeps T005 as the next task ID while narrowing its scope to service/domain/repository files.

## Next Step

Relaunch the supervised Billing Core final verification. The expected next worker is narrowed T005, not the previous broad backend service/handler/server/cmd worker.
