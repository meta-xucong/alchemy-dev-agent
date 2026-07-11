"""Requirement-locked task contract validation."""

from __future__ import annotations

from typing import Any


def validate_task_contract(task: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in ("requirement_ids", "transformation_ids", "expected_final_state"):
        if not task.get(field):
            errors.append(f"Task {task.get('id', '<unknown>')} lacks {field}.")
    if not task.get("read_only") and not task.get("allowed_write_paths"):
        errors.append(f"Task {task.get('id', '<unknown>')} lacks allowed_write_paths.")
    if task.get("read_only") and task.get("allowed_write_paths"):
        errors.append(f"Task {task.get('id', '<unknown>')} read-only task declares write paths.")
    if task.get("size") in {"medium", "large"} and not task.get("required_strategy_decision"):
        errors.append(f"Task {task.get('id', '<unknown>')} medium/large edit lacks required strategy decision.")
    if task.get("action") == "delete" and task.get("expected_final_state", {}).get("inventory_hits") != 0:
        errors.append(f"Task {task.get('id', '<unknown>')} delete task does not require zero inventory.")
    return errors
