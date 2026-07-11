"""Independent verification matrix for V2.187."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class VerificationItem:
    requirement_id: str
    obligation: str
    status: str
    repository_fingerprint: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "obligation": self.obligation,
            "status": self.status,
            "repository_fingerprint": self.repository_fingerprint,
            "evidence": dict(self.evidence),
        }


@dataclass(slots=True)
class VerificationMatrix:
    repository_fingerprint: str
    items: list[VerificationItem]
    hard_failures: list[str] = field(default_factory=list)

    @property
    def revision(self) -> str:
        canonical = {
            "repository_fingerprint": self.repository_fingerprint,
            "items": [item.to_dict() for item in self.items],
            "hard_failures": list(self.hard_failures),
        }
        encoded = json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "2.187",
            "repository_fingerprint": self.repository_fingerprint,
            "revision": self.revision,
            "items": [item.to_dict() for item in self.items],
            "hard_failures": list(self.hard_failures),
            "summary": {
                "total": len(self.items),
                "passed": len([item for item in self.items if item.status == "passed"]),
                "failed": len([item for item in self.items if item.status == "failed"]),
                "stale": len([item for item in self.items if item.status == "stale"]),
                "unproven": len([item for item in self.items if item.status == "unproven"]),
                "waived": len([item for item in self.items if item.status == "waived"]),
            },
        }
