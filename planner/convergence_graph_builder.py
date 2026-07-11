"""Goal-locked task graph builder for V2.187 runs."""

from __future__ import annotations

from context.objective_models import ObjectiveContract
from context.reference_baseline import ReferenceBaseline
from context.semantic_inventory import RepositoryInventory
from planner.task_contract_validator import validate_task_contract
from planner.transformation_manifest import TransformationItem, TransformationManifest
from runtime.models import Dependency, TaskGraph, TaskNode


class ConvergenceGraphBuilder:
    """Build requirement-locked state-transition tasks from a manifest."""

    def build(
        self,
        *,
        project_id: str,
        objective_contract: ObjectiveContract,
        reference_baseline: ReferenceBaseline,
        repository_inventory: RepositoryInventory,
        transformation_manifest: TransformationManifest,
    ) -> TaskGraph:
        nodes: list[TaskNode] = [
            TaskNode(
                id="T001",
                title="Validate objective contract and repository roles",
                description="Validate the immutable objective contract, reference baseline, and initial semantic inventory.",
                type="architecture",
                assigned_agent="architect",
                completion_criteria=[
                    "Objective contract has no validation errors.",
                    "Reference repositories are read-only and target repository is the only writable product root.",
                    "Initial semantic inventory is recorded.",
                ],
                evidence=[
                    {
                        "type": "goal_locked_contract",
                        "objective_revision": objective_contract.revision,
                        "reference_errors": list(reference_baseline.validation_errors),
                        "inventory_hits": len(repository_inventory.hits),
                    }
                ],
                relevant_files=[*objective_contract.source_documents],
                priority=100,
            )
        ]
        dependencies: list[Dependency] = []
        previous = "T001"
        for item in sorted(transformation_manifest.items, key=_manifest_order):
            task_id = f"T{len(nodes) + 1:03d}"
            title = _task_title(item.action, item.domain)
            read_only = item.action in {"inspect", "verify", "waive"}
            allowed_write_paths = [] if read_only else list(item.targets or ["**"])
            task_type = "test" if item.action == "verify" else "architecture" if read_only else "integration"
            assigned_agent = "test" if item.action == "verify" else "architect" if read_only else (
                "backend" if any(path.startswith("backend/") for path in item.targets) else "frontend"
            )
            nodes.append(
                TaskNode(
                    id=task_id,
                    title=title,
                    description=(
                        f"Apply {item.action} transformation for requirements {', '.join(item.requirements)}. "
                        f"Expected final state: {item.expected_final_state}."
                    ),
                    type=task_type,
                    assigned_agent=assigned_agent,
                    dependencies=[previous],
                    completion_criteria=[
                        f"Requirement IDs: {', '.join(item.requirements)}.",
                        f"Transformation IDs: {item.id}.",
                        f"Expected final state: {item.expected_final_state}.",
                        "Strategy decision record is present for medium or large changes.",
                    ],
                    relevant_files=item.targets or [],
                    commands_to_run=[],
                    priority=95 if item.action == "delete" else 85,
                    boundary_mode="strict" if read_only else "large_refactor",
                )
            )
            contract = {
                "id": task_id,
                "type": "task_contract",
                "requirement_ids": list(item.requirements),
                "transformation_ids": [item.id],
                "action": item.action,
                "size": _task_size(item),
                "read_only": read_only,
                "expected_final_state": dict(item.expected_final_state),
                "allowed_write_paths": allowed_write_paths,
                "reference_roots": [reference.path for reference in reference_baseline.references],
                "required_strategy_decision": _required_strategy(item),
            }
            contract["validation_errors"] = validate_task_contract(contract)
            nodes[-1].evidence.append(contract)
            dependencies.append(Dependency(source=previous, target=task_id, type="blocks"))
            previous = task_id
        verify_id = f"T{len(nodes) + 1:03d}"
        nodes.append(
            TaskNode(
                id=verify_id,
                title="Refresh independent verification matrix",
                description="Rebuild objective-derived evidence from the current repository fingerprint before delivery.",
                type="test",
                assigned_agent="test",
                dependencies=[previous],
                completion_criteria=[
                    "Every must requirement has fresh passing proof.",
                    "Every unwaived negative requirement has zero remaining inventory hits.",
                    "No stale evidence approves the final repository fingerprint.",
                ],
                priority=98,
            )
        )
        dependencies.append(Dependency(source=previous, target=verify_id, type="requires_test_pass"))
        review_id = f"T{len(nodes) + 1:03d}"
        nodes.append(
            TaskNode(
                id=review_id,
                title="Record coherent delivery ledger",
                description="Bind accepted checkpoints, final fingerprint, verification matrix, and handoff decision to one target worktree.",
                type="review",
                assigned_agent="reviewer",
                dependencies=[verify_id],
                completion_criteria=["Delivery ledger identifies one coherent final state.", "Reviewer approval is recorded."],
                priority=90,
            )
        )
        dependencies.append(Dependency(source=verify_id, target=review_id, type="requires_review"))
        return TaskGraph(graph_id=f"{project_id}-goal-locked-convergence", version=1, nodes=nodes, dependencies=dependencies)


def _task_title(action: str, domain: str) -> str:
    if action == "delete":
        return f"Delete forbidden {domain.replace('_', ' ')} dependency closure"
    if action == "transplant":
        return f"Apply governed reference strategy for {domain.replace('_', ' ')}"
    if action == "inspect":
        return f"Decide governed strategy for {domain.replace('_', ' ')}"
    if action == "verify":
        return f"Prove {domain.replace('_', ' ')} final state"
    if action == "waive":
        return f"Record authorized waiver for {domain.replace('_', ' ')}"
    return f"Implement {domain.replace('_', ' ')} final state"


def goal_locked_graph_errors(graph: TaskGraph) -> list[str]:
    errors: list[str] = []
    for node in graph.nodes:
        contracts = [item for item in node.evidence if isinstance(item, dict) and item.get("type") == "task_contract"]
        if node.id in {"T001"} or node.type in {"review"}:
            continue
        if node.title == "Refresh independent verification matrix":
            continue
        if len(contracts) != 1:
            errors.append(f"{node.id} must contain exactly one task contract.")
            continue
        errors.extend(str(item) for item in contracts[0].get("validation_errors", []) if str(item))
    return errors


def _manifest_order(item: TransformationItem) -> tuple[int, str, str]:
    priority = {
        "inspect": 0,
        "delete": 1,
        "transplant": 2,
        "add": 3,
        "modify": 4,
        "regenerate": 5,
        "verify": 6,
        "waive": 7,
    }
    return priority.get(item.action, 5), item.domain, item.id


def _task_size(item: TransformationItem) -> str:
    if item.action in {"inspect", "verify", "waive"}:
        return "small"
    if len(item.targets) <= 1:
        return "medium"
    return "large"


def _required_strategy(item: TransformationItem) -> str:
    if item.action == "delete":
        return "delete"
    if item.action in {"add", "modify", "transplant", "regenerate"}:
        return "preserve_or_repair_from_reference_or_redesign"
    return ""
