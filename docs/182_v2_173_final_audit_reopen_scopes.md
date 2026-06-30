# V2.173 Final Audit Reopen Scopes

## Problem

After V2.172, the controlled final-verification relaunch correctly preserved the deep frontend test tail and reran T060.

`final_verification/run_attempt_046` then behaved correctly as a runtime stop boundary:

- T056-T059 stayed completed.
- T060 ran as a read-only final audit.
- T060 returned `FINAL_AUDIT_STATUS=FAIL` with a non-partial `technical_limit` blocker.
- T061-T064 were not dispatched.

The remaining problem was the next repair handoff. T060 is an audit task with no editable files, so its findings must be mapped back to editable frontend repair tasks. The previous preserve logic could keep those tasks completed, causing the next launch to rerun T060 instead of repairing the product.

Two related issues caused the bad handoff:

- Repair-scope matching used weak glob semantics for paths such as `frontend/src/components/**/__tests__/**`, so deep frontend files could fail to reopen the task that owned them.
- When T056/T057 were removed from the completed-preserve list, the planner lost the signal that this was still the deep final frontend tail graph and compressed the graph again.

## Change

`autodev/full_roadmap_executor.py` now uses segment-aware recursive glob matching for repair target paths, matching the worker allowed-file semantics.

T060 audit findings now infer focused target hints for stable final-audit surfaces:

- `/admin/ops` maps to the frontend router, ops API module, and ops view tree.
- `UsageTable` / image usage tooltip findings map to the UsageTable component and spec.

The resume document now records deep final frontend tail graph shape separately from the completed-preserve list:

`Preserve final frontend split tail graph shape: T056, T057, T058, T059`

This lets Alchemy reopen T056/T057 or earlier frontend repair tasks while still keeping the 63-node final-verification graph shape.

`planner/task_graph_builder.py` now recognizes that graph-shape signal. It also narrows the split frontend test scopes so component spec failures do not unnecessarily reopen the API/integration test task through a broad `frontend/src/**/*.spec.ts` pattern.

`runtime/orchestrator.py` received the same segment-aware recursive glob matching for scope comparisons.

## Verification

- `tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_repair_scope_matching_supports_recursive_frontend_globs`
- `tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_final_audit_usage_and_ops_findings_reopen_preserved_frontend_scopes`
- `tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_final_audit_resume_records_deep_tail_shape_separately_from_preserve`
- `tests/test_document_to_plan.py::DocumentToPlanTests::test_final_audit_focus_keeps_deep_tail_shape_when_tail_tasks_reopen`
- `tests/test_runtime.py::CodexWorkerTests::test_orchestrator_scope_globs_match_nested_frontend_paths`
- `tests/test_full_roadmap_execution.py`
- `tests/test_document_to_plan.py`
- `python -B -m compileall autodev runtime planner tests`

## Real Billing Core Probe

The real `final_verification_resume_repair_documents` probe generated `final_verification_repair_resume_044.md` from `run_attempt_046`.

The preserve list now keeps the completed backend and frontend tail work, but reopens the frontend scopes implicated by T060:

- T006 frontend API module contracts
- T009 frontend route and app shell contracts
- T024 frontend admin usage component
- T039 frontend admin user/usage/redeem view contracts
- T041 frontend admin operations view contracts
- T056 frontend API/integration test contracts
- T057 frontend component/composable test contracts

The real graph probe using `_044` produced 63 nodes:

- 52 completed
- 11 pending
- pending repair tasks: T006, T009, T024, T039, T041, T056, T057
- pending gates: T060 final audit, T061 simulation probes, T062 real repository checks, T063 handoff review

This is the desired recovery shape: Alchemy should repair the current final-audit findings in the inherited worktree before rerunning final audit and repository checks.
