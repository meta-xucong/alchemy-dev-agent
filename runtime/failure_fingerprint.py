"""Failure fingerprinting for strategy-aware convergence recovery."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def failure_fingerprint(requirement_gaps: list[str], inventory_counts: dict[str, int], failure_kind: str) -> str:
    payload = {"failure_kind": failure_kind, "requirement_gaps": sorted(requirement_gaps), "inventory_counts": inventory_counts}
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
