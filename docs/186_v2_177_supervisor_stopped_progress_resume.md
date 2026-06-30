# V2.177 Supervisor-Stopped Progress Resume

## Problem

After V2.176, Billing Core `run_attempt_050` showed that final-verification resume generation could still reuse stale `_045` context and rerun T009, even though `run_attempt_049` had already completed T009 before Codex Desktop stopped the wrongly dispatched T056 worker.

This made progress preservation dependent on whether the latest stopped attempt was treated as a real failure. Operator-stopped attempts were correctly filtered as control-plane noise, but their completed task progress could also be lost.

## Fix

`autodev/full_roadmap_executor.py` now detects supervisor-stopped final-verification attempts that contain completed tasks not yet preserved by the latest valid repair resume.

When such progress exists, Alchemy writes a progress-preserving final-verification repair resume instead of falling back to an older failed attempt. The generated resume:

- Preserves newly completed tasks such as T009.
- Keeps final-verification repair context markers including source-boundary and final gate status markers.
- Does not treat operator-cancelled tasks such as T056 as product failures.
- Reuses the newest valid progress resume instead of letting older recovered failures overwrite it.

## Verification

- `python -m pytest tests/test_full_roadmap_execution.py -k "supervisor_stopped_progress or latest_non_stopped_failed_state"`
- `python -m pytest tests/test_full_roadmap_execution.py`
- `python -m pytest tests/test_document_to_plan.py`
- `python -m py_compile autodev\full_roadmap_executor.py tests\test_full_roadmap_execution.py`
- Real helper probe generated `final_verification_repair_resume_050.md` from `run_attempt_049`.
- Real graph probe using `_050` produced a 63-node graph with T009 completed and T024 as the first ready task.

## Next Step

Relaunch the supervised Billing Core final verification through the V2.88 entrypoint. The expected next worker is T024, not T009, T056, or T060.
