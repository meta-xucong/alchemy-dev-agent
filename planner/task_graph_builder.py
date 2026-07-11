"""Build runtime task graphs from ContextBundle objects."""

from __future__ import annotations

import re
from pathlib import Path

from context.models import ContextBundle, RepositoryFile, Requirement
from context.repository_indexer import RepositoryIndexer, node_install_command, package_parent
from runtime.models import Dependency, TaskGraph, TaskNode

WEB_GAME_SCAFFOLD_FILES = {
    "index.html",
    "src/main.js",
    "src/engine.js",
    "src/input.js",
    "src/physics.js",
    "src/tilemap.js",
    "src/entities.js",
    "src/renderer.js",
    "tests/static_checks.js",
}

WEB_GAME_DELIVERY_FILES = {
    *WEB_GAME_SCAFFOLD_FILES,
    "package.json",
    "tsconfig.json",
    "vite.config.ts",
    "docs/reference-register.md",
}


class TaskGraphBuilder:
    """Create deterministic task graphs from context bundles."""

    def build(self, context_bundle: ContextBundle) -> TaskGraph:
        if self._is_generated_artifact_context(context_bundle):
            return self._build_generated_artifact_graph(context_bundle)
        return self._build_document_driven_graph(context_bundle)

    def _build_document_driven_graph(self, context_bundle: ContextBundle) -> TaskGraph:
        requirements = context_bundle.requirements
        preserved_task_ids = focused_repair_completed_task_ids(requirements)
        test_commands = context_bundle.test_commands or ["static artifact inspection"]
        scope_controls = large_refactor_planning_scope_controls(
            normalize_scope_controls(context_bundle.scope_controls),
            requirements,
        )
        nodes: list[TaskNode] = [
            TaskNode(
                id="T001",
                title="Plan implementation from requirements",
                description="Map requirements, repository evidence, risks, and verification commands into an implementation plan.",
                type="architecture",
                assigned_agent="architect",
                completion_criteria=[
                    "All requirements are assigned to implementation tasks.",
                    "Known blockers and risks are reflected in task scope.",
                ],
                relevant_files=self._top_level_context_files(context_bundle, scope_controls),
                commands_to_run=[],
                priority=95,
            )
        ]
        if is_final_verification_audit_context(context_bundle):
            return self._build_final_verification_graph(
                context_bundle,
                nodes=nodes,
                scope_controls=scope_controls,
                preserved_task_ids=preserved_task_ids,
            )

        implementation_nodes, requirement_task_ids = self._implementation_nodes(
            requirements,
            test_commands,
            scope_controls=scope_controls,
            repository_files=context_bundle.repository_files,
            package_files=context_bundle.package_files,
            ci_files=context_bundle.ci_files,
        )
        nodes.extend(implementation_nodes)
        implementation_ids = [node.id for node in implementation_nodes]
        documentation_only = bool(implementation_nodes) and all(node.type == "documentation" for node in implementation_nodes)
        verification_commands = (
            ["static document inspection"]
            if documentation_only
            else scoped_verification_commands(scope_controls, test_commands + context_bundle.build_commands + context_bundle.lint_commands)
        )
        implementation_files = dedupe([file for node in implementation_nodes for file in node.relevant_files])
        verification_files = (
            implementation_files
            if documentation_only or test_commands == ["static artifact inspection"]
            else scoped_files(self._test_relevant_files(context_bundle), scope_controls, fallback=implementation_files)
        )
        verification_criteria = (
            dedupe([criterion for node in implementation_nodes for criterion in node.completion_criteria])
            if documentation_only
            else [
                "Detected verification commands pass or produce documented blockers.",
                "Every must requirement has implementation evidence.",
            ]
        )

        base_verify_id = next_graph_task_id(nodes, [])
        verify_id = next_graph_task_id(nodes, preserved_task_ids)
        if should_split_schema_final_verification_timeout(requirements, base_verify_id):
            verification_nodes = schema_final_verification_timeout_split_nodes(
                next_task_id=base_verify_id,
                dependencies=implementation_ids or ["T001"],
                verification_commands=verification_commands,
                scope_controls=scope_controls,
                fallback_files=verification_files,
                existing_nodes=nodes,
            )
            nodes.extend(verification_nodes)
        else:
            verification_nodes = [
                TaskNode(
                    id=verify_id,
                    title="Verify implementation against project checks",
                    description="Run detected tests, builds, lints, and requirement-specific verification.",
                    type="test",
                    assigned_agent="test",
                    dependencies=implementation_ids or ["T001"],
                    completion_criteria=verification_criteria,
                    commands_to_run=verification_commands,
                    relevant_files=verification_files,
                    priority=85,
                )
            ]
            nodes.extend(verification_nodes)
        verification_ids = [node.id for node in verification_nodes]

        review_id = next_graph_task_id(nodes, preserved_task_ids)
        nodes.append(
            TaskNode(
                id=review_id,
                title="Review delivery readiness",
                description="Check requirement traceability, risks, test evidence, and final gate readiness.",
                type="review",
                assigned_agent="reviewer",
                dependencies=[verification_ids[-1]],
                completion_criteria=[
                    "All must requirements are traced to completed tasks.",
                    "Reviewer approval is recorded.",
                    "Final gate score is at least 0.85.",
                ],
                relevant_files=self._top_level_context_files(context_bundle, scope_controls),
                priority=80,
            )
        )

        for requirement in requirements:
            if requirement.id in requirement_task_ids:
                requirement.planned_task_ids = [
                    requirement_task_ids[requirement.id],
                    *verification_ids,
                    review_id,
                ]

        dependencies = [Dependency(source="T001", target=node.id, type="blocks") for node in implementation_nodes]
        dependencies.extend(
            Dependency(source=node.id, target=verification_ids[0], type="requires_test_pass")
            for node in implementation_nodes
        )
        dependencies.extend(
            Dependency(source=source, target=target, type="requires_test_pass")
            for source, target in zip(verification_ids, verification_ids[1:])
        )
        dependencies.append(Dependency(source=verification_ids[-1], target=review_id, type="requires_review"))
        mark_preserved_completed_tasks(nodes, preserved_task_ids)
        return TaskGraph(graph_id=f"{context_bundle.project_id}-document-plan", version=1, nodes=nodes, dependencies=dependencies)

    def _build_final_verification_graph(
        self,
        context_bundle: ContextBundle,
        *,
        nodes: list[TaskNode],
        scope_controls: dict[str, list[str]],
        preserved_task_ids: list[str],
    ) -> TaskGraph:
        """Build an audit/test graph for the last full-roadmap verification pass."""

        planning_node = nodes[0]
        planning_node.title = "Use deterministic final verification graph"
        planning_node.description = (
            "Final verification uses a fixed audit/test graph, so no real planning worker is required before audit."
        )
        planning_node.status = "completed"
        planning_node.evidence.append(
            {
                "summary": "Final verification planning was pre-completed by the deterministic graph builder.",
                "kind": "deterministic_final_verification_graph",
            }
        )
        repair_specs = final_verification_repair_task_specs(context_bundle)
        repair_specs = final_verification_repair_specs_for_target_files(
            context_bundle,
            repair_specs,
        )
        test_commands = context_bundle.test_commands or ["static artifact inspection"]
        verification_commands = scoped_verification_commands(
            scope_controls,
            test_commands + context_bundle.build_commands + context_bundle.lint_commands,
        )
        top_level_files = self._top_level_context_files(context_bundle, scope_controls)
        verification_files = scoped_files(
            self._test_relevant_files(context_bundle),
            scope_controls,
            fallback=top_level_files,
        )
        audit_id = "T002"
        simulation_id = "T003"
        real_id = "T004"
        review_id = "T005"
        dependencies: list[Dependency] = []
        audit_dependencies = ["T001"]
        if repair_specs:
            previous_id = "T001"
            for offset, spec in enumerate(repair_specs, start=2):
                task_id = f"T{offset:03d}"
                nodes.append(
                    TaskNode(
                        id=task_id,
                        title=str(spec["title"]),
                        description=str(spec["description"]),
                        type="integration",
                        assigned_agent=str(spec.get("assigned_agent", "backend")),  # type: ignore[arg-type]
                        dependencies=[previous_id],
                        completion_criteria=[str(item) for item in spec.get("completion_criteria", [])],
                        relevant_files=[str(item) for item in spec.get("relevant_files", [])],
                        commands_to_run=[],
                        priority=int(spec.get("priority", 94)),
                        boundary_mode="large_refactor",
                    )
                )
                dependencies.append(Dependency(source=previous_id, target=task_id, type="blocks"))
                previous_id = task_id
            audit_dependencies = [f"T{index:03d}" for index in range(2, len(repair_specs) + 2)]
            audit_id = f"T{len(repair_specs) + 2:03d}"
            simulation_id = f"T{len(repair_specs) + 3:03d}"
            real_id = f"T{len(repair_specs) + 4:03d}"
            review_id = f"T{len(repair_specs) + 5:03d}"
        marker_criteria = [
            "FINAL_AUDIT_STATUS is reported as PASS or FAIL with evidence.",
            "REQUIRED_ACTIONS and BLOCKERS are explicitly reported.",
        ]
        nodes.extend(
            [
                TaskNode(
                    id=audit_id,
                    title="Audit final requirements and phase evidence",
                    description=(
                        "Challenge the completed roadmap against the source documents, phase records, "
                        "known risks, scope boundaries, and delivery evidence. Apply only small concrete "
                        "repairs when the audit identifies a specific defect. Do not fail this audit "
                        "solely because downstream final-verification gates are still pending; T010/T011/T012/T013 "
                        "must report their own simulation, real-check, review, and delivery status after this audit. "
                        "Treat historical blocked phase records as superseded when the current final-verification "
                        "repair graph provides direct evidence that the underlying defect was repaired."
                    ),
                    type="test",
                    assigned_agent="test",
                    dependencies=audit_dependencies,
                    completion_criteria=marker_criteria,
                    relevant_files=top_level_files,
                    commands_to_run=[],
                    priority=92,
                ),
                TaskNode(
                    id=simulation_id,
                    title="Run final simulation probes",
                    description=(
                        "Run or derive scenario, static, golden-case, browser, or API probes for the "
                        "completed product behavior. Apply only small concrete repairs when a probe "
                        "exposes a specific defect."
                    ),
                    type="test",
                    assigned_agent="test",
                    dependencies=[audit_id],
                    completion_criteria=[
                        "SIMULATION_TEST_STATUS is reported as PASS or FAIL with evidence.",
                        "Scenario/static/browser probe commands and results are recorded.",
                    ],
                    relevant_files=verification_files,
                    commands_to_run=test_commands,
                    priority=90,
                ),
                TaskNode(
                    id=real_id,
                    title="Run final real repository checks",
                    description=(
                        "Run the broad real repository checks available in this worktree, including tests, "
                        "builds, and lints when detected. Apply only small concrete repairs when a command "
                        "exposes a specific defect."
                    ),
                    type="test",
                    assigned_agent="test",
                    dependencies=[simulation_id],
                    completion_criteria=[
                        "REAL_TEST_STATUS is reported as PASS or FAIL with evidence.",
                        "Real repository command results are recorded with precise blockers if any command cannot run.",
                    ],
                    relevant_files=verification_files,
                    commands_to_run=verification_commands,
                    priority=88,
                ),
                TaskNode(
                    id=review_id,
                    title="Review final handoff markers",
                    description="Confirm final audit, simulation, real-test, blockers, and required-action markers are coherent.",
                    type="review",
                    assigned_agent="reviewer",
                    dependencies=[real_id],
                    completion_criteria=[
                        "FINAL_AUDIT_STATUS, SIMULATION_TEST_STATUS, and REAL_TEST_STATUS are present.",
                        "Any FAIL marker has a concrete blocker or repair recommendation.",
                        "Final handoff readiness is recorded.",
                    ],
                    relevant_files=top_level_files,
                    priority=82,
                ),
            ]
        )
        for requirement in context_bundle.requirements:
            requirement.planned_task_ids = [audit_id, simulation_id, real_id, review_id]
            if repair_specs:
                requirement.planned_task_ids = [f"T{index:03d}" for index in range(2, len(repair_specs) + 2)] + requirement.planned_task_ids
        dependencies.extend(
            [
                *[
                    Dependency(source=source, target=audit_id, type="requires_test_pass")
                    for source in audit_dependencies
                ],
                Dependency(source=audit_id, target=simulation_id, type="requires_test_pass"),
                Dependency(source=simulation_id, target=real_id, type="requires_test_pass"),
                Dependency(source=real_id, target=review_id, type="requires_review"),
            ]
        )
        preserved_task_ids = final_verification_preserved_task_ids_with_matching_repair_title(
            context_bundle,
            nodes,
            preserved_task_ids,
        )
        preserved_task_ids = final_verification_preserved_task_ids_without_new_target_file_tasks(
            context_bundle,
            nodes,
            preserved_task_ids,
        )
        if final_verification_gate_rerun_required(context_bundle):
            preserved_task_ids = final_verification_preserved_task_ids_without_gate_tasks(
                nodes,
                preserved_task_ids,
            )
        mark_preserved_completed_tasks(nodes, preserved_task_ids)
        if repair_specs:
            repair_task_ids = [f"T{index:03d}" for index in range(2, len(repair_specs) + 2)]
            enforce_reopened_repair_order(nodes, repair_task_ids)
        return TaskGraph(graph_id=f"{context_bundle.project_id}-document-plan", version=1, nodes=nodes, dependencies=dependencies)

    def _implementation_nodes(
        self,
        requirements: list[Requirement],
        test_commands: list[str],
        *,
        scope_controls: dict[str, list[str]] | None = None,
        repository_files: list[RepositoryFile] | None = None,
        package_files: list[str] | None = None,
        ci_files: list[str] | None = None,
    ) -> tuple[list[TaskNode], dict[str, str]]:
        nodes: list[TaskNode] = []
        requirement_task_ids: dict[str, str] = {}
        if not requirements:
            return nodes, requirement_task_ids
        scoped_targets = scoped_target_files(scope_controls)
        docs_only_scope = is_docs_only_scope(scoped_targets)
        is_web_game_delivery = should_group_as_single_web_game_delivery(requirements) or is_existing_canvas_game_repository(
            repository_files or []
        )
        if scoped_targets and (docs_only_scope or boundary_mode(scope_controls) != "large_refactor"):
            task_id = "T002"
            task_type = "documentation" if docs_only_scope else "integration"
            assigned_agent = "architect" if docs_only_scope else "backend"
            nodes.append(
                TaskNode(
                    id=task_id,
                    title="Update scoped documentation target files" if docs_only_scope else "Implement scoped V3 foundation target files",
                    description=(
                        "Update documentation inside the declared scope contract. "
                        "Do not run full repository build or test commands for documentation-only scope."
                        if docs_only_scope
                        else (
                            "Implement all document requirements inside the declared scope contract. "
                            "Do not edit protected directories or files outside target_files."
                        )
                    ),
                    type=task_type,
                    assigned_agent=assigned_agent,
                    dependencies=["T001"],
                    completion_criteria=dedupe([criterion for item in requirements for criterion in item.acceptance_criteria]),
                    relevant_files=scoped_targets,
                    commands_to_run=commands_for_task_type(task_type, scoped_verification_commands(scope_controls, test_commands)),
                    priority=max(priority_for_requirement(item) for item in requirements),
                    boundary_mode="strict",
                )
            )
            for item in requirements:
                requirement_task_ids[item.id] = task_id
                item.related_files = scoped_files(item.related_files, scope_controls, fallback=scoped_targets)
            return nodes, requirement_task_ids
        # A greenfield browser game is one coherent delivery even when callers
        # request a large-refactor boundary.  The generic large-refactor path
        # defaults to a backend owner and inferred backend/** files, which
        # misroutes a document-only game into an unrelated subproject.
        if boundary_mode(scope_controls) == "large_refactor" and not is_web_game_delivery:
            relevant_files = large_refactor_relevant_files(
                repository_files or [],
                package_files=package_files or [],
                ci_files=ci_files or [],
                scope_controls=scope_controls,
            )
            assigned_agent = classify_large_refactor_agent(requirements)
            relevant_files = dedupe(
                [
                    *relevant_files,
                    *large_refactor_phase_hint_files(
                        requirements,
                        assigned_agent=assigned_agent,
                        scope_controls=scope_controls,
                    ),
                ]
            )
            if should_decompose_large_refactor_frontend_phase(
                requirements,
                assigned_agent=assigned_agent,
            ) or should_decompose_frontend_verification_repair(requirements, assigned_agent=assigned_agent):
                return large_refactor_frontend_nodes(
                    requirements,
                    test_commands,
                    package_files=package_files or [],
                    scope_controls=scope_controls,
                    base_relevant_files=relevant_files,
                )
            if should_decompose_large_refactor_schema_build_phase(
                requirements,
                assigned_agent=assigned_agent,
            ):
                return large_refactor_schema_build_nodes(
                    requirements,
                    test_commands,
                    package_files=package_files or [],
                    scope_controls=scope_controls,
                    base_relevant_files=relevant_files,
                )

            task_id = "T002"
            nodes.append(
                TaskNode(
                    id=task_id,
                    title="Implement large refactor integration",
                    description=(
                        "Implement the document requirements as one product-scale repository transformation. "
                        "Preserve protected paths, remove obsolete product behavior required by the document, "
                        "and keep the result independently verifiable."
                    ),
                    type="integration",
                    assigned_agent=assigned_agent,
                    dependencies=["T001"],
                    completion_criteria=dedupe([criterion for item in requirements for criterion in item.acceptance_criteria]),
                    relevant_files=relevant_files,
                    commands_to_run=commands_for_task_type("integration", test_commands),
                    priority=max(priority_for_requirement(item) for item in requirements),
                    boundary_mode="large_refactor",
                )
            )
            for item in requirements:
                requirement_task_ids[item.id] = task_id
                item.related_files = scoped_files(item.related_files, scope_controls, fallback=relevant_files)
            return nodes, requirement_task_ids
        grouped_delivery = group_implementation_requirements(requirements)
        is_web_game_delivery = len(grouped_delivery) == 1 and is_web_game_delivery
        for index, grouped_requirements in enumerate(grouped_delivery, start=2):
            requirement = grouped_requirements[0]
            task_type, agent = (
                ("integration", "frontend")
                if is_web_game_delivery
                else classify_grouped_requirement_task(grouped_requirements)
            )
            task_id = f"T{index:03d}"
            title = (
                "Implement complete web game delivery"
                if is_web_game_delivery
                else task_title(requirement, task_type)
                if len(grouped_requirements) == 1
                else grouped_task_title(grouped_requirements, task_type)
            )
            description = (
                "Implement the complete browser-game delivery, including its runtime scaffold, gameplay systems, "
                "tests, and required reference records. Do not run final artifact verification until this task has "
                "created every required artifact."
                if is_web_game_delivery
                else f"Implement requirement {requirement.id}: {requirement.text}"
                if len(grouped_requirements) == 1
                else "Implement requirements "
                + ", ".join(item.id for item in grouped_requirements)
                + ": "
                + " ".join(item.text for item in grouped_requirements)
            )
            relevant_files = (
                sorted(WEB_GAME_DELIVERY_FILES)
                if is_web_game_delivery
                else scoped_files(
                    dedupe([file for item in grouped_requirements for file in item.related_files]),
                    scope_controls,
                )
            )
            nodes.append(
                TaskNode(
                    id=task_id,
                    title=title,
                    description=description,
                    type=task_type,
                    assigned_agent=agent,
                    dependencies=["T001"],
                    completion_criteria=dedupe([criterion for item in grouped_requirements for criterion in item.acceptance_criteria]),
                    relevant_files=relevant_files,
                    # A greenfield Vite game must prove both its deterministic
                    # contracts and a production build; static inspection alone
                    # is too easy for a visually weak implementation to satisfy.
                    commands_to_run=(
                        ["npm test", "npm run build", "static artifact inspection"]
                        if is_web_game_delivery
                        else commands_for_task_type(task_type, test_commands)
                    ),
                    priority=max(priority_for_requirement(item) for item in grouped_requirements),
                    boundary_mode="strict",
                )
            )
            for item in grouped_requirements:
                requirement_task_ids[item.id] = task_id
        return nodes, requirement_task_ids

    def _build_generated_artifact_graph(self, context_bundle: ContextBundle) -> TaskGraph:
        requirements = context_bundle.requirements
        criteria = requirements[0].acceptance_criteria if requirements else ["Generated artifact exists."]
        nodes = [
            TaskNode(
                id="T001",
                title="Architect generated application",
                description="Convert the context bundle into an implementation plan.",
                type="architecture",
                assigned_agent="architect",
                completion_criteria=["Implementation plan maps requirements to generated files."],
                commands_to_run=["static artifact inspection"],
            ),
            TaskNode(
                id="T002",
                title="Implement generated application",
                description="Generate the local application artifact.",
                type="frontend",
                assigned_agent="frontend",
                dependencies=["T001"],
                completion_criteria=criteria,
                relevant_files=["index.html"],
                commands_to_run=["static artifact inspection"],
            ),
            TaskNode(
                id="T003",
                title="Verify generated application",
                description="Inspect generated artifact for required controls, canvas, and safety constraints.",
                type="test",
                assigned_agent="test",
                dependencies=["T002"],
                completion_criteria=["Generated artifact passes static verification."],
                relevant_files=["index.html"],
                commands_to_run=["static artifact inspection"],
            ),
            TaskNode(
                id="T004",
                title="Review generated delivery",
                description="Review requirements, risks, and delivery evidence.",
                type="review",
                assigned_agent="reviewer",
                dependencies=["T003"],
                completion_criteria=["Reviewer approves delivery or records blockers."],
                relevant_files=["index.html"],
            ),
        ]
        dependencies = [
            Dependency(source="T001", target="T002", type="blocks"),
            Dependency(source="T002", target="T003", type="requires_test_pass"),
            Dependency(source="T003", target="T004", type="requires_review"),
        ]
        return TaskGraph(graph_id=f"{context_bundle.project_id}-generated-app", version=1, nodes=nodes, dependencies=dependencies)

    def _is_generated_artifact_context(self, context_bundle: ContextBundle) -> bool:
        return bool(context_bundle.requirements and context_bundle.requirements[0].source_document_id == "generated_one_line")

    def _top_level_context_files(self, context_bundle: ContextBundle, scope_controls: dict[str, list[str]] | None = None) -> list[str]:
        document_files = [document.path for document in context_bundle.documents]
        if not scope_controls:
            return dedupe([*document_files, *context_bundle.package_files])
        package_files = scoped_files(context_bundle.package_files, scope_controls)
        return dedupe([*document_files, *package_files])

    def _test_relevant_files(self, context_bundle: ContextBundle) -> list[str]:
        test_files = [file.path for file in context_bundle.repository_files if file.kind in {"test", "ci"}]
        return dedupe(test_files + context_bundle.ci_files)


def normalize_scope_controls(scope_controls: dict[str, object] | None) -> dict[str, list[str]]:
    if not scope_controls:
        return {"allowed_prefixes": [], "protected_prefixes": [], "target_files": [], "boundary_mode": ["strict"]}
    return {
        "allowed_prefixes": dedupe(str(item) for item in scope_controls.get("allowed_prefixes", []) or []),
        "protected_prefixes": dedupe(str(item) for item in scope_controls.get("protected_prefixes", []) or []),
        "target_files": dedupe(str(item) for item in scope_controls.get("target_files", []) or []),
        "boundary_mode": [str(scope_controls.get("boundary_mode", "strict") or "strict")],
    }


def is_final_verification_audit_context(context_bundle: ContextBundle) -> bool:
    chunks = [context_bundle.objective]
    for document in context_bundle.documents:
        chunks.extend([document.path, document.summary, *document.key_requirements])
        chunks.extend(final_verification_repair_document_text_fragments(document.path))
    chunks.extend(requirement.text for requirement in context_bundle.requirements)
    text = "\n".join(chunks).lower()
    final_audit_signal = "final_verification" in text or "final full-system audit" in text
    handoff_signal = "final handoff" in text or "required_actions" in text or "final_audit_status" in text
    return final_audit_signal and handoff_signal


def final_verification_repair_task_specs(context_bundle: ContextBundle) -> list[dict[str, object]]:
    chunks = [context_bundle.objective]
    for document in context_bundle.documents:
        chunks.extend([document.path, document.summary, *document.key_requirements])
        chunks.extend(final_verification_repair_document_text_fragments(document.path))
    chunks.extend(requirement.text for requirement in context_bundle.requirements)
    full_text = "\n".join(chunks).lower()
    text = final_verification_active_repair_text(context_bundle) or full_text
    if not any(token in text for token in ["source-boundary", "allowed_files", "retry repair", "repair final"]):
        return []
    specs: list[dict[str, object]] = []
    preserve_deep_final_frontend_tail = False
    if any(token in text for token in ["migration", "schema", "ent", "backend", "table", "domain"]):
        specs.append(
            {
                "title": "Repair final backend migration contracts",
                "description": (
                    "Remove residual relay-era fresh-migration table creation and align startup database contracts "
                    "with the CRM Billing Core source-boundary requirements."
                ),
                "assigned_agent": "backend",
                "relevant_files": [
                    "backend/migrations/001_init.sql",
                    "backend/migrations/003_subscription.sql",
                    "backend/migrations/081_create_channels.sql",
                    "backend/migrations/125_add_channel_monitors.sql",
                    "backend/cmd/server/database_contract.go",
                    "backend/cmd/server/database_contract_test.go",
                ],
                "completion_criteria": [
                    "The named fresh-migration files no longer create relay-era account-pool, proxy, channel, channel-monitor, subscription, or model-routing tables.",
                    "Startup cleanup is not the only mechanism enforcing the clean Billing Core schema.",
                ],
                "priority": 96,
            }
        )
        specs.append(
            {
                "title": "Repair final backend Ent schema contracts",
                "description": (
                    "Regenerate or reframe Ent schema/generated code so retired relay-era concepts are not exposed "
                    "as delivered CRM product behavior. Keep verification narrow in this implementation task; "
                    "full backend test/build commands are reserved for the final real repository checks."
                ),
                "assigned_agent": "backend",
                "relevant_files": [
                    "backend/ent/**",
                    "backend/ent/schema/**",
                    "backend/ent/migrate/**",
                    "backend/go.mod",
                    "backend/go.sum",
                ],
                "completion_criteria": [
                    "Backend Ent schema and generated table contracts align with identity, wallet, metering, charging, reconciliation, analytics, audit, and admin concepts.",
                    "Retired relay-era Ent entities are removed or reframed without running full repository Go tests in this repair task.",
                ],
                "priority": 95,
            }
        )
        if should_narrow_final_backend_domain_repository_leaf_timeout(text):
            specs.append(
                {
                    "title": "Repair final backend domain account repository contract leaf",
                    "description": (
                        "The already narrowed domain/repository repair timed out again. Keep task ID T004 stable "
                        "and checkpoint the next retry to the domain constants plus account repository contract leaf."
                    ),
                    "assigned_agent": "backend",
                    "relevant_files": [
                        "backend/internal/domain/constants.go",
                        "backend/internal/repository/account_repo.go",
                        "backend/go.mod",
                        "backend/go.sum",
                    ],
                    "completion_criteria": [
                        "Domain account type constants and account repository contracts use CRM-facing account terminology.",
                        "Residual upstream account compatibility is removed or isolated from delivered CRM account behavior.",
                        "Only narrow package-level or static checks are attempted; broad backend verification remains for final gates.",
                    ],
                    "priority": 94,
                }
            )
        elif should_narrow_final_backend_domain_repository_timeout(text):
            specs.append(
                {
                    "title": "Repair final backend domain repository contract leftovers",
                    "description": (
                        "Narrow the timed-out domain/repository repair to concrete CRM account type and repository "
                        "contract leftovers instead of replaying all domain and repository files."
                    ),
                    "assigned_agent": "backend",
                    "relevant_files": [
                        "backend/internal/domain/constants.go",
                        "backend/internal/repository/account_repo.go",
                        "backend/internal/repository/channel_repo.go",
                        "backend/internal/repository/http_upstream.go",
                        "backend/internal/repository/proxy_repo.go",
                        "backend/go.mod",
                        "backend/go.sum",
                    ],
                    "completion_criteria": [
                        "Domain constants and repository contracts use CRM-facing account and catalog terminology.",
                        "Residual upstream/proxy/channel repository compatibility is removed or isolated from delivered CRM behavior.",
                        "Narrow package-level or static checks are attempted without taking over full backend verification.",
                    ],
                    "priority": 94,
                }
            )
        else:
            specs.append(
                {
                    "title": "Repair final backend domain and repository contracts",
                    "description": (
                        "Align backend domain and repository callers with the CRM Billing Core schema after Ent/source-boundary cleanup. "
                        "Use targeted compile or static checks only; leave full-suite Go verification to the final real repository checks."
                    ),
                    "assigned_agent": "backend",
                    "relevant_files": [
                        "backend/internal/domain/**",
                        "backend/internal/repository/**",
                        "backend/go.mod",
                        "backend/go.sum",
                    ],
                    "completion_criteria": [
                        "Domain and repository contracts no longer expose upstream account-pool, proxy, channel, channel-monitor, model-routing, or subscription-plan product behavior.",
                        "Repository callers compile against the cleaned CRM schema using narrow package-level or no-test compile checks.",
                    ],
                    "priority": 94,
                }
            )
        if should_narrow_final_backend_service_handler_timeout(text):
            specs.append(
                {
                    "title": "Repair final backend service contract leftovers",
                    "description": (
                        "Narrow the timed-out service/handler/server repair to service-layer CRM billing contract "
                        "leftovers first. Keep handler, server, command, and broad backend verification for later audit-driven follow-up."
                    ),
                    "assigned_agent": "backend",
                    "relevant_files": [
                        "backend/internal/service/**",
                        "backend/internal/domain/**",
                        "backend/internal/repository/**",
                        "backend/go.mod",
                        "backend/go.sum",
                    ],
                    "completion_criteria": [
                        "Service-layer contracts no longer expose relay, upstream, proxy, channel, model-provider, or token middle-station product behavior.",
                        "Service package verification is attempted with narrow package-level checks or leaves precise downstream handler/server follow-ups.",
                    ],
                    "priority": 93,
                }
            )
        else:
            specs.append(
                {
                    "title": "Repair final backend service handler server contracts",
                    "description": (
                        "Align backend service, handler, server, and command wiring with the cleaned CRM domain contracts. "
                        "Avoid broad `go test ./...` here; final real repository checks own full backend verification."
                    ),
                    "assigned_agent": "backend",
                    "relevant_files": [
                        "backend/internal/service/**",
                        "backend/internal/handler/**",
                        "backend/internal/server/**",
                        "backend/cmd/**",
                        "backend/go.mod",
                        "backend/go.sum",
                    ],
                    "completion_criteria": [
                        "Service, handler, server, and command wiring expose CRM billing, identity, wallet, metering, charging, reconciliation, analytics, audit, and admin behavior only.",
                        "Hand-written backend callers align with the cleaned schema without running full repository Go tests in this repair task.",
                    ],
                    "priority": 93,
                }
            )
    if any(token in text for token in ["frontend", "i18n", "router", "view", "api module", "reachable views"]):
        preserve_deep_final_frontend_tail = should_preserve_final_frontend_deep_tail_split(text)
        split_routes_views = should_split_final_frontend_routes_views_timeout(text)
        split_api_i18n = should_split_final_frontend_api_i18n_timeout(
            text
        ) or should_preserve_final_frontend_api_i18n_split(text)
        # A resumed downstream route repair must keep the already-established
        # API/i18n task IDs stable instead of collapsing them into one task.
        split_api_i18n = split_api_i18n or split_routes_views
        split_i18n_locale_leaf = should_narrow_final_frontend_i18n_locale_timeout(text)
        split_api_i18n = split_api_i18n or split_i18n_locale_leaf
        split_admin_user_create_edit = should_split_final_frontend_admin_user_create_edit_timeout(
            text
        ) or should_preserve_final_frontend_admin_user_create_edit_split(text)
        split_admin_payment = should_split_final_frontend_admin_payment_timeout(
            text
        ) or should_preserve_final_frontend_admin_payment_split(text)
        split_admin_payment_refund = should_narrow_final_frontend_admin_payment_refund_timeout(
            text
        ) or should_preserve_final_frontend_admin_payment_refund_leaf(text)
        split_admin_payment = split_admin_payment or split_admin_payment_refund
        split_admin_email_template_leaf = should_narrow_final_frontend_admin_email_template_timeout(
            text
        ) or should_preserve_final_frontend_admin_email_template_leaf(text)
        split_admin_settings_email_compliance = should_split_final_frontend_admin_settings_email_compliance_timeout(
            text
        ) or should_preserve_final_frontend_admin_settings_email_compliance_split(text) or split_admin_email_template_leaf
        split_admin_announcement_backup_promo = should_split_final_frontend_admin_announcement_backup_promo_timeout(
            text
        ) or should_preserve_final_frontend_admin_announcement_backup_promo_split(text)
        if split_admin_announcement_backup_promo:
            split_api_i18n = True
            split_admin_user_create_edit = True
            split_admin_payment_refund = True
            split_admin_payment = True
        split_admin_email_template_leaf = split_admin_email_template_leaf or split_admin_announcement_backup_promo
        split_admin_settings_email_compliance = (
            split_admin_settings_email_compliance or split_admin_announcement_backup_promo
        )
        split_admin_dashboard_settings = (
            should_split_final_frontend_admin_dashboard_settings_timeout(text)
            or should_preserve_final_frontend_admin_dashboard_settings_split(text)
            or split_admin_settings_email_compliance
            or split_admin_announcement_backup_promo
        )
        split_admin_view_pages = (
            should_split_final_frontend_admin_view_page_timeout(text)
            or should_preserve_final_frontend_admin_view_page_split(text)
            or split_admin_dashboard_settings
        )
        split_auth_public_setup_views = (
            should_split_final_frontend_auth_public_setup_timeout(text)
            or should_preserve_final_frontend_auth_public_setup_split(text)
        )
        split_setup_not_found_views = (
            should_split_final_frontend_setup_not_found_timeout(text)
            or should_preserve_final_frontend_setup_not_found_split(text)
        )
        split_auth_public_setup_views = split_auth_public_setup_views or split_setup_not_found_views
        split_view_pages = (
            should_split_final_frontend_view_page_timeout(text)
            or should_preserve_final_frontend_view_page_split(text)
            or split_admin_view_pages
            or split_auth_public_setup_views
        )
        split_state_composable_utility = (
            should_split_final_frontend_state_composable_utility_timeout(text)
            or should_preserve_final_frontend_state_composable_utility_split(text)
        )
        split_composable_contracts = (
            should_split_final_frontend_composable_contracts_timeout(text)
            or should_preserve_final_frontend_composable_contracts_split(text)
        )
        split_metering_entitlement_composables = (
            should_split_final_frontend_metering_entitlement_composables_timeout(text)
            or should_preserve_final_frontend_metering_entitlement_composables_split(text)
        )
        split_frontend_test_fixtures = should_split_final_frontend_test_fixture_timeout(
            text
        ) or should_preserve_final_frontend_test_fixture_split(text)
        split_component_composable_tests = should_split_final_frontend_component_composable_test_timeout(text)
        split_composable_contracts = split_composable_contracts or split_metering_entitlement_composables
        split_state_composable_utility = split_state_composable_utility or split_composable_contracts
        split_admin_usage_payment = should_split_final_frontend_admin_usage_payment_timeout(
            text
        ) or should_preserve_final_frontend_admin_usage_payment_split(text) or split_admin_payment
        split_admin_user_account = (
            should_split_final_frontend_admin_user_account_timeout(text)
            or should_preserve_final_frontend_admin_user_account_split(text)
            or split_admin_user_create_edit
        )
        split_admin_account_modal = (
            should_split_final_frontend_admin_account_modal_timeout(text)
            or split_admin_user_account
        )
        split_admin_account_identity = (
            should_split_final_frontend_admin_account_identity_timeout(text)
            or split_admin_account_modal
        )
        split_admin_components = (
            should_split_final_frontend_admin_component_timeout(text)
            or split_admin_account_identity
            or split_admin_usage_payment
        )
        narrow_route_app_shell = should_narrow_final_frontend_route_app_shell_timeout(text)
        split_frontend_view_components = (
            should_split_final_frontend_view_component_timeout(text)
            or should_preserve_final_frontend_view_component_split(text)
            or split_admin_components
            or split_view_pages
        )
        if (
            split_frontend_view_components
            or split_state_composable_utility
            or split_composable_contracts
            or split_frontend_test_fixtures
        ):
            # Preserve stable upstream task IDs when a downstream frontend repair
            # is split again; otherwise every resume renumbers the failed leaf.
            split_api_i18n = True
        if preserve_deep_final_frontend_tail:
            split_api_i18n = True
            split_admin_user_create_edit = True
            split_admin_payment_refund = True
            split_admin_payment = True
            split_admin_announcement_backup_promo = True
            split_admin_email_template_leaf = True
            split_admin_settings_email_compliance = True
            split_admin_dashboard_settings = True
            split_admin_view_pages = True
            split_auth_public_setup_views = True
            split_setup_not_found_views = True
            split_view_pages = True
            split_metering_entitlement_composables = True
            split_composable_contracts = True
            split_state_composable_utility = True
            split_frontend_test_fixtures = True
            split_admin_usage_payment = True
            split_admin_user_account = True
            split_admin_account_modal = True
            split_admin_account_identity = True
            split_admin_components = True
            split_frontend_view_components = True
        specs.extend(
            final_frontend_api_i18n_repair_task_specs(
                split=split_api_i18n,
                split_api_module_leaf=should_narrow_final_frontend_api_module_leaf_timeout(text),
                split_i18n_locale_leaf=split_i18n_locale_leaf,
            )
        )
        specs.extend(
            final_frontend_routes_views_repair_task_specs(
                split=(
                    split_routes_views
                    or split_frontend_view_components
                    or split_state_composable_utility
                    or narrow_route_app_shell
                ),
                narrow_route_app_shell=narrow_route_app_shell,
                split_view_components=split_frontend_view_components,
                split_admin_components=split_admin_components,
                split_admin_account_identity=split_admin_account_identity,
                split_admin_account_modal=split_admin_account_modal,
                split_admin_user_account=split_admin_user_account,
                split_admin_user_create_edit=split_admin_user_create_edit,
                split_admin_usage_payment=split_admin_usage_payment,
                split_admin_payment=split_admin_payment,
                split_admin_payment_refund=split_admin_payment_refund,
                split_view_pages=split_view_pages,
                split_admin_view_pages=split_admin_view_pages,
                split_admin_dashboard_settings=split_admin_dashboard_settings,
                split_admin_settings_email_compliance=split_admin_settings_email_compliance,
                split_admin_email_template_leaf=split_admin_email_template_leaf,
                split_admin_announcement_backup_promo=split_admin_announcement_backup_promo,
                split_auth_public_setup_views=split_auth_public_setup_views,
                split_setup_not_found_views=split_setup_not_found_views,
                split_state_composable_utility=split_state_composable_utility,
                split_composable_contracts=split_composable_contracts,
                split_metering_entitlement_composables=split_metering_entitlement_composables,
                split_frontend_test_fixtures=split_frontend_test_fixtures,
                split_component_composable_tests=split_component_composable_tests,
            )
        )
    if should_repair_final_delivery_artifacts(text):
        specs.append(
            {
                "title": "Repair final delivery artifact contracts",
                "description": (
                    "Clean delivered documentation, Docker, compose, and deployment artifacts so the handoff no "
                    "longer exposes retired token relay, API gateway resale, proxy, provider channel, or relay "
                    "service behavior."
                ),
                "assigned_agent": "docs",
                "relevant_files": [
                    "README.md",
                    "Dockerfile",
                    "deploy/**",
                    "deploy/docker-compose*.yml",
                    "deploy/config.example.yaml",
                    ".github/workflows/**",
                ],
                "completion_criteria": [
                    "Delivery documentation and deployment samples describe the CRM Billing Core product, not a token relay or gateway resale service.",
                    "Retired relay service artifacts are removed, disabled, or reframed as non-delivered legacy infrastructure.",
                    "Static delivery audit findings from final verification are addressed before final audit reruns.",
                ],
                "priority": 87,
            }
        )
    if should_repair_final_embedded_runtime_assets(text):
        specs.append(
            {
                "title": "Repair final embedded runtime asset contracts",
                "description": (
                    "Repair embedded runtime HTML and Veyra portal assets so delivered static/runtime surfaces "
                    "no longer expose retired API gateway, sub2api console, provider channel, or model-channel "
                    "identity."
                ),
                "assigned_agent": "backend",
                "relevant_files": [
                    "backend/internal/web/embed_on.go",
                    "backend/internal/web/embed_test.go",
                    "backend/internal/veyra/portal_dist/index.html",
                    "backend/internal/veyra/portal_dist/mobile.html",
                    "backend/internal/veyra/portal_dist/app.js",
                    "extensions/veyra/portal/**",
                    "backend/go.mod",
                    "backend/go.sum",
                ],
                "completion_criteria": [
                    "Embedded runtime HTML titles and routes use CRM Billing Core identity instead of AI API Gateway or sub2api console copy.",
                    "Veyra portal source and bundled dist assets no longer expose retired gateway/provider/channel identity.",
                    "Embedded asset coverage rejects the obsolete gateway title and portal copy before final gates rerun.",
                ],
                "priority": 86,
            }
        )
    if should_repair_final_veyra_portal_branding(text):
        specs.append(
            {
                "title": "Repair final Veyra portal branding contracts",
                "description": (
                    "Align Veyra portal middleware tests and bundled portal HTML with the intended delivered "
                    "Billing Core branding."
                ),
                "assigned_agent": "backend",
                "relevant_files": [
                    "backend/internal/veyra/portal_test.go",
                    "backend/internal/veyra/portal_dist/index.html",
                    "backend/internal/veyra/portal_dist/mobile.html",
                    "extensions/veyra/portal/**",
                    "backend/go.mod",
                    "backend/go.sum",
                ],
                "completion_criteria": [
                    "Portal middleware tests assert the intended Veyra Billing Portal branding.",
                    "Bundled portal HTML and source portal branding are aligned.",
                    "Focused internal/veyra portal middleware tests pass.",
                ],
                "priority": 88,
            }
        )
    if should_repair_final_backend_startup_contract(text):
        specs.append(
            {
                "title": "Repair final backend startup contract wiring",
                "description": (
                    "Repair generated server startup wiring so fresh database contract enforcement runs after "
                    "SQL database initialization."
                ),
                "assigned_agent": "backend",
                "relevant_files": [
                    "backend/cmd/server/wire.go",
                    "backend/cmd/server/wire_gen.go",
                    "backend/cmd/server/database_contract.go",
                    "backend/cmd/server/database_contract_test.go",
                    "backend/go.mod",
                    "backend/go.sum",
                ],
                "completion_criteria": [
                    "Generated startup wiring calls enforceFreshDatabaseContract after SQL database initialization.",
                    "The focused cmd/server fresh database startup contract test passes.",
                    "No broad backend service or handler cleanup is bundled into this repair.",
                ],
                "priority": 88,
            }
        )
    if should_repair_final_backend_account_repository_predicates(text):
        specs.append(
            {
                "title": "Repair final backend account repository predicate contracts",
                "description": (
                    "Repair account repository callers that still reference removed Ent account-group predicates "
                    "after the CRM schema rename."
                ),
                "assigned_agent": "backend",
                "relevant_files": [
                    "backend/internal/repository/account_repo.go",
                    "backend/internal/repository/account_repo*_test.go",
                    "backend/ent/account/where.go",
                    "backend/go.mod",
                    "backend/go.sum",
                ],
                "completion_criteria": [
                    "Account repository callers use the CRM-renamed Ent predicates.",
                    "The focused cmd/server compile or account repository checks no longer fail on removed predicates.",
                    "No broad Ent schema or repository sweep is bundled unless the focused compile proves it is necessary.",
                ],
                "priority": 88,
            }
        )
    if should_repair_final_frontend_locale_component_surfaces(text):
        specs.append(
            {
                "title": "Repair final frontend locale component boundary contracts",
                "description": (
                    "Repair remaining user-facing locale and reachable component copy that still exposes "
                    "model-provider, gateway, client, or service-account-pool identity."
                ),
                "assigned_agent": "frontend",
                "relevant_files": [
                    "frontend/src/i18n/locales/en.ts",
                    "frontend/src/i18n/locales/zh.ts",
                    "frontend/src/views/admin/SettingsView.vue",
                    "frontend/src/components/payment/SubscriptionPlanCard.vue",
                    "frontend/src/components/user/PlatformUsageBreakdown.vue",
                    "frontend/package.json",
                    "frontend/pnpm-lock.yaml",
                ],
                "completion_criteria": [
                    "Locale copy and reachable component labels use CRM billing, wallet, usage, and account language.",
                    "Retired model/provider/client/gateway identity is removed from the named frontend surfaces.",
                    "Focused frontend semantic probes or component tests are updated or run before final gates rerun.",
                ],
                "priority": 87,
            }
        )
    if should_repair_final_frontend_locale_settings_surfaces(text):
        specs.append(
            {
                "title": "Repair final frontend locale settings boundary contracts",
                "description": (
                    "Repair the remaining frontend locale and admin settings copy that still exposes "
                    "provider, channel, proxy, gateway, or OpenAI-style identity."
                ),
                "assigned_agent": "frontend",
                "relevant_files": [
                    "frontend/src/i18n/locales/en.ts",
                    "frontend/src/i18n/locales/zh.ts",
                    "frontend/src/views/admin/SettingsView.vue",
                    "frontend/package.json",
                    "frontend/pnpm-lock.yaml",
                ],
                "completion_criteria": [
                    "The named locale/settings surfaces have zero user-facing old provider/channel/proxy/gateway/OpenAI-style hits.",
                    "Focused source-boundary probes for the three files pass before final gates rerun.",
                    "No unrelated frontend component work is bundled into this repair.",
                ],
                "priority": 88,
            }
        )
    if should_repair_final_frontend_admin_api_build_lint(text):
        specs.append(
            {
                "title": "Repair final frontend admin API build lint contracts",
                "description": (
                    "Repair frontend typecheck/build and lint failures reported by the final real repository checks."
                ),
                "assigned_agent": "frontend",
                "relevant_files": [
                    "frontend/src/api/admin/settings.ts",
                    "frontend/src/api/admin/usage.ts",
                    "frontend/src/api/admin/users.ts",
                    "frontend/src/views/admin/ops/components/__tests__/OpsSettingsDialog.spec.ts",
                    "frontend/src/views/admin/ops/components/__tests__/OpsSystemLogTable.spec.ts",
                    "frontend/src/api/__tests__/admin.users.spec.ts",
                    "frontend/package.json",
                    "frontend/pnpm-lock.yaml",
                ],
                "completion_criteria": [
                    "Frontend typecheck/build no longer fails in admin settings, usage, or users API modules.",
                    "Frontend lint:check no longer fails in the named ops/admin users specs.",
                    "Focused frontend build/lint checks are rerun before final gates.",
                ],
                "priority": 88,
            }
        )
    if should_repair_final_frontend_forbidden_admin_surface(text):
        specs.append(
            {
                "title": "Repair final frontend forbidden admin route surface contracts",
                "description": (
                    "Repair active frontend routes, sidebar entries, stores, APIs, views, and stale tests that still "
                    "expose backend-forbidden admin groups, announcements, or retired ops endpoints."
                ),
                "assigned_agent": "frontend",
                "relevant_files": [
                    "frontend/src/router/index.ts",
                    "frontend/src/components/layout/AppSidebar.vue",
                    "frontend/src/App.vue",
                    "frontend/src/stores/**",
                    "frontend/src/api/admin/groups.ts",
                    "frontend/src/api/admin/announcements.ts",
                    "frontend/src/api/announcements.ts",
                    "frontend/src/api/__tests__/admin.ops.spec.ts",
                    "frontend/src/views/admin/__tests__/legacyAdminRoutes.spec.ts",
                    "frontend/src/components/admin/announcements/**",
                    "frontend/src/views/admin/announcements/**",
                    "frontend/src/views/admin/UsersView.vue",
                    "frontend/src/views/admin/SettingsView.vue",
                    "frontend/src/views/admin/UsageView.vue",
                    "frontend/src/views/admin/ops/**",
                    "frontend/package.json",
                    "frontend/pnpm-lock.yaml",
                ],
                "completion_criteria": [
                    "Active frontend navigation and direct-route surfaces no longer expose backend-forbidden admin groups, announcements, or retired ops endpoints.",
                    "Admin groups and announcement API usage is removed, renamed, or rebound to allowed CRM access-policy, audit, analytics, or observability contracts.",
                    "Stale tests assert the new allowed CRM endpoints instead of /admin/ops, /admin/groups, /announcements, or /admin/announcements.",
                    "Focused frontend source-boundary probes and affected vitest specs pass before final gates rerun.",
                ],
                "priority": 89,
            }
        )
    if should_repair_final_frontend_route_sidebar_contract(text):
        specs.append(
            {
                "title": "Repair final frontend route/sidebar contract leftovers",
                "description": (
                    "Repair the final frontend route and sidebar contract mismatch around the CRM admin surface, "
                    "including the AdminAnnouncements expectation and unused AppSidebar icon build blocker."
                ),
                "assigned_agent": "frontend",
                "relevant_files": [
                    "frontend/src/router/index.ts",
                    "frontend/src/router/__tests__/crm-route-surface.spec.ts",
                    "frontend/src/components/layout/AppSidebar.vue",
                    "frontend/src/components/layout/__tests__/AppSidebar.spec.ts",
                    "frontend/src/views/admin/announcements/**",
                    "frontend/src/components/admin/announcements/**",
                    "frontend/package.json",
                    "frontend/pnpm-lock.yaml",
                ],
                "completion_criteria": [
                    "Frontend router and AppSidebar agree on the final CRM admin route surface.",
                    "AdminAnnouncements is either restored consistently or removed from tests and navigation contracts consistently.",
                    "AppSidebar.vue no longer declares an unused BellIcon and frontend build/test failures are resolved by focused checks.",
                ],
                "priority": 90,
            }
        )
    if should_split_final_admin_settings_legacy_timeout(text):
        specs.extend(final_admin_settings_legacy_timeout_split_task_specs())
    elif should_repair_final_admin_settings_legacy_surface(text):
        specs.append(
            {
                "title": "Repair final admin settings legacy surface contracts",
                "description": (
                    "Repair reachable admin settings API/UI contracts that still expose legacy OpenAI, gateway, "
                    "channel, or subscription-era settings."
                ),
                "assigned_agent": "integration",
                "relevant_files": [
                    "backend/internal/handler/admin/**/*settings*",
                    "backend/internal/service/**/*settings*",
                    "backend/internal/model/**/*settings*",
                    "backend/internal/dto/**/*settings*",
                    "backend/internal/config/**",
                    "backend/go.mod",
                    "backend/go.sum",
                    "frontend/src/api/admin/settings.ts",
                    "frontend/src/views/admin/SettingsView.vue",
                    "frontend/src/i18n/locales/en.ts",
                    "frontend/src/i18n/locales/zh.ts",
                    "frontend/src/api/__tests__/**/*settings*",
                    "frontend/src/views/admin/**/*settings*",
                    "frontend/src/views/admin/__tests__/**",
                    "frontend/package.json",
                    "frontend/pnpm-lock.yaml",
                ],
                "completion_criteria": [
                    "Reachable admin settings API/UI no longer exposes OpenAI, gateway, channel, or subscription-era settings as CRM product behavior.",
                    "Legacy-compatible settings are removed, renamed, or strictly fenced away from delivered admin UI contracts.",
                    "Focused backend/frontend settings tests, frontend typecheck, and settings source-boundary probes pass before final gates rerun.",
                ],
                "priority": 89,
            }
        )
    if should_repair_final_frontend_dependency_audit(text):
        specs.append(
            {
                "title": "Repair final frontend dependency audit contracts",
                "description": (
                    "Repair frontend dependency audit findings that block final handoff, especially stale high-severity "
                    "xlsx advisories recorded in frontend audit evidence."
                ),
                "assigned_agent": "frontend",
                "relevant_files": [
                    "frontend/package.json",
                    "frontend/pnpm-lock.yaml",
                    "frontend/audit.json",
                ],
                "completion_criteria": [
                    "Frontend package manifests no longer pin the vulnerable xlsx dependency reported by the audit evidence.",
                    "Frontend dependency audit evidence is regenerated or documented as clean enough for final handoff.",
                    "Package lockfile changes are limited to the dependency audit repair.",
                ],
                "priority": 86,
            }
        )
    if should_repair_final_frontend_admin_ops_audit_surface(text):
        specs.append(
            {
                "title": "Repair final frontend admin ops audit surface contracts",
                "description": (
                    "Repair the reachable AdminAudit/ops route and API surface so frontend CRM audit, "
                    "analytics, and observability calls are congruent with registered backend admin routes "
                    "and no retired /admin/ops relay-era endpoints remain reachable."
                ),
                "assigned_agent": "integration",
                "relevant_files": [
                    "backend/internal/server/routes/admin.go",
                    "backend/internal/server/**",
                    "backend/internal/handler/admin/**",
                    "backend/internal/service/**",
                    "backend/internal/repository/**",
                    "backend/cmd/server/**",
                    "backend/go.mod",
                    "backend/go.sum",
                    "frontend/src/router/index.ts",
                    "frontend/src/components/layout/AppSidebar.vue",
                    "frontend/src/api/admin/ops.ts",
                    "frontend/src/views/admin/ops/**",
                    "frontend/src/views/admin/UsageView.vue",
                    "frontend/src/router/__tests__/**",
                    "frontend/src/api/__tests__/**",
                    "frontend/src/views/admin/__tests__/**",
                    "frontend/package.json",
                    "frontend/pnpm-lock.yaml",
                ],
                "completion_criteria": [
                    "Reachable AdminAudit/admin ops surfaces are renamed, removed, or backed by registered CRM audit/analytics/observability backend admin routes.",
                    "A targeted route/API congruence check covers active frontend admin API bases versus backend registered route groups.",
                    "Source-boundary probes find zero reachable /admin/ops/** calls.",
                    "Focused frontend route/API tests and backend route/handler checks for the affected admin surfaces pass or record precise follow-ups.",
                ],
                "priority": 88,
            }
        )
    if should_repair_final_admin_dashboard_access_policy_congruence(text):
        specs.append(
            {
                "title": "Repair final admin dashboard access policy route contracts",
                "description": (
                    "Repair active AdminDashboard and access-policy frontend/backend contract mismatches so "
                    "/admin/dashboard and /admin/access-policies calls are either backed by registered CRM admin "
                    "routes or retargeted to registered analytics/access-policy contracts."
                ),
                "assigned_agent": "integration",
                "relevant_files": [
                    "backend/internal/server/routes/admin.go",
                    "backend/internal/server/**",
                    "backend/internal/handler/admin/dashboard_handler.go",
                    "backend/internal/handler/admin/dashboard_handler_*_test.go",
                    "backend/internal/handler/admin/*group*",
                    "backend/internal/service/**",
                    "backend/internal/repository/**",
                    "backend/cmd/server/**",
                    "backend/go.mod",
                    "backend/go.sum",
                    "frontend/src/api/admin/dashboard.ts",
                    "frontend/src/api/admin/groups.ts",
                    "frontend/src/views/admin/DashboardView.vue",
                    "frontend/src/views/admin/UsersView.vue",
                    "frontend/src/views/admin/SettingsView.vue",
                    "frontend/src/components/admin/user/**",
                    "frontend/src/components/charts/**",
                    "frontend/src/api/__tests__/**",
                    "frontend/src/views/admin/__tests__/**",
                    "frontend/package.json",
                    "frontend/pnpm-lock.yaml",
                ],
                "completion_criteria": [
                    "Active frontend /admin/dashboard calls are backed by registered backend admin dashboard routes or retargeted to registered analytics dashboard routes.",
                    "Active frontend /admin/access-policies usage is backed by registered backend routes or removed/retargeted to the final CRM access-policy contract.",
                    "A focused route/API congruence check covers dashboard and access-policy frontend bases versus backend registered route groups.",
                    "Focused backend route/handler checks and frontend dashboard/group API tests pass or leave only precise follow-ups.",
                ],
                "priority": 89,
            }
        )
    if should_repair_final_admin_user_group_quota_surface(text):
        specs.append(
            {
                "title": "Repair final admin user group quota surface contracts",
                "description": (
                    "Repair active admin user replace-group and platform-quota surfaces that final audit marks "
                    "as forbidden relay-era user group/quota APIs."
                ),
                "assigned_agent": "integration",
                "relevant_files": [
                    "backend/internal/server/routes/admin.go",
                    "backend/internal/handler/admin/user_handler.go",
                    "backend/internal/handler/admin/*user*_test.go",
                    "backend/internal/service/user_service.go",
                    "backend/internal/service/user_service_test.go",
                    "backend/go.mod",
                    "backend/go.sum",
                    "frontend/src/api/admin/users.ts",
                    "frontend/src/api/__tests__/admin.users.spec.ts",
                    "frontend/src/views/admin/UsersView.vue",
                    "frontend/src/views/admin/__tests__/UsersView.spec.ts",
                    "frontend/src/components/admin/user/GroupReplaceModal.vue",
                    "frontend/src/components/admin/user/UserAllowedGroupsModal.vue",
                    "frontend/src/components/admin/user/UserApiKeysModal.vue",
                    "frontend/src/components/admin/user/**",
                    "frontend/package.json",
                    "frontend/pnpm-lock.yaml",
                ],
                "completion_criteria": [
                    "Frontend admin user API and reachable UI no longer expose forbidden replace-group or platform-quota relay-era surfaces.",
                    "Any retained user group/quota behavior is renamed or proved as final CRM access-policy behavior and is registered/tested consistently.",
                    "Focused admin user API/view tests and backend route checks pass or record precise residual follow-ups.",
                ],
                "priority": 88,
            }
        )
    if should_repair_final_rpm_override_route_contract_leftovers(text):
        specs.append(final_rpm_override_route_contract_leftover_task_spec())
    if should_repair_final_settings_advanced_scheduler_contract(text):
        specs.append(final_settings_advanced_scheduler_contract_task_spec())
    if should_repair_final_settings_api_contract_test(text):
        specs.append(final_settings_api_contract_test_task_spec())
    if should_repair_final_frontend_user_quota_typecheck_import(text):
        specs.append(final_frontend_user_quota_typecheck_import_task_spec())
    if should_repair_final_simulation_suite_failures(text):
        specs.extend(final_simulation_suite_failure_task_specs())
    elif should_repair_final_platform_rpm_capacity_surface(text):
        if should_split_final_backend_admin_rpm_capacity_timeout(text):
            specs.extend(final_backend_admin_rpm_capacity_split_task_specs())
        elif should_split_final_admin_settings_rpm_capacity_timeout(text):
            specs.extend(final_admin_settings_rpm_capacity_split_task_specs())
        elif should_split_final_platform_rpm_capacity_timeout(text):
            specs.extend(final_platform_rpm_capacity_split_task_specs())
        else:
            specs.append(
                {
                    "title": "Repair final platform RPM capacity surface contracts",
                    "description": (
                        "Repair active /user/platform-quotas and admin platform/RPM quota settings that final audit "
                        "marks as forbidden or frontend/backend-incongruent, reframing any retained behavior as final "
                        "CRM account-capacity contracts."
                    ),
                    "assigned_agent": "integration",
                    "relevant_files": [
                        "backend/internal/server/routes/admin.go",
                        "backend/internal/server/routes/user.go",
                        "backend/internal/server/**",
                        "backend/internal/handler/user_handler.go",
                        "backend/internal/handler/user_platform_quotas_handler_test.go",
                        "backend/internal/handler/admin/setting_handler.go",
                        "backend/internal/handler/admin/user_handler.go",
                        "backend/internal/handler/admin/user_platform_quota_admin_test.go",
                        "backend/internal/service/**",
                        "backend/internal/service/user_service.go",
                        "backend/internal/config/**",
                        "backend/go.mod",
                        "backend/go.sum",
                        "frontend/src/api/user.ts",
                        "frontend/src/api/admin/settings.ts",
                        "frontend/src/api/admin/groups.ts",
                        "frontend/src/views/admin/SettingsView.vue",
                        "frontend/src/views/admin/__tests__/SettingsView.spec.ts",
                        "frontend/src/api/__tests__/**",
                        "frontend/src/i18n/locales/en.ts",
                        "frontend/src/i18n/locales/zh.ts",
                        "frontend/package.json",
                        "frontend/pnpm-lock.yaml",
                    ],
                    "completion_criteria": [
                        "/user/platform-quotas is removed or replaced by a registered CRM account-capacity frontend/backend contract.",
                        "Admin platform-quota and RPM quota settings/API controls are removed or reframed as source-approved generic capacity semantics.",
                        "Focused route/API congruence, admin settings, and user API tests cover the final capacity surface.",
                    ],
                    "priority": 90,
                }
            )
    if should_repair_final_backend_active_migration_model_routing(text):
        specs.append(
            {
                "title": "Repair final backend active migration model routing contracts",
                "description": (
                    "Repair active root migration files that still add model-routing/upstream/gateway-era columns "
                    "to the fresh Billing Core schema."
                ),
                "assigned_agent": "backend",
                "relevant_files": [
                    "backend/migrations/040_add_group_model_routing.sql",
                    "backend/migrations/041_add_model_routing_enabled.sql",
                    "backend/cmd/server/database_contract.go",
                    "backend/cmd/server/database_contract_test.go",
                    "backend/go.mod",
                    "backend/go.sum",
                ],
                "completion_criteria": [
                    "Active root migrations no longer add model-routing, upstream, or gateway-era schema fields to fresh Billing Core installs.",
                    "Fresh database contract checks reject the retired migration surfaces.",
                    "Focused migration/source-boundary probes and cmd/server database contract checks pass.",
                ],
                "priority": 88,
            }
        )
    if should_repair_final_backend_sub2api_protocol_identity(text):
        specs.append(
            {
                "title": "Repair final backend runtime protocol identity contracts",
                "description": (
                    "Repair backend runtime protocol and portal intent identifiers that still expose sub2api "
                    "identity after the CRM Billing Core rebrand."
                ),
                "assigned_agent": "backend",
                "relevant_files": [
                    "backend/internal/veyra/intent.go",
                    "backend/internal/veyra/ticket_test.go",
                    "backend/internal/server/middleware/admin_auth.go",
                    "backend/go.mod",
                    "backend/go.sum",
                ],
                "completion_criteria": [
                    "Backend runtime protocol and portal intent names no longer expose sub2api as user-facing identity.",
                    "Related backend tests assert CRM Billing Core protocol/intent naming.",
                    "Focused backend checks for the touched packages pass before final gates rerun.",
                ],
                "priority": 87,
            }
        )
    if should_repair_final_backend_production_identity_strings(text):
        specs.append(
            {
                "title": "Repair final backend production identity string leftovers",
                "description": (
                    "Repair residual backend production sub2api/new-api/middle-station identity strings found by "
                    "final simulation static probes while preserving CRM-compatible infrastructure behavior."
                ),
                "assigned_agent": "backend",
                "relevant_files": [
                    "backend/cmd/server/**",
                    "backend/internal/config/**",
                    "backend/internal/handler/**",
                    "backend/internal/service/**",
                    "backend/internal/repository/**",
                    "backend/internal/pkg/logger/**",
                    "backend/internal/repository/dashboard_cache.go",
                    "backend/internal/pkg/logger/options.go",
                    "backend/internal/pkg/logger/options_test.go",
                    "backend/internal/pkg/sysutil/restart.go",
                    "backend/internal/handler/admin/ops_ws_handler.go",
                    "backend/internal/service/update_service.go",
                    "backend/go.mod",
                    "backend/go.sum",
                ],
                "completion_criteria": [
                    "Backend production files no longer expose sub2api, new-api, or middle-station identity strings.",
                    "Retired gateway, proxy, subscription, provider, and account-relay capability code is removed from the production Billing Core server build or isolated as non-product compatibility infrastructure.",
                    "Cache prefixes, log defaults, websocket protocol names, restart/update text, wire generation, and related tests use CRM Billing Core identity.",
                    "Focused backend static identity/capability probes and affected Go tests pass before final gates rerun.",
                ],
                "priority": 89,
            }
        )
    if should_repair_final_source_boundary_sweep(text):
        specs.extend(
            [
                {
                    "title": "Repair final backend migration source-boundary leftovers",
                    "description": (
                        "Repair final migration-source boundary failures so fresh Billing Core installs no longer "
                        "create or alter retired relay-era tables."
                    ),
                    "assigned_agent": "backend",
                    "relevant_files": [
                        "backend/migrations/**",
                        "backend/cmd/server/database_contract.go",
                        "backend/cmd/server/database_contract_test.go",
                        "backend/internal/server/billing_core_routes_test.go",
                        "backend/go.mod",
                        "backend/go.sum",
                    ],
                    "completion_criteria": [
                        "Fresh-install migrations no longer create or alter retired account, proxy, upstream, channel, channel-monitor, model-routing, or subscription-plan tables.",
                        "Legacy upgrade SQL is removed, renamed, or isolated away from the fresh Billing Core migration path.",
                        "Focused migration static probes and fresh database contract checks are attempted before final gates rerun.",
                    ],
                    "priority": 91,
                },
                {
                    "title": "Repair final backend production source-boundary leftovers",
                    "description": (
                        "Repair remaining backend production source, config, and wiring that still exposes retired "
                        "gateway, proxy, upstream, account-relay, model-provider, or subscription behavior."
                    ),
                    "assigned_agent": "backend",
                    "relevant_files": [
                        "backend/cmd/server/**",
                        "backend/internal/config/**",
                        "backend/internal/domain/**",
                        "backend/internal/repository/**",
                        "backend/internal/service/**",
                        "backend/internal/handler/**",
                        "backend/internal/server/**",
                        "backend/internal/pkg/logger/**",
                        "backend/internal/pkg/sysutil/**",
                        "backend/go.mod",
                        "backend/go.sum",
                    ],
                    "completion_criteria": [
                        "Production backend source and generated wiring no longer expose retired gateway, proxy, upstream, channel-monitor, model-routing, account-relay, or subscription-plan product surfaces.",
                        "Reusable infrastructure is either reframed under CRM billing semantics or isolated from the delivered production build.",
                        "Focused backend source-boundary probes and affected package tests are attempted before final gates rerun.",
                    ],
                    "priority": 90,
                },
                *(
                    final_frontend_retired_source_boundary_split_task_specs()
                    if should_split_final_frontend_retired_source_boundary_timeout(text)
                    else [
                        {
                            "title": "Repair final frontend retired source-boundary leftovers",
                            "description": (
                                "Repair remaining frontend API, composable, type, store, and copy surfaces that still expose "
                                "retired relay-era product concepts."
                            ),
                            "assigned_agent": "frontend",
                            "relevant_files": [
                                "frontend/src/api/**",
                                "frontend/src/composables/**",
                                "frontend/src/stores/**",
                                "frontend/src/types/**",
                                "frontend/src/constants/**",
                                "frontend/src/i18n/**",
                                "frontend/src/router/**",
                                "frontend/src/views/**",
                                "frontend/src/components/**",
                                "frontend/package.json",
                                "frontend/pnpm-lock.yaml",
                            ],
                            "completion_criteria": [
                                "Frontend source probes no longer find retired API/composable/type/store surfaces for upstream account, proxy, channel-monitor, model-routing, token-log, or subscription-plan behavior.",
                                "Retired compatibility facades are removed, renamed, or quarantined outside delivered public/frontend contracts.",
                                "Focused frontend source-boundary probes and affected vitest specs are attempted before final gates rerun.",
                            ],
                            "priority": 89,
                        }
                    ]
                ),
            ]
        )
    unfiltered_specs = list(specs)
    if should_repair_final_remaining_source_boundary_after_split(text):
        specs.extend(
            [
                *(
                    [
                        *final_backend_provider_proxy_ops_service_quarantine_split_task_specs(),
                        final_backend_legacy_quarantine_split_task_specs()[2],
                    ]
                    if should_split_final_backend_provider_proxy_ops_service_quarantine_timeout(text)
                    else
                    [
                        *final_backend_service_repository_quarantine_exact_task_specs(),
                        final_backend_legacy_quarantine_split_task_specs()[2],
                    ]
                    if should_split_final_backend_service_repository_quarantine_timeout(text)
                    else
                    [
                        *final_backend_handler_server_quarantine_exact_task_specs(),
                        *final_backend_legacy_quarantine_split_task_specs()[1:],
                    ]
                    if should_split_final_backend_handler_server_quarantine_timeout(text)
                    else final_backend_legacy_quarantine_split_task_specs()
                    if should_split_final_backend_legacy_quarantine_timeout(text)
                    else [
                        {
                            "title": "Repair final backend legacy production quarantine leftovers",
                            "description": (
                                "Repair the final audit's remaining backend production/delivery source-boundary findings by "
                                "removing, quarantining, or CRM-renaming retired relay-era handlers, services, repositories, "
                                "config, and server wiring."
                            ),
                            "assigned_agent": "backend",
                            "relevant_files": [
                                "backend/internal/handler/**",
                                "backend/internal/service/**",
                                "backend/internal/repository/**",
                                "backend/internal/config/**",
                                "backend/internal/server/**",
                                "backend/cmd/server/**",
                                "backend/internal/pkg/**",
                                "backend/go.mod",
                                "backend/go.sum",
                            ],
                            "completion_criteria": [
                                "Backend production/delivery source no longer exposes retired gateway, OpenAI gateway, proxy, channel-monitor, upstream-account, or subscription-plan product surfaces.",
                                "Retired implementation files are removed, build-tag quarantined, or reframed under CRM billing/service-integration semantics without reintroducing forbidden routes.",
                                "Focused backend source-boundary probes and affected Go package checks are attempted before final gates rerun.",
                            ],
                            "priority": 91,
                        }
                    ]
                ),
                {
                    "title": "Repair final frontend API settings typecheck leftovers",
                    "description": (
                        "Repair frontend API, settings, ops, payment resume, types, and locale surfaces that still "
                        "block source-boundary and vue-tsc checks after API/composable cleanup."
                    ),
                    "assigned_agent": "frontend",
                    "relevant_files": [
                        "frontend/src/api/**",
                        "frontend/src/types/**",
                        "frontend/src/i18n/**",
                        "frontend/src/utils/paymentWechatResume.ts",
                        "frontend/src/utils/**",
                        "frontend/src/views/admin/ops/**",
                        "frontend/src/views/admin/SettingsView.vue",
                        "frontend/package.json",
                        "frontend/pnpm-lock.yaml",
                    ],
                    "completion_criteria": [
                        "Frontend API/settings/ops/payment resume code no longer exposes retired subscription, upstream, proxy, ops facade, or gateway product symbols.",
                        "Type contracts and locale labels use CRM billing, wallet, service integration, audit, and observability terms.",
                        "Focused vue-tsc or API/settings/ops checks are attempted before final gates rerun.",
                    ],
                    "priority": 90,
                },
                {
                    "title": "Repair final frontend view component typecheck leftovers",
                    "description": (
                        "Repair remaining frontend view and component consumers that still import removed retired "
                        "compatibility names or expose retired labels."
                    ),
                    "assigned_agent": "frontend",
                    "relevant_files": [
                        "frontend/src/components/common/SubscriptionProgressMini.vue",
                        "frontend/src/components/payment/SubscriptionPlanCard.vue",
                        "frontend/src/components/user/dashboard/UserDashboardCharts.vue",
                        "frontend/src/components/**",
                        "frontend/src/views/user/UsageView.vue",
                        "frontend/src/views/admin/UsageView.vue",
                        "frontend/src/views/**",
                        "frontend/src/i18n/**",
                        "frontend/package.json",
                        "frontend/pnpm-lock.yaml",
                    ],
                    "completion_criteria": [
                        "Frontend views/components consume the current CRM billing helper exports and constants instead of removed retired compatibility names.",
                        "User-facing labels no longer expose retired subscription/upstream/proxy/ops product vocabulary.",
                        "Focused component/view vitest specs and vue-tsc checks are attempted before final gates rerun.",
                    ],
                    "priority": 89,
                },
            ]
        )
    if should_repair_final_remaining_source_boundary_after_split(text):
        if should_split_final_backend_provider_proxy_ops_service_quarantine_timeout(text):
            backend_quarantine_titles = [
                "Repair final backend account OAuth service quarantine exact files",
                "Repair final backend channel monitor service quarantine exact files",
                "Repair final backend proxy upstream service quarantine exact files",
                "Repair final backend ops settings service quarantine exact files",
                "Repair final backend config runtime quarantine leftovers",
            ]
        elif should_split_final_backend_service_repository_quarantine_timeout(text):
            backend_quarantine_titles = [
                "Repair final backend repository domain quarantine exact files",
                "Repair final backend gateway OpenAI service quarantine exact files",
                "Repair final backend provider proxy ops service quarantine exact files",
                "Repair final backend config runtime quarantine leftovers",
            ]
        elif should_split_final_backend_handler_server_quarantine_timeout(text):
            backend_quarantine_titles = [
                "Repair final backend admin handler quarantine exact files",
                "Repair final backend gateway protocol handler exact files",
                "Repair final backend server middleware quarantine exact files",
                "Repair final backend service repository quarantine leftovers",
                "Repair final backend config runtime quarantine leftovers",
            ]
        elif should_split_final_backend_legacy_quarantine_timeout(text):
            backend_quarantine_titles = [
                "Repair final backend handler server quarantine leftovers",
                "Repair final backend service repository quarantine leftovers",
                "Repair final backend config runtime quarantine leftovers",
            ]
        else:
            backend_quarantine_titles = ["Repair final backend legacy production quarantine leftovers"]
        specs = repair_specs_matching_titles_in_order(
            specs,
            [
                *backend_quarantine_titles,
                "Repair final frontend API settings typecheck leftovers",
                "Repair final frontend view component typecheck leftovers",
                "Repair final frontend locale settings boundary contracts",
            ],
        )
    elif should_repair_final_source_boundary_sweep(text):
        frontend_source_boundary_titles = (
            [
                "Repair final frontend retired API type source-boundary leftovers",
                "Repair final frontend retired composable store source-boundary leftovers",
                "Repair final frontend retired view component source-boundary leftovers",
            ]
            if should_split_final_frontend_retired_source_boundary_timeout(text)
            else ["Repair final frontend retired source-boundary leftovers"]
        )
        specs = repair_specs_matching_titles_in_order(
            specs,
            [
                "Repair final backend migration source-boundary leftovers",
                "Repair final backend production source-boundary leftovers",
                *frontend_source_boundary_titles,
            ],
        )
    elif should_repair_final_backend_production_identity_strings(text):
        specs = repair_specs_matching_titles_in_order(
            specs,
            ["Repair final backend production identity string leftovers"],
        )
    elif should_repair_final_frontend_user_quota_typecheck_import(text):
        simulation_titles = [
            "Repair final backend settings advanced scheduler contract",
            "Repair final backend settings API contract test",
            "Repair final frontend user quota typecheck import",
        ]
        if should_repair_final_rpm_override_route_contract_leftovers(text):
            simulation_titles.insert(0, "Repair final RPM override route contract leftovers")
        specs = repair_specs_matching_titles_in_order(
            specs,
            simulation_titles,
        )
    elif should_repair_final_settings_api_contract_test(text):
        simulation_titles = [
            "Repair final backend settings advanced scheduler contract",
            "Repair final backend settings API contract test",
        ]
        if should_repair_final_rpm_override_route_contract_leftovers(text):
            simulation_titles.insert(0, "Repair final RPM override route contract leftovers")
        specs = repair_specs_matching_titles_in_order(
            specs,
            simulation_titles,
        )
    elif should_repair_final_settings_advanced_scheduler_contract(text):
        simulation_titles = ["Repair final backend settings advanced scheduler contract"]
        if should_repair_final_rpm_override_route_contract_leftovers(text):
            simulation_titles.insert(0, "Repair final RPM override route contract leftovers")
        specs = repair_specs_matching_titles_in_order(
            specs,
            simulation_titles,
        )
    elif should_repair_final_simulation_suite_failures(text):
        simulation_titles = [
            "Repair final frontend UsageTable simulation contracts",
            "Repair final backend admin simulation contracts",
            "Repair final backend DTO usage simulation contracts",
        ]
        if should_repair_final_rpm_override_route_contract_leftovers(text):
            simulation_titles.insert(0, "Repair final RPM override route contract leftovers")
        specs = repair_specs_matching_titles_in_order(
            specs,
            simulation_titles,
        )
    elif should_repair_final_rpm_override_route_contract_leftovers(text):
        specs = repair_specs_matching_titles_in_order(
            specs,
            ["Repair final RPM override route contract leftovers"],
        )
    elif should_repair_final_platform_rpm_capacity_surface(text):
        if should_split_final_backend_admin_rpm_capacity_timeout(text):
            specs = repair_specs_matching_titles_in_order(
                specs,
                [
                    "Repair final backend admin RPM route settings contracts",
                    "Repair final backend admin user capacity handler contracts",
                ],
            )
        elif should_split_final_admin_settings_rpm_capacity_timeout(text):
            specs = repair_specs_matching_titles_in_order(
                specs,
                [
                    "Repair final backend admin RPM capacity contracts",
                    "Repair final frontend admin RPM capacity settings contracts",
                ],
            )
        elif should_split_final_platform_rpm_capacity_timeout(text):
            specs = repair_specs_matching_titles_in_order(
                specs,
                [
                    "Repair final user platform capacity API contracts",
                    "Repair final admin settings RPM capacity contracts",
                ],
            )
        else:
            specs = repair_specs_matching_titles_in_order(
                specs,
                ["Repair final platform RPM capacity surface contracts"],
            )
    elif should_repair_final_frontend_route_sidebar_contract(text):
        specs = repair_specs_matching_titles_in_order(
            specs,
            ["Repair final frontend route/sidebar contract leftovers"],
        )
    elif should_repair_final_frontend_forbidden_admin_surface(text):
        specs = repair_specs_matching_titles_in_order(
            specs,
            ["Repair final frontend forbidden admin route surface contracts"],
        )
    elif should_repair_final_admin_dashboard_access_policy_congruence(
        text
    ) or should_repair_final_admin_user_group_quota_surface(text):
        titles = []
        if should_repair_final_admin_dashboard_access_policy_congruence(text):
            titles.append("Repair final admin dashboard access policy route contracts")
        if should_repair_final_admin_user_group_quota_surface(text):
            titles.append("Repair final admin user group quota surface contracts")
        specs = repair_specs_matching_titles_in_order(specs, titles)
    elif should_repair_final_frontend_admin_ops_audit_surface(text) or should_repair_final_backend_active_migration_model_routing(text):
        specs = repair_specs_matching_titles_in_order(
            specs,
            [
                "Repair final frontend admin ops audit surface contracts",
                "Repair final backend active migration model routing contracts",
            ],
        )
    elif should_split_final_admin_settings_legacy_timeout(text):
        specs = repair_specs_matching_titles_in_order(
            specs,
            [
                "Repair final backend admin settings legacy contracts",
                "Repair final frontend admin settings legacy contracts",
            ],
        )
    elif should_resume_final_admin_settings_boundary_expansion(text):
        specs = repair_specs_matching_titles_in_order(
            specs,
            ["Repair final admin settings legacy surface contracts"],
        )
    elif should_resume_final_supervisor_stopped_repair_order(text) or should_resume_final_frontend_dependency_audit_timeout(text):
        specs = repair_specs_matching_titles_in_order(
            specs,
            [
                "Repair final frontend forbidden admin route surface contracts",
                "Repair final frontend dependency audit contracts",
                "Repair final backend migration contracts",
                "Repair final backend service contract leftovers",
                "Repair final backend service handler server contracts",
                "Repair final frontend locale settings boundary contracts",
            ],
        )
    if preserve_deep_final_frontend_tail:
        specs = [
            spec
            for spec in unfiltered_specs
            if str(spec.get("title", ""))
            not in {
                "Repair final frontend admin ops audit surface contracts",
                "Repair final frontend forbidden admin route surface contracts",
            }
        ]
    return specs


def final_verification_active_repair_text(context_bundle: ContextBundle) -> str:
    """Return only the current repair window, excluding historical failure JSON."""
    fragments: list[str] = []
    for document in context_bundle.documents:
        path = Path(document.path)
        if "final_verification_repair" not in path.name.lower():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        active = False
        has_focus = False
        selected: list[str] = []
        for line in lines:
            lowered = line.strip().lower()
            if lowered.startswith("## previous final verification failure") or lowered.startswith("## previous repair context"):
                active = False
                break
            if (
                lowered.startswith("## requirements")
                or lowered.startswith("## failing verification issues")
                or lowered.startswith("## focused repair scope")
                or lowered.startswith("## previous graph titles")
            ):
                active = True
                has_focus = True
            elif lowered.startswith("## "):
                active = False
            if active or lowered.startswith("repair attempt:"):
                selected.append(line)
        focused = "\n".join(selected).strip()
        if focused and has_focus:
            fragments.append(focused)
    return "\n".join(fragments).lower()


def should_repair_final_delivery_artifacts(text: str) -> bool:
    if not any(marker in text for marker in ["readme", "deploy", "docker-compose", "delivery artifact"]):
        return False
    return any(
        marker in text
        for marker in [
            "relay",
            "gateway",
            "proxy",
            "old-domain",
            "retired",
            "token relay",
            "static delivery audit",
        ]
    )


def final_verification_repair_document_text_fragments(path: str) -> list[str]:
    if "final_verification_repair_resume_" not in str(path).lower():
        return []
    try:
        return [Path(path).read_text(encoding="utf-8", errors="replace")[:24000]]
    except OSError:
        return []


def should_repair_final_embedded_runtime_assets(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "embed_on.go",
            "backend/internal/web",
            "portal_dist",
            "portal_dist/app.js",
            "sub2api-console",
            "veyra portal",
            "embedded runtime assets",
        )
    )


def should_repair_final_frontend_locale_component_surfaces(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "frontend locale/component surfaces",
            "frontend/src/i18n/locales/en.ts",
            "frontend/src/i18n/locales/zh.ts",
            "subscriptionplancard.vue",
            "platformusagebreakdown.vue",
            "service account pool",
            "claude code client restriction",
        )
    )


def should_repair_final_frontend_locale_settings_surfaces(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "frontend locale/settings surfaces",
            "repair final frontend locale settings boundary contracts",
            "source-boundary probe for frontend locales/settings",
            "frontend/src/views/admin/settingsview.vue=121",
            "static_source_boundary_status=fail",
            "provider/v1 locale strings",
            "frontend user-facing strings",
            "remaining frontend i18n/source-boundary cleanup",
            "residual source-boundary terms remain",
            "/v1/chat/completions",
            "/v1/responses",
            "/v1/messages",
            "openai, gemini",
        )
    )


def should_repair_final_backend_old_domain_surface(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "backend sub2api relay/gateway code",
            "backend relay/gateway/provider service",
            "old-domain migration table creation",
            "fresh migration sources still create",
            "sub2api/openai gateway references",
            "denied old-domain tables",
        )
    )


def should_repair_final_frontend_dependency_audit(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "frontend/audit.json",
            "repair final frontend dependency audit contracts",
            "xlsx advisories",
            "xlsx 0.18.5",
            "high-severity xlsx",
        )
    )


def should_repair_final_veyra_portal_branding(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "testportalmiddlewareserves",
            "veyra agent",
            "veyra billing portal",
            "backend/internal/veyra/portal_test.go",
        )
    )


def should_repair_final_frontend_admin_api_build_lint(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "frontend/src/api/admin/settings.ts",
            "frontend/src/api/admin/usage.ts",
            "frontend/src/api/admin/users.ts",
            "admin.users.spec.ts",
            "vue-tsc errors",
            "lint:check",
        )
    )


def should_repair_final_frontend_admin_ops_audit_surface(text: str) -> bool:
    explicit = any(
        marker in text
        for marker in (
            "adminaudit",
            "/admin/audit",
            "/admin/analytics",
            "/admin/observability",
            "backend admin route wiring",
            "route/api congruence",
            "frontend/src/api/admin/ops.ts",
        )
    )
    semantic_ops_route = "/admin/ops" in text and bool(
        re.search(r"\b(route|reachable|expose|exposure|calls?|api surface)\b", text)
    )
    return explicit or semantic_ops_route


def should_repair_final_admin_dashboard_access_policy_congruence(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "active frontend admindashboard calls /admin/dashboard",
            "/admin/dashboard/* endpoints",
            "backend admin route registration does not register /admin/dashboard",
            "active frontend users/settings/user components call /admin/access-policies",
            "backend admin route registration does not register /admin/access-policies",
            "choose one contract for admindashboard",
            "choose one contract for access policies",
            "frontend/src/api/admin/dashboard.ts",
            "frontend/src/api/admin/groups.ts",
        )
    )


def should_repair_final_admin_user_group_quota_surface(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "replace-group",
            "platform-quota",
            "platform-quotas",
            "source plan forbids replace-group",
            "admin user apis",
        )
    )


def should_repair_final_platform_rpm_capacity_surface(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "/user/platform-quotas",
            "getmyplatformquotas",
            "default_platform_quotas",
            "platform_quotas",
            "rpm quota",
            "platform-quota/rpm quota",
            "platform/rpm quota",
            "remove rpm quota endpoints",
            "repair final backend admin rpm capacity contracts",
        )
    )


def should_repair_final_rpm_override_route_contract_leftovers(text: str) -> bool:
    if "source-boundary drift" in text and (
        "default_platform_quotas" in text or "platform quotas" in text or "platform_quotas" in text
    ):
        return False
    if "repair final rpm override route contract leftovers" in text:
        return True
    return (
        "rpm-overrides" in text
        and "frontend/src/api/admin/groups.ts" in text
        and "admin_dashboard_access_policy_routes_test.go" in text
    ) or (
        "retired rpm override frontend api surface" in text
        and "backend route-contract test" in text
    )


def final_rpm_override_route_contract_leftover_task_spec() -> dict[str, object]:
    return {
        "title": "Repair final RPM override route contract leftovers",
        "description": (
            "Repair the last retired RPM override API/test leftovers without reopening the completed backend "
            "admin capacity leaf tasks."
        ),
        "assigned_agent": "integration",
        "relevant_files": [
            "frontend/src/api/admin/groups.ts",
            "frontend/src/api/__tests__/**",
            "frontend/package.json",
            "frontend/pnpm-lock.yaml",
            "backend/internal/server/admin_dashboard_access_policy_routes_test.go",
            "backend/internal/server/routes/admin.go",
            "backend/go.mod",
            "backend/go.sum",
        ],
        "completion_criteria": [
            "Frontend admin groups/access-policy API no longer exposes the retired rpm-overrides endpoint.",
            "Backend admin route contract tests no longer require the retired /admin/access-policies/:id/rpm-overrides route.",
            "Focused frontend API and backend route contract checks pass or record precise residual follow-ups.",
        ],
        "priority": 91,
    }


def should_repair_final_simulation_suite_failures(text: str) -> bool:
    if "source-boundary drift" in text and (
        "default_platform_quotas" in text or "platform quotas" in text or "platform_quotas" in text
    ):
        return False
    if not any(
        marker in text
        for marker in (
            "simulation_test_status=fail",
            "simulation_test_status: fail",
            "simulation_test_status is failed",
        )
    ):
        return False
    return any(
        marker in text
        for marker in (
            "usagetable.spec.ts",
            "backend/internal/handler/admin",
            "backend/internal/handler/dto",
            "full frontend and backend suites fail",
            "14 backend tests failed across admin and dto packages",
        )
    )


def should_repair_final_settings_advanced_scheduler_contract(text: str) -> bool:
    if not any(
        marker in text
        for marker in (
            "simulation_test_status=fail",
            "simulation_test_status: fail",
            "simulation_test_status is failed",
        )
    ):
        return False
    return any(
        marker in text
        for marker in (
            "testsettinghandler_updatesettings_persistspaymentvisiblemethodsandadvancedscheduler",
            "openai_advanced_scheduler_enabled",
            "advanced_credential_scheduler_enabled",
        )
    )


def final_settings_advanced_scheduler_contract_task_spec() -> dict[str, object]:
    return {
        "title": "Repair final backend settings advanced scheduler contract",
        "description": (
            "Repair the final simulation failure where the admin settings update path does not persist "
            "the OpenAI advanced scheduler flag from the request payload."
        ),
        "assigned_agent": "backend",
        "relevant_files": [
            "backend/internal/handler/admin/setting_handler.go",
            "backend/internal/handler/admin/setting_handler_auth_source_defaults_test.go",
            "backend/internal/handler/dto/settings.go",
            "backend/internal/service/setting_service.go",
            "backend/internal/service/setting_service_update_test.go",
            "backend/go.mod",
            "backend/go.sum",
        ],
        "completion_criteria": [
            "The admin settings update handler accepts the final API payload key for OpenAIAdvancedSchedulerEnabled.",
            "The setting key openai_advanced_scheduler_enabled persists true/false through the tested admin update path.",
            "Focused backend admin settings tests pass or report precise remaining blockers.",
        ],
        "priority": 92,
    }


def should_repair_final_settings_api_contract_test(text: str) -> bool:
    if "backend/internal/server/api_contract_test.go" not in text:
        return False
    if "testapicontracts" not in text and "api contract" not in text:
        return False
    return "openai_advanced_scheduler_enabled" in text and "advanced_credential_scheduler_enabled" in text


def final_settings_api_contract_test_task_spec() -> dict[str, object]:
    return {
        "title": "Repair final backend settings API contract test",
        "description": (
            "Align the backend server API contract test with the final OpenAI advanced scheduler settings key."
        ),
        "assigned_agent": "backend",
        "relevant_files": [
            "backend/internal/server/api_contract_test.go",
            "backend/internal/handler/dto/settings.go",
            "backend/internal/handler/admin/setting_handler.go",
            "backend/go.mod",
            "backend/go.sum",
        ],
        "completion_criteria": [
            "The admin settings API contract expects openai_advanced_scheduler_enabled.",
            "The old advanced_credential_scheduler_enabled key is no longer classified as required or retired for the current response contract.",
            "go test -tags unit ./internal/server -run ^TestAPIContracts$ -count=1 passes or reports precise residual blockers.",
        ],
        "priority": 91,
    }


def should_repair_final_frontend_user_quota_typecheck_import(text: str) -> bool:
    if "source-boundary drift" in text and (
        "default_platform_quotas" in text or "platform quotas" in text or "platform_quotas" in text
    ):
        return False
    if "userplatformquotacell.vue" not in text:
        return False
    if "platformquotaitem" not in text or "platformquotaplatform" not in text:
        return False
    return "typecheck" in text or "vue-tsc" in text or "ts2614" in text


def final_frontend_user_quota_typecheck_import_task_spec() -> dict[str, object]:
    return {
        "title": "Repair final frontend user quota typecheck import",
        "description": (
            "Repair the frontend typecheck failure in UserPlatformQuotaCell by aligning type-only imports "
            "with the current shared type exports."
        ),
        "assigned_agent": "frontend",
        "relevant_files": [
            "frontend/src/components/user/UserPlatformQuotaCell.vue",
            "frontend/src/types/index.ts",
            "frontend/src/api/admin/users.ts",
            "frontend/package.json",
            "frontend/pnpm-lock.yaml",
        ],
        "completion_criteria": [
            "UserPlatformQuotaCell imports PlatformQuotaItem and PlatformQuotaPlatform from the module that exports them.",
            "pnpm --dir frontend run typecheck passes or reports precise remaining blockers.",
            "Focused frontend tests related to user platform quotas pass or are explicitly justified as unchanged.",
        ],
        "priority": 90,
    }


def final_simulation_suite_failure_task_specs() -> list[dict[str, object]]:
    return [
        {
            "title": "Repair final frontend UsageTable simulation contracts",
            "description": (
                "Repair the failing final simulation frontend UsageTable image metering tooltip contract."
            ),
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/components/admin/usage/UsageTable.vue",
                "frontend/src/components/admin/usage/__tests__/UsageTable.spec.ts",
                "frontend/src/types/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "UsageTable image metering tooltip renders Image count, Billing size, and Size source metadata expected by final simulation tests.",
                "Focused UsageTable Vitest spec passes.",
                "No backend or unrelated frontend surfaces are modified by this task.",
            ],
            "priority": 90,
        },
        {
            "title": "Repair final backend admin simulation contracts",
            "description": (
                "Repair final simulation failures in backend admin import/export, account mixed-channel, "
                "proxy import, upstream model sync, and settings persistence contracts."
            ),
            "assigned_agent": "backend",
            "relevant_files": [
                "backend/internal/handler/admin/account_codex_import_test.go",
                "backend/internal/handler/admin/account_data.go",
                "backend/internal/handler/admin/account_data_handler_test.go",
                "backend/internal/handler/admin/account_handler.go",
                "backend/internal/handler/admin/account_handler_available_models_test.go",
                "backend/internal/handler/admin/account_handler_mixed_channel_test.go",
                "backend/internal/handler/admin/data_management_handler.go",
                "backend/internal/handler/admin/data_management_handler_test.go",
                "backend/internal/handler/admin/proxy_data_handler.go",
                "backend/internal/handler/admin/proxy_data_handler_test.go",
                "backend/internal/handler/admin/setting_handler.go",
                "backend/internal/handler/admin/setting_handler_platform_quota_test.go",
                "backend/internal/service/**",
                "backend/go.mod",
                "backend/go.sum",
            ],
            "completion_criteria": [
                "Focused backend admin tests listed by the final simulation failure pass or leave only DTO-specific follow-ups.",
                "Admin import/export, mixed-channel, proxy import, upstream model sync, and settings persistence behavior is congruent with final CRM contracts.",
                "Broad `go test ./...` remains reserved for final real repository checks.",
            ],
            "priority": 89,
        },
        {
            "title": "Repair final backend DTO usage simulation contracts",
            "description": "Repair the backend DTO usage mapper failure found by final simulation.",
            "assigned_agent": "backend",
            "relevant_files": [
                "backend/internal/handler/dto/mappers.go",
                "backend/internal/handler/dto/mappers_usage_test.go",
                "backend/internal/handler/dto/types.go",
                "backend/go.mod",
                "backend/go.sum",
            ],
            "completion_criteria": [
                "Usage DTO serialization matches final CRM visibility rules for requested/upstream model fields.",
                "Focused backend DTO usage mapper test passes.",
                "No admin handler repair is reopened by this task.",
            ],
            "priority": 88,
        },
    ]


def should_split_final_platform_rpm_capacity_timeout(text: str) -> bool:
    return (
        "repair final platform rpm capacity surface contracts" in text
        and ("timed out after 900 seconds" in text or "focused timeout task titles" in text)
    )


def should_split_final_admin_settings_rpm_capacity_timeout(text: str) -> bool:
    return (
        "repair final admin settings rpm capacity contracts" in text
        and ("timed out after 900 seconds" in text or "focused timeout task titles" in text)
    )


def should_split_final_backend_admin_rpm_capacity_timeout(text: str) -> bool:
    return (
        "repair final backend admin rpm capacity contracts" in text
        and ("timed out after 900 seconds" in text or "focused timeout task titles" in text)
    )


def final_platform_rpm_capacity_split_task_specs() -> list[dict[str, object]]:
    return [
        {
            "title": "Repair final user platform capacity API contracts",
            "description": (
                "Split the timed-out platform/RPM capacity repair to the user-facing platform capacity API first."
            ),
            "assigned_agent": "integration",
            "relevant_files": [
                "backend/internal/server/routes/user.go",
                "backend/internal/handler/user_handler.go",
                "backend/internal/handler/user_platform_quotas_handler_test.go",
                "backend/go.mod",
                "backend/go.sum",
                "frontend/src/api/user.ts",
                "frontend/src/api/__tests__/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "/user/platform-quotas is removed or replaced by a registered CRM account-capacity contract.",
                "Frontend user API and backend user route registration are congruent for the retained capacity surface.",
                "Focused user API/route tests pass or record only admin settings follow-ups.",
            ],
            "priority": 90,
        },
        {
            "title": "Repair final admin settings RPM capacity contracts",
            "description": (
                "Split the timed-out platform/RPM capacity repair to admin settings, groups API, and backend admin route surfaces."
            ),
            "assigned_agent": "integration",
            "relevant_files": [
                "backend/internal/server/routes/admin.go",
                "backend/internal/handler/admin/setting_handler.go",
                "backend/internal/handler/admin/user_handler.go",
                "backend/internal/handler/admin/user_platform_quota_admin_test.go",
                "backend/internal/service/**",
                "backend/internal/config/**",
                "backend/go.mod",
                "backend/go.sum",
                "frontend/src/api/admin/settings.ts",
                "frontend/src/api/admin/groups.ts",
                "frontend/src/views/admin/SettingsView.vue",
                "frontend/src/views/admin/__tests__/SettingsView.spec.ts",
                "frontend/src/api/__tests__/**",
                "frontend/src/i18n/locales/en.ts",
                "frontend/src/i18n/locales/zh.ts",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "Admin platform-quota and RPM quota settings/API controls are removed or reframed as source-approved account-capacity semantics.",
                "Backend admin route registration and frontend admin settings/groups API are congruent for retained capacity behavior.",
                "Focused admin settings/API tests pass and do not reopen the user platform capacity repair.",
            ],
            "priority": 89,
        },
    ]


def final_admin_settings_rpm_capacity_split_task_specs() -> list[dict[str, object]]:
    return [
        {
            "title": "Repair final backend admin RPM capacity contracts",
            "description": (
                "Split the timed-out admin settings RPM capacity repair to backend admin route, handler, service, and config surfaces."
            ),
            "assigned_agent": "backend",
            "relevant_files": [
                "backend/internal/server/routes/admin.go",
                "backend/internal/handler/admin/setting_handler.go",
                "backend/internal/handler/admin/user_handler.go",
                "backend/internal/handler/admin/user_platform_quota_admin_test.go",
                "backend/internal/service/**",
                "backend/internal/config/**",
                "backend/go.mod",
                "backend/go.sum",
            ],
            "completion_criteria": [
                "Backend admin platform/RPM quota route and handler surfaces are removed or reframed as CRM account-capacity contracts.",
                "Backend admin route registration remains congruent with the final frontend settings/API contract.",
                "Focused backend admin route/handler tests pass or leave only frontend settings follow-ups.",
            ],
            "priority": 90,
        },
        {
            "title": "Repair final frontend admin RPM capacity settings contracts",
            "description": (
                "Split the timed-out admin settings RPM capacity repair to frontend settings, groups API, i18n, and focused tests."
            ),
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/api/admin/settings.ts",
                "frontend/src/api/admin/groups.ts",
                "frontend/src/views/admin/SettingsView.vue",
                "frontend/src/views/admin/__tests__/SettingsView.spec.ts",
                "frontend/src/api/__tests__/**",
                "frontend/src/i18n/locales/en.ts",
                "frontend/src/i18n/locales/zh.ts",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "Frontend admin settings/groups API no longer exposes platform-quota or RPM quota controls except as final account-capacity semantics.",
                "Settings UI and locale copy use final CRM capacity language and stay congruent with backend admin routes.",
                "Focused frontend settings/API tests pass and do not reopen backend admin capacity repair.",
            ],
            "priority": 89,
        },
    ]


def final_backend_admin_rpm_capacity_split_task_specs() -> list[dict[str, object]]:
    return [
        {
            "title": "Repair final backend admin RPM route settings contracts",
            "description": (
                "Split the timed-out backend admin RPM capacity repair to admin route registration, settings handler, service, and config."
            ),
            "assigned_agent": "backend",
            "relevant_files": [
                "backend/internal/server/routes/admin.go",
                "backend/internal/handler/admin/setting_handler.go",
                "backend/internal/service/**",
                "backend/internal/config/**",
                "backend/go.mod",
                "backend/go.sum",
            ],
            "completion_criteria": [
                "Backend admin settings routes no longer expose forbidden RPM quota controls except as approved account-capacity semantics.",
                "Settings handler/service/config contracts are congruent with final CRM capacity settings.",
                "Focused backend settings route/handler checks pass or leave only user-capacity handler follow-ups.",
            ],
            "priority": 90,
        },
        {
            "title": "Repair final backend admin user capacity handler contracts",
            "description": (
                "Split the timed-out backend admin RPM capacity repair to admin user capacity handler and tests."
            ),
            "assigned_agent": "backend",
            "relevant_files": [
                "backend/internal/server/routes/admin.go",
                "backend/internal/handler/admin/user_handler.go",
                "backend/internal/handler/admin/user_platform_quota_admin_test.go",
                "backend/internal/service/user_service.go",
                "backend/go.mod",
                "backend/go.sum",
            ],
            "completion_criteria": [
                "Admin user capacity handler routes use final CRM account-capacity terminology and avoid forbidden platform-quota/RPM quota surfaces.",
                "Backend admin route registration and admin user handler tests are congruent.",
                "Focused admin user capacity handler checks pass without reopening settings route repair.",
            ],
            "priority": 89,
        },
    ]


def should_repair_final_backend_active_migration_model_routing(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "active embedded migrations still add model-routing",
            "backend/migrations/040_add_group_model_routing.sql",
            "backend/migrations/041_add_model_routing_enabled.sql",
            "active migration files",
            "fresh migration source contract",
        )
    ) and "model-routing" in text


def should_repair_final_frontend_forbidden_admin_surface(text: str) -> bool:
    explicit_surface = any(
        marker in text
        for marker in (
            "frontend/src/api/admin/groups.ts",
            "frontend/src/api/admin/announcements.ts",
            "frontend/src/api/announcements.ts",
            "announcement surface",
            "announcement store",
            "announcementbell",
            "admin groups api",
            "backend-forbidden routes",
            "repair final frontend forbidden admin route surface contracts",
            "frontend route repair",
        )
    )
    route_signal = bool(re.search(r"\b(route|reachable|registered|navigation)\b", text))
    explicit_route = route_signal and any(
        marker in text for marker in ("/admin/groups", "/announcements", "/admin/announcements")
    )
    return explicit_surface or explicit_route


def should_repair_final_frontend_route_sidebar_contract(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "route/sidebar contract",
            "crm-route-surface",
            "appsidebar.spec.ts",
            "unused bellicon",
            "bellicon is declared but its value is never read",
            "adminannouncements at /admin/announcements",
            "appsidebar expected /admin/announcements",
        )
    )


def should_repair_final_admin_settings_legacy_surface(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "admin settings api/ui",
            "registered admin settings api/ui",
            "openai_codex_user_agent",
            "openai_advanced_scheduler_enabled",
            "channel_monitor_enabled",
            "available_channels_enabled",
            "default_subscriptions",
            "default_platform_quotas",
            "legacy openai/gateway/channel/subscription settings",
            "backend admin settings dto",
            "repair final admin settings legacy surface contracts",
        )
    )


def should_split_final_admin_settings_legacy_timeout(text: str) -> bool:
    return should_repair_final_admin_settings_legacy_surface(text) and all(
        marker in text
        for marker in (
            "repair final admin settings legacy surface contracts",
            "timeout",
        )
    )


def final_admin_settings_legacy_timeout_split_task_specs() -> list[dict[str, object]]:
    return [
        {
            "title": "Repair final backend admin settings legacy contracts",
            "description": (
                "Narrow the timed-out admin settings legacy repair to backend handler/service/model/dto/config "
                "contracts that still expose OpenAI, gateway, channel, or subscription-era settings."
            ),
            "assigned_agent": "backend",
            "relevant_files": [
                "backend/internal/handler/admin/**/*settings*",
                "backend/internal/service/**/*settings*",
                "backend/internal/model/**/*settings*",
                "backend/internal/dto/**/*settings*",
                "backend/internal/config/**",
                "backend/go.mod",
                "backend/go.sum",
            ],
            "completion_criteria": [
                "Reachable backend admin settings contracts no longer expose OpenAI, gateway, channel, or subscription-era settings as CRM product behavior.",
                "Legacy-compatible backend settings are removed, renamed, or strictly fenced away from delivered admin contracts.",
                "Focused backend settings checks are attempted without taking over final full-suite verification.",
            ],
            "priority": 89,
        },
        {
            "title": "Repair final frontend admin settings legacy contracts",
            "description": (
                "Narrow the timed-out admin settings legacy repair to frontend admin settings API, view, i18n, "
                "and tests that still expose OpenAI, gateway, channel, or subscription-era settings."
            ),
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/api/admin/settings.ts",
                "frontend/src/views/admin/SettingsView.vue",
                "frontend/src/i18n/locales/en.ts",
                "frontend/src/i18n/locales/zh.ts",
                "frontend/src/api/__tests__/**/*settings*",
                "frontend/src/views/admin/**/*settings*",
                "frontend/src/views/admin/__tests__/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "Reachable frontend admin settings API/UI no longer exposes OpenAI, gateway, channel, or subscription-era settings as CRM product behavior.",
                "Legacy-compatible frontend settings are removed, renamed, or strictly fenced away from delivered admin UI contracts.",
                "Focused frontend settings tests, typecheck, and source-boundary probes are attempted before final gates rerun.",
            ],
            "priority": 88,
        },
    ]


def should_resume_final_admin_settings_boundary_expansion(text: str) -> bool:
    return all(
        marker in text
        for marker in (
            "must continue focused task",
            "repair final admin settings legacy surface contracts",
            "out-of-scope files changed: frontend/src/views/admin/__tests__/settingsview.spec.ts",
        )
    )


def should_resume_final_frontend_dependency_audit_timeout(text: str) -> bool:
    return all(
        marker in text
        for marker in (
            "focused timeout task titles:",
            "repair final frontend dependency audit contracts",
        )
    )


def should_resume_final_supervisor_stopped_repair_order(text: str) -> bool:
    return all(
        marker in text
        for marker in (
            "previous supervisor-stopped progress",
            "continue from the next incomplete repair task",
            "repair final frontend dependency audit contracts",
            "repair final backend migration contracts",
            "repair final backend service handler server contracts",
            "repair final frontend locale settings boundary contracts",
        )
    )


def repair_specs_matching_titles(
    specs: list[dict[str, object]],
    titles: set[str],
) -> list[dict[str, object]]:
    return [spec for spec in specs if str(spec.get("title", "")) in titles]


def repair_specs_matching_titles_in_order(
    specs: list[dict[str, object]],
    titles: list[str],
) -> list[dict[str, object]]:
    by_title = {str(spec.get("title", "")): spec for spec in specs}
    return [by_title[title] for title in titles if title in by_title]


def should_repair_final_backend_startup_contract(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "testgeneratedstartupenforcesfreshdatabasecontract",
            "enforcefreshdatabasecontract",
            "backend/cmd/server/wire.go",
            "backend/cmd/server/wire_gen.go",
            "fresh-database startup contract",
            "fresh database startup contract",
        )
    )


def should_repair_final_backend_account_repository_predicates(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "backend/internal/repository/account_repo.go",
            "hasaccountgroups",
            "hasaccountgroupswith",
            "removed ent predicates",
            "crm-renamed predicates",
        )
    )


def should_repair_final_backend_sub2api_protocol_identity(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "backend sub2api protocol",
            "backend/internal/veyra/intent.go",
            "portalintentsub2api",
            "sub2api-admin",
            "sec-websocket-protocol",
        )
    )


def should_repair_final_backend_production_identity_strings(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "backend production static identity probe",
            "backend production static probe found",
            "backend production legacy identity",
            "residual backend production legacy identity",
            "production files containing residual sub2api",
            "backend/internal/repository/dashboard_cache.go",
            "backend/internal/pkg/logger/options.go",
            "backend/internal/pkg/sysutil/restart.go",
            "backend/internal/handler/admin/ops_ws_handler.go",
            "backend/internal/service/update_service.go",
        )
    )


def should_repair_final_source_boundary_sweep(text: str) -> bool:
    has_final_source_boundary_failure = (
        "final_audit_status=fail" in text
        and "source-boundary" in text
        and (
            "production source still contains retired" in text
            or "production source and wiring still retain retired capabilities" in text
            or "source-boundary violations remain" in text
        )
    )
    has_backend_static_probe = (
        "backend production static probe found" in text
        and any(marker in text for marker in ("gateway/proxy", "upstream", "channel-monitor", "capability terms"))
    )
    has_migration_probe = "backend migrations still contain forbidden" in text or "fresh migration safety is incomplete" in text
    has_frontend_probe = "frontend source probe found" in text and (
        "retired api/composable" in text or "retired concepts" in text
    )
    has_empty_allowed_files_blocker = "allowed_files is empty" in text or "allowed files is empty" in text
    return (
        has_final_source_boundary_failure
        and has_backend_static_probe
        and has_migration_probe
        and has_frontend_probe
        and has_empty_allowed_files_blocker
    )


def should_split_final_frontend_retired_source_boundary_timeout(text: str) -> bool:
    has_timeout = any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
            "codex worker timed out after 900 seconds",
        )
    )
    has_frontend_retired_scope = "repair final frontend retired source-boundary leftovers" in text or (
        "frontend retired source-boundary" in text and "frontend/src/api" in text and "frontend/src/composables" in text
    )
    return has_timeout and has_frontend_retired_scope


def final_frontend_retired_source_boundary_split_task_specs() -> list[dict[str, object]]:
    return [
        {
            "title": "Repair final frontend retired API type source-boundary leftovers",
            "description": (
                "Split the timed-out frontend source-boundary repair to API modules, shared constants, types, "
                "and package metadata first."
            ),
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/api/**",
                "frontend/src/types/**",
                "frontend/src/constants/**",
                "frontend/src/utils/**",
                "frontend/src/api/__tests__/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "Frontend API modules, constants, and shared types no longer expose retired upstream-account, proxy, channel-monitor, model-routing, token-log, or subscription-plan product surfaces.",
                "Retired API compatibility facades are removed, renamed, or quarantined outside delivered frontend contracts.",
                "Focused API/type source-boundary probes and affected API tests are attempted before final gates rerun.",
            ],
            "priority": 89,
        },
        {
            "title": "Repair final frontend retired composable store source-boundary leftovers",
            "description": (
                "Split the timed-out frontend source-boundary repair to composables, stores, and state utilities."
            ),
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/composables/**",
                "frontend/src/stores/**",
                "frontend/src/utils/**",
                "frontend/src/composables/__tests__/**",
                "frontend/src/stores/__tests__/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "Frontend composables and stores no longer expose retired relay, upstream-account, provider-channel, proxy, model-routing, token-log, or subscription-plan product behavior.",
                "State helpers are CRM-neutral or CRM billing scoped rather than relay-era compatibility surfaces.",
                "Focused composable/store source-boundary probes and affected vitest specs are attempted before final gates rerun.",
            ],
            "priority": 88,
        },
        {
            "title": "Repair final frontend retired view component source-boundary leftovers",
            "description": (
                "Split the timed-out frontend source-boundary repair to reachable views, components, router, and locale copy."
            ),
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/router/**",
                "frontend/src/views/**",
                "frontend/src/components/**",
                "frontend/src/i18n/**",
                "frontend/src/styles/**",
                "frontend/src/router/__tests__/**",
                "frontend/src/views/**/__tests__/**",
                "frontend/src/components/**/__tests__/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "Reachable frontend routes, views, components, and locale copy no longer expose retired upstream-account, proxy, channel-monitor, model-routing, token-log, or subscription-plan product concepts.",
                "User-facing copy uses CRM identity, billing, wallet, metering, entitlement, audit, and admin semantics.",
                "Focused route/view/component source-boundary probes and affected vitest specs are attempted before final gates rerun.",
            ],
            "priority": 87,
        },
    ]


def should_repair_final_remaining_source_boundary_after_split(text: str) -> bool:
    if should_split_final_backend_provider_proxy_ops_service_quarantine_timeout(text):
        return True
    if should_split_final_backend_handler_server_quarantine_timeout(text):
        return True
    has_final_audit_failure = "final_audit_status" in text and "fail" in text
    has_semantic_probe_failure = (
        "static semantic probes found" in text
        and "production/delivery files" in text
        and "non-test frontend files" in text
    )
    has_backend_residuals = all(
        marker in text
        for marker in (
            "backend production code still contains",
            "gateway",
            "proxy",
            "channel monitor",
            "upstream account",
        )
    )
    has_frontend_typecheck_failure = "vue-tsc --noemit" in text or "vue-tsc --noemit exited 2" in text
    has_frontend_consumers = (
        "frontend typecheck fails" in text
        and any(
            marker in text
            for marker in (
                "subscriptionprogressmini.vue",
                "subscriptionplancard.vue",
                "userdashboardcharts.vue",
                "paymentwechatresume.ts",
            )
        )
    )
    has_edit_scope_blocker = "allowed_files is empty" in text or "allowed files is empty" in text
    return (
        has_final_audit_failure
        and has_semantic_probe_failure
        and has_backend_residuals
        and has_frontend_typecheck_failure
        and has_frontend_consumers
        and has_edit_scope_blocker
    )


def should_split_final_backend_legacy_quarantine_timeout(text: str) -> bool:
    has_timeout = any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "codex worker timed out after 900 seconds",
        )
    )
    has_backend_quarantine_scope = "repair final backend legacy production quarantine leftovers" in text or (
        "backend legacy production quarantine" in text
        and "backend/internal/handler" in text
        and "backend/internal/service" in text
    )
    return has_timeout and has_backend_quarantine_scope


def final_backend_legacy_quarantine_split_task_specs() -> list[dict[str, object]]:
    return [
        {
            "title": "Repair final backend handler server quarantine leftovers",
            "description": (
                "Split the timed-out backend legacy quarantine repair to handler and server route surfaces first."
            ),
            "assigned_agent": "backend",
            "relevant_files": [
                "backend/internal/handler/**",
                "backend/internal/server/**",
                "backend/internal/middleware/**",
                "backend/cmd/server/**",
                "backend/go.mod",
                "backend/go.sum",
            ],
            "completion_criteria": [
                "Backend handlers and server route/middleware code no longer expose retired gateway, OpenAI gateway, proxy, channel-monitor, upstream-account, or subscription-plan product surfaces.",
                "Retired handler entrypoints are removed, build-tag quarantined, or renamed under CRM billing/service-integration semantics without re-registering forbidden routes.",
                "Focused handler/server source-boundary probes and affected Go checks are attempted before final gates rerun.",
            ],
            "priority": 91,
        },
        {
            "title": "Repair final backend service repository quarantine leftovers",
            "description": (
                "Split the timed-out backend legacy quarantine repair to service, repository, and domain implementation surfaces."
            ),
            "assigned_agent": "backend",
            "relevant_files": [
                "backend/internal/service/**",
                "backend/internal/repository/**",
                "backend/internal/domain/**",
                "backend/go.mod",
                "backend/go.sum",
            ],
            "completion_criteria": [
                "Backend services and repositories no longer expose retired proxy, channel-monitor, upstream-account, model-routing, token-log, or subscription-plan product behavior.",
                "Reusable persistence/service infrastructure is either CRM-renamed or isolated from delivered production behavior.",
                "Focused service/repository source-boundary probes and package checks are attempted before final gates rerun.",
            ],
            "priority": 90,
        },
        {
            "title": "Repair final backend config runtime quarantine leftovers",
            "description": (
                "Split the timed-out backend legacy quarantine repair to config, runtime helper, package, and command wiring surfaces."
            ),
            "assigned_agent": "backend",
            "relevant_files": [
                "backend/internal/config/**",
                "backend/internal/pkg/**",
                "backend/internal/runtime/**",
                "backend/cmd/server/**",
                "backend/go.mod",
                "backend/go.sum",
            ],
            "completion_criteria": [
                "Backend config and runtime helper surfaces no longer expose retired gateway/proxy/upstream/channel-monitor/subscription settings as CRM product behavior.",
                "Command wiring uses CRM billing/runtime names and does not reintroduce retired provider-channel or relay-era entrypoints.",
                "Focused config/runtime source-boundary probes and affected Go checks are attempted before final gates rerun.",
            ],
            "priority": 89,
        },
    ]


def should_split_final_backend_handler_server_quarantine_timeout(text: str) -> bool:
    has_timeout = any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "codex worker timed out after 900 seconds",
        )
    )
    return has_timeout and "repair final backend handler server quarantine leftovers" in text


def final_backend_handler_server_quarantine_exact_task_specs() -> list[dict[str, object]]:
    return [
        {
            "title": "Repair final backend admin handler quarantine exact files",
            "description": (
                "Repair exact admin handler files that still expose retired account/proxy/upstream/provider/channel "
                "surfaces after the final backend handler/server quarantine timeout."
            ),
            "assigned_agent": "backend",
            "relevant_files": [
                "backend/internal/handler/admin/account_codex_import.go",
                "backend/internal/handler/admin/account_data.go",
                "backend/internal/handler/admin/account_handler.go",
                "backend/internal/handler/admin/antigravity_oauth_handler.go",
                "backend/internal/handler/admin/gemini_oauth_handler.go",
                "backend/internal/handler/admin/openai_oauth_handler.go",
                "backend/internal/handler/admin/ops_alerts_handler.go",
                "backend/internal/handler/admin/ops_handler.go",
                "backend/internal/handler/admin/ops_ws_handler.go",
                "backend/internal/handler/admin/proxy_data.go",
                "backend/internal/handler/admin/proxy_handler.go",
                "backend/internal/handler/admin/setting_handler.go",
                "backend/internal/handler/dto/mappers.go",
                "backend/internal/handler/dto/settings.go",
                "backend/internal/handler/dto/types.go",
                "backend/go.mod",
                "backend/go.sum",
            ],
            "completion_criteria": [
                "Admin handler and DTO source no longer exposes retired upstream account, proxy, provider-channel, OpenAI/Gemini/Antigravity, or subscription-plan product surfaces.",
                "Retired admin compatibility is removed, CRM-renamed, or quarantined away from delivered production behavior.",
                "Focused admin handler source-boundary probes and affected Go checks are attempted before final gates rerun.",
            ],
            "priority": 91,
        },
        {
            "title": "Repair final backend gateway protocol handler exact files",
            "description": (
                "Repair exact gateway/protocol handler files that still expose retired relay, OpenAI gateway, "
                "streaming, failover, or model/provider surfaces."
            ),
            "assigned_agent": "backend",
            "relevant_files": [
                "backend/internal/handler/content_moderation_helper.go",
                "backend/internal/handler/endpoint.go",
                "backend/internal/handler/failover_loop.go",
                "backend/internal/handler/gateway_handler.go",
                "backend/internal/handler/gateway_handler_chat_completions.go",
                "backend/internal/handler/gateway_handler_responses.go",
                "backend/internal/handler/gateway_helper.go",
                "backend/internal/handler/gemini_v1beta_handler.go",
                "backend/internal/handler/openai_chat_completions.go",
                "backend/internal/handler/openai_embeddings.go",
                "backend/internal/handler/openai_gateway_handler.go",
                "backend/internal/handler/openai_images.go",
                "backend/internal/handler/ops_error_logger.go",
                "backend/internal/handler/stream_error_event.go",
                "backend/internal/handler/user_msg_queue_helper.go",
                "backend/go.mod",
                "backend/go.sum",
            ],
            "completion_criteria": [
                "Gateway/protocol handler source no longer exposes retired API gateway, OpenAI gateway, proxy, model-routing, provider-channel, or token-relay product surfaces.",
                "Reusable protocol helpers are CRM service-integration or billing runtime infrastructure, or are quarantined outside delivered production behavior.",
                "Focused gateway/protocol handler source-boundary probes and affected Go checks are attempted before final gates rerun.",
            ],
            "priority": 90,
        },
        {
            "title": "Repair final backend server middleware quarantine exact files",
            "description": (
                "Repair exact server, middleware, and startup contract files that still expose retired route or runtime surfaces."
            ),
            "assigned_agent": "backend",
            "relevant_files": [
                "backend/cmd/server/database_contract_test.go",
                "backend/internal/server/api_contract_test.go",
                "backend/internal/server/http.go",
                "backend/internal/server/middleware/api_key_auth_test.go",
                "backend/internal/server/middleware/middleware.go",
                "backend/go.mod",
                "backend/go.sum",
            ],
            "completion_criteria": [
                "Server and middleware source no longer exposes retired gateway, proxy, upstream-account, provider-channel, or subscription-plan route/runtime surfaces.",
                "Startup and route contract tests assert CRM Billing Core behavior without retaining relay-era product contracts.",
                "Focused server/middleware source-boundary probes and Go checks are attempted before final gates rerun.",
            ],
            "priority": 89,
        },
    ]


def should_split_final_backend_service_repository_quarantine_timeout(text: str) -> bool:
    has_timeout = any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "codex worker timed out after 900 seconds",
        )
    )
    return has_timeout and "repair final backend service repository quarantine leftovers" in text


def final_backend_service_repository_quarantine_exact_task_specs() -> list[dict[str, object]]:
    return [
        {
            "title": "Repair final backend repository domain quarantine exact files",
            "description": "Repair exact repository/domain files retaining retired relay-era source-boundary terms.",
            "assigned_agent": "backend",
            "relevant_files": [
                "backend/internal/domain/table_contract.go",
                "backend/internal/domain/table_contract_test.go",
                "backend/internal/repository/account_repo.go",
                "backend/internal/repository/claude_oauth_service.go",
                "backend/internal/repository/claude_usage_service.go",
                "backend/internal/repository/gateway_cache.go",
                "backend/internal/repository/gemini_oauth_client.go",
                "backend/internal/repository/geminicli_codeassist_client.go",
                "backend/internal/repository/github_release_service.go",
                "backend/internal/repository/http_upstream.go",
                "backend/internal/repository/openai_oauth_service.go",
                "backend/internal/repository/pricing_service.go",
                "backend/internal/repository/proxy_latency_cache.go",
                "backend/internal/repository/proxy_probe_service.go",
                "backend/internal/repository/proxy_repo.go",
                "backend/internal/repository/req_client_pool.go",
                "backend/internal/repository/wire.go",
                "backend/go.mod",
                "backend/go.sum",
            ],
            "completion_criteria": [
                "Repository/domain source no longer exposes retired upstream-account, gateway, proxy, provider-channel, or subscription-plan product surfaces.",
                "Repository compatibility helpers are CRM-renamed or quarantined away from delivered production behavior.",
                "Focused repository/domain source-boundary probes and package checks are attempted before final gates rerun.",
            ],
            "priority": 90,
        },
        {
            "title": "Repair final backend gateway OpenAI service quarantine exact files",
            "description": "Repair exact gateway/OpenAI/Gemini compatibility service files retaining retired product terms.",
            "assigned_agent": "backend",
            "relevant_files": [
                "backend/internal/service/gateway_forward_as_chat_completions.go",
                "backend/internal/service/gateway_forward_as_responses.go",
                "backend/internal/service/gateway_messages_cache.go",
                "backend/internal/service/gateway_record_usage_test.go",
                "backend/internal/service/gateway_request.go",
                "backend/internal/service/gateway_service.go",
                "backend/internal/service/gateway_websearch_emulation.go",
                "backend/internal/service/gemini_chat_completions_compat_service.go",
                "backend/internal/service/gemini_messages_compat_service.go",
                "backend/internal/service/openai_gateway_chat_completions.go",
                "backend/internal/service/openai_gateway_chat_completions_raw.go",
                "backend/internal/service/openai_gateway_messages.go",
                "backend/internal/service/openai_gateway_responses_chat_fallback.go",
                "backend/internal/service/openai_gateway_service.go",
                "backend/internal/service/openai_images.go",
                "backend/internal/service/openai_images_responses.go",
                "backend/internal/service/openai_embeddings.go",
                "backend/go.mod",
                "backend/go.sum",
            ],
            "completion_criteria": [
                "Gateway/OpenAI/Gemini service source no longer exposes retired API gateway, OpenAI gateway, model-routing, provider-channel, or token-relay product surfaces.",
                "Reusable compatibility services are CRM service-integration or billing runtime infrastructure, or are quarantined from delivered product behavior.",
                "Focused gateway/OpenAI service source-boundary probes and affected package checks are attempted before final gates rerun.",
            ],
            "priority": 89,
        },
        {
            "title": "Repair final backend provider proxy ops service quarantine exact files",
            "description": "Repair exact provider/proxy/channel-monitor/ops service files retaining retired product terms.",
            "assigned_agent": "backend",
            "relevant_files": [
                "backend/internal/service/account.go",
                "backend/internal/service/account_service.go",
                "backend/internal/service/account_usage_service.go",
                "backend/internal/service/admin_service.go",
                "backend/internal/service/antigravity_gateway_service.go",
                "backend/internal/service/antigravity_oauth_service.go",
                "backend/internal/service/antigravity_token_provider.go",
                "backend/internal/service/api_key_auth_cache.go",
                "backend/internal/service/billing_cache_service.go",
                "backend/internal/service/channel_monitor_aggregator.go",
                "backend/internal/service/channel_monitor_const.go",
                "backend/internal/service/channel_monitor_runner.go",
                "backend/internal/service/channel_monitor_service.go",
                "backend/internal/service/channel_monitor_ssrf.go",
                "backend/internal/service/channel_monitor_validate.go",
                "backend/internal/service/channel_service.go",
                "backend/internal/service/domain_constants.go",
                "backend/internal/service/gemini_oauth.go",
                "backend/internal/service/gemini_oauth_service.go",
                "backend/internal/service/gemini_token_provider.go",
                "backend/internal/service/oauth_service.go",
                "backend/internal/service/openai_account_scheduler.go",
                "backend/internal/service/openai_oauth_service.go",
                "backend/internal/service/ops_models.go",
                "backend/internal/service/ops_service.go",
                "backend/internal/service/ops_upstream_context.go",
                "backend/internal/service/proxy.go",
                "backend/internal/service/proxy_expiry_service.go",
                "backend/internal/service/proxy_fallback.go",
                "backend/internal/service/proxy_latency_cache.go",
                "backend/internal/service/proxy_service.go",
                "backend/internal/service/quota_fetcher.go",
                "backend/internal/service/setting_service.go",
                "backend/internal/service/token_refresh_service.go",
                "backend/internal/service/upstream_models.go",
                "backend/internal/service/upstream_response_limit.go",
                "backend/internal/service/usage_record_worker_pool.go",
                "backend/internal/service/wire.go",
                "backend/go.mod",
                "backend/go.sum",
            ],
            "completion_criteria": [
                "Provider/proxy/channel-monitor/ops service source no longer exposes retired upstream-account, proxy, provider-channel, channel-monitor, token-refresh, or subscription-plan product surfaces.",
                "Remaining reusable services are CRM billing, service-health, connector, wallet, metering, or observability scoped.",
                "Focused provider/proxy/ops service source-boundary probes and package checks are attempted before final gates rerun.",
            ],
            "priority": 88,
        },
    ]


def should_split_final_backend_provider_proxy_ops_service_quarantine_timeout(text: str) -> bool:
    has_timeout = any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "codex worker timed out after 900 seconds",
        )
    )
    return has_timeout and "repair final backend provider proxy ops service quarantine exact files" in text


def final_backend_provider_proxy_ops_service_quarantine_split_task_specs() -> list[dict[str, object]]:
    return [
        {
            "title": "Repair final backend account OAuth service quarantine exact files",
            "description": "Repair exact account/OAuth/connector service files retaining retired product terms.",
            "assigned_agent": "backend",
            "relevant_files": [
                "backend/internal/service/account.go",
                "backend/internal/service/account_service.go",
                "backend/internal/service/account_usage_service.go",
                "backend/internal/service/admin_service.go",
                "backend/internal/service/antigravity_gateway_service.go",
                "backend/internal/service/antigravity_oauth_service.go",
                "backend/internal/service/antigravity_token_provider.go",
                "backend/internal/service/gemini_oauth.go",
                "backend/internal/service/gemini_oauth_service.go",
                "backend/internal/service/gemini_token_provider.go",
                "backend/internal/service/oauth_service.go",
                "backend/internal/service/openai_account_scheduler.go",
                "backend/internal/service/openai_oauth_service.go",
                "backend/internal/service/token_refresh_service.go",
                "backend/go.mod",
                "backend/go.sum",
            ],
            "completion_criteria": [
                "Account/OAuth connector service source no longer exposes retired upstream-account, provider-channel, token-refresh, or token-relay product surfaces.",
                "Reusable connector/auth helpers are CRM account identity or service-integration scoped.",
                "Focused account/OAuth service source-boundary probes and package checks are attempted before final gates rerun.",
            ],
            "priority": 88,
        },
        {
            "title": "Repair final backend channel monitor service quarantine exact files",
            "description": "Repair exact service-health/channel-monitor service files retaining retired product terms.",
            "assigned_agent": "backend",
            "relevant_files": [
                "backend/internal/service/channel_monitor_aggregator.go",
                "backend/internal/service/channel_monitor_const.go",
                "backend/internal/service/channel_monitor_runner.go",
                "backend/internal/service/channel_monitor_service.go",
                "backend/internal/service/channel_monitor_ssrf.go",
                "backend/internal/service/channel_monitor_validate.go",
                "backend/internal/service/channel_service.go",
                "backend/internal/service/quota_fetcher.go",
                "backend/internal/service/usage_record_worker_pool.go",
                "backend/go.mod",
                "backend/go.sum",
            ],
            "completion_criteria": [
                "Service-health/channel-monitor source no longer exposes retired channel-monitor, provider-channel, upstream-account, or subscription-plan product surfaces.",
                "Remaining monitoring behavior is CRM service-health, metering, or observability scoped.",
                "Focused service-health source-boundary probes and package checks are attempted before final gates rerun.",
            ],
            "priority": 87,
        },
        {
            "title": "Repair final backend proxy upstream service quarantine exact files",
            "description": "Repair exact proxy/upstream service files retaining retired product terms.",
            "assigned_agent": "backend",
            "relevant_files": [
                "backend/internal/service/proxy.go",
                "backend/internal/service/proxy_expiry_service.go",
                "backend/internal/service/proxy_fallback.go",
                "backend/internal/service/proxy_latency_cache.go",
                "backend/internal/service/proxy_service.go",
                "backend/internal/service/upstream_models.go",
                "backend/internal/service/upstream_response_limit.go",
                "backend/go.mod",
                "backend/go.sum",
            ],
            "completion_criteria": [
                "Proxy/upstream source no longer exposes retired proxy, upstream-account, model-routing, or provider-channel product surfaces.",
                "Remaining connector/network behavior is CRM integration infrastructure rather than delivered relay product behavior.",
                "Focused proxy/upstream source-boundary probes and package checks are attempted before final gates rerun.",
            ],
            "priority": 86,
        },
        {
            "title": "Repair final backend ops settings service quarantine exact files",
            "description": "Repair exact ops/settings/wire service files retaining retired product terms.",
            "assigned_agent": "backend",
            "relevant_files": [
                "backend/internal/service/api_key_auth_cache.go",
                "backend/internal/service/billing_cache_service.go",
                "backend/internal/service/domain_constants.go",
                "backend/internal/service/ops_models.go",
                "backend/internal/service/ops_service.go",
                "backend/internal/service/ops_upstream_context.go",
                "backend/internal/service/setting_service.go",
                "backend/internal/service/wire.go",
                "backend/go.mod",
                "backend/go.sum",
            ],
            "completion_criteria": [
                "Ops/settings service source no longer exposes retired upstream-account, proxy, provider-channel, token-refresh, or subscription-plan product surfaces.",
                "Remaining settings and observability behavior is CRM billing/runtime scoped.",
                "Focused ops/settings source-boundary probes and package checks are attempted before final gates rerun.",
            ],
            "priority": 85,
        },
    ]


def should_split_final_frontend_api_i18n_timeout(text: str) -> bool:
    if not any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    ):
        return False
    if "repair final frontend api and i18n contracts" in text:
        return True
    focused_api_i18n_scope = all(
        marker in text
        for marker in (
            "primary failed task ids: t006",
            "frontend api",
            "i18n",
            "constants",
            "type",
        )
    )
    return focused_api_i18n_scope


def should_narrow_final_frontend_api_module_leaf_timeout(text: str) -> bool | str:
    if "primary failed task ids: t006" not in text:
        return False
    if "focused timeout task ids: t006" not in text:
        return False
    if "repair final frontend admin billing api contract leaf" in text:
        return "payment_usage"
    return "repair final frontend api module contracts" in text


def should_narrow_final_frontend_i18n_locale_timeout(text: str) -> bool:
    if "primary failed task ids: t007" not in text:
        return False
    if "repair final frontend i18n locale contracts" not in text:
        return False
    return any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    )


def should_narrow_final_backend_service_handler_timeout(text: str) -> bool:
    if "primary failed task ids: t005" not in text:
        return False
    service_scope = "repair final backend service handler server contracts" in text or (
        "backend/internal/service" in text
        and ("backend/internal/handler" in text or "backend/internal/server" in text)
    ) or (
        "service/handler/server contracts" in text
        or "domain/repository/service/handler/server contracts" in text
    )
    if not service_scope:
        return False
    return any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    )


def should_narrow_final_backend_domain_repository_timeout(text: str) -> bool:
    if "primary failed task ids: t004" not in text:
        return False
    if "focused timeout task ids: t004" in text:
        return True
    return any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    )


def should_narrow_final_backend_domain_repository_leaf_timeout(text: str) -> bool:
    if not should_narrow_final_backend_domain_repository_timeout(text):
        return False
    return "repair final backend domain repository contract leftovers" in text


def should_preserve_final_frontend_api_i18n_split(text: str) -> bool:
    return all(
        marker in text
        for marker in (
            "repair final frontend api module contracts",
            "repair final frontend i18n locale contracts",
            "repair final frontend constants and shared types contracts",
        )
    )


def should_preserve_final_frontend_deep_tail_split(text: str) -> bool:
    if "preserve final frontend split tail graph shape:" in text:
        return True
    if _primary_failed_task_has_title(text, "repair final frontend test and fixture contracts"):
        return True
    if "completed tasks to preserve:" not in text or not _has_primary_failed_task_id_in_range(text, 50, 90):
        return False
    if completed_preserve_line_contains_all(text, "t056", "t057", "t058", "t059"):
        return True
    return any(
        marker in text
        for marker in (
            "repair final frontend table navigation composables",
            "repair final frontend channel monitor format composable",
            "repair final frontend onboarding quota composables",
        )
    )


def should_split_final_frontend_test_fixture_timeout(text: str) -> bool:
    if not any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    ):
        return False
    return _has_primary_failed_task_id_in_range(text, 56, 90) and any(
        marker in text
        for marker in (
            "repair final frontend test and fixture contracts",
            "frontend/src/**/__tests__/**",
            "frontend/src/**/*.spec.ts",
            "frontend/tests/**",
        )
    )


def should_split_final_frontend_component_composable_test_timeout(text: str) -> bool:
    if not any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
            "timeout split required",
        )
    ):
        return False
    return (
        "repair final frontend component and composable test contracts" in text
        and "frontend/src/components" in text
        and "frontend/src/composables" in text
    )


def should_preserve_final_frontend_test_fixture_split(text: str) -> bool:
    split_titles_present = all(
        marker in text
        for marker in (
            "repair final frontend api and integration test contracts",
            "repair final frontend component and composable test contracts",
            "repair final frontend view router i18n utility test contracts",
            "repair final frontend test config and fixture contracts",
        )
    )
    if split_titles_present:
        return True
    if completed_preserve_line_contains_all(text, "t056", "t057", "t058", "t059"):
        return _has_primary_failed_task_id_in_range(text, 56, 90)
    return all(
        marker in text
        for marker in (
            "completed tasks to preserve:",
            "repair final frontend test and fixture contracts",
        )
    ) and _has_primary_failed_task_id_in_range(text, 56, 90)


def completed_preserve_line_contains_all(text: str, *task_ids: str) -> bool:
    for line in text.splitlines():
        if "completed tasks to preserve:" not in line:
            continue
        if all(task_id.lower() in line for task_id in task_ids):
            return True
    return False


def final_frontend_api_i18n_repair_task_specs(
    *, split: bool, split_api_module_leaf: bool | str = False, split_i18n_locale_leaf: bool = False
) -> list[dict[str, object]]:
    if not split:
        return [
            {
                "title": "Repair final frontend API and i18n contracts",
                "description": (
                    "Remove or reframe frontend API modules, constants, types, and i18n copy that still expose upstream account, "
                    "proxy, channel, channel-monitor, model-routing, or subscription-plan product behavior."
                ),
                "assigned_agent": "frontend",
                "relevant_files": [
                    "frontend/src/api/**",
                    "frontend/src/i18n/**",
                    "frontend/src/constants/**",
                    "frontend/src/types/**",
                ],
                "completion_criteria": [
                    "Frontend API contracts and user-facing copy describe CRM billing, identity, wallet, metering, charging, payment, analytics, audit, and admin behavior only.",
                    "Residual relay-era terms are removed or clearly reframed as internal-compatible infrastructure where still necessary.",
                ],
                "priority": 94,
            }
        ]
    return [
        final_frontend_api_module_repair_spec(split_leaf=split_api_module_leaf),
        final_frontend_i18n_locale_repair_spec(split_leaf=split_i18n_locale_leaf),
        {
            "title": "Repair final frontend constants and shared types contracts",
            "description": (
                "Align frontend constants and shared types with the final CRM Billing Core product boundary after API and locale cleanup."
            ),
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/constants/**",
                "frontend/src/types/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "Shared frontend constants and types no longer expose upstream account, proxy, channel, channel-monitor, model-routing, or subscription-plan product behavior.",
                "The remaining shared contract names are compatible with CRM billing, identity, wallet, metering, charging, payment, analytics, audit, and admin workflows.",
            ],
            "priority": 92,
        },
    ]


def final_frontend_i18n_locale_repair_spec(*, split_leaf: bool) -> dict[str, object]:
    if split_leaf:
        return {
            "title": "Repair final frontend i18n locale contracts",
            "description": (
                "The final frontend i18n locale repair timed out. Keep task ID T007 stable and narrow the retry "
                "to locale dictionaries, the i18n entrypoint, and focused i18n specs."
            ),
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/i18n/index.ts",
                "frontend/src/i18n/locales/en.ts",
                "frontend/src/i18n/locales/zh.ts",
                "frontend/src/i18n/__tests__/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "Frontend locale copy uses CRM identity, wallet, metering, charging, reconciliation, analytics, audit, and admin language.",
                "Residual relay-era wording is removed or clearly reframed as internal compatibility language.",
            ],
            "priority": 93,
        }
    return {
        "title": "Repair final frontend i18n locale contracts",
        "description": (
            "Replace frontend locale copy that still presents upstream account, proxy, channel, channel-monitor, "
            "model-routing, or subscription-plan behavior as delivered CRM product behavior."
        ),
        "assigned_agent": "frontend",
        "relevant_files": [
            "frontend/src/i18n/**",
            "frontend/package.json",
            "frontend/pnpm-lock.yaml",
        ],
        "completion_criteria": [
            "Frontend locale copy uses CRM identity, wallet, metering, charging, reconciliation, analytics, audit, and admin language.",
            "Residual relay-era wording is removed or clearly reframed as internal compatibility language.",
        ],
        "priority": 93,
    }


def final_frontend_api_module_repair_spec(*, split_leaf: bool | str) -> dict[str, object]:
    if split_leaf == "payment_usage":
        return {
            "title": "Repair final frontend payment usage API contract leaf",
            "description": (
                "The admin billing API leaf timed out again. Keep task ID T006 stable and narrow the retry "
                "to payment and usage API contracts plus their focused tests."
            ),
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/api/admin/payment.ts",
                "frontend/src/api/admin/usage.ts",
                "frontend/src/api/payment.ts",
                "frontend/src/api/usage.ts",
                "frontend/src/api/__tests__/admin.payment.spec.ts",
                "frontend/src/api/__tests__/admin.usage.spec.ts",
                "frontend/src/api/__tests__/payment.spec.ts",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "Payment and usage API contracts use CRM billing, wallet, metering, charging, and reconciliation terminology.",
                "Residual upstream, proxy, channel, model-routing, or subscription-plan API surfaces are removed from these files or isolated from delivered behavior.",
                "Only focused payment/usage API checks are attempted; broad frontend verification remains for final gates.",
            ],
            "priority": 94,
        }
    if split_leaf:
        return {
            "title": "Repair final frontend admin billing API contract leaf",
            "description": (
                "The frontend API module repair timed out. Keep task ID T006 stable and narrow the retry "
                "to admin billing, usage, settings, redeem, and retired-surface API contracts."
            ),
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/api/admin/payment.ts",
                "frontend/src/api/admin/usage.ts",
                "frontend/src/api/admin/redeem.ts",
                "frontend/src/api/admin/settings.ts",
                "frontend/src/api/payment.ts",
                "frontend/src/api/usage.ts",
                "frontend/src/api/redeem.ts",
                "frontend/src/api/retired.ts",
                "frontend/src/api/__tests__/admin.payment.spec.ts",
                "frontend/src/api/__tests__/admin.usage.spec.ts",
                "frontend/src/api/__tests__/redeem.wallet-ledger.spec.ts",
                "frontend/src/api/__tests__/retired-surfaces.spec.ts",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "Admin billing, usage, redeem, settings, and retired-surface API contracts use CRM billing terminology.",
                "Residual upstream, proxy, channel, model-routing, or subscription-plan API surfaces are removed or isolated from delivered frontend behavior.",
                "Only narrow API module checks are attempted; broad frontend verification remains for final gates.",
            ],
            "priority": 94,
        }
    return {
        "title": "Repair final frontend API module contracts",
        "description": (
            "Remove or reframe frontend API modules and service contract types that still expose upstream account, "
            "proxy, channel, channel-monitor, model-routing, or subscription-plan product behavior."
        ),
        "assigned_agent": "frontend",
        "relevant_files": [
            "frontend/src/api/**",
            "frontend/src/types/**",
            "frontend/package.json",
            "frontend/pnpm-lock.yaml",
        ],
        "completion_criteria": [
            "Frontend API modules describe CRM billing, identity, wallet, metering, charging, payment, analytics, audit, and admin behavior only.",
            "Retired relay-era API exports are removed or clearly quarantined as internal compatibility infrastructure.",
        ],
        "priority": 94,
    }


def should_split_final_frontend_routes_views_timeout(text: str) -> bool:
    if not any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    ):
        return False
    if "repair final frontend routes views and tests" in text:
        return True
    return all(
        marker in text
        for marker in (
            "primary failed task ids: t009",
            "router",
            "view",
            "component",
            "store",
            "test",
        )
    )


def should_narrow_final_frontend_route_app_shell_timeout(text: str) -> bool:
    if not any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    ):
        return False
    if "primary failed task ids: t009" not in text:
        return False
    return any(
        marker in text
        for marker in (
            "repair final frontend route and app shell contracts",
            "route/app-shell repair timed out",
            "route and app shell",
            "route/app-shell workflow",
        )
    )


def should_split_final_frontend_view_component_timeout(text: str) -> bool:
    if not any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    ):
        return False
    if "repair final frontend view and component contracts" in text:
        return True
    return all(
        marker in text
        for marker in (
            "primary failed task ids: t010",
            "frontend",
            "view",
            "component",
        )
    )


def should_preserve_final_frontend_view_component_split(text: str) -> bool:
    split_titles_present = all(
        marker in text
        for marker in (
            "repair final frontend account component contracts",
            "repair final frontend admin operation component contracts",
            "repair final frontend analytics and shared component contracts",
            "repair final frontend view page contracts",
        )
    )
    if split_titles_present:
        return True
    return all(
        marker in text
        for marker in (
            "completed tasks to preserve:",
            "t009",
            "t010",
        )
    ) and _has_primary_failed_task_id_in_range(text, 11, 55)


def should_split_final_frontend_view_page_timeout(text: str) -> bool:
    focused_view_page_scope = _has_primary_failed_task_id_in_range(text, 29, 31) and any(
        marker in text
        for marker in (
            "repair final frontend view page contracts",
            "repair final frontend admin view page contracts",
            "repair final frontend user payment view page contracts",
            "repair final frontend auth public setup view contracts",
            "frontend/src/views",
            "views/admin",
            "views/user",
            "views/auth",
        )
    )
    if focused_view_page_scope:
        return True
    if not any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    ):
        return False
    return all(
        marker in text
        for marker in (
            "primary failed task ids: t029",
            "frontend",
            "view",
            "page",
        )
    )


def should_preserve_final_frontend_view_page_split(text: str) -> bool:
    split_titles_present = all(
        marker in text
        for marker in (
            "repair final frontend admin view page contracts",
            "repair final frontend user payment view page contracts",
            "repair final frontend auth public setup view contracts",
        )
    )
    if split_titles_present:
        return True
    return all(
        marker in text
        for marker in (
            "completed tasks to preserve:",
            "t029",
            "t030",
            "t031",
        )
    ) and _has_primary_failed_task_id_in_range(text, 32, 55)


def should_split_final_frontend_admin_view_page_timeout(text: str) -> bool:
    focused_admin_view_scope = _has_primary_failed_task_id_in_range(text, 29, 32) and any(
        marker in text
        for marker in (
            "repair final frontend admin view page contracts",
            "frontend/src/views/admin",
            "views/admin",
            "admin view page",
        )
    )
    if focused_admin_view_scope:
        return True
    if not any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    ):
        return False
    return "primary failed task ids: t029" in text and any(
        marker in text
        for marker in (
            "repair final frontend admin view page contracts",
            "frontend/src/views/admin",
            "views/admin",
            "admin view page",
        )
    )


def should_preserve_final_frontend_admin_view_page_split(text: str) -> bool:
    split_titles_present = all(
        marker in text
        for marker in (
            "repair final frontend admin dashboard settings view contracts",
            "repair final frontend admin user usage redeem view contracts",
            "repair final frontend admin payment order plan view contracts",
            "repair final frontend admin operations view contracts",
            "repair final frontend legacy admin view cleanup",
        )
    )
    if split_titles_present:
        return True
    return all(
        marker in text
        for marker in (
            "completed tasks to preserve:",
            "t029",
            "t030",
            "t031",
            "t032",
            "t033",
        )
    ) and _has_primary_failed_task_id_in_range(text, 34, 55)


def should_split_final_frontend_auth_public_setup_timeout(text: str) -> bool:
    focused_auth_public_scope = _has_primary_failed_task_id_in_range(text, 31, 55) and any(
        marker in text
        for marker in (
            "repair final frontend auth public setup view contracts",
            "frontend/src/views/auth",
            "frontend/src/views/public",
            "frontend/src/views/setup",
            "frontend/src/views/notfoundview.vue",
            "auth public setup",
        )
    )
    if focused_auth_public_scope:
        return True
    if not any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    ):
        return False
    return "repair final frontend auth public setup view contracts" in text and any(
        marker in text
        for marker in (
            "frontend/src/views/auth",
            "frontend/src/views/public",
            "frontend/src/views/setup",
            "notfoundview",
        )
    )


def should_preserve_final_frontend_auth_public_setup_split(text: str) -> bool:
    split_titles_present = all(
        marker in text
        for marker in (
            "repair final frontend auth view contracts",
            "repair final frontend public legal view contracts",
            "repair final frontend setup and not-found view contracts",
            "repair final frontend auth public setup support files",
        )
    )
    if split_titles_present:
        return True
    return all(
        marker in text
        for marker in (
            "completed tasks to preserve:",
            "repair final frontend state composable utility contracts",
        )
    ) and _has_primary_failed_task_id_in_range(text, 45, 60)


def should_split_final_frontend_setup_not_found_timeout(text: str) -> bool:
    focused_setup_scope = (
        _has_primary_failed_task_id_in_range(text, 31, 60)
        and "repair final frontend setup and not-found view contracts" in text
        and any(
        marker in text
        for marker in (
            "frontend/src/views/setup",
            "frontend/src/views/notfoundview.vue",
            "not-found view",
        )
        )
    )
    if focused_setup_scope:
        return True
    if not any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    ):
        return False
    return "repair final frontend setup and not-found view contracts" in text and any(
        marker in text
        for marker in (
            "frontend/src/views/setup",
            "notfoundview",
            "not-found",
        )
    )


def should_preserve_final_frontend_setup_not_found_split(text: str) -> bool:
    split_titles_present = all(
        marker in text
        for marker in (
            "repair final frontend setup view contracts",
            "repair final frontend not-found view file",
        )
    )
    if split_titles_present:
        return True
    return all(
        marker in text
        for marker in (
            "completed tasks to preserve:",
            "t046",
            "t047",
        )
    ) and _has_primary_failed_task_id_in_range(text, 48, 65)


def should_split_final_frontend_state_composable_utility_timeout(text: str) -> bool:
    if not any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    ):
        return False
    return _primary_failed_task_has_title(
        text,
        "repair final frontend state composable utility contracts",
    )


def should_preserve_final_frontend_state_composable_utility_split(text: str) -> bool:
    split_titles_present = all(
        marker in text
        for marker in (
            "repair final frontend store contracts",
            "repair final frontend composable contracts",
            "repair final frontend utility constant type contracts",
        )
    )
    if split_titles_present:
        return True
    return all(
        marker in text
        for marker in (
            "completed tasks to preserve:",
            "t049",
            "t050",
            "t051",
        )
    ) and _has_primary_failed_task_id_in_range(text, 52, 65)


def should_split_final_frontend_composable_contracts_timeout(text: str) -> bool:
    if not any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    ):
        return False
    return _primary_failed_task_has_title(
        text,
        "repair final frontend composable contracts",
    )


def should_preserve_final_frontend_composable_contracts_split(text: str) -> bool:
    split_titles_present = all(
        marker in text
        for marker in (
            "repair final frontend identity oauth composables",
            "repair final frontend metering entitlement composables",
            "repair final frontend table navigation composables",
        )
    )
    if split_titles_present:
        return True
    return all(
        marker in text
        for marker in (
            "completed tasks to preserve:",
            "t050",
            "t051",
            "t052",
        )
    ) and _has_primary_failed_task_id_in_range(text, 53, 70)


def should_split_final_frontend_metering_entitlement_composables_timeout(text: str) -> bool:
    if not any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    ):
        return False
    return _primary_failed_task_has_title(
        text,
        "repair final frontend metering entitlement composables",
    )


def should_preserve_final_frontend_metering_entitlement_composables_split(text: str) -> bool:
    split_titles_present = all(
        marker in text
        for marker in (
            "repair final frontend channel monitor format composable",
            "repair final frontend model entitlement composable",
            "repair final frontend onboarding quota composables",
        )
    )
    if split_titles_present:
        return True
    return all(
        marker in text
        for marker in (
            "completed tasks to preserve:",
            "t051",
            "t052",
            "t053",
        )
    ) and _has_primary_failed_task_id_in_range(text, 54, 75)


def should_split_final_frontend_admin_dashboard_settings_timeout(text: str) -> bool:
    focused_dashboard_settings_scope = _has_primary_failed_task_id_in_range(text, 29, 33) and any(
        marker in text
        for marker in (
            "repair final frontend admin dashboard settings view contracts",
            "frontend/src/views/admin/dashboardview.vue",
            "frontend/src/views/admin/settingsview.vue",
            "frontend/src/views/admin/announcementsview.vue",
            "frontend/src/views/admin/backupview.vue",
            "frontend/src/views/admin/promocodesview.vue",
            "dashboard settings view",
        )
    )
    if focused_dashboard_settings_scope:
        return True
    if not any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    ):
        return False
    return "primary failed task ids: t029" in text and any(
        marker in text
        for marker in (
            "repair final frontend admin dashboard settings view contracts",
            "frontend/src/views/admin/dashboardview.vue",
            "frontend/src/views/admin/settingsview.vue",
            "dashboard settings view",
        )
    )


def should_preserve_final_frontend_admin_dashboard_settings_split(text: str) -> bool:
    split_titles_present = all(
        marker in text
        for marker in (
            "repair final frontend admin dashboard view file",
            "repair final frontend admin settings email compliance files",
            "repair final frontend admin announcement backup promo files",
            "repair final frontend admin dashboard settings support files",
        )
    )
    if split_titles_present:
        return True
    return all(
        marker in text
        for marker in (
            "completed tasks to preserve:",
            "t029",
            "t030",
            "t031",
            "t032",
        )
    ) and _has_primary_failed_task_id_in_range(text, 33, 48)


def should_split_final_frontend_admin_settings_email_compliance_timeout(text: str) -> bool:
    focused_settings_scope = _has_primary_failed_task_id_in_range(text, 30, 34) and any(
        marker in text
        for marker in (
            "repair final frontend admin settings email compliance files",
            "frontend/src/views/admin/settingsview.vue",
            "frontend/src/views/admin/settings/emailtemplateeditor.vue",
            "frontend/src/components/admin/admincompliancedialog.vue",
            "settings email compliance",
        )
    )
    if focused_settings_scope:
        return True
    if not any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    ):
        return False
    return "primary failed task ids: t030" in text and any(
        marker in text
        for marker in (
            "repair final frontend admin settings email compliance files",
            "frontend/src/views/admin/settingsview.vue",
            "settings email compliance",
        )
    )


def should_preserve_final_frontend_admin_settings_email_compliance_split(text: str) -> bool:
    split_titles_present = all(
        marker in text
        for marker in (
            "repair final frontend admin settings view file",
            "repair final frontend admin email template editor file",
            "repair final frontend admin compliance dialog file",
            "repair final frontend admin settings support files",
        )
    )
    if split_titles_present:
        return True
    return all(
        marker in text
        for marker in (
            "completed tasks to preserve:",
            "t029",
            "t030",
            "t031",
            "t032",
            "t033",
        )
    ) and _has_primary_failed_task_id_in_range(text, 34, 50)


def should_narrow_final_frontend_admin_email_template_timeout(text: str) -> bool:
    focused_email_template_scope = _has_primary_failed_task_id_in_range(text, 31, 35) and any(
        marker in text
        for marker in (
            "repair final frontend admin email template editor file",
            "frontend/src/views/admin/settings/emailtemplateeditor.vue",
            "emailtemplateeditor.vue",
        )
    )
    if focused_email_template_scope:
        return True
    if not any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    ):
        return False
    return "primary failed task ids: t031" in text and any(
        marker in text
        for marker in (
            "repair final frontend admin email template editor file",
            "frontend/src/views/admin/settings/emailtemplateeditor.vue",
            "emailtemplateeditor.vue",
        )
    )


def should_preserve_final_frontend_admin_email_template_leaf(text: str) -> bool:
    split_titles_present = all(
        marker in text
        for marker in (
            "repair final frontend admin settings view file",
            "repair final frontend admin email template editor leaf file",
            "repair final frontend admin compliance dialog file",
            "repair final frontend admin settings support files",
        )
    )
    if split_titles_present:
        return True
    return all(
        marker in text
        for marker in (
            "completed tasks to preserve:",
            "t029",
            "t030",
            "t031",
        )
    ) and _has_primary_failed_task_id_in_range(text, 32, 50)


def should_split_final_frontend_admin_announcement_backup_promo_timeout(text: str) -> bool:
    focused_announcement_scope = _has_primary_failed_task_id_in_range(text, 34, 40) and any(
        marker in text
        for marker in (
            "repair final frontend admin announcement backup promo files",
            "repair final frontend admin announcements view file",
            "repair final frontend admin backup view file",
            "repair final frontend admin promo codes view file",
            "frontend/src/views/admin/announcementsview.vue",
            "frontend/src/views/admin/backupview.vue",
            "frontend/src/views/admin/promocodesview.vue",
            "components/admin/announcements",
            "announcement backup promo",
        )
    )
    if focused_announcement_scope:
        return True
    if not any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    ):
        return False
    return "primary failed task ids: t034" in text and any(
        marker in text
        for marker in (
            "repair final frontend admin announcement backup promo files",
            "repair final frontend admin announcements view file",
            "repair final frontend admin backup view file",
            "repair final frontend admin promo codes view file",
            "frontend/src/views/admin/announcementsview.vue",
            "frontend/src/views/admin/backupview.vue",
            "frontend/src/views/admin/promocodesview.vue",
            "announcement backup promo",
        )
    )


def should_preserve_final_frontend_admin_announcement_backup_promo_split(text: str) -> bool:
    split_titles_present = all(
        marker in text
        for marker in (
            "repair final frontend admin announcements view file",
            "repair final frontend admin backup view file",
            "repair final frontend admin promo codes view file",
            "repair final frontend admin announcement components support files",
        )
    )
    if split_titles_present:
        return True
    return all(
        marker in text
        for marker in (
            "completed tasks to preserve:",
            "t034",
            "t035",
            "t036",
            "t037",
        )
    ) and _has_primary_failed_task_id_in_range(text, 38, 55)


def should_split_final_frontend_admin_component_timeout(text: str) -> bool:
    focused_admin_scope = "primary failed task ids: t011" in text and any(
        marker in text
        for marker in (
            "repair final frontend admin operation component contracts",
            "frontend/src/components/admin",
            "components/admin",
        )
    )
    if focused_admin_scope:
        return True
    if not any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    ):
        return False
    if "repair final frontend admin operation component contracts" in text:
        return True
    return all(
        marker in text
        for marker in (
            "primary failed task ids: t011",
            "frontend",
            "admin",
            "component",
        )
    )


def should_split_final_frontend_admin_account_identity_timeout(text: str) -> bool:
    focused_account_identity_scope = "primary failed task ids: t011" in text and any(
        marker in text
        for marker in (
            "repair final frontend admin account identity components",
            "frontend/src/components/admin/account",
            "frontend/src/components/admin/user",
        )
    )
    if focused_account_identity_scope:
        return True
    if not any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    ):
        return False
    return all(
        marker in text
        for marker in (
            "primary failed task ids: t011",
            "account",
            "identity",
            "component",
        )
    )


def should_split_final_frontend_admin_account_modal_timeout(text: str) -> bool:
    focused_account_modal_scope = "primary failed task ids: t012" in text and any(
        marker in text
        for marker in (
            "repair final frontend admin account modal components",
            "accounttestmodal",
            "importdatamodal",
            "reauthaccountmodal",
            "scheduledtestspanel",
        )
    )
    if focused_account_modal_scope:
        return True
    if not any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    ):
        return False
    return all(
        marker in text
        for marker in (
            "primary failed task ids: t012",
            "account",
            "modal",
            "component",
        )
    )


def should_split_final_frontend_admin_user_account_timeout(text: str) -> bool:
    focused_user_account_scope = _has_primary_failed_task_id_in_range(text, 16, 18) and any(
        marker in text
        for marker in (
            "repair final frontend admin user account components",
            "repair final frontend admin user access group components",
            "repair final frontend admin user api key component",
            "repair final frontend admin user create edit components",
            "groupreplacemodal",
            "userallowedgroupsmodal",
            "userapikeysmodal",
            "usercreatemodal",
            "usereditmodal",
        )
    )
    if focused_user_account_scope:
        return True
    if not any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    ):
        return False
    return all(
        marker in text
        for marker in (
            "primary failed task ids: t016",
            "admin",
            "user",
            "account",
            "component",
        )
    )


def should_preserve_final_frontend_admin_user_account_split(text: str) -> bool:
    split_titles_present = all(
        marker in text
        for marker in (
            "repair final frontend admin user access group components",
            "repair final frontend admin user api key component",
            "repair final frontend admin user create edit components",
        )
    )
    if split_titles_present:
        return True
    return all(
        marker in text
        for marker in (
            "completed tasks to preserve:",
            "t016",
            "t017",
            "t018",
        )
    ) and _has_primary_failed_task_id_in_range(text, 19, 55)


def should_split_final_frontend_admin_user_create_edit_timeout(text: str) -> bool:
    focused_create_edit_scope = _has_primary_failed_task_id_in_range(text, 18, 19) and any(
        marker in text
        for marker in (
            "repair final frontend admin user create edit components",
            "repair final frontend admin user create modal component",
            "repair final frontend admin user edit modal component",
            "usercreatemodal",
            "usereditmodal",
        )
    )
    if focused_create_edit_scope:
        return True
    if not any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    ):
        return False
    return all(
        marker in text
        for marker in (
            "primary failed task ids: t018",
            "admin",
            "user",
            "create",
            "edit",
            "component",
        )
    )


def should_preserve_final_frontend_admin_user_create_edit_split(text: str) -> bool:
    split_titles_present = all(
        marker in text
        for marker in (
            "repair final frontend admin user create modal component",
            "repair final frontend admin user edit modal component",
        )
    )
    if split_titles_present:
        return True
    return all(
        marker in text
        for marker in (
            "completed tasks to preserve:",
            "t018",
            "t019",
        )
    ) and _has_primary_failed_task_id_in_range(text, 20, 55)


def should_split_final_frontend_admin_usage_payment_timeout(text: str) -> bool:
    focused_usage_payment_scope = _has_primary_failed_task_id_in_range(text, 24, 25) and any(
        marker in text
        for marker in (
            "repair final frontend admin usage payment components",
            "repair final frontend admin usage component",
            "repair final frontend admin payment component",
            "frontend/src/components/admin/usage",
            "frontend/src/components/admin/payment",
        )
    )
    if focused_usage_payment_scope:
        return True
    if not any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    ):
        return False
    return all(
        marker in text
        for marker in (
            "primary failed task ids: t024",
            "admin",
            "usage",
            "payment",
            "component",
        )
    )


def should_preserve_final_frontend_admin_usage_payment_split(text: str) -> bool:
    split_titles_present = all(
        marker in text
        for marker in (
            "repair final frontend admin usage component",
            "repair final frontend admin payment component",
        )
    )
    if split_titles_present:
        return True
    return all(
        marker in text
        for marker in (
            "completed tasks to preserve:",
            "t024",
            "t025",
        )
    ) and _has_primary_failed_task_id_in_range(text, 26, 35)


def should_split_final_frontend_admin_payment_timeout(text: str) -> bool:
    focused_payment_scope = _has_primary_failed_task_id_in_range(text, 25, 27) and any(
        marker in text
        for marker in (
            "repair final frontend admin payment component",
            "repair final frontend admin payment order detail components",
            "repair final frontend admin payment refund dialog component",
            "repair final frontend admin payment analytics components",
            "adminordertable",
            "adminorderdetail",
            "adminrefunddialog",
            "dailyrevenuechart",
            "paymentmethodchart",
            "orderstatscards",
            "topusersleaderboard",
        )
    )
    if focused_payment_scope:
        return True
    if not any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    ):
        return False
    return _has_primary_failed_task_id_in_range(text, 25, 27) and all(
        marker in text
        for marker in (
            "admin",
            "payment",
            "component",
        )
    )


def should_preserve_final_frontend_admin_payment_split(text: str) -> bool:
    split_titles_present = all(
        marker in text
        for marker in (
            "repair final frontend admin payment order detail components",
            "repair final frontend admin payment refund dialog component",
            "repair final frontend admin payment analytics components",
        )
    )
    if split_titles_present:
        return True
    return all(
        marker in text
        for marker in (
            "completed tasks to preserve:",
            "t025",
            "t026",
            "t027",
        )
    ) and _has_primary_failed_task_id_in_range(text, 28, 35)


def should_narrow_final_frontend_admin_payment_refund_timeout(text: str) -> bool:
    focused_refund_scope = _has_primary_failed_task_id_in_range(text, 26, 26) and any(
        marker in text
        for marker in (
            "repair final frontend admin payment refund dialog component",
            "repair final frontend admin payment refund dialog file",
            "adminrefunddialog",
            "frontend/src/components/admin/payment/adminrefunddialog.vue",
        )
    )
    if focused_refund_scope:
        return True
    if not any(
        marker in text
        for marker in (
            "worker timeout",
            "timed out",
            "exceeded the codex worker timeout",
            "timeout note",
        )
    ):
        return False
    return all(
        marker in text
        for marker in (
            "primary failed task ids: t026",
            "admin",
            "payment",
            "refund",
            "dialog",
        )
    )


def should_preserve_final_frontend_admin_payment_refund_leaf(text: str) -> bool:
    if "repair final frontend admin payment refund dialog file" in text:
        return True
    return all(
        marker in text
        for marker in (
            "completed tasks to preserve:",
            "t026",
        )
    ) and _has_primary_failed_task_id_in_range(text, 27, 35)


def _has_primary_failed_task_id_in_range(text: str, start: int, end: int) -> bool:
    return any(f"primary failed task ids: t{index:03d}" in text for index in range(start, end + 1))


def _primary_failed_task_has_title(text: str, title: str) -> bool:
    """Match a title to the current failed task, never to history-only titles."""

    for match in PRIMARY_FAILED_TASK_IDS_PATTERN.finditer(text):
        for task_id in TASK_ID_PATTERN.findall(match.group(1)):
            normalized_id = re.escape(task_id.lower())
            normalized_title = re.escape(title.lower())
            if re.search(
                rf"(?m)^###\s+task\s+{normalized_id}\s+-\s+{normalized_title}\s*$",
                text,
            ):
                return True
            if re.search(
                rf"(?m)^\s*-\s*must continue focused task\s+{normalized_id}\s*:\s*{normalized_title}\.?\s*$",
                text,
            ):
                return True
    return False


def final_frontend_routes_views_repair_task_specs(
    *,
    split: bool,
    narrow_route_app_shell: bool = False,
    split_view_components: bool = False,
    split_admin_components: bool = False,
    split_admin_account_identity: bool = False,
    split_admin_account_modal: bool = False,
    split_admin_user_account: bool = False,
    split_admin_user_create_edit: bool = False,
    split_admin_usage_payment: bool = False,
    split_admin_payment: bool = False,
    split_admin_payment_refund: bool = False,
    split_view_pages: bool = False,
    split_admin_view_pages: bool = False,
    split_admin_dashboard_settings: bool = False,
    split_admin_settings_email_compliance: bool = False,
    split_admin_email_template_leaf: bool = False,
    split_admin_announcement_backup_promo: bool = False,
    split_auth_public_setup_views: bool = False,
    split_setup_not_found_views: bool = False,
    split_state_composable_utility: bool = False,
    split_composable_contracts: bool = False,
    split_metering_entitlement_composables: bool = False,
    split_frontend_test_fixtures: bool = False,
    split_component_composable_tests: bool = False,
) -> list[dict[str, object]]:
    if not split:
        return [
            {
                "title": "Repair final frontend routes views and tests",
                "description": (
                    "Close reachable frontend routes, views, components, stores, composables, and tests that still expose retired relay-era workflows."
                ),
                "assigned_agent": "frontend",
                "relevant_files": [
                    "frontend/src/router/**",
                    "frontend/src/views/**",
                    "frontend/src/components/**",
                    "frontend/src/composables/**",
                    "frontend/src/stores/**",
                    "frontend/src/utils/**",
                    "frontend/src/tests/**",
                    "frontend/tests/**",
                ],
                "completion_criteria": [
                    "Reachable frontend workflows no longer present token relay, provider channel, upstream account, model-routing, proxy, or subscription-plan behavior.",
                    "Frontend tests and fixtures align with the final CRM Billing Core product language.",
                ],
                "priority": 93,
            }
        ]
    route_task = (
        {
            "title": "Repair final frontend route registration file",
            "description": (
                "Narrow the final route/app-shell repair to the concrete route registration and navigation files "
                "that can keep retired /admin/ops behavior reachable."
            ),
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/router/index.ts",
                "frontend/src/components/layout/AppSidebar.vue",
                "frontend/src/App.vue",
                "frontend/src/stores/app.ts",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "The concrete router registration and app navigation files no longer expose retired relay-era /admin/ops behavior.",
                "Navigation still exposes CRM billing, identity, wallet, metering, analytics, audit, and admin workflows.",
            ],
            "priority": 93,
        }
        if narrow_route_app_shell
        else {
            "title": "Repair final frontend route and app shell contracts",
            "description": (
                "Close residual route, app-shell, layout, and navigation references to retired relay-era workflows."
            ),
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/router/**",
                "frontend/src/components/layout/**",
                "frontend/src/App.vue",
                "frontend/src/main.ts",
                "frontend/src/stores/app.ts",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "Reachable navigation and route registration expose CRM billing, identity, wallet, metering, analytics, audit, and admin workflows only.",
                "Retired relay-era pages are not reachable through router, app shell, or layout navigation.",
            ],
            "priority": 93,
        }
    )
    state_task = {
        "title": "Repair final frontend state composable utility contracts",
        "description": (
            "Align frontend stores, composables, and utilities with CRM billing contracts and the migrated shared types."
        ),
        "assigned_agent": "frontend",
        "relevant_files": [
            "frontend/src/stores/**",
            "frontend/src/composables/**",
            "frontend/src/utils/**",
            "frontend/src/constants/**",
            "frontend/src/types/**",
            "frontend/package.json",
            "frontend/pnpm-lock.yaml",
        ],
        "completion_criteria": [
            "Stores, composables, and utilities no longer import retired relay-era shared contracts.",
            "State and helper code uses CRM billing, wallet, connector, metering, entitlement, payment, analytics, and audit language.",
        ],
        "priority": 91,
    }
    composable_task = {
        "title": "Repair final frontend composable contracts",
        "description": "Align frontend composables with CRM billing, wallet, metering, payment, and account workflows.",
        "assigned_agent": "frontend",
        "relevant_files": [
            "frontend/src/composables/**",
            "frontend/src/types/**",
            "frontend/package.json",
            "frontend/pnpm-lock.yaml",
        ],
        "completion_criteria": [
            "Composables no longer expose relay, provider-channel, proxy, model-routing, upstream account, or token-log product concepts.",
            "Composable APIs use CRM billing, wallet, metering, entitlement, payment, analytics, and audit language.",
        ],
        "priority": 90,
    }
    metering_entitlement_task = {
        "title": "Repair final frontend metering entitlement composables",
        "description": "Align domain composables with CRM metering, entitlement, onboarding, and account-capacity semantics.",
        "assigned_agent": "frontend",
        "relevant_files": [
            "frontend/src/composables/useChannelMonitorFormat.ts",
            "frontend/src/composables/useModelWhitelist.ts",
            "frontend/src/composables/useOnboardingTour.ts",
            "frontend/src/composables/useQuotaNotifyState.ts",
            "frontend/src/composables/__tests__/useModelWhitelist.spec.ts",
            "frontend/src/types/**",
            "frontend/package.json",
            "frontend/pnpm-lock.yaml",
        ],
        "completion_criteria": [
            "Domain composables use CRM metering, entitlement, onboarding, and account-capacity language.",
            "Domain composable contracts no longer expose retired channel-monitor, provider-channel, proxy, model-routing, or token-log behavior as product concepts.",
        ],
        "priority": 89,
    }
    metering_entitlement_split_tasks = [
        {
            "title": "Repair final frontend channel monitor format composable",
            "description": "Align the channel monitor formatting composable with CRM metering and service-health language.",
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/composables/useChannelMonitorFormat.ts",
                "frontend/src/types/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "useChannelMonitorFormat uses CRM metering, service-health, account-activity, and operational status language.",
                "The composable no longer exposes retired provider-channel, proxy, relay, model-routing, or token-log product semantics.",
            ],
            "priority": 89,
        },
        {
            "title": "Repair final frontend model entitlement composable",
            "description": "Align the model whitelist composable with CRM entitlement and plan-capability language.",
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/composables/useModelWhitelist.ts",
                "frontend/src/composables/__tests__/useModelWhitelist.spec.ts",
                "frontend/src/types/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "useModelWhitelist uses CRM entitlement, plan-capability, and account-access language.",
                "The composable and test no longer expose relay model-routing, provider-channel, proxy, or token-log behavior as product concepts.",
            ],
            "priority": 88,
        },
        {
            "title": "Repair final frontend onboarding quota composables",
            "description": "Align onboarding and quota notification composables with CRM account setup and account-capacity semantics.",
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/composables/useOnboardingTour.ts",
                "frontend/src/composables/useQuotaNotifyState.ts",
                "frontend/src/types/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "Onboarding and quota notification composables use CRM account setup, wallet, entitlement, and account-capacity language.",
                "These composables no longer expose retired relay, upstream-account, provider-channel, model-routing, or token-log product behavior.",
            ],
            "priority": 87,
        },
    ]
    composable_split_tasks = [
        {
            "title": "Repair final frontend identity OAuth composables",
            "description": "Align identity and OAuth composables with CRM account, connector, and authentication workflows.",
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/composables/useAccountOAuth.ts",
                "frontend/src/composables/useAntigravityOAuth.ts",
                "frontend/src/composables/useGeminiOAuth.ts",
                "frontend/src/composables/useOpenAIOAuth.ts",
                "frontend/src/composables/__tests__/useOpenAIOAuth.spec.ts",
                "frontend/src/types/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "Identity/OAuth composables use CRM account, connector, authentication, and authorization language.",
                "OAuth composable contracts no longer expose relay, upstream-account, provider-channel, token-log, or model-routing product behavior.",
            ],
            "priority": 90,
        },
        *(metering_entitlement_split_tasks if split_metering_entitlement_composables else [metering_entitlement_task]),
        {
            "title": "Repair final frontend table navigation composables",
            "description": "Align shared UI composables with CRM-neutral table, navigation, loading, and form contracts.",
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/composables/useAutoRefresh.ts",
                "frontend/src/composables/useClipboard.ts",
                "frontend/src/composables/useForm.ts",
                "frontend/src/composables/useKeyedDebouncedSearch.ts",
                "frontend/src/composables/useNavigationLoading.ts",
                "frontend/src/composables/usePersistedPageSize.ts",
                "frontend/src/composables/useRoutePrefetch.ts",
                "frontend/src/composables/useSwipeSelect.ts",
                "frontend/src/composables/useTableLoader.ts",
                "frontend/src/composables/useTableSelection.ts",
                "frontend/src/composables/__tests__/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "Shared UI composables remain CRM-neutral helpers without relay-era product vocabulary.",
                "Navigation, loading, form, table, search, and selection composable tests compile against the final frontend contracts.",
            ],
            "priority": 88,
        },
    ]
    state_split_tasks = [
        {
            "title": "Repair final frontend store contracts",
            "description": "Align frontend stores with CRM billing, wallet, metering, payment, and account state semantics.",
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/stores/**",
                "frontend/src/types/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "Stores no longer import or expose retired relay-era shared contracts.",
                "Store state uses CRM billing, wallet, metering, entitlement, payment, analytics, and audit language.",
            ],
            "priority": 91,
        },
        *(composable_split_tasks if split_composable_contracts else [composable_task]),
        {
            "title": "Repair final frontend utility constant type contracts",
            "description": "Align frontend utilities, constants, and shared types with the final CRM product boundary.",
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/utils/**",
                "frontend/src/constants/**",
                "frontend/src/types/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "Utilities, constants, and shared types no longer expose retired relay-era contracts as product behavior.",
                "Shared helpers and types compile with CRM billing, wallet, metering, connector, entitlement, payment, analytics, and audit semantics.",
            ],
            "priority": 89,
        },
    ]
    test_task = {
        "title": "Repair final frontend test and fixture contracts",
        "description": (
            "Update frontend tests and fixtures to assert the CRM Billing Core behavior after final frontend repair."
        ),
        "assigned_agent": "frontend",
        "relevant_files": [
            "frontend/src/**/__tests__/**",
            "frontend/src/**/*.spec.ts",
            "frontend/src/**/*.spec.tsx",
            "frontend/tests/**",
            "frontend/vitest.config.ts",
            "frontend/package.json",
            "frontend/pnpm-lock.yaml",
        ],
        "completion_criteria": [
            "Frontend tests and fixtures no longer depend on retired relay-era route, view, API, type, or copy contracts.",
            "Targeted frontend tests verify CRM billing, identity, wallet, metering, payment, analytics, audit, and admin workflows.",
        ],
        "priority": 90,
    }
    component_composable_test_tasks = (
        [
            {
                "title": "Repair final frontend component test contracts",
                "description": "Update component specs to match the final CRM frontend contracts.",
                "assigned_agent": "frontend",
                "relevant_files": [
                    "frontend/src/components/**/__tests__/**",
                    "frontend/src/components/**/*.spec.ts",
                    "frontend/src/components/**/*.spec.tsx",
                    "frontend/package.json",
                    "frontend/pnpm-lock.yaml",
                ],
                "completion_criteria": [
                    "Component specs use CRM account, wallet, metering, connector, entitlement, and audit language.",
                    "Component tests no longer depend on retired provider-channel, proxy, relay, model-routing, or token-log product contracts.",
                ],
                "priority": 89,
            },
            {
                "title": "Repair final frontend composable test contracts",
                "description": "Update composable specs to match the final CRM frontend contracts.",
                "assigned_agent": "frontend",
                "relevant_files": [
                    "frontend/src/composables/__tests__/**",
                    "frontend/src/composables/**/*.spec.ts",
                    "frontend/package.json",
                    "frontend/pnpm-lock.yaml",
                ],
                "completion_criteria": [
                    "Composable specs use CRM account, wallet, metering, connector, entitlement, and audit language.",
                    "Composable tests no longer depend on retired provider-channel, proxy, relay, model-routing, or token-log product contracts.",
                ],
                "priority": 88,
            },
        ]
        if split_component_composable_tests
        else [
            {
                "title": "Repair final frontend component and composable test contracts",
                "description": "Update component and composable specs to match the final CRM frontend contracts.",
                "assigned_agent": "frontend",
                "relevant_files": [
                    "frontend/src/components/**/__tests__/**",
                    "frontend/src/components/**/*.spec.ts",
                    "frontend/src/components/**/*.spec.tsx",
                    "frontend/src/composables/__tests__/**",
                    "frontend/src/composables/**/*.spec.ts",
                    "frontend/package.json",
                    "frontend/pnpm-lock.yaml",
                ],
                "completion_criteria": [
                    "Component and composable specs use CRM account, wallet, metering, connector, entitlement, and audit language.",
                    "Component/composable tests no longer depend on retired provider-channel, proxy, relay, model-routing, or token-log product contracts.",
                ],
                "priority": 89,
            }
        ]
    )
    test_split_tasks = [
        {
            "title": "Repair final frontend API and integration test contracts",
            "description": "Update frontend API and integration specs to assert CRM Billing Core behavior.",
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/api/__tests__/**",
                "frontend/src/api/**/*.spec.ts",
                "frontend/src/api/**/*.spec.tsx",
                "frontend/src/__tests__/integration/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "API and integration specs no longer assert retired relay-era API, route, or payload contracts.",
                "API/integration tests cover CRM identity, wallet, metering, billing, payment, and admin workflows.",
            ],
            "priority": 90,
        },
        *component_composable_test_tasks,
        {
            "title": "Repair final frontend view router i18n utility test contracts",
            "description": "Update view, router, i18n, and utility specs after the final CRM frontend contract repair.",
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/views/**/__tests__/**",
                "frontend/src/views/**/*.spec.ts",
                "frontend/src/views/**/*.spec.tsx",
                "frontend/src/router/__tests__/**",
                "frontend/src/router/**/*.spec.ts",
                "frontend/src/router/**/*.spec.tsx",
                "frontend/src/i18n/__tests__/**",
                "frontend/src/i18n/**/*.spec.ts",
                "frontend/src/i18n/**/*.spec.tsx",
                "frontend/src/utils/__tests__/**",
                "frontend/src/utils/**/*.spec.ts",
                "frontend/src/utils/**/*.spec.tsx",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "View, router, i18n, and utility specs assert CRM Billing Core workflows and copy.",
                "Tests no longer expose retired relay, channel, proxy, model-routing, or subscription-plan language as product behavior.",
            ],
            "priority": 88,
        },
        {
            "title": "Repair final frontend test config and fixture contracts",
            "description": "Update frontend test fixtures, setup files, and Vitest configuration for the final CRM test suite.",
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/tests/**",
                "frontend/src/__tests__/**",
                "frontend/src/__tests__/setup.ts",
                "frontend/vitest.config.ts",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "Frontend test fixtures and setup helpers use CRM Billing Core domain language.",
                "Vitest configuration and shared fixtures support the final frontend test contracts without broad product-code edits.",
            ],
            "priority": 87,
        },
    ]
    final_test_tasks = test_split_tasks if split_frontend_test_fixtures else [test_task]
    account_component_task = {
        "title": "Repair final frontend account component contracts",
        "description": (
            "Align account-facing frontend components with CRM identity, connector, capacity, wallet, and metering language."
        ),
        "assigned_agent": "frontend",
        "relevant_files": [
            "frontend/src/components/account/**",
            "frontend/src/components/auth/**",
            "frontend/src/types/**",
            "frontend/package.json",
            "frontend/pnpm-lock.yaml",
        ],
        "completion_criteria": [
            "Account and auth components no longer present upstream account, provider channel, proxy, model-routing, or subscription-plan behavior.",
            "Component contracts compile against CRM identity, connector, wallet, capacity, entitlement, and metering types.",
        ],
        "priority": 92,
    }
    admin_component_task = {
        "title": "Repair final frontend admin operation component contracts",
        "description": (
            "Align admin operation components with CRM billing, connector, monitoring, payment, user, and usage administration."
        ),
        "assigned_agent": "frontend",
        "relevant_files": [
            "frontend/src/components/admin/**",
            "frontend/src/components/channels/**",
            "frontend/src/types/**",
            "frontend/package.json",
            "frontend/pnpm-lock.yaml",
        ],
        "completion_criteria": [
            "Admin components no longer expose relay-era channel, upstream account, proxy, model-routing, or token-log product language.",
            "Admin component consumers compile against CRM billing, connector, monitor, payment, user, usage, audit, and reconciliation contracts.",
        ],
        "priority": 91,
    }
    admin_account_identity_task = {
        "title": "Repair final frontend admin account identity components",
        "description": (
            "Align admin account, user, announcement, and compliance components with CRM identity, wallet, account, and audit workflows."
        ),
        "assigned_agent": "frontend",
        "relevant_files": [
            "frontend/src/components/admin/account/**",
            "frontend/src/components/admin/user/**",
            "frontend/src/components/admin/announcements/**",
            "frontend/src/components/admin/AdminComplianceDialog.vue",
            "frontend/src/types/**",
            "frontend/package.json",
            "frontend/pnpm-lock.yaml",
        ],
        "completion_criteria": [
            "Admin account, user, announcement, and compliance components no longer expose upstream account, provider-channel, token-log, proxy, or model-routing behavior.",
            "These components compile against CRM identity, wallet, account, audit, and notification contracts.",
        ],
        "priority": 91,
    }
    admin_account_table_task = {
        "title": "Repair final frontend admin account table components",
        "description": (
            "Align admin account table, action, filter, and stats components with CRM account, wallet, capacity, and audit semantics."
        ),
        "assigned_agent": "frontend",
        "relevant_files": [
            "frontend/src/components/admin/account/AccountActionMenu.vue",
            "frontend/src/components/admin/account/AccountBulkActionsBar.vue",
            "frontend/src/components/admin/account/AccountStatsModal.vue",
            "frontend/src/components/admin/account/AccountTableActions.vue",
            "frontend/src/components/admin/account/AccountTableFilters.vue",
            "frontend/src/types/**",
            "frontend/package.json",
            "frontend/pnpm-lock.yaml",
        ],
        "completion_criteria": [
            "Admin account table/action UI no longer exposes upstream account, provider-channel, proxy, token-log, or model-routing behavior.",
            "Account table components compile against CRM identity, wallet, capacity, and audit contracts.",
        ],
        "priority": 91,
    }
    admin_account_modal_task = {
        "title": "Repair final frontend admin account modal components",
        "description": (
            "Align admin account import, reauth, scheduled-test, and account-test modals with CRM account lifecycle and verification semantics."
        ),
        "assigned_agent": "frontend",
        "relevant_files": [
            "frontend/src/components/admin/account/AccountTestModal.vue",
            "frontend/src/components/admin/account/ImportDataModal.vue",
            "frontend/src/components/admin/account/ReAuthAccountModal.vue",
            "frontend/src/components/admin/account/ScheduledTestsPanel.vue",
            "frontend/src/components/admin/account/__tests__/**",
            "frontend/src/types/**",
            "frontend/package.json",
            "frontend/pnpm-lock.yaml",
        ],
        "completion_criteria": [
            "Admin account modal workflows use CRM account verification, import, and lifecycle language.",
            "Account modal tests and contracts no longer depend on token relay, provider-channel, proxy, or model-routing concepts.",
        ],
        "priority": 90,
    }
    admin_account_modal_split_tasks = [
        {
            "title": "Repair final frontend admin account test modal component",
            "description": "Align the admin account test modal with CRM account verification semantics.",
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/components/admin/account/AccountTestModal.vue",
                "frontend/src/components/admin/account/__tests__/**",
                "frontend/src/types/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "AccountTestModal no longer exposes relay provider, upstream-account, proxy, token-log, or model-routing language.",
                "Account test modal behavior is framed as CRM account verification and compiles against shared CRM types.",
            ],
            "priority": 90,
        },
        {
            "title": "Repair final frontend admin account import modal component",
            "description": "Align the admin account import modal with CRM account onboarding and data import semantics.",
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/components/admin/account/ImportDataModal.vue",
                "frontend/src/types/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "ImportDataModal uses CRM account onboarding/import language.",
                "Import modal contracts no longer depend on relay provider, proxy, token-log, or model-routing concepts.",
            ],
            "priority": 89,
        },
        {
            "title": "Repair final frontend admin account reauth modal component",
            "description": "Align the admin account reauthorization modal with CRM account security and lifecycle semantics.",
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/components/admin/account/ReAuthAccountModal.vue",
                "frontend/src/types/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "ReAuthAccountModal uses CRM account security and lifecycle language.",
                "Reauthorization modal contracts no longer expose upstream account, provider-channel, proxy, token-log, or model-routing product behavior.",
            ],
            "priority": 88,
        },
        {
            "title": "Repair final frontend admin scheduled account tests panel",
            "description": "Align the scheduled account tests panel with CRM account health and verification semantics.",
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/components/admin/account/ScheduledTestsPanel.vue",
                "frontend/src/types/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "ScheduledTestsPanel uses CRM account health, verification, and audit language.",
                "Scheduled test contracts no longer present relay provider, proxy, token-log, or model-routing concepts as product behavior.",
            ],
            "priority": 87,
        },
    ]
    admin_user_account_task = {
        "title": "Repair final frontend admin user account components",
        "description": (
            "Align admin user account, group, API key, create, and edit modals with CRM identity and access-management semantics."
        ),
        "assigned_agent": "frontend",
        "relevant_files": [
            "frontend/src/components/admin/user/GroupReplaceModal.vue",
            "frontend/src/components/admin/user/UserAllowedGroupsModal.vue",
            "frontend/src/components/admin/user/UserApiKeysModal.vue",
            "frontend/src/components/admin/user/UserCreateModal.vue",
            "frontend/src/components/admin/user/UserEditModal.vue",
            "frontend/src/types/**",
            "frontend/package.json",
            "frontend/pnpm-lock.yaml",
        ],
        "completion_criteria": [
            "Admin user account modals use CRM identity, access control, account, and audit language.",
            "User account component contracts no longer expose relay provider, proxy, token-log, or model-routing product concepts.",
        ],
        "priority": 89,
    }
    admin_user_create_edit_task = {
        "title": "Repair final frontend admin user create edit components",
        "description": "Align admin user create and edit modals with CRM identity lifecycle and account administration semantics.",
        "assigned_agent": "frontend",
        "relevant_files": [
            "frontend/src/components/admin/user/UserCreateModal.vue",
            "frontend/src/components/admin/user/UserEditModal.vue",
            "frontend/src/types/**",
            "frontend/package.json",
            "frontend/pnpm-lock.yaml",
        ],
        "completion_criteria": [
            "Admin user create/edit modals use CRM identity lifecycle, account administration, and audit language.",
            "Create/edit component contracts no longer expose relay provider, proxy, token-log, or model-routing behavior.",
        ],
        "priority": 87,
    }
    admin_user_create_edit_split_tasks = [
        {
            "title": "Repair final frontend admin user create modal component",
            "description": "Align the admin user creation modal with CRM identity lifecycle and account onboarding semantics.",
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/components/admin/user/UserCreateModal.vue",
                "frontend/src/types/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "UserCreateModal uses CRM identity lifecycle, account onboarding, and audit language.",
                "Create modal contracts no longer expose relay provider, proxy, token-log, or model-routing behavior.",
            ],
            "priority": 87,
        },
        {
            "title": "Repair final frontend admin user edit modal component",
            "description": "Align the admin user edit modal with CRM identity lifecycle and account administration semantics.",
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/components/admin/user/UserEditModal.vue",
                "frontend/src/types/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "UserEditModal uses CRM identity lifecycle, account administration, and audit language.",
                "Edit modal contracts no longer expose relay provider, proxy, token-log, or model-routing behavior.",
            ],
            "priority": 86,
        },
    ]
    admin_user_account_split_tasks = [
        {
            "title": "Repair final frontend admin user access group components",
            "description": "Align admin user group replacement and allowed-group modals with CRM account access control semantics.",
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/components/admin/user/GroupReplaceModal.vue",
                "frontend/src/components/admin/user/UserAllowedGroupsModal.vue",
                "frontend/src/types/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "Admin user group modals use CRM access-control, account, and audit language.",
                "Group access component contracts no longer expose relay provider, proxy, token-log, or model-routing behavior.",
            ],
            "priority": 89,
        },
        {
            "title": "Repair final frontend admin user API key component",
            "description": "Align the admin user API key modal with CRM integration credential and audit semantics.",
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/components/admin/user/UserApiKeysModal.vue",
                "frontend/src/types/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "UserApiKeysModal uses CRM integration credential, account, and audit language.",
                "API key component contracts no longer present relay provider, proxy, token-log, or model-routing concepts as product behavior.",
            ],
            "priority": 88,
        },
        *(admin_user_create_edit_split_tasks if split_admin_user_create_edit else [admin_user_create_edit_task]),
    ]
    admin_account_identity_split_tasks = [
        admin_account_table_task,
        *(admin_account_modal_split_tasks if split_admin_account_modal else [admin_account_modal_task]),
        *(admin_user_account_split_tasks if split_admin_user_account else [admin_user_account_task]),
        {
            "title": "Repair final frontend admin user balance quota components",
            "description": (
                "Align admin user balance, balance history, and platform quota components with CRM wallet, ledger, entitlement, and quota semantics."
            ),
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/components/admin/user/UserBalanceHistoryModal.vue",
                "frontend/src/components/admin/user/UserBalanceModal.vue",
                "frontend/src/components/admin/user/UserPlatformQuotaModal.vue",
                "frontend/src/components/admin/user/__tests__/**",
                "frontend/src/types/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "Admin balance and quota components use CRM wallet, ledger, entitlement, and account-capacity language.",
                "Balance/quota tests and contracts no longer depend on token relay, provider-channel, proxy, or model-routing concepts.",
            ],
            "priority": 88,
        },
        {
            "title": "Repair final frontend admin announcement compliance components",
            "description": (
                "Align admin announcement targeting and compliance components with CRM notification, audit, and governance semantics."
            ),
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/components/admin/announcements/**",
                "frontend/src/components/admin/AdminComplianceDialog.vue",
                "frontend/src/types/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "Announcement and compliance components use CRM notification, audit, governance, and account-targeting language.",
                "Compliance UI no longer presents relay-era token-log, upstream-account, provider-channel, proxy, or model-routing concepts as product behavior.",
            ],
            "priority": 87,
        },
    ]
    admin_usage_payment_task = {
        "title": "Repair final frontend admin usage payment components",
        "description": (
            "Align admin usage and payment components with CRM metering, wallet, charging, reconciliation, revenue, and refund workflows."
        ),
        "assigned_agent": "frontend",
        "relevant_files": [
            "frontend/src/components/admin/usage/**",
            "frontend/src/components/admin/payment/**",
            "frontend/src/types/**",
            "frontend/package.json",
            "frontend/pnpm-lock.yaml",
        ],
        "completion_criteria": [
            "Usage and payment components use CRM metering, wallet, charging, revenue, refund, and reconciliation language.",
            "Usage/payment tests and component contracts no longer depend on token relay, provider-channel, or token-log concepts.",
        ],
        "priority": 88,
    }
    admin_payment_task = {
        "title": "Repair final frontend admin payment component",
        "description": "Align admin payment components with CRM wallet, charging, reconciliation, revenue, and refund workflows.",
        "assigned_agent": "frontend",
        "relevant_files": [
            "frontend/src/components/admin/payment/**",
            "frontend/src/types/**",
            "frontend/package.json",
            "frontend/pnpm-lock.yaml",
        ],
        "completion_criteria": [
            "Admin payment components use CRM wallet, charging, reconciliation, revenue, and refund language.",
            "Payment component contracts no longer expose relay provider, channel, token-log, or model-routing behavior.",
        ],
        "priority": 87,
    }
    admin_payment_refund_task = {
        "title": "Repair final frontend admin payment refund dialog component",
        "description": "Align the admin payment refund dialog with CRM wallet reversal, refund, and audit semantics.",
        "assigned_agent": "frontend",
        "relevant_files": [
            "frontend/src/components/admin/payment/AdminRefundDialog.vue",
            "frontend/src/types/**",
            "frontend/package.json",
            "frontend/pnpm-lock.yaml",
        ],
        "completion_criteria": [
            "AdminRefundDialog uses CRM refund, wallet reversal, reconciliation, and audit language.",
            "Refund dialog contracts no longer expose relay provider, channel, token-log, or model-routing behavior.",
        ],
        "priority": 86,
    }
    admin_payment_refund_leaf_task = {
        "title": "Repair final frontend admin payment refund dialog file",
        "description": (
            "Perform a file-only refund dialog repair after the broader refund task timed out. "
            "Do not edit shared types or package metadata in this leaf task."
        ),
        "assigned_agent": "frontend",
        "relevant_files": [
            "frontend/src/components/admin/payment/AdminRefundDialog.vue",
        ],
        "completion_criteria": [
            "AdminRefundDialog uses CRM refund, wallet reversal, reconciliation, and audit language within the component file.",
            "If a shared type or package metadata change is required, report the exact follow-up path instead of widening this task.",
        ],
        "priority": 86,
    }
    admin_payment_split_tasks = [
        {
            "title": "Repair final frontend admin payment order detail components",
            "description": "Align admin payment order table and detail components with CRM charging and reconciliation semantics.",
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/components/admin/payment/AdminOrderTable.vue",
                "frontend/src/components/admin/payment/AdminOrderDetail.vue",
                "frontend/src/types/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "Admin payment order table/detail components use CRM order, charging, wallet, reconciliation, and audit language.",
                "Order component contracts no longer expose relay provider, channel, token-log, or model-routing behavior.",
            ],
            "priority": 87,
        },
        admin_payment_refund_leaf_task if split_admin_payment_refund else admin_payment_refund_task,
        {
            "title": "Repair final frontend admin payment analytics components",
            "description": "Align admin payment charts and stat cards with CRM revenue, charging, reconciliation, and customer value analytics.",
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/components/admin/payment/DailyRevenueChart.vue",
                "frontend/src/components/admin/payment/PaymentMethodChart.vue",
                "frontend/src/components/admin/payment/OrderStatsCards.vue",
                "frontend/src/components/admin/payment/TopUsersLeaderboard.vue",
                "frontend/src/types/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "Admin payment analytics components use CRM revenue, charging, reconciliation, and customer value language.",
                "Payment analytics contracts no longer expose relay provider, channel, token-log, or model-routing behavior.",
            ],
            "priority": 85,
        },
    ]
    admin_usage_payment_split_tasks = [
        {
            "title": "Repair final frontend admin usage component",
            "description": "Align admin usage components with CRM metering, wallet impact, and account analytics semantics.",
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/components/admin/usage/**",
                "frontend/src/types/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "Admin usage components use CRM metering, account analytics, wallet impact, and audit language.",
                "Usage component contracts no longer depend on token relay, provider-channel, or token-log concepts.",
            ],
            "priority": 88,
        },
        *(admin_payment_split_tasks if split_admin_payment else [admin_payment_task]),
    ]
    admin_split_tasks = [
        *(admin_account_identity_split_tasks if split_admin_account_identity else [admin_account_identity_task]),
        {
            "title": "Repair final frontend admin connector channel components",
            "description": (
                "Align admin connector, channel, group, proxy-compatibility, and available-channel components with CRM connector and capacity semantics."
            ),
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/components/admin/channel/**",
                "frontend/src/components/admin/group/**",
                "frontend/src/components/admin/proxy/**",
                "frontend/src/components/admin/ErrorPassthroughRulesModal.vue",
                "frontend/src/components/admin/TLSFingerprintProfilesModal.vue",
                "frontend/src/components/channels/**",
                "frontend/src/types/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "Connector and channel components no longer present relay provider channels, proxy resale, or model-routing as CRM product behavior.",
                "Remaining connector/capacity UI is framed as CRM integration infrastructure and compiles against shared CRM types.",
            ],
            "priority": 90,
        },
        {
            "title": "Repair final frontend admin monitor components",
            "description": (
                "Align admin monitor components with CRM observability, health, and operational monitoring semantics."
            ),
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/components/admin/monitor/**",
                "frontend/src/types/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "Monitor components no longer surface upstream account, provider-channel, token-log, proxy, or model-routing product language.",
                "Monitoring UI describes CRM connector health, usage health, billing operations, and observability checks.",
            ],
            "priority": 89,
        },
        *(admin_usage_payment_split_tasks if split_admin_usage_payment else [admin_usage_payment_task]),
    ]
    analytics_component_task = {
        "title": "Repair final frontend analytics and shared component contracts",
        "description": (
            "Align charts, guide, common, and shared display components with final CRM analytics and billing semantics."
        ),
        "assigned_agent": "frontend",
        "relevant_files": [
            "frontend/src/components/charts/**",
            "frontend/src/components/common/**",
            "frontend/src/components/Guide/**",
            "frontend/src/components/ui/**",
            "frontend/src/styles/**",
            "frontend/src/types/**",
            "frontend/package.json",
            "frontend/pnpm-lock.yaml",
        ],
        "completion_criteria": [
            "Shared display components use CRM analytics, usage, wallet, billing, and audit language.",
            "Residual token, upstream, provider, proxy, and model-routing references are removed or quarantined as internal compatibility where required.",
        ],
        "priority": 87,
    }
    view_page_task = {
        "title": "Repair final frontend view page contracts",
        "description": (
            "Align reachable view pages with the final CRM product boundary after component cleanup."
        ),
        "assigned_agent": "frontend",
        "relevant_files": [
            "frontend/src/views/**",
            "frontend/src/components/**",
            "frontend/src/styles/**",
            "frontend/src/types/**",
            "frontend/package.json",
            "frontend/pnpm-lock.yaml",
        ],
        "completion_criteria": [
            "Reachable view pages no longer present token relay, provider channel, upstream account, model-routing, proxy, or subscription-plan behavior.",
            "View pages compile against CRM billing, identity, wallet, metering, payment, analytics, audit, and admin workflows.",
        ],
        "priority": 86,
    }
    view_page_split_tasks = [
        *(
            [
                *(
                    [
                        {
                            "title": "Repair final frontend admin dashboard view file",
                            "description": "Align the admin dashboard page with CRM billing, wallet, metering, customer, and audit semantics.",
                            "assigned_agent": "frontend",
                            "relevant_files": [
                                "frontend/src/views/admin/DashboardView.vue",
                                "frontend/src/styles/onboarding.css",
                                "frontend/src/types/index.ts",
                            ],
                            "completion_criteria": [
                                "Dashboard copy and data labels describe CRM billing, wallet, usage metering, customers, and audit operations.",
                                "The dashboard no longer exposes relay provider, channel, proxy, model-routing, upstream account, or token-log behavior.",
                            ],
                            "priority": 86,
                        },
                        *(
                            [
                                {
                                    "title": "Repair final frontend admin settings view file",
                                    "description": "Align the admin settings page with CRM configuration, billing, account, and compliance semantics.",
                                    "assigned_agent": "frontend",
                                    "relevant_files": [
                                        "frontend/src/views/admin/SettingsView.vue",
                                        "frontend/src/styles/onboarding.css",
                                        "frontend/src/types/index.ts",
                                    ],
                                    "completion_criteria": [
                                        "SettingsView uses CRM configuration, account, billing, notification, compliance, and audit language.",
                                        "SettingsView no longer exposes relay provider, channel, model-routing, proxy, upstream account, or token-log behavior.",
                                    ],
                                    "priority": 85,
                                },
                                (
                                    {
                                        "title": "Repair final frontend admin email template editor leaf file",
                                        "description": "Align only the admin email template editor Vue file with CRM communication and compliance semantics.",
                                        "assigned_agent": "frontend",
                                        "relevant_files": [
                                            "frontend/src/views/admin/settings/EmailTemplateEditor.vue",
                                        ],
                                        "completion_criteria": [
                                            "EmailTemplateEditor uses CRM customer communication, notification, onboarding, billing, and compliance language.",
                                            "Email template editing no longer exposes relay provider, channel, proxy, upstream account, model-routing, or token-log behavior.",
                                            "The worker does not reopen shared style or type support files; those remain in the later support-file task.",
                                        ],
                                        "priority": 84,
                                    }
                                    if split_admin_email_template_leaf
                                    else {
                                        "title": "Repair final frontend admin email template editor file",
                                        "description": "Align the admin email template editor with CRM communication and compliance semantics.",
                                        "assigned_agent": "frontend",
                                        "relevant_files": [
                                            "frontend/src/views/admin/settings/EmailTemplateEditor.vue",
                                            "frontend/src/styles/onboarding.css",
                                            "frontend/src/types/index.ts",
                                        ],
                                        "completion_criteria": [
                                            "EmailTemplateEditor uses CRM customer communication, notification, onboarding, billing, and compliance language.",
                                            "Email template editing no longer exposes relay provider, channel, proxy, upstream account, model-routing, or token-log behavior.",
                                        ],
                                        "priority": 84,
                                    }
                                ),
                                {
                                    "title": "Repair final frontend admin compliance dialog file",
                                    "description": "Align the admin compliance dialog with CRM audit, risk, and operations semantics.",
                                    "assigned_agent": "frontend",
                                    "relevant_files": [
                                        "frontend/src/components/admin/AdminComplianceDialog.vue",
                                        "frontend/src/styles/onboarding.css",
                                        "frontend/src/types/index.ts",
                                    ],
                                    "completion_criteria": [
                                        "AdminComplianceDialog describes CRM compliance, audit, risk review, account, billing, and operations controls.",
                                        "The dialog no longer exposes token relay, provider channel, upstream account, proxy, model-routing, or token-log behavior.",
                                    ],
                                    "priority": 83,
                                },
                                {
                                    "title": "Repair final frontend admin settings support files",
                                    "description": "Align support files touched by settings/email/compliance cleanup without reopening the settings pages.",
                                    "assigned_agent": "frontend",
                                    "relevant_files": [
                                        "frontend/src/styles/onboarding.css",
                                        "frontend/src/types/index.ts",
                                    ],
                                    "completion_criteria": [
                                        "Support styles and types compile with CRM settings, billing, compliance, and audit semantics.",
                                        "Support files do not reintroduce relay/provider/channel/proxy/model-routing product concepts.",
                                    ],
                                    "priority": 82,
                                },
                            ]
                            if split_admin_settings_email_compliance
                            else [
                                {
                                    "title": "Repair final frontend admin settings email compliance files",
                                    "description": "Align admin settings, email template, and compliance UI files with CRM administration semantics.",
                                    "assigned_agent": "frontend",
                                    "relevant_files": [
                                        "frontend/src/views/admin/SettingsView.vue",
                                        "frontend/src/views/admin/settings/EmailTemplateEditor.vue",
                                        "frontend/src/components/admin/AdminComplianceDialog.vue",
                                        "frontend/src/styles/onboarding.css",
                                        "frontend/src/types/index.ts",
                                    ],
                                    "completion_criteria": [
                                        "Settings and email/compliance UI use CRM account, billing, notification, compliance, and audit language.",
                                        "Settings surfaces no longer expose relay provider, channel, model-routing, proxy, upstream account, or token-log behavior.",
                                    ],
                                    "priority": 85,
                                }
                            ]
                        ),
                        *(
                            [
                                {
                                    "title": "Repair final frontend admin announcements view file",
                                    "description": "Align the admin announcements page with CRM customer communication and operations semantics.",
                                    "assigned_agent": "frontend",
                                    "relevant_files": [
                                        "frontend/src/views/admin/AnnouncementsView.vue",
                                    ],
                                    "completion_criteria": [
                                        "AnnouncementsView describes CRM customer communication, account notices, billing events, and operations workflows.",
                                        "AnnouncementsView no longer surfaces relay provider, channel, proxy, token-log, model-routing, or upstream account language.",
                                    ],
                                    "priority": 84,
                                },
                                {
                                    "title": "Repair final frontend admin backup view file",
                                    "description": "Align the admin backup page with CRM data protection and operations semantics.",
                                    "assigned_agent": "frontend",
                                    "relevant_files": [
                                        "frontend/src/views/admin/BackupView.vue",
                                    ],
                                    "completion_criteria": [
                                        "BackupView describes CRM account, billing, audit, and operational backup workflows.",
                                        "BackupView no longer surfaces relay provider, channel, proxy, token-log, model-routing, or upstream account language.",
                                    ],
                                    "priority": 83,
                                },
                                {
                                    "title": "Repair final frontend admin promo codes view file",
                                    "description": "Align the admin promo-code page with CRM wallet, credit, and campaign semantics.",
                                    "assigned_agent": "frontend",
                                    "relevant_files": [
                                        "frontend/src/views/admin/PromoCodesView.vue",
                                    ],
                                    "completion_criteria": [
                                        "PromoCodesView describes CRM wallet credit, recharge incentives, customer campaigns, and billing operations.",
                                        "PromoCodesView no longer surfaces relay provider, channel, proxy, token-log, model-routing, or upstream account language.",
                                    ],
                                    "priority": 82,
                                },
                                {
                                    "title": "Repair final frontend admin announcement components support files",
                                    "description": "Align announcement component support files with CRM communication semantics.",
                                    "assigned_agent": "frontend",
                                    "relevant_files": [
                                        "frontend/src/components/admin/announcements/**",
                                        "frontend/src/styles/onboarding.css",
                                        "frontend/src/types/index.ts",
                                    ],
                                    "completion_criteria": [
                                        "Announcement components and support files compile with CRM communication, account, billing, and operations semantics.",
                                        "Support files do not reintroduce relay/provider/channel/proxy/model-routing product concepts.",
                                    ],
                                    "priority": 81,
                                },
                            ]
                            if split_admin_announcement_backup_promo
                            else [
                                {
                                    "title": "Repair final frontend admin announcement backup promo files",
                                    "description": "Align admin announcement, backup, promo-code, and announcement component files with CRM operations semantics.",
                                    "assigned_agent": "frontend",
                                    "relevant_files": [
                                        "frontend/src/views/admin/AnnouncementsView.vue",
                                        "frontend/src/views/admin/BackupView.vue",
                                        "frontend/src/views/admin/PromoCodesView.vue",
                                        "frontend/src/components/admin/announcements/**",
                                        "frontend/src/styles/onboarding.css",
                                        "frontend/src/types/index.ts",
                                    ],
                                    "completion_criteria": [
                                        "Announcement, backup, and promo-code pages describe CRM customer communication, credit, wallet, and operations workflows.",
                                        "These files no longer surface relay provider, channel, proxy, token-log, model-routing, or upstream account language.",
                                    ],
                                    "priority": 84,
                                }
                            ]
                        ),
                        {
                            "title": "Repair final frontend admin dashboard settings support files",
                            "description": "Align support files touched by admin dashboard/settings cleanup without reopening broad admin views.",
                            "assigned_agent": "frontend",
                            "relevant_files": [
                                "frontend/package.json",
                                "frontend/pnpm-lock.yaml",
                                "frontend/src/types/index.ts",
                                "frontend/src/types/payment.ts",
                                "frontend/src/styles/onboarding.css",
                            ],
                            "completion_criteria": [
                                "Shared support files required by dashboard/settings cleanup compile with CRM billing, wallet, metering, and admin semantics.",
                                "Package, type, and style support changes do not reintroduce relay/provider/channel/proxy/model-routing product concepts.",
                            ],
                            "priority": 83,
                        },
                    ]
                    if split_admin_dashboard_settings
                    else [
                        {
                            "title": "Repair final frontend admin dashboard settings view contracts",
                            "description": "Align admin dashboard, settings, announcement, backup, and promo-code pages with CRM administration semantics.",
                            "assigned_agent": "frontend",
                            "relevant_files": [
                                "frontend/src/views/admin/DashboardView.vue",
                                "frontend/src/views/admin/SettingsView.vue",
                                "frontend/src/views/admin/AnnouncementsView.vue",
                                "frontend/src/views/admin/BackupView.vue",
                                "frontend/src/views/admin/PromoCodesView.vue",
                                "frontend/src/views/admin/settings/**",
                                "frontend/src/components/admin/announcements/**",
                                "frontend/src/components/admin/AdminComplianceDialog.vue",
                                "frontend/src/styles/**",
                                "frontend/src/types/**",
                                "frontend/package.json",
                                "frontend/pnpm-lock.yaml",
                            ],
                            "completion_criteria": [
                                "Dashboard, settings, announcement, backup, and promo-code pages use CRM administration, compliance, billing, and account language.",
                                "These pages no longer expose relay provider, channel, proxy, model-routing, token-log, or upstream account behavior.",
                            ],
                            "priority": 86,
                        }
                    ]
                ),
                {
                    "title": "Repair final frontend admin user usage redeem view contracts",
                    "description": "Align admin user, usage, and redeem pages with CRM account, wallet, metering, and credit workflows.",
                    "assigned_agent": "frontend",
                    "relevant_files": [
                        "frontend/src/views/admin/UsersView.vue",
                        "frontend/src/views/admin/UsageView.vue",
                        "frontend/src/views/admin/RedeemView.vue",
                        "frontend/src/views/admin/apiKeyGroupFilterOptions.ts",
                        "frontend/src/components/admin/user/**",
                        "frontend/src/components/admin/usage/**",
                        "frontend/src/styles/**",
                        "frontend/src/types/**",
                        "frontend/package.json",
                        "frontend/pnpm-lock.yaml",
                    ],
                    "completion_criteria": [
                        "Admin user, usage, and redeem pages describe CRM customers, identity, wallet ledger, credits, usage metering, and audit workflows.",
                        "Residual relay token, model, provider, upstream, proxy, and channel language is removed from these admin pages.",
                    ],
                    "priority": 85,
                },
                {
                    "title": "Repair final frontend admin payment order plan view contracts",
                    "description": "Align admin order, payment dashboard, plan, and plan-edit pages with CRM billing and reconciliation semantics.",
                    "assigned_agent": "frontend",
                    "relevant_files": [
                        "frontend/src/views/admin/orders/**",
                        "frontend/src/components/admin/payment/**",
                        "frontend/src/styles/**",
                        "frontend/src/types/**",
                        "frontend/package.json",
                        "frontend/pnpm-lock.yaml",
                    ],
                    "completion_criteria": [
                        "Admin order, payment, and plan pages present CRM catalog, order, invoice/payment, wallet, refund, and reconciliation workflows.",
                        "Payment and plan pages no longer describe subscription resale, relay channels, upstream accounts, token logs, or model-routing behavior.",
                    ],
                    "priority": 84,
                },
                {
                    "title": "Repair final frontend admin operations view contracts",
                    "description": "Align admin ops dashboard, runtime, error, alert, and observability pages with CRM operations semantics.",
                    "assigned_agent": "frontend",
                    "relevant_files": [
                        "frontend/src/views/admin/ops/**",
                        "frontend/src/components/admin/monitor/**",
                        "frontend/src/styles/**",
                        "frontend/src/types/**",
                        "frontend/package.json",
                        "frontend/pnpm-lock.yaml",
                    ],
                    "completion_criteria": [
                        "Ops pages describe CRM platform observability, billing operations health, connector health, runtime settings, and audit diagnostics.",
                        "Ops pages no longer expose OpenAI token, relay provider, proxy, model-routing, upstream account, or token-log product semantics.",
                    ],
                    "priority": 83,
                },
                {
                    "title": "Repair final frontend legacy admin view cleanup",
                    "description": "Remove or quarantine legacy admin relay view pages and helpers that are no longer reachable in the CRM product.",
                    "assigned_agent": "frontend",
                    "relevant_files": [
                        "frontend/src/views/admin/AccountsView.vue",
                        "frontend/src/views/admin/ChannelsView.vue",
                        "frontend/src/views/admin/ChannelMonitorView.vue",
                        "frontend/src/views/admin/GroupsView.vue",
                        "frontend/src/views/admin/ProxiesView.vue",
                        "frontend/src/views/admin/RiskControlView.vue",
                        "frontend/src/views/admin/SubscriptionsView.vue",
                        "frontend/src/views/admin/affiliates/**",
                        "frontend/src/views/admin/groups*.ts",
                        "frontend/src/views/admin/__tests__/**",
                        "frontend/src/components/admin/channel/**",
                        "frontend/src/components/admin/group/**",
                        "frontend/src/components/admin/proxy/**",
                        "frontend/src/styles/**",
                        "frontend/src/types/**",
                        "frontend/package.json",
                        "frontend/pnpm-lock.yaml",
                    ],
                    "completion_criteria": [
                        "Legacy relay, provider-channel, proxy, subscription-resale, model-scope, and affiliate admin view pages are removed or quarantined from reachable CRM behavior.",
                        "Remaining legacy helpers/tests compile only as internal compatibility or are deleted with corresponding route/test cleanup.",
                    ],
                    "priority": 82,
                },
            ]
            if split_admin_view_pages
            else [
                {
                    "title": "Repair final frontend admin view page contracts",
                    "description": "Align admin view pages with CRM identity, billing, wallet, metering, audit, operations, and admin semantics.",
                    "assigned_agent": "frontend",
                    "relevant_files": [
                        "frontend/src/views/admin/**",
                        "frontend/src/components/admin/**",
                        "frontend/src/styles/**",
                        "frontend/src/types/**",
                        "frontend/package.json",
                        "frontend/pnpm-lock.yaml",
                    ],
                    "completion_criteria": [
                        "Admin view pages no longer present token relay, provider channel, upstream account, model-routing, proxy, or subscription-plan behavior.",
                        "Admin pages compile against CRM billing, identity, wallet, metering, payment, analytics, audit, and operations workflows.",
                    ],
                    "priority": 86,
                }
            ]
        ),
        {
            "title": "Repair final frontend user payment view page contracts",
            "description": "Align user dashboard, usage, API key, order, payment, redeem, and profile view pages with CRM account and billing semantics.",
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/views/user/**",
                "frontend/src/components/account/**",
                "frontend/src/components/charts/**",
                "frontend/src/styles/**",
                "frontend/src/types/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "User view pages use CRM account identity, wallet, usage metering, billing, order, payment, and audit language.",
                "User payment and account views no longer expose relay provider, channel, token-log, proxy, or model-routing behavior.",
            ],
            "priority": 85,
        },
        *(
            [
                {
                    "title": "Repair final frontend auth view contracts",
                    "description": "Align login, registration, session, and account access views with the final CRM identity boundary.",
                    "assigned_agent": "frontend",
                    "relevant_files": [
                        "frontend/src/views/auth/**",
                    ],
                    "completion_criteria": [
                        "Auth views describe CRM account identity, onboarding, access, and compliance flows.",
                        "Auth views no longer surface relay/API gateway/provider/channel/token-log product behavior.",
                    ],
                    "priority": 84,
                },
                {
                    "title": "Repair final frontend public legal view contracts",
                    "description": "Align public legal, marketing, and policy views with CRM billing and compliance semantics.",
                    "assigned_agent": "frontend",
                    "relevant_files": [
                        "frontend/src/views/public/**",
                    ],
                    "completion_criteria": [
                        "Public pages describe a CRM identity, billing, wallet, metering, payment, and compliance platform.",
                        "Public pages no longer present relay, provider-channel, proxy, model-routing, or token-log behavior.",
                    ],
                    "priority": 83,
                },
                *(
                    [
                        {
                            "title": "Repair final frontend setup view contracts",
                            "description": "Align setup pages with CRM onboarding, account, billing, and product boundary semantics.",
                            "assigned_agent": "frontend",
                            "relevant_files": [
                                "frontend/src/views/setup/**",
                            ],
                            "completion_criteria": [
                                "Setup pages use CRM onboarding, account, billing, wallet, and support language.",
                                "Setup pages no longer expose relay/API gateway/provider/channel/token-log copy.",
                            ],
                            "priority": 82,
                        },
                        {
                            "title": "Repair final frontend not-found view file",
                            "description": "Align the not-found page with CRM product recovery and support semantics.",
                            "assigned_agent": "frontend",
                            "relevant_files": [
                                "frontend/src/views/NotFoundView.vue",
                            ],
                            "completion_criteria": [
                                "NotFoundView uses CRM product, account recovery, billing, and support language.",
                                "NotFoundView no longer exposes relay/API gateway/provider/channel/token-log copy.",
                            ],
                            "priority": 81,
                        },
                    ]
                    if split_setup_not_found_views
                    else [
                        {
                            "title": "Repair final frontend setup and not-found view contracts",
                            "description": "Align setup and not-found pages with CRM onboarding, recovery, and product boundary semantics.",
                            "assigned_agent": "frontend",
                            "relevant_files": [
                                "frontend/src/views/setup/**",
                                "frontend/src/views/NotFoundView.vue",
                            ],
                            "completion_criteria": [
                                "Setup and not-found pages use CRM onboarding, account, billing, and support language.",
                                "Setup and not-found pages no longer expose relay/API gateway/provider/channel/token-log copy.",
                            ],
                            "priority": 82,
                        }
                    ]
                ),
                {
                    "title": "Repair final frontend auth public setup support files",
                    "description": "Align shared support files touched by auth, public, setup, and not-found view cleanup.",
                    "assigned_agent": "frontend",
                    "relevant_files": [
                        "frontend/src/styles/**",
                        "frontend/src/types/**",
                        "frontend/package.json",
                        "frontend/pnpm-lock.yaml",
                    ],
                    "completion_criteria": [
                        "Support files compile with CRM auth, onboarding, billing, and compliance view semantics.",
                        "Support files do not reintroduce relay/API gateway/provider/channel/token-log product concepts.",
                    ],
                    "priority": 81,
                },
            ]
            if split_auth_public_setup_views
            else [
                {
                    "title": "Repair final frontend auth public setup view contracts",
                    "description": "Align auth, public legal, setup, and not-found view pages with the final CRM product boundary.",
                    "assigned_agent": "frontend",
                    "relevant_files": [
                        "frontend/src/views/auth/**",
                        "frontend/src/views/public/**",
                        "frontend/src/views/setup/**",
                        "frontend/src/views/NotFoundView.vue",
                        "frontend/src/styles/**",
                        "frontend/src/types/**",
                        "frontend/package.json",
                        "frontend/pnpm-lock.yaml",
                    ],
                    "completion_criteria": [
                        "Auth, public, setup, and not-found views use CRM product, account, compliance, and onboarding language.",
                        "Residual relay/API gateway/provider/channel/token-log copy is removed or quarantined from public product behavior.",
                    ],
                    "priority": 84,
                }
            ]
        ),
    ]
    if split_view_components:
        component_tasks = [
            account_component_task,
            *(admin_split_tasks if split_admin_components else [admin_component_task]),
            analytics_component_task,
            *(view_page_split_tasks if split_view_pages else [view_page_task]),
        ]
        return [
            route_task,
            *component_tasks,
            *(state_split_tasks if split_state_composable_utility else [state_task]),
            *final_test_tasks,
        ]
    return [
        route_task,
        {
            "title": "Repair final frontend view and component contracts",
            "description": (
                "Align reachable views and components with the final CRM product boundary after API, locale, constants, and type cleanup."
            ),
            "assigned_agent": "frontend",
            "relevant_files": [
                "frontend/src/views/**",
                "frontend/src/components/**",
                "frontend/src/styles/**",
                "frontend/src/types/**",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ],
            "completion_criteria": [
                "Reachable views and components no longer present token relay, provider channel, upstream account, model-routing, proxy, or subscription-plan behavior.",
                "Component consumers compile against CRM billing, connector, wallet, metering, entitlement, payment, analytics, and audit contracts.",
            ],
            "priority": 92,
        },
        *(state_split_tasks if split_state_composable_utility else [state_task]),
        *final_test_tasks,
    ]


def large_refactor_planning_scope_controls(
    scope_controls: dict[str, list[str]],
    requirements: list[Requirement],
) -> dict[str, list[str]]:
    """Relax stale file-level frontend repair scopes without dropping protections."""

    if boundary_mode(scope_controls) != "large_refactor" or not is_large_refactor_frontend_phase(requirements):
        return scope_controls
    allowed = list(scope_controls.get("allowed_prefixes", []))
    targets = list(scope_controls.get("target_files", []))
    frontend_scope_items = [
        normalize_repo_path(path)
        for path in [*allowed, *targets]
        if normalize_repo_path(path).startswith("frontend/")
    ]
    if not frontend_scope_items:
        return scope_controls

    widened_allowed: list[str] = []
    widened = False
    for path in allowed:
        normalized = normalize_repo_path(path)
        if normalized.startswith("frontend/") and Path(normalized).suffix:
            widened_allowed.append("frontend/")
            widened = True
        else:
            widened_allowed.append(path)
    if not any(is_frontend_directory_scope(path) for path in widened_allowed) and any(Path(path).suffix for path in frontend_scope_items):
        widened_allowed.append("frontend/")
        widened = True
    if not widened:
        return scope_controls
    return {
        "allowed_prefixes": dedupe(widened_allowed),
        "protected_prefixes": list(scope_controls.get("protected_prefixes", [])),
        "target_files": targets,
        "boundary_mode": list(scope_controls.get("boundary_mode", ["large_refactor"])),
    }


def is_frontend_directory_scope(path: str) -> bool:
    normalized = normalize_repo_path(path)
    if normalized == "frontend" or normalized == "frontend/**":
        return True
    return normalized.startswith("frontend/") and not Path(normalized).suffix


def boundary_mode(scope_controls: dict[str, list[str]] | None) -> str:
    values = list((scope_controls or {}).get("boundary_mode", []))
    return values[0] if values else "strict"


def scoped_target_files(scope_controls: dict[str, list[str]] | None) -> list[str]:
    scoped = scoped_files(list((scope_controls or {}).get("target_files", [])), scope_controls)
    if scoped:
        return scoped
    return dedupe(prefix_to_writable_glob(path) for path in (scope_controls or {}).get("allowed_prefixes", []))


def scoped_files(
    files: list[str],
    scope_controls: dict[str, list[str]] | None,
    *,
    fallback: list[str] | None = None,
) -> list[str]:
    if not scope_controls:
        return dedupe(files)
    allowed = list(scope_controls.get("allowed_prefixes", []))
    protected = list(scope_controls.get("protected_prefixes", []))
    selected: list[str] = []
    for file_path in files:
        normalized = normalize_repo_path(file_path)
        if not normalized:
            continue
        if protected and any(path_matches_prefix(normalized, prefix) for prefix in protected):
            continue
        if allowed and not any(path_matches_prefix(normalized, prefix) for prefix in allowed):
            continue
        selected.append(normalized)
    result = dedupe(selected)
    if not result and fallback:
        return scoped_files(list(fallback), scope_controls)
    return result


def scoped_verification_commands(scope_controls: dict[str, list[str]] | None, commands: list[str]) -> list[str]:
    if is_docs_only_scope(scoped_target_files(scope_controls)):
        return ["static document inspection"]
    normalized_commands = dedupe(commands)
    target_files = scoped_target_files(scope_controls)
    joined_targets = "\n".join(target_files)
    if "alchemy_creative_agent_3_0/" not in joined_targets:
        return normalized_commands
    return ["python -B -m pytest alchemy_creative_agent_3_0/tests"]


def is_docs_only_scope(paths: list[str]) -> bool:
    normalized = [normalize_repo_path(path) for path in paths if normalize_repo_path(path)]
    if not normalized:
        return False
    return all(path == "docs" or path.startswith("docs/") or is_external_or_document_context(path) for path in normalized)


LARGE_REFACTOR_ROOTS = {
    ".github",
    "api",
    "app",
    "apps",
    "autodev",
    "backend",
    "cmd",
    "config",
    "configs",
    "database",
    "db",
    "deploy",
    "deployment",
    "docker",
    "docs",
    "ent",
    "examples",
    "frontend",
    "internal",
    "migrations",
    "pkg",
    "runtime",
    "scripts",
    "server",
    "services",
    "src",
    "tests",
    "web",
}

LARGE_REFACTOR_TOP_LEVEL_FILES = {
    ".env.example",
    ".gitignore",
    "Dockerfile",
    "Makefile",
    "README.md",
    "README",
    "Cargo.toml",
    "go.mod",
    "go.sum",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "pyproject.toml",
    "requirements.txt",
    "docker-compose.yml",
    "docker-compose.yaml",
}


def large_refactor_relevant_files(
    repository_files: list[RepositoryFile],
    *,
    package_files: list[str],
    ci_files: list[str],
    scope_controls: dict[str, list[str]] | None,
) -> list[str]:
    protected = list((scope_controls or {}).get("protected_prefixes", []))
    candidates: list[str] = []
    for file in repository_files:
        normalized = normalize_repo_path(file.path)
        if not normalized or (protected and any(path_matches_prefix(normalized, prefix) for prefix in protected)):
            continue
        first = normalized.split("/", 1)[0]
        if first in LARGE_REFACTOR_ROOTS:
            candidates.append(f"{first}/**")
        elif "/" not in normalized and (normalized in LARGE_REFACTOR_TOP_LEVEL_FILES or normalized.lower().startswith("readme")):
            candidates.append(normalized)
    for path in [*package_files, *ci_files]:
        normalized = normalize_repo_path(path)
        if not normalized or (protected and any(path_matches_prefix(normalized, prefix) for prefix in protected)):
            continue
        first = normalized.split("/", 1)[0]
        if "/" in normalized and first in LARGE_REFACTOR_ROOTS:
            candidates.append(f"{first}/**")
        elif "/" not in normalized and (normalized in LARGE_REFACTOR_TOP_LEVEL_FILES or normalized.lower().startswith("readme")):
            candidates.append(normalized)
    candidates.extend(package_files)
    candidates.extend(ci_files)
    result = dedupe(scoped_files(candidates, scope_controls))
    return result or ["**"]


def normalize_repo_path(path: str) -> str:
    clean = str(path).replace("\\", "/").strip().strip("`").strip()
    if clean.endswith("."):
        clean = clean[:-1]
    return clean.strip("/")


def normalize_scope_prefix(path: str) -> str:
    clean = normalize_repo_path(path)
    if clean.endswith("/**"):
        clean = clean[:-3]
    if clean and not Path(clean).suffix and not clean.endswith("/"):
        clean += "/"
    return clean


def path_matches_prefix(path: str, prefix: str) -> bool:
    clean_prefix = normalize_scope_prefix(prefix)
    if clean_prefix.endswith("/"):
        return path.startswith(clean_prefix)
    return path == clean_prefix or path.startswith(clean_prefix + "/")


def prefix_to_writable_glob(path: str) -> str:
    clean = normalize_scope_prefix(path).rstrip("/")
    if not clean:
        return ""
    return clean if Path(clean).suffix else f"{clean}/**"


def is_external_or_document_context(path: str) -> bool:
    normalized = normalize_repo_path(path)
    if not normalized:
        return False
    if ":" in normalized:
        return True
    return Path(normalized).suffix.lower() in {".md", ".txt", ".json", ".yaml", ".yml"}


def classify_requirement_task(requirement: Requirement) -> tuple[str, str]:
    text = requirement.text.lower()
    files = " ".join(requirement.related_files).lower()
    combined = f"{text} {files}"
    if requirement.source_role == "feedback" or any(
        marker in text
        for marker in ("bug", "issue", "feedback", "playtest", "regression", "验收反馈", "反馈", "问题")
    ):
        return "debug", "debug"
    if any(file.endswith((".md", ".txt", ".rst")) for file in requirement.related_files):
        return "documentation", "architect"
    test_text = any(marker in text for marker in ("test", "测试", "qa", "verification", "验证", "验收", "coverage", "ci"))
    all_test_files = bool(requirement.related_files) and all(
        any(marker in file.lower() for marker in ("test", "tests/", ".test.", ".spec.", ".github/workflows"))
        for file in requirement.related_files
    )
    if test_text or all_test_files:
        return "test", "test"
    if any(marker in combined for marker in ("api", "backend", "database", "schema", "migration", "auth", "server", "service")):
        return "backend", "backend"
    if any(
        marker in combined
        for marker in (
            "ui",
            "frontend",
            "dashboard",
            "page",
            "screen",
            "component",
            ".tsx",
            ".jsx",
            ".css",
            ".html",
            ".js",
            "canvas",
            "renderer",
            "tilemap",
            "platformer",
            "game",
            "游戏",
            "渲染",
            "关卡",
        )
    ):
        return "frontend", "frontend"
    if any(marker in combined for marker in ("readme", "docs", "documentation", ".md")):
        return "documentation", "architect"
    if len(requirement.related_files) > 1:
        return "integration", "backend"
    return "backend", "backend"


def classify_grouped_requirement_task(requirements: list[Requirement]) -> tuple[str, str]:
    if any(requirement.source_role == "feedback" for requirement in requirements):
        return "debug", "debug"
    return classify_requirement_task(requirements[0])


def classify_large_refactor_agent(requirements: list[Requirement]) -> str:
    if is_large_refactor_frontend_phase(requirements):
        return "frontend"
    return "backend"


FRONTEND_LARGE_REFACTOR_TASK_SPECS = (
    {
        "title": "Close frontend router, menu, and direct pages",
        "description": (
            "Remove obsolete old-domain routes, navigation entries, and directly reachable pages while keeping "
            "CRM billing routes available."
        ),
        "markers": (
            "router",
            "route",
            "menu",
            "navigation",
            "direct page",
            "direct url",
            "删除 router",
            "删除菜单",
            "可直达页面",
            "旧页面",
            "菜单",
        ),
        "files": (
            "frontend/src/router/**",
            "frontend/src/components/**",
            "frontend/src/layouts/**",
            "frontend/src/views/**",
            "frontend/src/App.vue",
            "frontend/src/main.ts",
            "frontend/src/i18n/**",
            "frontend/package.json",
        ),
    },
    {
        "title": "Clean frontend API service references",
        "description": (
            "Remove or quarantine old provider, channel, proxy, gateway, subscription, and upstream service "
            "exports from frontend API barrels and callers."
        ),
        "markers": (
            "api service",
            "service reference",
            "service 引用",
            "api service 引用",
            "清理 api",
            "清理 API",
        ),
        "files": (
            "frontend/src/api/**",
            "frontend/src/components/**",
            "frontend/src/composables/**",
            "frontend/src/constants/**",
            "frontend/src/types/**",
            "frontend/src/stores/**",
            "frontend/src/views/**",
            "frontend/src/utils/**",
            "frontend/src/i18n/**",
            "frontend/package.json",
        ),
    },
    {
        "title": "Convert wallet recharge and payment surfaces",
        "description": (
            "Make wallet, recharge, payment-provider, and order screens support balance recharge only, without "
            "subscription or model-routing product flows."
        ),
        "markers": (
            "wallet",
            "recharge",
            "payment",
            "payment providers",
            "order",
            "余额",
            "充值",
            "支付",
            "订单",
            "Payment Providers",
        ),
        "files": (
            "frontend/src/views/user/*Payment*.vue",
            "frontend/src/views/user/*Order*.vue",
            "frontend/src/views/admin/*Payment*.vue",
            "frontend/src/views/admin/*Order*.vue",
            "frontend/src/views/admin/orders/**",
            "frontend/src/stores/payment.ts",
            "frontend/src/api/**",
            "frontend/src/types/**",
            "frontend/src/utils/**",
            "frontend/src/i18n/**",
            "frontend/package.json",
        ),
    },
    {
        "title": "Convert redeem code pages to balance-only flows",
        "description": (
            "Update user and admin redeem pages so visible creation and redemption paths only handle wallet "
            "balance recharge."
        ),
        "markers": (
            "redeem",
            "redemption",
            "兑换",
            "兑换码",
        ),
        "files": (
            "frontend/src/views/user/*Redeem*.vue",
            "frontend/src/views/admin/*Redeem*.vue",
            "frontend/src/api/**",
            "frontend/src/types/**",
            "frontend/src/stores/**",
            "frontend/src/i18n/**",
            "frontend/package.json",
        ),
    },
    {
        "title": "Close usage API key and admin user workflows",
        "description": (
            "Keep generic CRM usage, API key, user management, balance adjustment, order query, and admin usage "
            "workflows while removing quota, channel, provider, and subscription controls."
        ),
        "markers": (
            "usage",
            "api key",
            "admin users",
            "user management",
            "balance adjustment",
            "用量",
            "API Key",
            "用户管理",
            "余额调整",
        ),
        "files": (
            "frontend/src/views/user/*Usage*.vue",
            "frontend/src/views/user/*Key*.vue",
            "frontend/src/views/admin/*Usage*.vue",
            "frontend/src/views/admin/*User*.vue",
            "frontend/src/components/account/**",
            "frontend/src/components/admin/usage/**",
            "frontend/src/components/layout/AppSidebar.vue",
            "frontend/src/composables/**",
            "frontend/src/router/index.ts",
            "frontend/src/views/admin/DashboardView.vue",
            "frontend/src/views/auth/**",
            "frontend/src/api/**",
            "frontend/src/types/**",
            "frontend/src/stores/**",
            "frontend/src/utils/**",
            "frontend/src/i18n/**",
            "frontend/package.json",
        ),
    },
    {
        "title": "Sweep frontend product copy and i18n",
        "description": (
            "Replace user-facing token relay, gateway, upstream account, channel, model-routing, and subscription "
            "copy with CRM identity, wallet, metering, billing, reconciliation, analytics, and audit language."
        ),
        "markers": (
            "copy",
            "i18n",
            "wording",
            "token relay",
            "middle station",
            "产品文案",
            "文案",
            "token 中转",
            "中转站",
        ),
        "files": (
            "frontend/src/i18n/**",
            "frontend/src/views/**",
            "frontend/src/components/**",
            "frontend/src/styles/**",
            "frontend/src/stores/**",
            "frontend/package.json",
        ),
    },
)

FRONTEND_COPY_SWEEP_TIMEOUT_SPLIT_TASK_SPECS = (
    {
        "title": "Sweep frontend i18n product copy",
        "description": (
            "Replace token relay, gateway, upstream account, channel, model-routing, and subscription wording "
            "inside frontend locale dictionaries."
        ),
        "markers": (
            "copy",
            "i18n",
            "wording",
            "token relay",
            "middle station",
            "浜у搧鏂囨",
            "鏂囨",
            "token 涓浆",
            "涓浆绔?",
        ),
        "files": (
            "frontend/src/i18n/**",
            "frontend/package.json",
        ),
    },
    {
        "title": "Sweep frontend view and component product copy",
        "description": (
            "Replace token relay, gateway, upstream account, channel, model-routing, and subscription wording "
            "inside frontend views, components, stores, styles, and constants."
        ),
        "markers": (
            "copy",
            "i18n",
            "wording",
            "token relay",
            "middle station",
            "浜у搧鏂囨",
            "鏂囨",
            "token 涓浆",
            "涓浆绔?",
        ),
        "files": (
            "frontend/src/views/**",
            "frontend/src/components/**",
            "frontend/src/styles/**",
            "frontend/src/stores/**",
            "frontend/src/constants/**",
            "frontend/package.json",
        ),
    },
)


FRONTEND_REMAINING_CLOSURE_TIMEOUT_SPLIT_TASK_SPECS = (
    {
        "title": "Complete remaining frontend shell and route closure",
        "description": (
            "Close residual frontend app-shell, router, layout, navigation, and direct-entry gaps left after "
            "the more specific frontend workflow tasks."
        ),
        "files": (
            "frontend/src/router/**",
            "frontend/src/layouts/**",
            "frontend/src/components/layout/**",
            "frontend/src/App.vue",
            "frontend/src/main.ts",
            "frontend/src/i18n/**",
            "frontend/package.json",
        ),
    },
    {
        "title": "Complete remaining frontend state and API closure",
        "description": (
            "Close residual frontend API, store, composable, type, utility, and constant gaps left after the "
            "more specific frontend workflow tasks."
        ),
        "files": (
            "frontend/src/api/**",
            "frontend/src/stores/**",
            "frontend/src/composables/**",
            "frontend/src/constants/**",
            "frontend/src/types/**",
            "frontend/src/utils/**",
            "frontend/package.json",
        ),
    },
    {
        "title": "Complete remaining frontend view workflow closure",
        "description": (
            "Close residual frontend view, component, and style workflow gaps left after the more specific "
            "frontend workflow tasks."
        ),
        "files": (
            "frontend/src/views/**",
            "frontend/src/components/**",
            "frontend/src/styles/**",
            "frontend/package.json",
        ),
    },
)


FRONTEND_STATE_API_TIMEOUT_SPLIT_TASK_SPECS = (
    {
        "title": "Complete remaining frontend API service closure",
        "description": "Close residual frontend API service and shared type gaps left after prior closure tasks.",
        "files": (
            "frontend/src/api/**",
            "frontend/src/types/**",
            "frontend/package.json",
        ),
    },
    {
        "title": "Complete remaining frontend store and composable closure",
        "description": "Close residual frontend store, composable, and utility gaps left after prior closure tasks.",
        "files": (
            "frontend/src/stores/**",
            "frontend/src/composables/**",
            "frontend/src/utils/**",
            "frontend/package.json",
        ),
    },
    {
        "title": "Complete remaining frontend constants and type closure",
        "description": "Close residual frontend constants and type gaps left after prior closure tasks.",
        "files": (
            "frontend/src/constants/**",
            "frontend/src/types/**",
            "frontend/package.json",
        ),
    },
)


SCHEMA_BUILD_PHASE_MARKER_GROUPS = (
    ("ent schema", "schema pruning", "prune ent"),
    ("regenerate ent", "generate ent", "ent generate"),
    ("migration", "migrate", "fresh db", "fresh database"),
    ("service/repository/test", "service repository test", "repository/test"),
    ("go test ./backend/internal", "go test ./backend", "backend/internal"),
    ("build/typecheck", "frontend build", "typecheck"),
)


SCHEMA_BUILD_LARGE_REFACTOR_TASK_SPECS = (
    {
        "title": "Prune legacy Ent schemas and table contracts",
        "description": (
            "Remove obsolete token-relay schema/table contracts from the backend data model while preserving "
            "the CRM identity, wallet, billing, metering, and audit schema surface."
        ),
        "markers": (
            "ent schema",
            "schema",
            "prune",
            "table",
            "fresh db",
            "token relay table",
            "fresh migration",
        ),
        "files": (
            "backend/ent/schema/**",
            "backend/ent/migrate/**",
            "backend/internal/domain/**",
            "backend/internal/server/**",
            "backend/cmd/server/**",
            "backend/go.mod",
        ),
        "include_frontend_commands": False,
    },
    {
        "title": "Regenerate Ent clients and migration artifacts",
        "description": (
            "Regenerate Ent output and migration artifacts from the pruned schema, then keep fresh database "
            "migration behavior aligned with the Billing Core v1 contract."
        ),
        "markers": (
            "regenerate ent",
            "generate ent",
            "migration",
            "migrate",
            "fresh db",
            "fresh database",
            "ent",
        ),
        "files": (
            "backend/ent/**",
            "backend/migrations/**",
            "backend/internal/repository/**",
            "backend/go.mod",
            "backend/go.sum",
        ),
        "include_frontend_commands": False,
    },
    {
        "title": "Clean legacy backend services repositories and tests",
        "description": (
            "Remove or rewrite backend services, repositories, route registrations, and tests that still depend "
            "on token relay, provider/channel, subscription-fulfillment, or gateway semantics."
        ),
        "markers": (
            "service/repository/test",
            "service",
            "repository",
            "test",
            "route",
            "paymentservice",
            "redeemservice",
            "usage billing",
            "walletservice",
            "admin routes",
            "gateway",
            "provider",
            "channel",
            "clean unused service/repository/test code",
            "clean legacy backend services",
            "service/repository/test",
            "backend/internal/handler",
            "backend/internal/server",
            "backend/cmd/server",
        ),
        "files": (
            "backend/internal/service/**",
            "backend/internal/repository/**",
            "backend/internal/handler/**",
            "backend/internal/server/**",
            "backend/internal/config/**",
            "backend/go.mod",
        ),
        "include_frontend_commands": False,
    },
    {
        "title": "Stabilize schema and build verification contracts",
        "description": (
            "Close backend test/build and frontend build/typecheck contract gaps introduced by schema pruning "
            "without reopening broad product-surface work."
        ),
        "markers": (
            "go test",
            "build/typecheck",
            "frontend build",
            "typecheck",
            "test ./backend/internal",
            "passes",
        ),
        "files": (
            "backend/go.mod",
            "backend/go.sum",
            "frontend/package.json",
            "frontend/pnpm-lock.yaml",
            "Makefile",
            ".github/workflows/**",
        ),
        "include_frontend_commands": True,
    },
)


SCHEMA_PRUNE_TIMEOUT_SPLIT_TASK_SPECS = (
    {
        "title": "Prune Ent schema definitions",
        "description": (
            "Narrow the timed-out schema-pruning workflow to Ent schema definition files and remove obsolete "
            "token-relay table definitions from that layer first."
        ),
        "markers": (
            "ent schema",
            "schema",
            "prune",
            "table",
            "token relay table",
        ),
        "files": (
            "backend/ent/schema/**",
            "backend/go.mod",
        ),
        "include_frontend_commands": False,
    },
    {
        "title": "Align Ent migration and server table contracts",
        "description": (
            "After schema definitions are narrowed, align migration/server table contracts and fresh DB behavior "
            "without reopening service cleanup or frontend build work."
        ),
        "markers": (
            "fresh db",
            "fresh migration",
            "migration",
            "migrate",
            "table",
            "schema",
        ),
        "files": (
            "backend/ent/migrate/**",
            "backend/internal/domain/**",
            "backend/internal/server/**",
            "backend/cmd/server/**",
            "backend/go.mod",
        ),
        "include_frontend_commands": False,
    },
)


SCHEMA_MIGRATION_TIMEOUT_SPLIT_TASK_SPECS = (
    {
        "title": "Align Ent migration contracts",
        "description": (
            "Narrow the timed-out migration/server alignment workflow to Ent migration artifacts and fresh "
            "migration table contracts first."
        ),
        "markers": (
            "fresh migration",
            "migration",
            "migrate",
            "table",
            "schema",
        ),
        "files": (
            "backend/ent/migrate/**",
            "backend/go.mod",
        ),
        "include_frontend_commands": False,
        "restrict_relevant_files_to_spec": True,
    },
    {
        "title": "Align server and domain table contracts",
        "description": (
            "Then align server startup, domain constants, and fresh DB behavior with the narrowed migration "
            "contract without reopening Ent schema definitions or service cleanup."
        ),
        "markers": (
            "fresh db",
            "server",
            "domain",
            "table",
            "schema",
        ),
        "files": (
            "backend/internal/domain/**",
            "backend/internal/server/**",
            "backend/cmd/server/**",
            "backend/go.mod",
        ),
        "include_frontend_commands": False,
        "restrict_relevant_files_to_spec": True,
    },
)


SCHEMA_MIGRATION_CONTRACT_CHECKPOINT_TASK_SPECS = (
    {
        "title": "Inventory Ent migration contract deltas",
        "description": (
            "Create a narrow checkpoint of the Ent migration table-contract delta before patching, including "
            "obsolete CRM-incompatible table references and the exact migrate/schema.go sections to change."
        ),
        "markers": (
            "migration",
            "migrate",
            "table",
            "schema",
            "timeout",
        ),
        "files": (
            "backend/ent/migrate/schema.go",
            "backend/go.mod",
        ),
        "commands_to_run": (),
        "include_frontend_commands": False,
        "restrict_relevant_files_to_spec": True,
    },
    {
        "title": "Patch Ent migration contract deltas",
        "description": (
            "Apply only the migration-contract patch identified by the checkpoint and verify the Ent migration "
            "package without reopening server/domain alignment."
        ),
        "markers": (
            "fresh migration",
            "migration",
            "migrate",
            "table",
            "schema",
        ),
        "files": (
            "backend/ent/migrate/schema.go",
            "backend/go.mod",
        ),
        "include_frontend_commands": False,
        "restrict_relevant_files_to_spec": True,
    },
    {
        "title": "Align server and domain table contracts",
        "description": (
            "Then align server startup, domain constants, and fresh DB behavior with the narrowed migration "
            "contract without reopening Ent schema definitions or service cleanup."
        ),
        "markers": (
            "fresh db",
            "server",
            "domain",
            "table",
            "schema",
        ),
        "files": (
            "backend/internal/domain/**",
            "backend/internal/server/**",
            "backend/cmd/server/**",
            "backend/go.mod",
        ),
        "include_frontend_commands": False,
        "restrict_relevant_files_to_spec": True,
    },
)


SCHEMA_ENT_REGENERATION_TIMEOUT_SPLIT_TASK_SPECS = (
    {
        "title": "Inventory Ent regeneration inputs",
        "description": (
            "Checkpoint the Ent regeneration inputs and current generated-artifact drift before running another "
            "broad regeneration worker."
        ),
        "completion_criteria": (
            "Current Ent generator inputs and generated-artifact drift are inventoried without editing repository files.",
            "Follow-up generation and caller-alignment targets are identified with concise evidence.",
        ),
        "markers": (
            "regenerate ent",
            "ent clients",
            "migration artifacts",
            "schema",
            "generate",
        ),
        "files": (
            "backend/ent/generate.go",
            "backend/ent/schema/**",
            "backend/ent/migrate/schema.go",
            "backend/go.mod",
        ),
        "commands_to_run": (),
        "include_frontend_commands": False,
        "restrict_relevant_files_to_spec": True,
    },
    {
        "title": "Regenerate Ent generated clients",
        "description": (
            "Run the Ent generation/update workflow and keep this task limited to generated Ent artifacts and Go "
            "module metadata."
        ),
        "completion_criteria": (
            "Ent generated artifacts are regenerated from the current schema inputs.",
            "Generated Ent packages pass scoped verification such as `cd backend && go test ./ent/...`.",
            "Repository/service/server caller failures outside generated Ent files are documented for the caller-alignment task instead of repaired here.",
        ),
        "markers": (
            "regenerate ent",
            "ent clients",
            "migration artifacts",
            "generate",
        ),
        "files": (
            "backend/ent/**",
            "backend/go.mod",
            "backend/go.sum",
        ),
        "commands_to_run": ("cd backend && go test ./ent/...",),
        "include_frontend_commands": False,
        "restrict_relevant_files_to_spec": True,
    },
    {
        "title": "Align repository callers after Ent regeneration",
        "description": (
            "Align repository/service/server callers with regenerated Ent types before the broader legacy cleanup "
            "task runs."
        ),
        "markers": (
            "repository",
            "service",
            "server",
            "ent clients",
            "generated",
        ),
        "files": (
            "backend/internal/repository/**",
            "backend/internal/service/**",
            "backend/internal/server/**",
            "backend/cmd/server/**",
            "backend/go.mod",
        ),
        "include_frontend_commands": False,
        "restrict_relevant_files_to_spec": True,
    },
)


SCHEMA_ENT_CALLER_ALIGNMENT_TIMEOUT_SPLIT_TASK_SPECS = (
    {
        "title": "Inventory Ent caller alignment failures",
        "description": (
            "Checkpoint the repository, service, and server caller failures left after Ent regeneration before "
            "dispatching another editable caller-alignment worker."
        ),
        "completion_criteria": (
            "Current generated-Ent caller failures are inventoried without editing repository files.",
            "Repository, service, and server/handler follow-up targets are separated with concise evidence.",
        ),
        "markers": (
            "repository",
            "service",
            "server",
            "ent clients",
            "generated",
            "timeout",
        ),
        "files": (
            "backend/internal/repository/**",
            "backend/internal/service/**",
            "backend/internal/server/**",
            "backend/internal/handler/**",
            "backend/cmd/server/**",
            "backend/go.mod",
        ),
        "commands_to_run": (),
        "include_frontend_commands": False,
        "restrict_relevant_files_to_spec": True,
    },
    {
        "title": "Align repository Ent callers",
        "description": (
            "Update repository-layer queries and adapters to compile against regenerated Ent types without "
            "reopening service or route cleanup."
        ),
        "completion_criteria": (
            "Repository-layer callers compile against regenerated Ent APIs.",
            "Repository package verification passes or records only downstream service/server follow-ups.",
        ),
        "markers": (
            "repository",
            "ent clients",
            "generated",
        ),
        "files": (
            "backend/internal/repository/**",
            "backend/go.mod",
        ),
        "commands_to_run": ("cd backend && go test ./internal/repository/...",),
        "include_frontend_commands": False,
        "restrict_relevant_files_to_spec": True,
    },
    {
        "title": "Align service Ent caller contracts",
        "description": (
            "Update service-layer repository calls and DTO mappings after the repository Ent caller patch, "
            "leaving route wiring and full backend verification to later tasks."
        ),
        "completion_criteria": (
            "Service-layer callers compile against the updated repository and Ent contracts.",
            "Service package verification passes or records only downstream server/handler follow-ups.",
        ),
        "markers": (
            "service",
            "repository",
            "ent clients",
            "generated",
        ),
        "files": (
            "backend/internal/service/**",
            "backend/internal/repository/**",
            "backend/internal/domain/**",
            "backend/go.mod",
        ),
        "commands_to_run": ("cd backend && go test ./internal/service/...",),
        "include_frontend_commands": False,
        "restrict_relevant_files_to_spec": True,
    },
    {
        "title": "Align server and handler Ent wiring",
        "description": (
            "Update server, handler, and command wiring after repository/service Ent caller contracts are aligned, "
            "without taking over the later full schema/build stabilization task."
        ),
        "completion_criteria": (
            "Server, handler, and command wiring compile against the updated CRM billing backend contracts.",
            "Route/server package verification passes or leaves only full-backend stabilization work for the final schema/build task.",
        ),
        "markers": (
            "server",
            "handler",
            "route",
            "service",
            "ent clients",
            "generated",
        ),
        "files": (
            "backend/internal/server/**",
            "backend/internal/handler/**",
            "backend/internal/service/**",
            "backend/cmd/server/**",
            "backend/go.mod",
        ),
        "commands_to_run": ("cd backend && go test ./internal/server/... ./internal/handler/... ./cmd/server/...",),
        "include_frontend_commands": False,
        "restrict_relevant_files_to_spec": True,
    },
)


SCHEMA_REPOSITORY_CALLER_TIMEOUT_SPLIT_TASK_SPECS = (
    {
        "title": "Align account repository Ent callers",
        "description": (
            "Patch account and identity repository callers that still reference removed Ent edges or generated "
            "clients after schema pruning."
        ),
        "completion_criteria": (
            "Account and identity repository callers no longer reference removed Proxy or retired generated Ent clients.",
            "Repository package compile verification is attempted with a lightweight no-test run or the remaining blockers are recorded for the next repository split task.",
        ),
        "markers": (
            "repository",
            "account_repo",
            "identity",
            "api key",
            "proxy",
            "ent callers",
        ),
        "files": (
            "backend/internal/repository/account_repo.go",
            "backend/internal/repository/account_repo*_test.go",
            "backend/internal/repository/auth_identity*.go",
            "backend/internal/repository/identity*.go",
            "backend/internal/repository/api_key*.go",
            "backend/internal/repository/user_repo*.go",
            "backend/go.mod",
        ),
        "commands_to_run": ("cd backend && go test ./internal/repository -run '^$'",),
        "include_frontend_commands": False,
        "restrict_relevant_files_to_spec": True,
    },
    {
        "title": "Remove retired generated-client repositories",
        "description": (
            "Remove or neutralize repository implementations, tests, and providers for Ent clients that no longer "
            "exist after Billing Core schema pruning."
        ),
        "completion_criteria": (
            "Proxy, channel monitor, error passthrough, TLS fingerprint, and user platform quota repositories no longer call removed generated Ent clients.",
            "Repository provider wiring no longer registers retired repository constructors.",
        ),
        "markers": (
            "repository",
            "proxy",
            "channel monitor",
            "error passthrough",
            "tls fingerprint",
            "user platform quota",
            "wire",
        ),
        "files": (
            "backend/internal/repository/proxy*.go",
            "backend/internal/repository/channel_monitor*.go",
            "backend/internal/repository/error_passthrough*.go",
            "backend/internal/repository/tls_fingerprint*.go",
            "backend/internal/repository/user_platform_quota*.go",
            "backend/internal/repository/wire.go",
            "backend/go.mod",
        ),
        "commands_to_run": ("cd backend && go test ./internal/repository -run '^$'",),
        "include_frontend_commands": False,
        "restrict_relevant_files_to_spec": True,
    },
    {
        "title": "Align remaining repository compile contracts",
        "description": (
            "Close residual repository compile errors after account and retired-client repository patches without "
            "taking over service or server cleanup."
        ),
        "completion_criteria": (
            "Remaining repository package compile errors are fixed or narrowed to explicit service/server follow-ups.",
            "Repository package lightweight compile verification passes or records focused residual blockers.",
        ),
        "markers": (
            "repository",
            "tests",
            "compile",
            "ent callers",
        ),
        "files": (
            "backend/internal/repository/*.go",
            "backend/internal/repository/*_test.go",
            "backend/go.mod",
        ),
        "commands_to_run": ("cd backend && go test ./internal/repository -run '^$'",),
        "include_frontend_commands": False,
        "restrict_relevant_files_to_spec": True,
    },
)


SCHEMA_BACKEND_CLEANUP_TIMEOUT_SPLIT_TASK_SPECS = (
    {
        "title": "Inventory legacy backend cleanup leftovers",
        "description": (
            "Checkpoint remaining legacy service, repository, handler, server, and test references before "
            "dispatching another editable cleanup worker."
        ),
        "completion_criteria": (
            "Remaining legacy backend cleanup targets are inventoried without editing repository files.",
            "Service/repository and handler/server follow-up targets are separated with concise evidence.",
        ),
        "markers": (
            "service/repository/test",
            "clean",
            "legacy",
            "service",
            "repository",
            "handler",
            "server",
            "test",
            "timeout",
        ),
        "files": (
            "backend/internal/service/**",
            "backend/internal/repository/**",
            "backend/internal/handler/**",
            "backend/internal/server/**",
            "backend/internal/config/**",
            "backend/cmd/server/**",
            "backend/go.mod",
        ),
        "commands_to_run": (),
        "include_frontend_commands": False,
        "restrict_relevant_files_to_spec": True,
    },
    {
        "title": "Clean service and repository legacy contracts",
        "description": (
            "Remove or rewrite residual legacy service and repository contracts without reopening handler or "
            "server route wiring."
        ),
        "completion_criteria": (
            "Service and repository packages no longer depend on retired token-relay/provider/channel contracts.",
            "Scoped service/repository compile verification passes or records handler/server follow-ups.",
        ),
        "markers": (
            "service",
            "repository",
            "service/repository/test",
            "paymentservice",
            "redeemservice",
            "usage billing",
            "walletservice",
        ),
        "files": (
            "backend/internal/service/**",
            "backend/internal/repository/**",
            "backend/internal/domain/**",
            "backend/internal/config/**",
            "backend/go.mod",
        ),
        "commands_to_run": ("cd backend && go test ./internal/service/... ./internal/repository/... -run '^$'",),
        "include_frontend_commands": False,
        "restrict_relevant_files_to_spec": True,
    },
    {
        "title": "Clean handler and server legacy routes",
        "description": (
            "Remove or rewrite residual legacy handler, route, command, and server wiring after service and "
            "repository cleanup."
        ),
        "completion_criteria": (
            "Handler, server, and command packages no longer expose retired token relay/provider/channel routes.",
            "Scoped handler/server compile verification passes or records residual backend cleanup follow-ups.",
        ),
        "markers": (
            "handler",
            "server",
            "route",
            "admin routes",
            "gateway",
            "provider",
            "channel",
            "clean unused service/repository/test code",
            "clean legacy backend services",
            "service/repository/test",
            "backend/internal/handler",
            "backend/internal/server",
            "backend/cmd/server",
        ),
        "files": (
            "backend/internal/handler/**",
            "backend/internal/server/**",
            "backend/internal/service/**",
            "backend/internal/config/**",
            "backend/cmd/server/**",
            "backend/go.mod",
        ),
        "commands_to_run": ("cd backend && go test ./internal/handler/... ./internal/server/... ./cmd/server/... -run '^$'",),
        "include_frontend_commands": False,
        "restrict_relevant_files_to_spec": True,
    },
    {
        "title": "Compile residual backend cleanup contracts",
        "description": (
            "Close residual backend/internal compile contract gaps after service/repository and handler/server "
            "cleanup, leaving full build and frontend verification to the stabilization task."
        ),
        "completion_criteria": (
            "Residual backend/internal compile errors are fixed or narrowed to explicit stabilization follow-ups.",
            "Backend internal packages pass lightweight compile verification without running the full test suite.",
        ),
        "markers": (
            "test",
            "go test",
            "backend/internal",
            "service/repository/test",
            "clean",
            "legacy",
        ),
        "files": (
            "backend/internal/service/**",
            "backend/internal/repository/**",
            "backend/internal/handler/**",
            "backend/internal/server/**",
            "backend/internal/config/**",
            "backend/internal/testutil/**",
            "backend/cmd/server/**",
            "backend/go.mod",
            "backend/go.sum",
        ),
        "commands_to_run": ("cd backend && go test ./internal/... -run '^$'",),
        "include_frontend_commands": False,
        "restrict_relevant_files_to_spec": True,
    },
)


SCHEMA_HANDLER_SERVER_CLEANUP_TIMEOUT_SPLIT_TASK_SPECS = (
    {
        "title": "Inventory handler and server cleanup leftovers",
        "description": (
            "Checkpoint remaining legacy handler, route, server, and command wiring references before another "
            "editable route-cleanup worker."
        ),
        "completion_criteria": (
            "Remaining handler/server cleanup targets are inventoried without editing repository files.",
            "Handler-only, server/cmd, and residual compile follow-up targets are separated with concise evidence.",
        ),
        "markers": (
            "handler",
            "server",
            "route",
            "backend/internal/handler",
            "backend/internal/server",
            "backend/cmd/server",
            "clean unused service/repository/test code",
            "service/repository/test",
            "clean legacy backend services",
            "timeout",
        ),
        "files": (
            "backend/internal/handler/**",
            "backend/internal/server/**",
            "backend/internal/config/**",
            "backend/cmd/server/**",
            "backend/go.mod",
        ),
        "commands_to_run": (),
        "include_frontend_commands": False,
        "restrict_relevant_files_to_spec": True,
    },
    {
        "title": "Clean handler legacy route contracts",
        "description": (
            "Remove or rewrite residual legacy handler routes, DTO mappings, and tests without taking over "
            "server registration or command wiring."
        ),
        "completion_criteria": (
            "Handler packages no longer expose retired token relay/provider/channel handler contracts.",
            "Scoped handler compile verification passes or records server/cmd follow-ups.",
        ),
        "markers": (
            "handler",
            "route",
            "gateway",
            "admin routes",
            "provider",
            "channel",
            "backend/internal/handler",
            "clean unused service/repository/test code",
            "service/repository/test",
            "clean legacy backend services",
        ),
        "files": (
            "backend/internal/handler/**",
            "backend/internal/service/**",
            "backend/internal/config/**",
            "backend/go.mod",
        ),
        "commands_to_run": ("cd backend && go test ./internal/handler/... -run '^$'",),
        "include_frontend_commands": False,
        "restrict_relevant_files_to_spec": True,
    },
    {
        "title": "Clean server route and command wiring",
        "description": (
            "Remove or rewrite residual legacy server route registrations, setup wiring, and command-server "
            "dependencies after handler cleanup."
        ),
        "completion_criteria": (
            "Server and command packages no longer register retired token relay/provider/channel routes.",
            "Scoped server/cmd compile verification passes or records residual handler/server follow-ups.",
        ),
        "markers": (
            "server",
            "route",
            "cmd",
            "command",
            "backend/internal/server",
            "backend/cmd/server",
            "clean unused service/repository/test code",
            "service/repository/test",
            "clean legacy backend services",
        ),
        "files": (
            "backend/internal/server/**",
            "backend/internal/config/**",
            "backend/cmd/server/**",
            "backend/go.mod",
        ),
        "commands_to_run": ("cd backend && go test ./internal/server/... ./cmd/server/... -run '^$'",),
        "include_frontend_commands": False,
        "restrict_relevant_files_to_spec": True,
    },
    {
        "title": "Compile handler and server cleanup contracts",
        "description": (
            "Close residual handler/server compile contract gaps after handler and server route cleanup, leaving "
            "broader backend/internal verification to the residual cleanup task."
        ),
        "completion_criteria": (
            "Residual handler/server compile errors are fixed or narrowed to explicit backend cleanup follow-ups.",
            "Handler, server, and command packages pass lightweight compile verification.",
        ),
        "markers": (
            "handler",
            "server",
            "route",
            "compile",
            "backend/internal/handler",
            "backend/internal/server",
            "backend/cmd/server",
            "clean unused service/repository/test code",
            "service/repository/test",
            "clean legacy backend services",
        ),
        "files": (
            "backend/internal/handler/**",
            "backend/internal/server/**",
            "backend/internal/service/**",
            "backend/internal/config/**",
            "backend/cmd/server/**",
            "backend/go.mod",
        ),
        "commands_to_run": ("cd backend && go test ./internal/handler/... ./internal/server/... ./cmd/server/... -run '^$'",),
        "include_frontend_commands": False,
        "restrict_relevant_files_to_spec": True,
    },
)


SCHEMA_FINAL_VERIFICATION_TIMEOUT_SPLIT_TASK_SPECS = (
    {
        "title": "Verify backend tests",
        "description": (
            "Run only the backend Go test suite after schema/build stabilization, preserving the final "
            "verification evidence without bundling frontend checks into the same worker."
        ),
        "completion_criteria": (
            "Backend Go tests pass or produce a focused backend verification blocker.",
        ),
        "command_group": "backend_tests",
        "default_commands": ("cd backend && go test ./...",),
        "files": (
            "backend/**",
            "backend/go.mod",
            "backend/go.sum",
            ".github/workflows/**",
        ),
    },
    {
        "title": "Verify frontend tests",
        "description": (
            "Run only the frontend test suite after backend tests, keeping frontend test failures separate from "
            "build and lint evidence."
        ),
        "completion_criteria": (
            "Frontend tests pass or produce a focused frontend verification blocker.",
        ),
        "command_group": "frontend_tests",
        "default_commands": ("pnpm --dir frontend test",),
        "files": (
            "frontend/**",
            "frontend/package.json",
            "frontend/pnpm-lock.yaml",
        ),
    },
    {
        "title": "Verify backend build",
        "description": (
            "Run only the backend Go build after test evidence is recorded, avoiding another wide final "
            "verification worker."
        ),
        "completion_criteria": (
            "Backend Go build passes or produces a focused backend build blocker.",
        ),
        "command_group": "backend_build",
        "default_commands": ("cd backend && go build ./...",),
        "files": (
            "backend/**",
            "backend/go.mod",
            "backend/go.sum",
            ".github/workflows/**",
        ),
    },
    {
        "title": "Verify frontend build and lint",
        "description": (
            "Run frontend build and lint as the final verification step, after backend and frontend test/build "
            "evidence has been isolated."
        ),
        "completion_criteria": (
            "Frontend build and lint pass or produce focused frontend delivery blockers.",
        ),
        "command_group": "frontend_build_lint",
        "default_commands": ("pnpm --dir frontend run build", "pnpm --dir frontend run lint"),
        "files": (
            "frontend/**",
            "frontend/package.json",
            "frontend/pnpm-lock.yaml",
            ".github/workflows/**",
        ),
    },
)


def frontend_large_refactor_task_specs(requirements: list[Requirement]) -> tuple[dict[str, object], ...]:
    if not focused_timeout_repair_for_task(requirements, "T007"):
        return FRONTEND_LARGE_REFACTOR_TASK_SPECS
    specs: list[dict[str, object]] = []
    for spec in FRONTEND_LARGE_REFACTOR_TASK_SPECS:
        if spec["title"] == "Sweep frontend product copy and i18n":
            specs.extend(FRONTEND_COPY_SWEEP_TIMEOUT_SPLIT_TASK_SPECS)
        else:
            specs.append(spec)
    return tuple(specs)


def frontend_remaining_closure_timeout_split_task_specs(requirements: list[Requirement]) -> tuple[dict[str, object], ...]:
    if not (
        focused_timeout_repair_for_task(requirements, "T009")
        or focused_timeout_repair_for_task(requirements, "T010")
    ):
        return ()
    specs: list[dict[str, object]] = []
    for spec in FRONTEND_REMAINING_CLOSURE_TIMEOUT_SPLIT_TASK_SPECS:
        if (
            spec["title"] == "Complete remaining frontend state and API closure"
            and focused_timeout_repair_for_task(requirements, "T010")
        ):
            specs.extend(FRONTEND_STATE_API_TIMEOUT_SPLIT_TASK_SPECS)
        else:
            specs.append(spec)
    return tuple(specs)


def focused_timeout_repair_for_task(requirements: list[Requirement], task_id: str) -> bool:
    text = "\n".join(requirement.text for requirement in requirements).lower()
    normalized_task_id = task_id.lower()
    return (
        focused_repair_primary_failed_task_ids_include(text, normalized_task_id)
        and any(marker in text for marker in ("timeout", "timed out", "worker timeout"))
        and any(marker in text for marker in ("split", "checkpoint"))
    )


COMPLETED_TASKS_TO_PRESERVE_PATTERN = re.compile(r"completed tasks to preserve:\s*([^.\n]+)", re.IGNORECASE)
PRIMARY_FAILED_TASK_IDS_PATTERN = re.compile(r"primary failed task ids:\s*([^\n]+)", re.IGNORECASE)
TASK_ID_PATTERN = re.compile(r"\bT\d{3}(?:-DEBUG-\d+)*\b", re.IGNORECASE)


def next_graph_task_id(nodes: list[TaskNode], reserved_task_ids: list[str] | set[str]) -> str:
    max_id = 0
    for task_id in [*(node.id for node in nodes), *reserved_task_ids]:
        match = re.match(r"^T(\d{3})$", str(task_id).upper())
        if match:
            max_id = max(max_id, int(match.group(1)))
    return f"T{max_id + 1:03d}"


def next_unreserved_task_id(task_index: int, reserved_task_ids: set[str]) -> tuple[str, int]:
    while f"T{task_index:03d}" in reserved_task_ids:
        task_index += 1
    return f"T{task_index:03d}", task_index + 1


def focused_repair_primary_failed_task_ids_include(text: str, normalized_task_id: str) -> bool:
    for match in PRIMARY_FAILED_TASK_IDS_PATTERN.finditer(text):
        task_ids = {item.lower() for item in TASK_ID_PATTERN.findall(match.group(1))}
        if normalized_task_id in task_ids:
            return True
    return f"primary failed task ids: {normalized_task_id}" in text


def focused_repair_completed_task_ids(requirements: list[Requirement]) -> list[str]:
    task_ids: list[str] = []
    for requirement in requirements:
        for match in COMPLETED_TASKS_TO_PRESERVE_PATTERN.finditer(requirement.text):
            task_ids.extend(item.upper() for item in TASK_ID_PATTERN.findall(match.group(1)))
    return dedupe(task_ids)


def mark_preserved_completed_tasks(nodes: list[TaskNode], task_ids: list[str]) -> None:
    preserved_ids = set(task_ids)
    if not preserved_ids:
        return
    for node in nodes:
        if node.id.upper() not in preserved_ids:
            continue
        node.status = "completed"
        node.evidence.append(
            {
                "type": "focused_repair_preserved_task",
                "summary": "Task preserved as completed from focused repair brief evidence.",
            }
        )


FINAL_VERIFICATION_GATE_TITLE_PREFIXES = (
    "audit final requirements",
    "run final simulation probes",
    "run final real repository checks",
    "review final handoff markers",
)


def final_verification_gate_rerun_required(context_bundle: ContextBundle) -> bool:
    chunks = [context_bundle.objective]
    for document in context_bundle.documents:
        chunks.extend([document.path, document.summary, *document.key_requirements])
    chunks.extend(requirement.text for requirement in context_bundle.requirements)
    text = "\n".join(chunks).lower()
    return (
        "final verification gate tasks must rerun after repair" in text
        or "gate tasks must rerun after repair" in text
        or "not be preserved as completed" in text and "final verification gate" in text
        or "final_audit_status is failed" in text
        or "simulation_test_status is failed" in text
        or "real_test_status is failed" in text
        or "final_audit_status=fail" in text
        or "simulation_test_status=fail" in text
        or "real_test_status=fail" in text
        or "final_audit_status: fail" in text
        or "simulation_test_status: fail" in text
        or "real_test_status: fail" in text
    )


def final_verification_preserved_task_ids_without_gate_tasks(
    nodes: list[TaskNode],
    preserved_task_ids: list[str],
) -> list[str]:
    gate_ids = {
        node.id.upper()
        for node in nodes
        if any(node.title.lower().startswith(prefix) for prefix in FINAL_VERIFICATION_GATE_TITLE_PREFIXES)
    }
    if not gate_ids:
        return preserved_task_ids
    return [task_id for task_id in preserved_task_ids if task_id.upper() not in gate_ids]


def final_verification_preserved_task_ids_with_matching_repair_title(
    context_bundle: ContextBundle,
    nodes: list[TaskNode],
    preserved_task_ids: list[str],
) -> list[str]:
    if not preserved_task_ids:
        return preserved_task_ids
    context_text = final_verification_context_text(context_bundle)
    nodes_by_id = {node.id.upper(): node for node in nodes}
    result: list[str] = []
    for task_id in preserved_task_ids:
        normalized_id = task_id.upper()
        node = nodes_by_id.get(normalized_id)
        if node is None:
            continue
        if node.type in {"architecture", "test", "review", "release"}:
            result.append(task_id)
            continue
        declared_titles = [
            match.group(1).strip().rstrip(".")
            for match in re.finditer(
                rf"(?:task\s+)?{re.escape(normalized_id.lower())}\s*[-:]\s*([^\n]+)",
                context_text,
            )
        ]
        if not declared_titles or any(node.title.lower() in declared for declared in declared_titles):
            result.append(task_id)
    return result


def final_verification_preserved_task_ids_without_new_target_file_tasks(
    context_bundle: ContextBundle,
    nodes: list[TaskNode],
    preserved_task_ids: list[str],
) -> list[str]:
    target_files = final_verification_new_target_files(context_bundle)
    if not target_files:
        return preserved_task_ids
    reopen_ids = {
        node.id.upper()
        for node in nodes
        if node.type not in {"architecture", "test", "review", "release"}
        and task_relevant_files_match_targets(node.relevant_files, target_files)
    }
    if not reopen_ids:
        return preserved_task_ids
    return [task_id for task_id in preserved_task_ids if task_id.upper() not in reopen_ids]


def final_verification_repair_specs_for_target_files(
    context_bundle: ContextBundle,
    repair_specs: list[dict[str, object]],
) -> list[dict[str, object]]:
    context_text = final_verification_active_repair_text(context_bundle) or final_verification_context_text(context_bundle)
    target_files = final_verification_new_target_files(context_bundle)
    if not target_files:
        return repair_specs
    matching_specs = [
        spec
        for spec in repair_specs
        if task_relevant_files_match_targets(
            [str(item) for item in spec.get("relevant_files", []) or []],
            target_files,
        )
    ]
    if not matching_specs:
        return repair_specs
    matching_titles = {str(spec.get("title", "")) for spec in matching_specs}
    if "Repair final frontend locale component boundary contracts" in matching_titles:
        matching_specs = [
            spec
            for spec in matching_specs
            if str(spec.get("title", ""))
            not in {
                "Repair final frontend API and i18n contracts",
                "Repair final frontend i18n locale contracts",
                "Repair final frontend routes views and tests",
            }
        ]
    if "Repair final frontend locale settings boundary contracts" in matching_titles:
        matching_specs = [
            spec
            for spec in matching_specs
            if str(spec.get("title", "")) != "Repair final frontend locale component boundary contracts"
        ]
    if (
        "Repair final backend runtime protocol identity contracts" in matching_titles
        or "Repair final backend startup contract wiring" in matching_titles
    ):
        matching_specs = [
            spec
            for spec in matching_specs
            if str(spec.get("title", "")) != "Repair final backend service handler server contracts"
        ]
    if "Repair final backend account repository predicate contracts" in matching_titles:
        matching_specs = [
            spec
            for spec in matching_specs
            if str(spec.get("title", ""))
            not in {
                "Repair final backend Ent schema contracts",
                "Repair final backend domain and repository contracts",
            }
        ]
    if "Repair final Veyra portal branding contracts" in matching_titles:
        matching_specs = [
            spec
            for spec in matching_specs
            if str(spec.get("title", ""))
            not in {
                "Repair final embedded runtime asset contracts",
                "Repair final backend Ent schema contracts",
                "Repair final backend service handler server contracts",
            }
        ]
    if "Repair final frontend admin API build lint contracts" in matching_titles:
        matching_specs = [
            spec
            for spec in matching_specs
            if str(spec.get("title", ""))
            not in {
                "Repair final frontend API and i18n contracts",
                "Repair final frontend routes views and tests",
                "Repair final delivery artifact contracts",
            }
        ]
    if "Repair final frontend dependency audit contracts" in matching_titles:
        matching_specs = [
            spec
            for spec in matching_specs
            if str(spec.get("title", ""))
            not in {
                "Repair final backend Ent schema contracts",
                "Repair final backend domain and repository contracts",
                "Repair final frontend API and i18n contracts",
                "Repair final frontend routes views and tests",
                "Repair final frontend admin ops audit surface contracts",
                "Repair final delivery artifact contracts",
            }
        ]
    if "Repair final frontend admin ops audit surface contracts" in matching_titles:
        matching_specs = [
            spec
            for spec in matching_specs
            if str(spec.get("title", ""))
            not in {
                "Repair final backend service handler server contracts",
                "Repair final frontend API and i18n contracts",
                "Repair final frontend routes views and tests",
                "Repair final delivery artifact contracts",
            }
        ]
    if (
        "Repair final platform RPM capacity surface contracts" in matching_titles
        or "Repair final user platform capacity API contracts" in matching_titles
        or "Repair final admin settings RPM capacity contracts" in matching_titles
        or "Repair final backend admin RPM capacity contracts" in matching_titles
        or "Repair final frontend admin RPM capacity settings contracts" in matching_titles
        or "Repair final backend admin RPM route settings contracts" in matching_titles
        or "Repair final backend admin user capacity handler contracts" in matching_titles
        or "Repair final RPM override route contract leftovers" in matching_titles
        or "Repair final admin dashboard access policy route contracts" in matching_titles
        or "Repair final admin user group quota surface contracts" in matching_titles
    ):
        matching_specs = [
            spec
            for spec in matching_specs
            if str(spec.get("title", ""))
            not in {
                "Repair final backend service handler server contracts",
                "Repair final frontend API and i18n contracts",
                "Repair final frontend routes views and tests",
                "Repair final frontend admin ops audit surface contracts",
                "Repair final frontend forbidden admin route surface contracts",
                "Repair final delivery artifact contracts",
            }
        ]
    if "Repair final frontend forbidden admin route surface contracts" in matching_titles:
        matching_specs = [
            spec
            for spec in matching_specs
            if str(spec.get("title", ""))
            not in {
                "Repair final backend service handler server contracts",
                "Repair final frontend API and i18n contracts",
                "Repair final frontend routes views and tests",
                "Repair final frontend admin ops audit surface contracts",
                "Repair final delivery artifact contracts",
            }
        ]
    if "Repair final frontend route/sidebar contract leftovers" in matching_titles:
        matching_specs = [
            spec
            for spec in matching_specs
            if str(spec.get("title", ""))
            not in {
                "Repair final backend service handler server contracts",
                "Repair final frontend API and i18n contracts",
                "Repair final frontend routes views and tests",
                "Repair final frontend forbidden admin route surface contracts",
                "Repair final delivery artifact contracts",
            }
        ]
    if "Repair final backend production identity string leftovers" in matching_titles:
        matching_specs = [
            spec
            for spec in matching_specs
            if str(spec.get("title", ""))
            not in {
                "Repair final backend service handler server contracts",
                "Repair final backend runtime protocol identity contracts",
                "Repair final frontend routes views and tests",
                "Repair final frontend route/sidebar contract leftovers",
                "Repair final delivery artifact contracts",
            }
        ]
    if "Repair final embedded runtime asset contracts" in matching_titles and final_verification_embedded_targets_resolved(
        context_bundle
    ):
        matching_specs = [
            spec
            for spec in matching_specs
            if str(spec.get("title", "")) != "Repair final embedded runtime asset contracts"
        ]
    if should_split_final_admin_settings_legacy_timeout(context_text):
        split_titles = {
            "Repair final backend admin settings legacy contracts",
            "Repair final frontend admin settings legacy contracts",
        }
        matching_specs = append_repair_specs_by_title(
            matching_specs,
            repair_specs,
            split_titles,
        )
        matching_specs = [spec for spec in matching_specs if str(spec.get("title", "")) in split_titles]
    if should_repair_final_backend_old_domain_surface(context_text):
        matching_specs = append_repair_specs_by_title(
            matching_specs,
            repair_specs,
            {
                "Repair final backend migration contracts",
                "Repair final backend service handler server contracts",
            },
        )
    if should_repair_final_frontend_locale_settings_surfaces(context_text):
        matching_specs = append_repair_specs_by_title(
            matching_specs,
            repair_specs,
            {"Repair final frontend locale settings boundary contracts"},
        )
    if should_repair_final_frontend_dependency_audit(context_text):
        matching_specs = append_repair_specs_by_title(
            matching_specs,
            repair_specs,
            {"Repair final frontend dependency audit contracts"},
        )
    if should_repair_final_frontend_route_sidebar_contract(context_text):
        matching_specs = append_repair_specs_by_title(
            matching_specs,
            repair_specs,
            {"Repair final frontend route/sidebar contract leftovers"},
        )
    if should_repair_final_rpm_override_route_contract_leftovers(context_text):
        matching_specs = append_repair_specs_by_title(
            matching_specs,
            repair_specs,
            {"Repair final RPM override route contract leftovers"},
        )
    frontend_user_quota_typecheck_import = should_repair_final_frontend_user_quota_typecheck_import(context_text)
    if frontend_user_quota_typecheck_import:
        matching_specs = append_repair_specs_by_title(
            matching_specs,
            repair_specs,
            {"Repair final frontend user quota typecheck import"},
        )
    settings_api_contract_test = should_repair_final_settings_api_contract_test(context_text)
    if settings_api_contract_test:
        matching_specs = append_repair_specs_by_title(
            matching_specs,
            repair_specs,
            {"Repair final backend settings API contract test"},
        )
    settings_advanced_scheduler_contract = should_repair_final_settings_advanced_scheduler_contract(context_text)
    if settings_advanced_scheduler_contract:
        matching_specs = append_repair_specs_by_title(
            matching_specs,
            repair_specs,
            {"Repair final backend settings advanced scheduler contract"},
        )
    if (
        not frontend_user_quota_typecheck_import
        and not settings_api_contract_test
        and not settings_advanced_scheduler_contract
        and should_repair_final_simulation_suite_failures(context_text)
    ):
        simulation_titles = {
            "Repair final frontend UsageTable simulation contracts",
            "Repair final backend admin simulation contracts",
            "Repair final backend DTO usage simulation contracts",
        }
        matching_specs = append_repair_specs_by_title(
            matching_specs,
            repair_specs,
            simulation_titles,
        )
    elif should_repair_final_platform_rpm_capacity_surface(context_text):
        if should_split_final_backend_admin_rpm_capacity_timeout(context_text):
            capacity_titles = {
                "Repair final backend admin RPM route settings contracts",
                "Repair final backend admin user capacity handler contracts",
            }
        elif should_split_final_admin_settings_rpm_capacity_timeout(context_text):
            capacity_titles = {
                "Repair final backend admin RPM capacity contracts",
                "Repair final frontend admin RPM capacity settings contracts",
            }
        elif should_split_final_platform_rpm_capacity_timeout(context_text):
            capacity_titles = {
                "Repair final user platform capacity API contracts",
                "Repair final admin settings RPM capacity contracts",
            }
        else:
            capacity_titles = {"Repair final platform RPM capacity surface contracts"}
        matching_specs = append_repair_specs_by_title(
            matching_specs,
            repair_specs,
            capacity_titles,
        )
    if should_repair_final_admin_dashboard_access_policy_congruence(context_text):
        matching_specs = append_repair_specs_by_title(
            matching_specs,
            repair_specs,
            {"Repair final admin dashboard access policy route contracts"},
        )
    if should_repair_final_admin_user_group_quota_surface(context_text):
        matching_specs = append_repair_specs_by_title(
            matching_specs,
            repair_specs,
            {"Repair final admin user group quota surface contracts"},
        )
    if should_repair_final_backend_production_identity_strings(context_text):
        matching_specs = append_repair_specs_by_title(
            matching_specs,
            repair_specs,
            {"Repair final backend production identity string leftovers"},
        )
    if should_repair_final_source_boundary_sweep(context_text):
        sweep_titles = (
            {
                "Repair final backend migration source-boundary leftovers",
                "Repair final backend production source-boundary leftovers",
                "Repair final frontend retired API type source-boundary leftovers",
                "Repair final frontend retired composable store source-boundary leftovers",
                "Repair final frontend retired view component source-boundary leftovers",
            }
            if should_split_final_frontend_retired_source_boundary_timeout(context_text)
            else {
                "Repair final backend migration source-boundary leftovers",
                "Repair final backend production source-boundary leftovers",
                "Repair final frontend retired source-boundary leftovers",
            }
        )
        matching_specs = append_repair_specs_by_title(
            matching_specs,
            repair_specs,
            sweep_titles,
        )
        matching_specs = [spec for spec in matching_specs if str(spec.get("title", "")) in sweep_titles]
    if should_repair_final_remaining_source_boundary_after_split(context_text):
        remaining_titles = (
            {
                "Repair final backend account OAuth service quarantine exact files",
                "Repair final backend channel monitor service quarantine exact files",
                "Repair final backend proxy upstream service quarantine exact files",
                "Repair final backend ops settings service quarantine exact files",
                "Repair final backend config runtime quarantine leftovers",
                "Repair final frontend locale settings boundary contracts",
                "Repair final frontend API settings typecheck leftovers",
                "Repair final frontend view component typecheck leftovers",
            }
            if should_split_final_backend_provider_proxy_ops_service_quarantine_timeout(context_text)
            else {
                "Repair final backend repository domain quarantine exact files",
                "Repair final backend gateway OpenAI service quarantine exact files",
                "Repair final backend provider proxy ops service quarantine exact files",
                "Repair final backend config runtime quarantine leftovers",
                "Repair final frontend locale settings boundary contracts",
                "Repair final frontend API settings typecheck leftovers",
                "Repair final frontend view component typecheck leftovers",
            }
            if should_split_final_backend_service_repository_quarantine_timeout(context_text)
            else {
                "Repair final backend admin handler quarantine exact files",
                "Repair final backend gateway protocol handler exact files",
                "Repair final backend server middleware quarantine exact files",
                "Repair final backend service repository quarantine leftovers",
                "Repair final backend config runtime quarantine leftovers",
                "Repair final frontend locale settings boundary contracts",
                "Repair final frontend API settings typecheck leftovers",
                "Repair final frontend view component typecheck leftovers",
            }
            if should_split_final_backend_handler_server_quarantine_timeout(context_text)
            else {
                "Repair final backend handler server quarantine leftovers",
                "Repair final backend service repository quarantine leftovers",
                "Repair final backend config runtime quarantine leftovers",
                "Repair final frontend locale settings boundary contracts",
                "Repair final frontend API settings typecheck leftovers",
                "Repair final frontend view component typecheck leftovers",
            }
            if should_split_final_backend_legacy_quarantine_timeout(context_text)
            else {
                "Repair final backend legacy production quarantine leftovers",
                "Repair final frontend locale settings boundary contracts",
                "Repair final frontend API settings typecheck leftovers",
                "Repair final frontend view component typecheck leftovers",
            }
        )
        matching_specs = append_repair_specs_by_title(
            matching_specs,
            repair_specs,
            remaining_titles,
        )
        matching_specs = [spec for spec in matching_specs if str(spec.get("title", "")) in remaining_titles]
    if should_repair_final_admin_settings_legacy_surface(context_text):
        matching_specs = append_repair_specs_by_title(
            matching_specs,
            repair_specs,
            {"Repair final admin settings legacy surface contracts"},
        )
    if should_repair_final_frontend_forbidden_admin_surface(context_text):
        matching_specs = append_repair_specs_by_title(
            matching_specs,
            repair_specs,
            {"Repair final frontend forbidden admin route surface contracts"},
        )
    return sort_repair_specs_by_original_order(matching_specs, repair_specs)


def final_verification_context_text(context_bundle: ContextBundle) -> str:
    chunks = [context_bundle.objective]
    for document in context_bundle.documents:
        chunks.extend([document.path, document.summary, *document.key_requirements])
    chunks.extend(requirement.text for requirement in context_bundle.requirements)
    return "\n".join(chunks).lower()


def append_repair_specs_by_title(
    selected_specs: list[dict[str, object]],
    all_specs: list[dict[str, object]],
    titles: set[str],
) -> list[dict[str, object]]:
    selected_titles = {str(spec.get("title", "")) for spec in selected_specs}
    result = list(selected_specs)
    for spec in all_specs:
        title = str(spec.get("title", ""))
        if title in titles and title not in selected_titles:
            result.append(spec)
            selected_titles.add(title)
    return result


def sort_repair_specs_by_original_order(
    selected_specs: list[dict[str, object]],
    all_specs: list[dict[str, object]],
) -> list[dict[str, object]]:
    order = {str(spec.get("title", "")): index for index, spec in enumerate(all_specs)}
    return sorted(selected_specs, key=lambda spec: order.get(str(spec.get("title", "")), len(order)))


def final_verification_embedded_targets_resolved(context_bundle: ContextBundle) -> bool:
    chunks = [context_bundle.objective]
    for document in context_bundle.documents:
        chunks.extend([document.path, document.summary, *document.key_requirements])
    chunks.extend(requirement.text for requirement in context_bundle.requirements)
    text = "\n".join(chunks).lower()
    return any(
        marker in text
        for marker in (
            "previous embedded runtime blocker appears repaired",
            "previous embedded portal_dist/app.js blocker now pass",
            "stale route-key issue is resolved",
            "0 hits for sub2api-console",
        )
    )


def final_verification_new_target_files(context_bundle: ContextBundle) -> list[str]:
    chunks = [context_bundle.objective]
    for document in context_bundle.documents:
        chunks.extend([document.path, document.summary, *document.key_requirements])
    chunks.extend(requirement.text for requirement in context_bundle.requirements)
    files: list[str] = []
    for line in "\n".join(chunks).splitlines():
        if "target files:" not in line.lower():
            continue
        _, value = line.split(":", 1)
        for item in re.split(r"[,;]", value):
            normalized = normalize_repo_path(item)
            if (
                normalized
                and "/" in normalized
                and ":" not in normalized
                and not final_verification_non_reopen_target_file(normalized)
            ):
                files.append(normalized)
    return dedupe(files)


def final_verification_non_reopen_target_file(path: str) -> bool:
    normalized = normalize_repo_path(path).lower()
    if not normalized:
        return True
    basename = normalized.rsplit("/", 1)[-1]
    if basename in {
        "package.json",
        "pnpm-lock.yaml",
        "package-lock.json",
        "yarn.lock",
        "go.mod",
        "go.sum",
        "phase_record.json",
    }:
        return True
    if basename.startswith("attempt_") and basename.endswith(".json"):
        return True
    return normalized.startswith(
        (
            "final_verification_",
            ".alchemy/",
            "docs/billing_core_dev_plan.md",
        )
    )


def task_relevant_files_match_targets(relevant_files: list[str], target_files: list[str]) -> bool:
    return any(
        path_pattern_matches_target(relevant_file, target_file)
        for relevant_file in relevant_files
        for target_file in target_files
    )


def path_pattern_matches_target(pattern: str, target: str) -> bool:
    normalized_pattern = normalize_repo_path(pattern)
    normalized_target = normalize_repo_path(target)
    if not normalized_pattern or not normalized_target:
        return False
    if normalized_pattern.endswith("/**"):
        prefix = normalized_pattern[:-3].rstrip("/")
        return normalized_target == prefix or normalized_target.startswith(prefix + "/")
    if "*" in normalized_pattern:
        regex = re.escape(normalized_pattern).replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
        return re.fullmatch(regex, normalized_target) is not None
    return normalized_pattern == normalized_target


def enforce_reopened_repair_order(nodes: list[TaskNode], task_ids: list[str]) -> None:
    nodes_by_id = {node.id: node for node in nodes}
    open_predecessors: list[str] = []
    for task_id in task_ids:
        node = nodes_by_id.get(task_id)
        if not node:
            continue
        already_waits_for_open_repair = any(predecessor_id in node.dependencies for predecessor_id in open_predecessors)
        if not already_waits_for_open_repair:
            for predecessor_id in open_predecessors:
                if predecessor_id not in node.dependencies:
                    node.dependencies.append(predecessor_id)
        if node.status not in {"completed", "skipped"}:
            open_predecessors.append(task_id)


def should_decompose_large_refactor_frontend_phase(requirements: list[Requirement], *, assigned_agent: str) -> bool:
    if assigned_agent != "frontend" or not is_large_refactor_frontend_phase(requirements):
        return False
    matching_specs = 0
    for spec in frontend_large_refactor_task_specs(requirements):
        if any(requirement_matches_markers(requirement, spec["markers"]) for requirement in requirements):
            matching_specs += 1
    return matching_specs >= 3


def should_decompose_frontend_verification_repair(requirements: list[Requirement], *, assigned_agent: str) -> bool:
    return assigned_agent == "frontend" and bool(focused_verification_repair_requirements(requirements))


def should_decompose_large_refactor_schema_build_phase(requirements: list[Requirement], *, assigned_agent: str) -> bool:
    if assigned_agent != "backend":
        return False
    return is_large_refactor_schema_build_phase(requirements)


def is_large_refactor_schema_build_phase(requirements: list[Requirement]) -> bool:
    text = "\n".join(requirement.text for requirement in requirements).lower()
    marker_score = sum(1 for group in SCHEMA_BUILD_PHASE_MARKER_GROUPS if any(marker in text for marker in group))
    if marker_score < 3:
        return False
    return any(marker in text for marker in ("ent", "schema", "fresh db", "migration", "migrate"))


def large_refactor_schema_build_nodes(
    requirements: list[Requirement],
    test_commands: list[str],
    *,
    package_files: list[str],
    scope_controls: dict[str, list[str]] | None,
    base_relevant_files: list[str],
) -> tuple[list[TaskNode], dict[str, str]]:
    nodes: list[TaskNode] = []
    requirement_task_ids: dict[str, str] = {}
    task_index = 2
    matched_requirement_ids: set[str] = set()
    phase_requirements = [
        requirement for requirement in requirements if not is_focused_repair_metadata_requirement(requirement)
    ]

    for spec in schema_build_large_refactor_task_specs(requirements):
        matched_requirements = [
            requirement
            for requirement in phase_requirements
            if requirement_matches_markers(requirement, spec["markers"])
        ]
        if not matched_requirements:
            continue
        task_id = f"T{task_index:03d}"
        task_index += 1
        matched_requirement_ids.update(requirement.id for requirement in matched_requirements)
        for requirement in matched_requirements:
            requirement_task_ids.setdefault(requirement.id, task_id)
        nodes.append(
            TaskNode(
                id=task_id,
                title=str(spec["title"]),
                description=frontend_large_refactor_description(str(spec["description"]), matched_requirements),
                type="backend",
                assigned_agent="backend",
                dependencies=["T001"],
                completion_criteria=list(spec.get("completion_criteria", ()))
                or dedupe([criterion for item in matched_requirements for criterion in item.acceptance_criteria])
                or ["The targeted schema/build workflow is closed against the phase requirements."],
                relevant_files=schema_build_refactor_relevant_files(
                    list(spec["files"]),
                    [] if bool(spec.get("restrict_relevant_files_to_spec", False)) else matched_requirements,
                    package_files=package_files,
                    scope_controls=scope_controls,
                    fallback=base_relevant_files,
                ),
                commands_to_run=list(spec["commands_to_run"])
                if "commands_to_run" in spec
                else schema_build_refactor_commands(
                    test_commands,
                    package_files=package_files,
                    include_frontend=bool(spec["include_frontend_commands"]),
                ),
                priority=max(priority_for_requirement(item) for item in matched_requirements),
                boundary_mode="large_refactor",
            )
        )

    if not nodes:
        return nodes, requirement_task_ids

    remaining_requirements = [
        requirement for requirement in phase_requirements if requirement.id not in matched_requirement_ids
    ]
    if remaining_requirements:
        residual_node = nodes[-1]
        residual_node.description = frontend_large_refactor_description(
            (
                f"{residual_node.description} Preserve remaining phase-level CRM constraints while closing "
                "schema/build verification."
            ),
            remaining_requirements,
        )
        residual_node.completion_criteria = dedupe(
            [
                *residual_node.completion_criteria,
                *[criterion for item in remaining_requirements for criterion in item.acceptance_criteria],
            ]
        )
        residual_node.relevant_files = schema_build_refactor_relevant_files(
            residual_node.relevant_files,
            remaining_requirements,
            package_files=package_files,
            scope_controls=scope_controls,
            fallback=base_relevant_files,
        )
        for requirement in remaining_requirements:
            requirement_task_ids.setdefault(requirement.id, residual_node.id)

    return nodes, requirement_task_ids


def schema_build_large_refactor_task_specs(requirements: list[Requirement]) -> tuple[dict[str, object], ...]:
    specs: list[dict[str, object]] = []
    for spec in SCHEMA_BUILD_LARGE_REFACTOR_TASK_SPECS:
        if (
            spec["title"] == "Prune legacy Ent schemas and table contracts"
            and focused_schema_prune_timeout_repair(requirements)
        ):
            for split_spec in SCHEMA_PRUNE_TIMEOUT_SPLIT_TASK_SPECS:
                if (
                    split_spec["title"] == "Align Ent migration and server table contracts"
                    and focused_schema_migration_contract_timeout_repair(requirements)
                ):
                    specs.extend(SCHEMA_MIGRATION_CONTRACT_CHECKPOINT_TASK_SPECS)
                elif (
                    split_spec["title"] == "Align Ent migration and server table contracts"
                    and focused_schema_migration_timeout_repair(requirements)
                ):
                    specs.extend(SCHEMA_MIGRATION_TIMEOUT_SPLIT_TASK_SPECS)
                else:
                    specs.append(split_spec)
        elif (
            spec["title"] == "Regenerate Ent clients and migration artifacts"
            and (
                focused_schema_ent_regeneration_timeout_repair(requirements)
                or focused_schema_ent_caller_alignment_timeout_repair(requirements)
            )
        ):
            specs.extend(schema_ent_regeneration_timeout_split_task_specs(requirements))
        elif (
            spec["title"] == "Clean legacy backend services repositories and tests"
            and focused_schema_backend_cleanup_timeout_repair(requirements)
        ):
            specs.extend(schema_backend_cleanup_timeout_split_task_specs(requirements))
        else:
            specs.append(spec)
    return tuple(specs)


def schema_backend_cleanup_timeout_split_task_specs(requirements: list[Requirement]) -> tuple[dict[str, object], ...]:
    specs: list[dict[str, object]] = []
    split_handler_server_cleanup = focused_schema_handler_server_cleanup_timeout_repair(requirements)
    for spec in SCHEMA_BACKEND_CLEANUP_TIMEOUT_SPLIT_TASK_SPECS:
        if spec["title"] == "Clean handler and server legacy routes" and split_handler_server_cleanup:
            specs.extend(SCHEMA_HANDLER_SERVER_CLEANUP_TIMEOUT_SPLIT_TASK_SPECS)
        else:
            specs.append(spec)
    return tuple(specs)


def schema_ent_regeneration_timeout_split_task_specs(requirements: list[Requirement]) -> tuple[dict[str, object], ...]:
    specs: list[dict[str, object]] = []
    split_caller_alignment = focused_schema_ent_caller_alignment_timeout_repair(requirements)
    for spec in SCHEMA_ENT_REGENERATION_TIMEOUT_SPLIT_TASK_SPECS:
        if spec["title"] == "Align repository callers after Ent regeneration" and split_caller_alignment:
            specs.extend(schema_ent_caller_alignment_timeout_split_task_specs(requirements))
        else:
            specs.append(spec)
    return tuple(specs)


def schema_ent_caller_alignment_timeout_split_task_specs(requirements: list[Requirement]) -> tuple[dict[str, object], ...]:
    specs: list[dict[str, object]] = []
    split_repository_alignment = focused_schema_repository_ent_caller_timeout_repair(requirements)
    for spec in SCHEMA_ENT_CALLER_ALIGNMENT_TIMEOUT_SPLIT_TASK_SPECS:
        if spec["title"] == "Align repository Ent callers" and split_repository_alignment:
            specs.extend(SCHEMA_REPOSITORY_CALLER_TIMEOUT_SPLIT_TASK_SPECS)
        else:
            specs.append(spec)
    return tuple(specs)


def focused_schema_prune_timeout_repair(requirements: list[Requirement]) -> bool:
    return focused_timeout_repair_for_task(requirements, "T002")


def focused_schema_migration_timeout_repair(requirements: list[Requirement]) -> bool:
    return focused_timeout_repair_for_task(requirements, "T003")


def focused_schema_migration_contract_timeout_repair(requirements: list[Requirement]) -> bool:
    return focused_timeout_repair_for_task(requirements, "T003")


def focused_schema_ent_regeneration_timeout_repair(requirements: list[Requirement]) -> bool:
    return focused_timeout_repair_for_task(requirements, "T006")


def focused_schema_ent_caller_alignment_timeout_repair(requirements: list[Requirement]) -> bool:
    return focused_timeout_repair_for_task(requirements, "T008")


def focused_schema_repository_ent_caller_timeout_repair(requirements: list[Requirement]) -> bool:
    return focused_timeout_repair_for_task(requirements, "T009")


def focused_schema_backend_cleanup_timeout_repair(requirements: list[Requirement]) -> bool:
    text = "\n".join(requirement.text for requirement in requirements).lower()
    if focused_timeout_repair_for_task(requirements, "T014"):
        return True
    cleanup_context = any(
        marker in text
        for marker in (
            "clean legacy backend",
            "legacy backend",
            "service/repository/test",
            "cleanup",
            "unused service/repository/test",
        )
    )
    if not cleanup_context:
        return False
    return any(focused_timeout_repair_for_task(requirements, task_id) for task_id in ("T015", "T016", "T017"))


def focused_schema_handler_server_cleanup_timeout_repair(requirements: list[Requirement]) -> bool:
    text = "\n".join(requirement.text for requirement in requirements).lower()
    if focused_timeout_repair_for_task(requirements, "T016"):
        return True
    handler_server_context = any(
        marker in text
        for marker in (
            "clean handler and server",
            "handler and server legacy",
            "backend/internal/handler",
            "backend/internal/server",
            "backend/cmd/server",
        )
    )
    if not handler_server_context:
        return False
    return any(focused_timeout_repair_for_task(requirements, task_id) for task_id in ("T017", "T018", "T019"))


def should_split_schema_final_verification_timeout(requirements: list[Requirement], verify_id: str) -> bool:
    text = "\n".join(requirement.text for requirement in requirements).lower()
    if not is_large_refactor_schema_build_phase(requirements):
        return False
    if not focused_timeout_repair_for_task(requirements, verify_id):
        return False
    split_titles = tuple(str(spec["title"]).lower() for spec in SCHEMA_FINAL_VERIFICATION_TIMEOUT_SPLIT_TASK_SPECS)
    return any(
        marker in text
        for marker in (
            "verify implementation against project checks",
            "verification issue",
            "schema/build verification",
            "frontend build/typecheck",
            "required tests are failing",
            *split_titles,
        )
    )


def schema_final_verification_timeout_split_nodes(
    *,
    next_task_id: str,
    dependencies: list[str],
    verification_commands: list[str],
    scope_controls: dict[str, list[str]] | None,
    fallback_files: list[str],
    existing_nodes: list[TaskNode],
) -> list[TaskNode]:
    nodes: list[TaskNode] = []
    previous_dependencies = list(dependencies)
    command_groups = schema_final_verification_command_groups(verification_commands)
    start_match = re.match(r"^T(\d{3})$", next_task_id.upper())
    start_number = int(start_match.group(1)) if start_match else 0
    for offset, spec in enumerate(SCHEMA_FINAL_VERIFICATION_TIMEOUT_SPLIT_TASK_SPECS):
        task_id = f"T{start_number + offset:03d}" if start_number else next_graph_task_id([*existing_nodes, *nodes], [])
        command_group = str(spec["command_group"])
        commands = command_groups.get(command_group) or list(spec["default_commands"])
        nodes.append(
            TaskNode(
                id=task_id,
                title=str(spec["title"]),
                description=str(spec["description"]),
                type="test",
                assigned_agent="test",
                dependencies=previous_dependencies,
                completion_criteria=list(spec["completion_criteria"]),
                commands_to_run=list(commands),
                relevant_files=scoped_files(list(spec["files"]), scope_controls, fallback=fallback_files),
                priority=85 - offset,
            )
        )
        previous_dependencies = [task_id]
    return nodes


def schema_final_verification_command_groups(commands: list[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {
        "backend_tests": [],
        "frontend_tests": [],
        "backend_build": [],
        "frontend_build_lint": [],
    }
    for command in dedupe(commands):
        normalized = command.replace("\\", "/").lower()
        if "install" in normalized:
            continue
        if "go test" in normalized:
            groups["backend_tests"].append(command)
            continue
        if "go build" in normalized:
            groups["backend_build"].append(command)
            continue
        if is_frontend_verification_command(normalized) and ("test" in normalized or "vitest" in normalized):
            groups["frontend_tests"].append(command)
            continue
        if is_frontend_verification_command(normalized) and ("build" in normalized or "lint" in normalized):
            groups["frontend_build_lint"].append(command)
    return {key: dedupe(value) for key, value in groups.items() if value}


def is_frontend_verification_command(normalized_command: str) -> bool:
    return "frontend" in normalized_command or any(
        marker in normalized_command for marker in ("pnpm ", "npm ", "yarn ", "bun ", "vitest", "vite")
    )


def schema_build_refactor_relevant_files(
    base_files: list[str],
    requirements: list[Requirement],
    *,
    package_files: list[str],
    scope_controls: dict[str, list[str]] | None,
    fallback: list[str],
) -> list[str]:
    requirement_files = [
        normalize_repo_path(file)
        for requirement in requirements
        for file in requirement.related_files
        if schema_build_requirement_file(file)
    ]
    package_hints = schema_build_package_files(package_files, base_files)
    files = dedupe([*base_files, *requirement_files, *package_hints])
    narrowed = [file for file in files if normalize_repo_path(file) not in {"backend/**", "frontend/**"}]
    return scoped_files(narrowed or files, scope_controls, fallback=fallback)


def schema_build_requirement_file(path: str) -> str:
    normalized = normalize_repo_path(path)
    if normalized.startswith("backend/"):
        return normalized
    if normalized in {"Makefile", "Dockerfile", "README.md"}:
        return normalized
    if normalized.startswith(".github/workflows/"):
        return normalized
    if normalized.startswith("frontend/") and Path(normalized).name in {
        "package.json",
        "pnpm-lock.yaml",
        "package-lock.json",
        "yarn.lock",
    }:
        return normalized
    return ""


def schema_build_package_files(package_files: list[str], base_files: list[str]) -> list[str]:
    normalized_base = {normalize_repo_path(file) for file in base_files}
    selected: list[str] = []
    for file in package_files:
        normalized = normalize_repo_path(file)
        if normalized.startswith("backend/"):
            selected.append(normalized)
        if normalized.startswith("frontend/") and any(item.startswith("frontend/") for item in normalized_base):
            selected.append(normalized)
    return dedupe(selected)


def schema_build_refactor_commands(
    test_commands: list[str],
    *,
    package_files: list[str],
    include_frontend: bool,
) -> list[str]:
    backend_commands = [
        command
        for command in dedupe(test_commands)
        if any(marker in command.lower() for marker in ("go test", "go build", "backend"))
    ]
    if not include_frontend:
        return backend_commands or dedupe(test_commands)
    frontend_commands = frontend_large_refactor_commands(test_commands, package_files=package_files)
    return dedupe([*(backend_commands or []), *frontend_commands]) or dedupe(test_commands)


def large_refactor_frontend_nodes(
    requirements: list[Requirement],
    test_commands: list[str],
    *,
    package_files: list[str],
    scope_controls: dict[str, list[str]] | None,
    base_relevant_files: list[str],
) -> tuple[list[TaskNode], dict[str, str]]:
    nodes: list[TaskNode] = []
    requirement_task_ids: dict[str, str] = {}
    frontend_commands = frontend_large_refactor_commands(test_commands, package_files=package_files)
    task_index = 2
    preserved_task_ids = set(focused_repair_completed_task_ids(requirements))
    matched_requirement_ids: set[str] = set()
    for spec in frontend_large_refactor_task_specs(requirements):
        matched_requirements = [
            requirement
            for requirement in requirements
            if requirement_matches_markers(requirement, spec["markers"])
        ]
        if not matched_requirements:
            continue
        task_id = f"T{task_index:03d}"
        task_index += 1
        matched_requirement_ids.update(requirement.id for requirement in matched_requirements)
        for requirement in matched_requirements:
            requirement_task_ids.setdefault(requirement.id, task_id)
        nodes.append(
            TaskNode(
                id=task_id,
                title=str(spec["title"]),
                description=frontend_large_refactor_description(str(spec["description"]), matched_requirements),
                type="frontend",
                assigned_agent="frontend",
                dependencies=["T001"],
                completion_criteria=dedupe([criterion for item in matched_requirements for criterion in item.acceptance_criteria])
                or ["The targeted frontend workflow is closed against the phase requirements."],
                relevant_files=frontend_large_refactor_relevant_files(
                    list(spec["files"]),
                    matched_requirements,
                    scope_controls=scope_controls,
                    fallback=base_relevant_files,
                ),
                commands_to_run=frontend_commands,
                priority=max(priority_for_requirement(item) for item in matched_requirements),
                boundary_mode="large_refactor",
            )
        )

    verification_repair_requirements = focused_verification_repair_requirements(requirements)
    if verification_repair_requirements:
        task_id, task_index = next_unreserved_task_id(task_index, preserved_task_ids)
        matched_requirement_ids.update(requirement.id for requirement in verification_repair_requirements)
        for requirement in verification_repair_requirements:
            requirement_task_ids.setdefault(requirement.id, task_id)
        nodes.append(
            TaskNode(
                id=task_id,
                title="Repair failing frontend verification assets",
                description=frontend_large_refactor_description(
                    "Repair the concrete frontend build or test evidence from the latest verification gate.",
                    verification_repair_requirements,
                ),
                type="frontend",
                assigned_agent="frontend",
                dependencies=["T001"],
                completion_criteria=dedupe(
                    [criterion for item in verification_repair_requirements for criterion in item.acceptance_criteria]
                )
                or ["The failing frontend verification command passes after the targeted repair."],
                relevant_files=frontend_verification_repair_relevant_files(
                    verification_repair_requirements,
                    scope_controls=scope_controls,
                    fallback=base_relevant_files,
                ),
                commands_to_run=frontend_commands,
                priority=max(priority_for_requirement(item) for item in verification_repair_requirements),
                boundary_mode="large_refactor",
            )
        )

    matched_requirement_ids.update(requirement.id for requirement in focused_repair_metadata_requirements(requirements))
    remaining_requirements = [requirement for requirement in requirements if requirement.id not in matched_requirement_ids]
    if should_suppress_remaining_frontend_fallback_after_verification_repair(
        verification_repair_requirements,
        preserved_task_ids,
    ):
        if remaining_requirements:
            task_id, task_index = next_unreserved_task_id(
                task_index,
                {*preserved_task_ids, *(node.id for node in nodes)},
            )
            for requirement in remaining_requirements:
                requirement_task_ids.setdefault(requirement.id, task_id)
            nodes.append(
                preserved_frontend_coverage_node(
                    task_id,
                    remaining_requirements,
                    scope_controls=scope_controls,
                    fallback=base_relevant_files,
                )
            )
        remaining_requirements = []
    if remaining_requirements:
        split_specs = frontend_remaining_closure_timeout_split_task_specs(requirements)
        if split_specs:
            for spec in split_specs:
                task_id = f"T{task_index:03d}"
                task_index += 1
                for requirement in remaining_requirements:
                    requirement_task_ids.setdefault(requirement.id, task_id)
                nodes.append(
                    TaskNode(
                        id=task_id,
                        title=str(spec["title"]),
                        description=frontend_large_refactor_description(str(spec["description"]), remaining_requirements),
                        type="frontend",
                        assigned_agent="frontend",
                        dependencies=["T001"],
                        completion_criteria=dedupe(
                            [criterion for item in remaining_requirements for criterion in item.acceptance_criteria]
                        )
                        or ["The remaining frontend requirements are implemented."],
                        relevant_files=frontend_timeout_split_relevant_files(
                            list(spec["files"]),
                            remaining_requirements,
                            scope_controls=scope_controls,
                            fallback=base_relevant_files,
                        ),
                        commands_to_run=frontend_commands,
                        priority=max(priority_for_requirement(item) for item in remaining_requirements),
                        boundary_mode="large_refactor",
                    )
                )
        else:
            task_id = f"T{task_index:03d}"
            for requirement in remaining_requirements:
                requirement_task_ids.setdefault(requirement.id, task_id)
            nodes.append(
                TaskNode(
                    id=task_id,
                    title="Complete remaining frontend closure requirements",
                    description=frontend_large_refactor_description(
                        "Implement frontend closure requirements that were not covered by a more specific workflow task.",
                        remaining_requirements,
                    ),
                    type="frontend",
                    assigned_agent="frontend",
                    dependencies=["T001"],
                    completion_criteria=dedupe(
                        [criterion for item in remaining_requirements for criterion in item.acceptance_criteria]
                    )
                    or ["The remaining frontend requirements are implemented."],
                    relevant_files=frontend_large_refactor_relevant_files(
                        ["frontend/**", "frontend/package.json"],
                        remaining_requirements,
                        scope_controls=scope_controls,
                        fallback=base_relevant_files,
                    ),
                    commands_to_run=frontend_commands,
                    priority=max(priority_for_requirement(item) for item in remaining_requirements),
                    boundary_mode="large_refactor",
                )
            )

    return nodes, requirement_task_ids


def frontend_large_refactor_description(prefix: str, requirements: list[Requirement]) -> str:
    requirement_refs = "; ".join(f"{requirement.id}: {shorten(requirement.text, 120)}" for requirement in requirements)
    return f"{prefix} Phase requirements: {requirement_refs}"


def focused_verification_repair_requirements(requirements: list[Requirement]) -> list[Requirement]:
    return [requirement for requirement in requirements if is_focused_verification_repair_requirement(requirement)]


def focused_repair_metadata_requirements(requirements: list[Requirement]) -> list[Requirement]:
    return [requirement for requirement in requirements if is_focused_repair_metadata_requirement(requirement)]


def should_suppress_remaining_frontend_fallback_after_verification_repair(
    verification_repair_requirements: list[Requirement],
    preserved_task_ids: set[str],
) -> bool:
    if not verification_repair_requirements:
        return False
    numeric_ids = [
        int(match.group(1))
        for task_id in preserved_task_ids
        if (match := re.match(r"^T(\d{3})$", str(task_id).upper()))
    ]
    return len(numeric_ids) >= 8 and max(numeric_ids, default=0) >= 10


def is_focused_repair_metadata_requirement(requirement: Requirement) -> bool:
    text = requirement.text.lower().strip()
    metadata_prefixes = (
        "completed tasks to preserve:",
        "primary failed task ids:",
        "target files:",
        "do not regenerate",
        "convert out-of-scope",
        "treat a worker timeout",
        "previous relevant files:",
        "worker summary:",
        "retry state:",
        "tests passed:",
        "tests failed:",
        "known issues:",
        "follow-up tasks:",
        "files changed:",
        "failed commands:",
    )
    return any(text.startswith(prefix) for prefix in metadata_prefixes)


def is_focused_verification_repair_requirement(requirement: Requirement) -> bool:
    text = requirement.text.lower()
    if not requirement.related_files:
        return False
    verification_markers = (
        "failing verification",
        "verification issue",
        "tests failed",
        "failed commands",
        "known issues",
        "follow-up tasks",
        "build failed",
        "build blocker",
        "could not resolve",
    )
    repair_markers = ("must repair", "repair ", "fix ", "missing", "target files")
    return any(marker in text for marker in verification_markers) and any(marker in text for marker in repair_markers)


def frontend_verification_repair_relevant_files(
    requirements: list[Requirement],
    *,
    scope_controls: dict[str, list[str]] | None,
    fallback: list[str],
) -> list[str]:
    files = dedupe(
        [
            file
            for requirement in requirements
            for file in requirement.related_files
            if normalize_repo_path(file).startswith(("frontend/", "docs/"))
        ]
    )
    if "frontend/package.json" not in files:
        files.append("frontend/package.json")
    return scoped_files(files, scope_controls, fallback=fallback)


def preserved_frontend_coverage_node(
    task_id: str,
    requirements: list[Requirement],
    *,
    scope_controls: dict[str, list[str]] | None,
    fallback: list[str],
) -> TaskNode:
    return TaskNode(
        id=task_id,
        title="Preserve completed frontend closure coverage",
        description=frontend_large_refactor_description(
            "Carry forward completed frontend closure work from the focused repair preserve list without dispatching a broad fallback worker.",
            requirements,
        ),
        type="frontend",
        assigned_agent="frontend",
        status="completed",
        dependencies=["T001"],
        completion_criteria=dedupe([criterion for item in requirements for criterion in item.acceptance_criteria])
        or ["Previously completed frontend closure requirements remain covered."],
        evidence=[
            {
                "type": "focused_repair_preserved_coverage",
                "summary": "Coverage preserved from completed task evidence in the focused repair brief.",
            }
        ],
        relevant_files=frontend_large_refactor_relevant_files(
            ["frontend/**", "frontend/package.json"],
            requirements,
            scope_controls=scope_controls,
            fallback=fallback,
        ),
        commands_to_run=[],
        priority=max(priority_for_requirement(item) for item in requirements) if requirements else 50,
        boundary_mode="large_refactor",
    )


def frontend_large_refactor_relevant_files(
    base_files: list[str],
    requirements: list[Requirement],
    *,
    scope_controls: dict[str, list[str]] | None,
    fallback: list[str],
) -> list[str]:
    requirement_files = [
        frontend_requirement_file(file)
        for requirement in requirements
        for file in requirement.related_files
        if frontend_requirement_file(file)
    ]
    files = dedupe([*base_files, *requirement_files, "frontend/package.json"])
    return scoped_files(files, scope_controls, fallback=fallback)


def frontend_timeout_split_relevant_files(
    base_files: list[str],
    requirements: list[Requirement],
    *,
    scope_controls: dict[str, list[str]] | None,
    fallback: list[str],
) -> list[str]:
    files = frontend_large_refactor_relevant_files(
        base_files,
        requirements,
        scope_controls=scope_controls,
        fallback=fallback,
    )
    narrowed = [file for file in files if normalize_repo_path(file) != "frontend/**"]
    return narrowed or files


def frontend_requirement_file(path: str) -> str:
    normalized = normalize_repo_path(path)
    if normalized.startswith("frontend/"):
        return normalized
    if normalized.startswith("src/"):
        return f"frontend/{normalized}"
    return ""


def frontend_large_refactor_commands(test_commands: list[str], *, package_files: list[str] | None = None) -> list[str]:
    frontend_markers = (
        "frontend",
        "npm ",
        "pnpm ",
        "yarn ",
        "vitest",
        "vite",
    )
    commands = [
        command
        for command in dedupe(test_commands)
        if any(marker in command.lower() for marker in frontend_markers)
    ]
    selected = commands or dedupe(test_commands)
    setup_commands = frontend_dependency_setup_commands(selected, package_files or [])
    return dedupe([*setup_commands, *selected])


def frontend_dependency_setup_commands(commands: list[str], package_files: list[str]) -> list[str]:
    if not commands:
        return []
    frontend_package_files = [
        file
        for file in package_files
        if Path(file).name == "package.json" and _package_is_referenced_by_frontend_commands(file, commands)
    ]
    return dedupe([node_install_command(file, package_files) for file in frontend_package_files])


def _package_is_referenced_by_frontend_commands(package_file: str, commands: list[str]) -> bool:
    parent = package_parent(package_file)
    if parent and any(parent in command.replace("\\", "/") for command in commands):
        return True
    return parent.startswith("frontend") or any("frontend" in command.lower() for command in commands)


def migrate_resumed_frontend_tasks_for_repository(task_graph: TaskGraph, repository_path: str | Path) -> list[str]:
    """Refresh persisted frontend tasks with current package-manager and boundary rules."""

    index = RepositoryIndexer().index(Path(repository_path))
    package_files = list(index.package_files)
    frontend_test_commands = frontend_package_commands(index.test_commands)
    frontend_build_commands = frontend_package_commands(index.build_commands)
    frontend_lint_commands = frontend_package_commands(index.lint_commands)
    frontend_setup_commands = frontend_dependency_setup_commands(
        [*frontend_test_commands, *frontend_build_commands, *frontend_lint_commands],
        package_files,
    )
    changed_task_ids: list[str] = []

    for task in task_graph.nodes:
        if not task_references_frontend(task):
            continue

        original_commands = list(task.commands_to_run)
        original_files = list(task.relevant_files)
        task.commands_to_run = migrated_frontend_commands(
            task,
            frontend_setup_commands=frontend_setup_commands,
            frontend_test_commands=frontend_test_commands,
            frontend_build_commands=frontend_build_commands,
            frontend_lint_commands=frontend_lint_commands,
            package_files=package_files,
        )
        task.relevant_files = migrated_frontend_relevant_files(task)

        if task.commands_to_run != original_commands or task.relevant_files != original_files:
            changed_task_ids.append(task.id)

    return dedupe(changed_task_ids)


def task_references_frontend(task: TaskNode) -> bool:
    fields = [task.title, task.description, *task.relevant_files, *task.commands_to_run]
    return any("frontend" in str(field).replace("\\", "/").lower() for field in fields)


def frontend_package_commands(commands: list[str]) -> list[str]:
    return [command for command in dedupe(commands) if "frontend" in command.replace("\\", "/").lower()]


def migrated_frontend_commands(
    task: TaskNode,
    *,
    frontend_setup_commands: list[str],
    frontend_test_commands: list[str],
    frontend_build_commands: list[str],
    frontend_lint_commands: list[str],
    package_files: list[str],
) -> list[str]:
    if task.boundary_mode == "large_refactor" and task.type in {"frontend", "integration"}:
        selected = frontend_test_commands or frontend_package_commands(task.commands_to_run)
        migrated = frontend_large_refactor_commands(selected, package_files=package_files)
        if migrated:
            return migrated

    if not task.commands_to_run:
        return []

    commands: list[str] = []
    replaced_frontend_command = False
    for command in task.commands_to_run:
        replacement = replacement_frontend_command(
            command,
            frontend_test_commands=frontend_test_commands,
            frontend_build_commands=frontend_build_commands,
            frontend_lint_commands=frontend_lint_commands,
        )
        if replacement is None:
            commands.append(command)
            continue
        replaced_frontend_command = True
        commands.extend(replacement)

    if replaced_frontend_command:
        commands = [*frontend_setup_commands, *commands]
    return dedupe(commands)


def replacement_frontend_command(
    command: str,
    *,
    frontend_test_commands: list[str],
    frontend_build_commands: list[str],
    frontend_lint_commands: list[str],
) -> list[str] | None:
    normalized = command.replace("\\", "/").lower()
    if "frontend" not in normalized or not any(marker in normalized for marker in ("npm ", "pnpm ", "yarn ", "bun ")):
        return None
    if "install" in normalized:
        return []
    if "lint" in normalized and frontend_lint_commands:
        return frontend_lint_commands
    if "build" in normalized and frontend_build_commands:
        return frontend_build_commands
    if ("test" in normalized or "vitest" in normalized) and frontend_test_commands:
        return frontend_test_commands
    return None


def migrated_frontend_relevant_files(task: TaskNode) -> list[str]:
    files = list(task.relevant_files)
    title = task.title.lower()
    description = task.description.lower()
    if any(marker in f"{title} {description}" for marker in ("payment", "order", "recharge", "wallet", "订单", "支付", "充值")):
        files.append("frontend/src/views/admin/orders/**")
    return dedupe(files)


def requirement_matches_markers(requirement: Requirement, markers: tuple[str, ...]) -> bool:
    original = requirement.text
    lower = original.lower()
    return any(marker.lower() in lower or marker in original for marker in markers)


def is_large_refactor_frontend_phase(requirements: list[Requirement]) -> bool:
    primary_original = "\n".join(requirement.text for requirement in requirements[:8])
    primary_text = primary_original.lower()
    frontend_phase_markers = (
        "删除 router",
        "删除菜单",
        "可直达页面",
        "前端没有",
        "前端收口",
        "frontend closure",
        "frontend router",
        "frontend menu",
        "api service 引用",
        "wallet、recharge、usage",
        "admin users",
        "payment providers 页面",
    )
    return any(marker in primary_text or marker in primary_original for marker in frontend_phase_markers)


def large_refactor_phase_hint_files(
    requirements: list[Requirement],
    *,
    assigned_agent: str,
    scope_controls: dict[str, list[str]] | None,
) -> list[str]:
    hints: list[str] = []
    if assigned_agent == "frontend" or is_large_refactor_frontend_phase(requirements):
        hints.append("frontend/**")
    text = "\n".join(requirement.text for requirement in requirements).lower()
    if any(marker in text for marker in ("backend", "api", "route", "schema", "migration", "service", "后端", "接口", "路由")):
        hints.append("backend/**")
    return scoped_files(hints, scope_controls)


def task_title(requirement: Requirement, task_type: str) -> str:
    label = {
        "backend": "Implement backend requirement",
        "frontend": "Implement frontend requirement",
        "test": "Implement verification requirement",
        "documentation": "Update documentation requirement",
        "integration": "Implement integration requirement",
        "debug": "Fix feedback requirement",
    }.get(task_type, "Implement requirement")
    return f"{label}: {shorten(requirement.text)}"


def grouped_task_title(requirements: list[Requirement], task_type: str) -> str:
    label = {
        "backend": "Implement grouped backend requirements",
        "frontend": "Implement grouped frontend requirements",
        "test": "Implement grouped verification requirements",
        "documentation": "Update grouped documentation requirements",
        "integration": "Implement grouped integration requirements",
        "debug": "Fix grouped feedback requirements",
    }.get(task_type, "Implement grouped requirements")
    files = dedupe([file for requirement in requirements for file in requirement.related_files])
    if files:
        return f"{label}: {', '.join(files)}"
    return f"{label}: {shorten(requirements[0].text)}"


def group_implementation_requirements(requirements: list[Requirement]) -> list[list[Requirement]]:
    if should_group_as_single_web_game_delivery(requirements):
        return [list(requirements)]

    groups: list[list[Requirement]] = []
    group_index: dict[tuple[str, tuple[str, ...]], int] = {}
    file_group_index: dict[tuple[str, ...], int] = {}
    for requirement in requirements:
        task_type, _agent = classify_requirement_task(requirement)
        files_key = tuple(requirement.related_files)
        if files_key and files_key in file_group_index:
            existing_group = groups[file_group_index[files_key]]
            if requirement.source_role == "feedback" or any(item.source_role == "feedback" for item in existing_group):
                existing_group.append(requirement)
                continue
        key = (task_type, files_key)
        if requirement.related_files and key in group_index:
            groups[group_index[key]].append(requirement)
            continue
        group_index[key] = len(groups)
        if files_key:
            file_group_index.setdefault(files_key, len(groups))
        groups.append([requirement])
    return groups


def should_group_as_single_web_game_delivery(requirements: list[Requirement]) -> bool:
    if len(requirements) < 5:
        return False
    related = {file for requirement in requirements for file in requirement.related_files}
    text = "\n".join(requirement.text for requirement in requirements).lower()
    game_markers = ("game", "platformer", "tilemap", "canvas", "webgl", "vite", "level", "游戏", "关卡", "玩家", "敌人")
    has_game_intent = any(marker in text for marker in game_markers)
    scaffold_signals = len(related & WEB_GAME_SCAFFOLD_FILES)
    if not has_game_intent and scaffold_signals < 4:
        return False
    # Existing projects frequently name every scaffold file in their requirements.
    # New document-only game repositories cannot: those files do not exist yet.
    # Both are one integrated delivery, not independent per-requirement artifacts.
    return scaffold_signals >= 4 or any(
        marker in text for marker in ("canvas", "webgl", "platformer", "tilemap", "vite", "横版")
    )


def is_existing_canvas_game_repository(repository_files: list[RepositoryFile]) -> bool:
    """Keep repair runs for an existing canvas game on the frontend game path.

    A focused repair brief may contain fewer than five game requirements, so the
    document-only grouping heuristic alone cannot recognize it.  Repository
    evidence is stronger in that case: an HTML entrypoint plus a Vite-style
    game source layout must never be routed through the generic backend
    large-refactor planner.
    """

    paths = {normalize_repo_path(file.path) for file in repository_files}
    has_entrypoint = "index.html" in paths
    has_package = "package.json" in paths
    game_modules = len(paths & WEB_GAME_SCAFFOLD_FILES)
    return has_entrypoint and has_package and game_modules >= 3


def priority_for_requirement(requirement: Requirement) -> int:
    return {"must": 90, "should": 70, "could": 50}.get(requirement.priority, 70)


def commands_for_task_type(task_type: str, test_commands: list[str]) -> list[str]:
    if task_type == "documentation":
        return ["static document inspection"]
    return list(test_commands)


def shorten(text: str, limit: int = 72) -> str:
    clean = " ".join(text.split())
    return clean if len(clean) <= limit else clean[: limit - 3].rstrip() + "..."


def dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value)
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result
