"""Objective-derived verifier that does not trust task completion."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from context.objective_models import ObjectiveContract
from context.reference_baseline import ReferenceBaseline
from context.semantic_inventory import RepositoryInventory
from runtime.verification_matrix import VerificationItem, VerificationMatrix


class IndependentVerifier:
    def verify(
        self,
        root: Path | str,
        contract: ObjectiveContract,
        inventory: RepositoryInventory,
        *,
        evidence: dict[str, dict[str, dict[str, Any]]] | None = None,
        reference_baseline: ReferenceBaseline | None = None,
        waivers: list[dict[str, Any]] | None = None,
    ) -> VerificationMatrix:
        fingerprint = repository_fingerprint(root)
        evidence = evidence or {}
        authorized_waivers = authorized_obligation_waivers(waivers or [])
        remaining_hits = {}
        for hit in inventory.hits:
            if hit.polarity == "forbidden":
                remaining_hits[hit.requirement_id] = remaining_hits.get(hit.requirement_id, 0) + 1
        items: list[VerificationItem] = []
        hard_failures: list[str] = []
        for requirement in contract.requirements:
            for obligation in requirement.proof_obligations:
                supplied = evidence.get(requirement.id, {}).get(obligation, {})
                waiver = authorized_waivers.get((requirement.id, obligation))
                if waiver:
                    status = "waived"
                    item_evidence = {"waiver": waiver}
                elif (
                    requirement.class_name.startswith("must_absent")
                    and obligation in _INVENTORY_OBLIGATIONS
                    and remaining_hits.get(requirement.id, 0)
                ):
                    status = "failed"
                    item_evidence = {"remaining_inventory_hits": remaining_hits[requirement.id]}
                elif requirement.class_name.startswith("must_absent") and obligation in _INVENTORY_OBLIGATIONS:
                    status = "passed"
                    item_evidence = {"remaining_inventory_hits": 0, "inventory_root": inventory.root_path}
                elif obligation == "reference_baseline_declared" and reference_baseline and reference_baseline.references:
                    status = "passed"
                    item_evidence = {
                        "reference_ids": [item.id for item in reference_baseline.references],
                        "reference_heads": [item.head for item in reference_baseline.references],
                    }
                elif supplied:
                    supplied_fingerprint = str(supplied.get("repository_fingerprint", ""))
                    if supplied_fingerprint != fingerprint:
                        status = "stale"
                        item_evidence = {
                            **supplied,
                            "reason": "Evidence repository fingerprint does not match the current target.",
                        }
                    elif str(supplied.get("status", "")).lower() == "passed":
                        status = "passed"
                        item_evidence = dict(supplied.get("evidence", supplied))
                    else:
                        status = "failed"
                        item_evidence = dict(supplied.get("evidence", supplied))
                else:
                    status = "unproven"
                    item_evidence = {"reason": "No fresh objective-derived evidence proves this obligation."}
                if requirement.strength == "must" and status not in {"passed", "waived"}:
                    if status == "failed" and requirement.class_name.startswith("must_absent"):
                        hard_failures.append(f"{requirement.id} has remaining forbidden inventory for {obligation}.")
                    else:
                        hard_failures.append(f"{requirement.id} obligation {obligation} is {status}.")
                items.append(
                    VerificationItem(
                        requirement_id=requirement.id,
                        obligation=obligation,
                        status=status,
                        repository_fingerprint=fingerprint,
                        evidence=item_evidence,
                    )
                )
        return VerificationMatrix(repository_fingerprint=fingerprint, items=items, hard_failures=sorted(set(hard_failures)))


def repository_fingerprint(root: Path | str) -> str:
    root_path = Path(root)
    digest = hashlib.sha256()
    if not root_path.exists():
        return "missing"
    skip = {".git", ".alchemy", ".codex-longrun", ".test-tmp", "node_modules", "vendor", "__pycache__"}
    for path in sorted(
        p
        for p in root_path.rglob("*")
        if p.is_file()
        and not p.is_symlink()
        and not any(part in skip for part in p.relative_to(root_path).parts)
    ):
        relative = path.relative_to(root_path).as_posix()
        digest.update(relative.encode("utf-8"))
        try:
            with path.open("rb") as stream:
                while chunk := stream.read(64 * 1024):
                    digest.update(chunk)
        except OSError:
            continue
    return "sha256:" + digest.hexdigest()


def run_independent_repository_checks(
    root: Path | str | None,
    *,
    timeout_seconds: int = 120,
) -> list[dict[str, Any]]:
    """Run only controller-selected repository checks and return their real results.

    Worker-reported command names are deliberately not accepted here.  The
    controller discovers a small, predictable set of repository-native test
    commands and executes them without a shell, so an agent cannot manufacture
    a passing exit code by editing its own result payload.
    """

    if root is None:
        return []
    target = Path(root).resolve()
    if not target.is_dir():
        return []
    checks = _discovered_checks(target)
    results: list[dict[str, Any]] = []
    for kind, command in checks:
        results.append(_run_independent_check(target, kind, command, timeout_seconds=timeout_seconds))
    return results


def independent_checks_passed(results: list[dict[str, Any]]) -> bool:
    """Return true only when an actual repository test/build check passed."""

    substantive = [item for item in results if str(item.get("kind", "")) in {"test", "build"}]
    return bool(substantive) and all(
        item.get("source") == "alchemy_controller"
        and item.get("executed") is True
        and _safe_exit_code(item.get("exit_code")) == 0
        for item in substantive
    )


def _discovered_checks(root: Path) -> list[tuple[str, list[str]]]:
    checks: list[tuple[str, list[str]]] = []
    python_tests = root / "tests"
    if python_tests.is_dir() and any(path.is_file() for path in python_tests.rglob("test*.py")):
        interpreter = _project_python(root)
        if _uses_pytest(root):
            checks.append(("test", [str(interpreter), "-m", "pytest", "-q"]))
        else:
            checks.append(("test", [str(interpreter), "-m", "unittest", "discover", "-s", "tests", "-q"]))

    go_mod = root / "go.mod"
    if go_mod.is_file():
        checks.append(("test", ["go", "test", "./..."]))

    package_json = root / "package.json"
    if package_json.is_file():
        try:
            package = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            package = {}
        scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
        if isinstance(scripts, dict) and str(scripts.get("test", "")).strip():
            checks.append(("test", ["npm", "test"]))
    return checks


def _project_python(root: Path) -> Path:
    candidates = (
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
    )
    return next((candidate for candidate in candidates if candidate.is_file()), Path(sys.executable))


def _uses_pytest(root: Path) -> bool:
    if any((root / name).is_file() for name in ("pytest.ini", "tox.ini")):
        return True
    if any(path.is_file() for path in root.rglob("conftest.py")):
        return True
    pyproject = root / "pyproject.toml"
    try:
        return "[tool.pytest" in pyproject.read_text(encoding="utf-8")
    except OSError:
        return False


def _run_independent_check(
    root: Path,
    kind: str,
    command: list[str],
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    display = " ".join(command)
    try:
        completed = subprocess.run(
            command,
            cwd=str(root),
            check=False,
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout_seconds)),
        )
        return {
            "command": display,
            "kind": kind,
            "exit_code": completed.returncode,
            "executed": True,
            "source": "alchemy_controller",
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": display,
            "kind": kind,
            "exit_code": 124,
            "executed": True,
            "source": "alchemy_controller",
            "stdout": str(exc.stdout or "")[-4000:],
            "stderr": "independent check timed out",
        }
    except OSError as exc:
        return {
            "command": display,
            "kind": kind,
            "exit_code": 127,
            "executed": False,
            "source": "alchemy_controller",
            "stdout": "",
            "stderr": str(exc)[-4000:],
        }


def _safe_exit_code(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


_INVENTORY_OBLIGATIONS = {
    "static_inventory_zero",
    "runtime_route_inventory_zero",
    "fresh_schema_inventory_zero",
    "public_contract_inventory_zero",
}


def authorized_obligation_waivers(waivers: list[dict[str, Any]], *, now: datetime | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    """Return only obligation-scoped, currently valid, authority-bound waivers."""

    now = now or datetime.now(UTC)
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for waiver in waivers:
        requirement_id = str(waiver.get("requirement_id", "")).strip()
        obligation = str(waiver.get("obligation", "")).strip()
        authority = str(waiver.get("authority", "")).strip()
        reason = str(waiver.get("reason", "")).strip()
        expires_at = str(waiver.get("expires_at", "")).strip()
        if waiver.get("authorized") is not True or not all((requirement_id, obligation, authority, reason, expires_at)):
            continue
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            continue
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if expiry <= now:
            continue
        result[(requirement_id, obligation)] = dict(waiver)
    return result
