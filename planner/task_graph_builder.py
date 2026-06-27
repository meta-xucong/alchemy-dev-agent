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

        verify_id = next_graph_task_id(nodes, preserved_task_ids)
        nodes.append(
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
        )

        review_id = next_graph_task_id(nodes, preserved_task_ids)
        nodes.append(
            TaskNode(
                id=review_id,
                title="Review delivery readiness",
                description="Check requirement traceability, risks, test evidence, and final gate readiness.",
                type="review",
                assigned_agent="reviewer",
                dependencies=[verify_id],
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
                requirement.planned_task_ids = [requirement_task_ids[requirement.id], verify_id, review_id]

        dependencies = [Dependency(source="T001", target=node.id, type="blocks") for node in implementation_nodes]
        dependencies.extend(Dependency(source=node.id, target=verify_id, type="requires_test_pass") for node in implementation_nodes)
        dependencies.append(Dependency(source=verify_id, target=review_id, type="requires_review"))
        mark_preserved_completed_tasks(nodes, preserved_task_ids)
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
        if boundary_mode(scope_controls) == "large_refactor":
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
        for index, grouped_requirements in enumerate(group_implementation_requirements(requirements), start=2):
            requirement = grouped_requirements[0]
            task_type, agent = classify_grouped_requirement_task(grouped_requirements)
            task_id = f"T{index:03d}"
            title = task_title(requirement, task_type) if len(grouped_requirements) == 1 else grouped_task_title(grouped_requirements, task_type)
            description = (
                f"Implement requirement {requirement.id}: {requirement.text}"
                if len(grouped_requirements) == 1
                else "Implement requirements "
                + ", ".join(item.id for item in grouped_requirements)
                + ": "
                + " ".join(item.text for item in grouped_requirements)
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
                    relevant_files=scoped_files(
                        dedupe([file for item in grouped_requirements for file in item.related_files]),
                        scope_controls,
                    ),
                    commands_to_run=commands_for_task_type(task_type, test_commands),
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
    if not WEB_GAME_SCAFFOLD_FILES.issubset(related):
        return False
    text = "\n".join(requirement.text for requirement in requirements).lower()
    game_markers = ("game", "platformer", "tilemap", "canvas", "level", "游戏", "关卡", "玩家", "敌人")
    return any(marker in text for marker in game_markers)


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
