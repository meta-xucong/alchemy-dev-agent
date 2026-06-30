# V2.172 Final Audit Deep Tail And Gate Preservation

## Problem

After V2.171 generated a correct T060-focused resume document, the controlled relaunch created `final_verification/run_attempt_045`.

That attempt revealed another Alchemy planner/gate bug:

- The resume document preserved old deep final-verification task IDs T001-T059 and focused T060.
- The planner compressed the graph back to a 30-node version.
- `mark_preserved_completed_tasks` then applied old task IDs to different new nodes, marking the compressed final audit, simulation, real-check, and review gates as completed from preserve evidence.
- The evaluator reported `final_score=1.0`, so the final-verification worker wrote a false `passed` result.

The CRM product was not actually re-audited. This was an Alchemy ID-drift and promotion-gate issue.

## Change

`planner/task_graph_builder.py` now treats a final audit focused resume that preserves T056-T059 as proof that the V2.170 frontend test/fixture split tail must remain expanded.

The deep final frontend tail preservation switch now also enables the V2.170 `split_frontend_test_fixtures` family, so the planner keeps:

- T056 `Repair final frontend API and integration test contracts`
- T057 `Repair final frontend component and composable test contracts`
- T058 `Repair final frontend view router i18n utility test contracts`
- T059 `Repair final frontend test config and fixture contracts`
- T060+ final audit and verification gates

`autodev/phase_promotion.py` now rejects `final_verification` promotion when final gate tasks such as audit, simulation probes, real repository checks, or handoff review are completed only by `focused_repair_preserved_task` evidence. Those gates must rerun after repair.

## Verification

- `tests/test_document_to_plan.py::DocumentToPlanTests::test_final_verification_test_fixture_focus_preserves_deep_tail_graph`
- `tests/test_document_to_plan.py::DocumentToPlanTests::test_final_audit_focus_preserves_test_fixture_split_tail`
- `tests/test_full_roadmap_execution.py::FullRoadmapExecutionTests::test_final_verification_promotion_rejects_preserved_gate_tasks`
- `tests/test_document_to_plan.py`
- `tests/test_full_roadmap_execution.py`
- `python -B -m compileall planner autodev tests -q`

## Real Billing Core Probe

Using the real `final_verification_repair_resume_041.md` and inherited Billing Core worktree, the planner now produces a 63-node graph with:

- T056-T059 completed
- T060 `Audit final requirements and phase evidence` pending
- T061 `Run final simulation probes` pending
- T062 `Run final real repository checks` pending
- T063 `Review final handoff markers` pending

The old false `run_attempt_045` payload is now rejected by `phase_promotion_decision` with:

`Final verification gate tasks must rerun after repair, not be preserved as completed: T026, T027, T028, T029.`

The next controlled relaunch should create a fresh final-verification attempt instead of trusting the false pass.
