"""Small JSON-schema subset validator for local intake contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def validate_project_brief_contract(
    payload: dict[str, Any],
    schema_path: str | Path | None = None,
) -> list[str]:
    path = Path(schema_path) if schema_path else Path(__file__).resolve().parents[1] / "specs" / "project_brief_schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    return validate_json_subset(payload, schema, schema, "$")


def validate_json_subset(payload: Any, schema: dict[str, Any], root: dict[str, Any], path: str) -> list[str]:
    errors: list[str] = []

    if "$ref" in schema:
        ref_schema = resolve_ref(schema["$ref"], root)
        return validate_json_subset(payload, ref_schema, root, path)

    if "anyOf" in schema:
        alternatives = [validate_json_subset(payload, alternative, root, path) for alternative in schema["anyOf"]]
        if any(not alternative_errors for alternative_errors in alternatives):
            return []
        return [f"{path}: does not match any allowed schema"]

    if "const" in schema and payload != schema["const"]:
        errors.append(f"{path}: expected constant {schema['const']!r}")

    if "enum" in schema and payload not in schema["enum"]:
        errors.append(f"{path}: expected one of {schema['enum']!r}")

    expected_type = schema.get("type")
    if expected_type and not matches_type(payload, expected_type):
        errors.append(f"{path}: expected type {expected_type}")
        return errors

    if expected_type == "object":
        errors.extend(validate_object(payload, schema, root, path))
    elif expected_type == "array":
        item_schema = schema.get("items", {})
        for index, item in enumerate(payload):
            errors.extend(validate_json_subset(item, item_schema, root, f"{path}[{index}]"))
    elif expected_type == "string":
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(payload) < min_length:
            errors.append(f"{path}: shorter than minLength {min_length}")
    elif expected_type == "integer":
        minimum = schema.get("minimum")
        if isinstance(minimum, int) and payload < minimum:
            errors.append(f"{path}: below minimum {minimum}")

    return errors


def validate_object(payload: dict[str, Any], schema: dict[str, Any], root: dict[str, Any], path: str) -> list[str]:
    errors: list[str] = []
    properties = schema.get("properties", {})

    for required_key in schema.get("required", []):
        if required_key not in payload:
            errors.append(f"{path}: missing required key {required_key!r}")

    if schema.get("additionalProperties") is False:
        for key in payload:
            if key not in properties:
                errors.append(f"{path}: unexpected key {key!r}")

    for key, value in payload.items():
        if key in properties:
            errors.extend(validate_json_subset(value, properties[key], root, f"{path}.{key}"))

    return errors


def resolve_ref(ref: str, root: dict[str, Any]) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise ValueError(f"Only local schema refs are supported: {ref}")
    current: Any = root
    for part in ref[2:].split("/"):
        current = current[part]
    return current


def matches_type(payload: Any, expected_type: str) -> bool:
    if expected_type == "object":
        return isinstance(payload, dict)
    if expected_type == "array":
        return isinstance(payload, list)
    if expected_type == "string":
        return isinstance(payload, str)
    if expected_type == "boolean":
        return isinstance(payload, bool)
    if expected_type == "integer":
        return isinstance(payload, int) and not isinstance(payload, bool)
    if expected_type == "null":
        return payload is None
    return True
