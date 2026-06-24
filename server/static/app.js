const state = {
  projectId: "",
  runId: "",
  pollTimer: 0,
  eventSource: null,
  events: [],
  deliveryTab: "overview",
  language: localStorage.getItem("alchemyConsoleLanguage") || "en",
  advancedVisible: localStorage.getItem("alchemyAdvancedVisible") === "true",
  apiStatus: "checking",
  delivery: null,
  evidenceIndex: null,
  evidencePackage: null,
  evidenceReadiness: null,
  evidenceToolResult: null,
  environmentReady: false,
  environmentReport: null,
  environmentDefaults: null,
  environmentChecking: false,
  runStatusSnapshot: null,
  sourceType: "",
  sourceLocked: false,
  projectSourceType: "",
  uploadedDocumentPaths: [],
  projects: [],
};

const el = (id) => document.getElementById(id);

const SOURCE_TYPES = ["idea", "documents", "github"];

const I18N = {
  en: {
    "app.subtitle": "One-click software generation for people who do not write code",
    "advanced.show": "Advanced details",
    "advanced.hide": "Hide details",
    "advanced.config": "Advanced configuration",
    "advanced.run_controls": "Advanced run controls",
    "api.checking": "Checking Service",
    "api.online": "Service Ready",
    "api.offline": "Service Offline",
    "config.title": "1. Prepare This Computer",
    "config.simple_help": "Check once before development. Alchemy will use the recommended local setup unless you open advanced configuration.",
    "config.not_checked": "Not checked",
    "config.ready": "Ready",
    "config.blocked": "Blocked",
    "config.checking": "Checking...",
    "config.models": "Model Access",
    "config.model_help": "Recommended mode uses your logged-in Codex CLI. No API key is needed.",
    "config.recommended": "Recommended",
    "config.advanced": "Advanced",
    "config.model_mode": "Model mode",
    "config.provider_codex": "Recommended: Codex CLI login",
    "config.provider_openai": "Advanced: OpenAI API key",
    "config.provider_anthropic": "Advanced: Anthropic API key",
    "config.provider_custom": "Advanced: Custom endpoint",
    "config.advanced_model": "Advanced model settings",
    "config.model_provider": "Provider",
    "config.orchestrator_model": "Orchestrator model",
    "config.expansion_model": "Document expansion model",
    "config.reviewer_model": "Reviewer model",
    "config.api_key_env": "API key environment variable",
    "config.base_url": "Base URL",
    "controls.title": "Create Project",
    "controls.objective": "Objective",
    "controls.documents": "Development documents",
    "controls.attachments": "Supporting files",
    "controls.upload_files": "Upload files",
    "controls.github_source": "GitHub repository source",
    "controls.local_source": "Local repository source",
    "controls.source_mode": "Source mode",
    "controls.codex_executable": "Codex CLI executable",
    "controls.ci_wait": "CI wait seconds",
    "controls.ci_poll": "CI poll seconds",
    "controls.prepare_repository": "Prepare GitHub source",
    "controls.real_codex": "Real Codex worker",
    "controls.real_github": "Real GitHub flow",
    "controls.collect_ci": "Collect GitHub CI",
    "controls.isolated_worktree": "Isolated worktree",
    "controls.keep_worktree": "Keep worktree",
    "controls.auto_browser": "Auto browser verify",
    "controls.static_ci": "Generate static CI",
    "controls.native_ui_tests": "Write native UI tests",
    "controls.auto_merge": "Auto merge after checks",
    "workspace.title": "0. Project Workspace",
    "workspace.simple_help": "Start fresh or reopen a previous result.",
    "workspace.new_ready": "New project",
    "workspace.active": "Current project",
    "workspace.no_active": "No project selected",
    "workspace.no_active_detail": "Choose an input source below to start a new project.",
    "workspace.history": "History",
    "workspace.no_history": "No previous projects yet.",
    "workspace.latest_run": "Latest run",
    "workspace.local_folder": "Local folder",
    "workspace.restored": "Project restored from history.",
    "button.new_project": "New Project",
    "button.refresh_history": "Refresh History",
    "button.delete_project": "Delete",
    "source.title": "2. Choose What To Build From",
    "source.simple_help": "Pick exactly one input method. Alchemy will turn it into a development plan and start building.",
    "source.locked": "Locked",
    "source.unlocked": "Ready",
    "source.selected": "Source locked",
    "source.idea.title": "Idea prompt",
    "source.idea.subtitle": "Expand one paragraph into a full development document.",
    "source.idea.placeholder": "Describe what you want to build.",
    "source.documents.title": "Local documents",
    "source.documents.subtitle": "Upload one or more development documents from this computer.",
    "source.documents.objective_placeholder": "Optional delivery goal",
    "source.github.title": "GitHub repository",
    "source.github.subtitle": "Use a GitHub repository URL after GitHub login is verified.",
    "source.github.objective_placeholder": "Optional delivery goal",
    "source.auto": "Auto",
    "source.none": "No repository",
    "source.local": "Local repository",
    "source.github_public": "Public GitHub",
    "source.github_private": "Private GitHub",
    "button.create": "Create",
    "button.upload": "Upload",
    "button.feedback_reopen": "Feedback Reopen",
    "button.plan": "Plan",
    "button.check_env": "Check And Prepare",
    "button.preflight": "Preflight",
    "button.unified_run": "Unified Run",
    "button.run": "Run",
    "button.pause": "Pause",
    "button.resume": "Resume",
    "button.stop": "Stop",
    "button.stop_development": "Stop Development",
    "button.index": "Index",
    "button.package": "Package",
    "button.readiness": "Readiness",
    "button.choose_files": "Choose files",
    "button.change_source": "Choose Again",
    "button.start_development": "Start Auto Development",
    "file.no_file": "No file selected",
    "file.selected": "files selected",
    "file.uploaded": "files loaded",
    "env.git": "Git",
    "env.gh": "GitHub CLI",
    "env.gh_auth": "GitHub login",
    "env.codex": "Codex CLI",
    "env.model_access": "Model access",
    "env.browser_automation": "Browser automation",
    "model.summary_codex": "Uses the Codex CLI account already logged in on this computer. This is the recommended setup.",
    "model.summary_api": "Uses an API key from an environment variable. Choose this only if you intentionally want an external model API.",
    "model.codex_path": "Codex CLI",
    "model.github_path": "GitHub CLI",
    "model.key_configured": "API key detected",
    "model.key_missing": "API key not detected",
    "model.defaults_loaded": "Local defaults loaded",
    "message.environment_required": "Check and pass configuration before starting development.",
    "message.select_source": "Select exactly one development source.",
    "message.select_files": "Choose at least one local development document.",
    "message.github_required": "Enter a GitHub repository URL.",
    "message.objective_required": "Enter an objective or idea prompt.",
    "message.source_reset": "Source selection reset.",
    "message.new_project_ready": "New project is ready. Choose a source below.",
    "message.history_loaded": "Project history loaded.",
    "message.delete_project_confirm": "Delete this project and all Alchemy local files? This cannot be undone.",
    "message.project_deleted": "Project deleted.",
    "message.environment_ready": "Environment is ready. Development sources are unlocked.",
    "message.environment_blocked": "Environment is blocked. Resolve configuration blockers first.",
    "project.title": "Project",
    "project.project_id": "Project ID",
    "project.status": "Status",
    "project.run_id": "Run ID",
    "project.run_status": "Run Status",
    "progress.title": "3. Development Progress",
    "progress.waiting": "Waiting to start",
    "progress.choose_source": "Choose a source and start development.",
    "progress.delivery_loaded": "Ready to review. The generated result is available below.",
    "progress.last_activity": "Last activity",
    "progress.elapsed": "Elapsed",
    "progress.tasks": "Tasks",
    "progress.roadmap": "Roadmap",
    "progress.stalled": "Still running, but no recent activity was detected.",
    "central.title": "Central review",
    "central.waiting": "Waiting for a run.",
    "central.next_actions": "Next actions",
    "central.missing_steps": "Missing loop steps",
    "central.completed_steps": "Completed loop steps",
    "central.decision.continue": "Keep building",
    "central.decision.handoff": "Ready to inspect",
    "central.decision.iterate": "Needs another iteration",
    "central.decision.blocked": "Needs help",
    "central.decision.wait_for_input": "Waiting for input",
    "auto_iteration.action": "Continue optimizing",
    "auto_iteration.starting": "Starting another optimization pass...",
    "auto_iteration.started": "Started another optimization pass.",
    "auto_iteration.unavailable": "Automatic optimization is not available for this run.",
    "auto_iteration.plan": "Optimization plan",
    "phase.configure": "Configure",
    "phase.choose_source": "Choose source",
    "phase.planning": "Planning",
    "phase.developing": "Developing",
    "phase.testing": "Testing",
    "phase.reviewing": "Reviewing",
    "phase.ready": "Ready to review",
    "phase.blocked": "Needs attention",
    "panel.intake": "Intake",
    "panel.task_graph": "Task Graph",
    "panel.events": "Events",
    "delivery.title": "4. Review The Result",
    "delivery.simple_help": "When the run is done, open the result from here. Technical evidence is available in advanced details.",
    "delivery.no_delivery": "Waiting for result",
    "delivery.ready_for_review": "Ready for review",
    "delivery.needs_iteration": "Needs iteration",
    "delivery.final_gate": "Review score",
    "delivery.actions": "Review actions",
    "delivery.local_only": "Local delivery. No pull request was created.",
    "delivery.folder_opening": "Opening the result folder...",
    "delivery.folder_opened": "Result folder opened.",
    "delivery.folder_failed": "Could not open the folder automatically. Path or error:",
    "delivery.result_opened": "Opening result in a browser tab. If nothing appears, use the Result Files tab.",
    "delivery.action_unavailable": "This action is not available for the current run.",
    "delivery.evidence_index": "Evidence index",
    "delivery.evidence_package": "Evidence package",
    "delivery.evidence_readiness": "Evidence readiness",
    "score.title": "Why this score?",
    "score.excellent": "The delivery evidence is close to complete.",
    "score.pass_with_gaps": "This passed the delivery gate, but some verification evidence is still incomplete.",
    "score.needs_work": "This score needs another iteration before handoff.",
    "score.reason_requirements": "Some must-have requirements are missing or only partially covered.",
    "score.reason_browser": "Browser, scenario, or gameplay verification is missing or incomplete.",
    "score.reason_cycle": "The full development cycle has partial or missing steps.",
    "score.reason_github": "This was a local/dry-run delivery, so real PR, CI, or merge proof is not available.",
    "score.reason_blockers": "The run still reports blockers or required changes.",
    "score.improve": "To raise the score, rerun with browser verification and real GitHub/CI evidence when that delivery path is needed.",
    "tab.overview": "Result",
    "tab.artifacts": "Result Files",
    "tab.evidence_gate": "Evidence Gate",
    "tab.raw_json": "Raw JSON",
    "gate.title": "Evidence Gate",
    "gate.roots": "Evidence roots",
    "gate.index_output": "Index output",
    "gate.package_output": "Package output",
    "gate.readiness_output": "Readiness output",
    "gate.index_report": "Evidence index report",
    "gate.package_manifest": "Evidence package manifest",
    "gate.benchmark_report": "Benchmark regression report",
    "placeholder.paths": "One local path per line",
    "placeholder.evidence_roots": ".alchemy/run_a\n.alchemy/run_b",
    "summary.status": "Status",
    "summary.gate": "Gate",
    "summary.pr": "PR",
    "summary.ci": "CI",
    "summary.merge": "Merge",
    "summary.artifact": "Artifact",
    "summary.semantic": "Semantic",
    "summary.scenarios": "Scenarios",
    "summary.gameplay": "Gameplay",
    "summary.coverage": "Coverage",
    "summary.entries": "Entries",
    "summary.blocked": "Blocked",
    "summary.files": "Files",
    "summary.blockers": "Blockers",
    "summary.passed": "Passed",
    "summary.checks": "Checks",
    "summary.requirements": "Requirements",
    "summary.score": "Score",
    "summary.must_gaps": "Must gaps",
    "summary.tasks": "Tasks",
    "summary.agents": "Agents",
    "summary.with_deps": "With deps",
    "evidence.requirements": "Requirements",
    "evidence.covered": "covered",
    "evidence.partial": "partial",
    "evidence.missing": "missing",
    "evidence.must_gaps": "Must gaps",
    "evidence.pull_request": "Pull request",
    "evidence.action": "Action",
    "evidence.source": "source",
    "evidence.current": "current",
    "evidence.steps": "steps",
    "evidence.browser_probes": "Browser Probes",
    "evidence.native_ui_tests": "Native UI Tests",
    "evidence.github": "GitHub",
    "evidence.development_cycle": "Development Cycle",
    "evidence.repair_comparison": "Repair Comparison",
    "evidence.repair_suggestions": "Repair Suggestions",
    "evidence.next_actions": "Next Actions",
    "evidence.artifacts": "Evidence Artifacts",
    "evidence.requirement_coverage": "Requirement Coverage",
    "evidence.awaiting_gate": "Awaiting evidence gate",
    "evidence.awaiting_gate_detail": "Run index and package, then evaluate readiness.",
    "evidence.no_checks": "No checks",
    "common.none": "None",
    "common.no_blockers": "No blockers",
    "common.no_next_action": "No next action",
    "common.no_repair_comparison": "No repair comparison",
    "common.no_repair_suggestions": "No repair suggestions",
    "common.open_preview": "Open preview",
    "artifact.hidden_sources": "technical files are hidden in simple mode. Turn on advanced details to inspect source files.",
    "common.no_files": "no files",
    "status.passed": "passed",
    "status.ready": "ready",
    "status.failed": "failed",
    "status.blocked": "blocked",
    "status.partial": "partial",
    "status.skipped": "skipped",
    "status.unknown": "unknown",
    "status.running": "running",
    "status.done": "done",
    "status.needs_iteration": "needs iteration",
    "status.pending": "pending",
    "check.evidence_index_status": "Evidence Index Status",
    "check.evidence_index_entries": "Evidence Index Entries",
    "check.evidence_index_no_blocked_or_failed": "Evidence Index No Blocked Or Failed",
    "check.evidence_package_status": "Evidence Package Status",
    "check.evidence_package_files": "Evidence Package Files",
    "check.evidence_package_no_blockers": "Evidence Package No Blockers",
    "check.benchmark_regression_status": "Benchmark Regression Status",
    "check.benchmark_regression_no_blockers": "Benchmark Regression No Blockers",
  },
  zh: {
    "app.subtitle": "给不会写代码的人用的一键生成软件工具",
    "advanced.show": "高级详情",
    "advanced.hide": "收起详情",
    "advanced.config": "高级配置",
    "advanced.run_controls": "高级运行控制",
    "api.checking": "正在检查服务",
    "api.online": "服务可用",
    "api.offline": "服务离线",
    "config.title": "1. 准备这台电脑",
    "config.simple_help": "开发前检查一次即可。默认使用推荐的本机配置，普通用户不需要改高级配置。",
    "config.not_checked": "未检查",
    "config.ready": "已就绪",
    "config.blocked": "未就绪",
    "config.checking": "检查中...",
    "config.models": "大模型接入",
    "config.model_help": "推荐模式会使用本机已登录的 Codex CLI，不需要填写 API Key。",
    "config.recommended": "推荐",
    "config.advanced": "高级",
    "config.model_mode": "模型模式",
    "config.provider_codex": "推荐：使用 Codex CLI 登录",
    "config.provider_openai": "高级：OpenAI API Key",
    "config.provider_anthropic": "高级：Anthropic API Key",
    "config.provider_custom": "高级：自定义接口",
    "config.advanced_model": "高级模型设置",
    "config.model_provider": "供应商",
    "config.orchestrator_model": "中枢模型",
    "config.expansion_model": "文档扩展模型",
    "config.reviewer_model": "评审模型",
    "config.api_key_env": "API Key 环境变量",
    "config.base_url": "Base URL",
    "controls.title": "创建项目",
    "controls.objective": "开发目标",
    "controls.documents": "开发文档",
    "controls.attachments": "配套文件",
    "controls.upload_files": "上传文件",
    "controls.github_source": "GitHub 仓库来源",
    "controls.local_source": "本地仓库来源",
    "controls.source_mode": "来源模式",
    "controls.codex_executable": "Codex CLI 可执行文件",
    "controls.ci_wait": "CI 等待秒数",
    "controls.ci_poll": "CI 轮询秒数",
    "controls.prepare_repository": "准备 GitHub 来源",
    "controls.real_codex": "真实 Codex worker",
    "controls.real_github": "真实 GitHub 流程",
    "controls.collect_ci": "采集 GitHub CI",
    "controls.isolated_worktree": "隔离工作区",
    "controls.keep_worktree": "保留工作区",
    "controls.auto_browser": "自动浏览器验收",
    "controls.static_ci": "生成静态 CI",
    "controls.native_ui_tests": "写入原生 UI 测试",
    "controls.auto_merge": "检查通过后自动合并",
    "workspace.title": "0. 项目工作台",
    "workspace.simple_help": "从这里新建项目，或打开之前生成过的项目。",
    "workspace.new_ready": "新项目",
    "workspace.active": "当前项目",
    "workspace.no_active": "还没有选择项目",
    "workspace.no_active_detail": "在下方选择一种输入方式，即可开始新项目。",
    "workspace.history": "历史项目",
    "workspace.no_history": "还没有历史项目。",
    "workspace.latest_run": "最近运行",
    "workspace.local_folder": "本地文件夹",
    "workspace.restored": "已从历史项目恢复。",
    "button.new_project": "新建项目",
    "button.refresh_history": "刷新历史",
    "button.delete_project": "删除",
    "source.title": "2. 选择你要怎么开始",
    "source.simple_help": "三种方式只能选一种。Alchemy 会自动把输入整理成开发计划并开始执行。",
    "source.locked": "已锁定",
    "source.unlocked": "可选择",
    "source.selected": "来源已锁定",
    "source.idea.title": "一句话目标",
    "source.idea.subtitle": "由 LLM 扩充分析成完整开发文档，再进入开发流程。",
    "source.idea.placeholder": "描述你想构建的程序。",
    "source.documents.title": "本地开发文档",
    "source.documents.subtitle": "从本机选择并上传一份或多份开发文档。",
    "source.documents.objective_placeholder": "可选交付目标",
    "source.github.title": "GitHub 仓库",
    "source.github.subtitle": "验证 GitHub 登录后，直接使用仓库 URL。",
    "source.github.objective_placeholder": "可选交付目标",
    "source.auto": "自动",
    "source.none": "无仓库",
    "source.local": "本地仓库",
    "source.github_public": "公开 GitHub",
    "source.github_private": "私有 GitHub",
    "button.create": "创建",
    "button.upload": "上传",
    "button.feedback_reopen": "反馈重开",
    "button.plan": "生成计划",
    "button.check_env": "检查并准备",
    "button.preflight": "预检",
    "button.unified_run": "统一运行",
    "button.run": "运行",
    "button.pause": "暂停",
    "button.resume": "恢复",
    "button.stop": "停止",
    "button.stop_development": "停止开发",
    "button.index": "索引",
    "button.package": "打包",
    "button.readiness": "就绪评估",
    "button.choose_files": "选择文件",
    "button.change_source": "重新选择",
    "button.start_development": "开始自动开发",
    "file.no_file": "未选择文件",
    "file.selected": "个文件已选择",
    "file.uploaded": "个文件已加载",
    "env.git": "Git",
    "env.gh": "GitHub CLI",
    "env.gh_auth": "GitHub 登录",
    "env.codex": "Codex CLI",
    "env.model_access": "大模型接入",
    "env.browser_automation": "浏览器自动验收",
    "model.summary_codex": "使用这台电脑上已经登录的 Codex CLI，这是推荐配置。",
    "model.summary_api": "使用环境变量里的 API Key。只有你明确要接外部模型 API 时才需要选它。",
    "model.codex_path": "Codex CLI",
    "model.github_path": "GitHub CLI",
    "model.key_configured": "已检测到 API Key",
    "model.key_missing": "未检测到 API Key",
    "model.defaults_loaded": "已加载本机默认配置",
    "message.environment_required": "请先通过配置检查，再开始开发。",
    "message.select_source": "请选择且只能选择一种开发来源。",
    "message.select_files": "请至少选择一份本地开发文档。",
    "message.github_required": "请输入 GitHub 仓库 URL。",
    "message.objective_required": "请输入目标或一句话想法。",
    "message.source_reset": "已重置开发来源选择。",
    "message.new_project_ready": "已准备新项目，请在下方选择开发来源。",
    "message.history_loaded": "历史项目已加载。",
    "message.delete_project_confirm": "确定删除这个项目及其本地生成文件吗？此操作不可撤销。",
    "message.project_deleted": "项目已删除。",
    "message.environment_ready": "环境已就绪，开发来源已解锁。",
    "message.environment_blocked": "环境未就绪，请先处理配置阻塞项。",
    "project.title": "项目",
    "project.project_id": "项目 ID",
    "project.status": "项目状态",
    "project.run_id": "运行 ID",
    "project.run_status": "运行状态",
    "progress.title": "3. 开发进度",
    "progress.waiting": "等待开始",
    "progress.choose_source": "选择来源后开始开发。",
    "progress.delivery_loaded": "可以验收，生成结果已在下方显示。",
    "progress.last_activity": "最近活动",
    "progress.elapsed": "已运行",
    "progress.tasks": "任务",
    "progress.roadmap": "路线图",
    "progress.stalled": "仍在运行，但暂时没有检测到新的活动。",
    "central.title": "中枢复盘",
    "central.waiting": "等待开始运行。",
    "central.next_actions": "下一步",
    "central.missing_steps": "缺失环节",
    "central.completed_steps": "已完成环节",
    "central.decision.continue": "继续开发",
    "central.decision.handoff": "可以验收",
    "central.decision.iterate": "需要再迭代",
    "central.decision.blocked": "需要处理",
    "central.decision.wait_for_input": "等待输入",
    "auto_iteration.action": "继续优化",
    "auto_iteration.starting": "正在开始下一轮优化...",
    "auto_iteration.started": "已开始下一轮优化。",
    "auto_iteration.unavailable": "当前运行暂时不能自动优化。",
    "auto_iteration.plan": "优化计划",
    "phase.configure": "配置",
    "phase.choose_source": "选择来源",
    "phase.planning": "规划中",
    "phase.developing": "开发中",
    "phase.testing": "测试中",
    "phase.reviewing": "待复核",
    "phase.ready": "可以验收",
    "phase.blocked": "需要处理",
    "panel.intake": "输入解析",
    "panel.task_graph": "任务图",
    "panel.events": "事件",
    "delivery.title": "4. 验收结果",
    "delivery.simple_help": "开发完成后，从这里打开结果。技术证据和工程细节收在高级详情里。",
    "delivery.no_delivery": "等待结果",
    "delivery.ready_for_review": "可验收",
    "delivery.needs_iteration": "需迭代",
    "delivery.final_gate": "验收分数",
    "delivery.actions": "验收入口",
    "delivery.local_only": "本地交付：本次没有创建拉取请求。",
    "delivery.folder_opening": "正在打开结果文件夹...",
    "delivery.folder_opened": "结果文件夹已打开。",
    "delivery.folder_failed": "无法自动打开文件夹。路径或错误：",
    "delivery.result_opened": "正在浏览器中打开作品。如果没有弹出，请到“结果文件”页打开。",
    "delivery.action_unavailable": "当前运行不支持这个操作。",
    "delivery.evidence_index": "证据索引",
    "delivery.evidence_package": "证据包",
    "delivery.evidence_readiness": "证据就绪",
    "score.title": "为什么是这个分数？",
    "score.excellent": "交付证据已经接近完整。",
    "score.pass_with_gaps": "已通过交付门禁，但还有部分验收证据不完整。",
    "score.needs_work": "这个分数还需要继续迭代后再交付。",
    "score.reason_requirements": "还有强制需求缺失或只被部分覆盖。",
    "score.reason_browser": "浏览器、场景或玩法验证缺失/未完成。",
    "score.reason_cycle": "完整开发闭环里还有部分步骤未完成。",
    "score.reason_github": "这是本地/模拟交付，因此没有真实 PR、CI 或合并证据。",
    "score.reason_blockers": "运行结果仍报告阻塞项或必须修改项。",
    "score.improve": "想提高分数，可以开启浏览器验收；需要 GitHub 交付时，再走真实 PR/CI/合并流程。",
    "tab.overview": "结果",
    "tab.artifacts": "结果文件",
    "tab.evidence_gate": "证据门禁",
    "tab.raw_json": "原始 JSON",
    "gate.title": "证据门禁",
    "gate.roots": "证据来源",
    "gate.index_output": "索引输出",
    "gate.package_output": "证据包输出",
    "gate.readiness_output": "就绪输出",
    "gate.index_report": "证据索引报告",
    "gate.package_manifest": "证据包清单",
    "gate.benchmark_report": "基准回归报告",
    "placeholder.paths": "每行一个本地路径",
    "placeholder.evidence_roots": ".alchemy/run_a\n.alchemy/run_b",
    "summary.status": "状态",
    "summary.gate": "门禁",
    "summary.pr": "PR",
    "summary.ci": "CI",
    "summary.merge": "合并",
    "summary.artifact": "产物",
    "summary.semantic": "语义",
    "summary.scenarios": "场景",
    "summary.gameplay": "玩法",
    "summary.coverage": "覆盖率",
    "summary.entries": "条目",
    "summary.blocked": "阻塞",
    "summary.files": "文件",
    "summary.blockers": "阻塞项",
    "summary.passed": "通过",
    "summary.checks": "检查",
    "summary.requirements": "需求",
    "summary.score": "分数",
    "summary.must_gaps": "强制缺口",
    "summary.tasks": "任务",
    "summary.agents": "Agent",
    "summary.with_deps": "有依赖",
    "evidence.requirements": "需求",
    "evidence.covered": "已覆盖",
    "evidence.partial": "部分覆盖",
    "evidence.missing": "缺失",
    "evidence.must_gaps": "强制缺口",
    "evidence.pull_request": "拉取请求",
    "evidence.action": "操作",
    "evidence.source": "来源",
    "evidence.current": "当前",
    "evidence.steps": "步骤",
    "evidence.browser_probes": "浏览器探针",
    "evidence.native_ui_tests": "原生 UI 测试",
    "evidence.github": "GitHub",
    "evidence.development_cycle": "开发闭环",
    "evidence.repair_comparison": "修复对比",
    "evidence.repair_suggestions": "修复建议",
    "evidence.next_actions": "下一步",
    "evidence.artifacts": "证据产物",
    "evidence.requirement_coverage": "需求覆盖",
    "evidence.awaiting_gate": "等待证据门禁",
    "evidence.awaiting_gate_detail": "先运行索引和打包，再执行就绪评估。",
    "evidence.no_checks": "暂无检查",
    "common.none": "无",
    "common.no_blockers": "无阻塞项",
    "common.no_next_action": "无下一步",
    "common.no_repair_comparison": "无修复对比",
    "common.no_repair_suggestions": "无修复建议",
    "common.open_preview": "打开预览",
    "artifact.hidden_sources": "个技术文件已在简洁模式隐藏。打开高级详情可查看源码文件。",
    "common.no_files": "无文件",
    "status.passed": "通过",
    "status.ready": "就绪",
    "status.failed": "失败",
    "status.blocked": "阻塞",
    "status.partial": "部分完成",
    "status.skipped": "跳过",
    "status.unknown": "未知",
    "status.running": "运行中",
    "status.done": "完成",
    "status.needs_iteration": "需迭代",
    "status.pending": "等待中",
    "check.evidence_index_status": "证据索引状态",
    "check.evidence_index_entries": "证据索引条目",
    "check.evidence_index_no_blocked_or_failed": "索引无阻塞/失败",
    "check.evidence_package_status": "证据包状态",
    "check.evidence_package_files": "证据包文件",
    "check.evidence_package_no_blockers": "证据包无阻塞",
    "check.benchmark_regression_status": "基准回归状态",
    "check.benchmark_regression_no_blockers": "基准回归无阻塞",
  },
};

async function api(path, options = {}) {
  const request = {
    method: options.method || "GET",
  };
  if (options.formData) {
    request.body = options.formData;
  } else {
    request.headers = { "Content-Type": "application/json" };
    request.body = options.body ? JSON.stringify(options.body) : undefined;
  }
  const response = await fetch(path, request);
  const payload = await response.json();
  if (!response.ok) {
    const message = payload.error?.message || `HTTP ${response.status}`;
    throw new Error(message);
  }
  return payload;
}

function lines(id) {
  const node = el(id);
  if (!node) return [];
  return node.value
    .split(/\r?\n/)
    .map((value) => value.trim())
    .filter(Boolean);
}

function show(id, payload) {
  el(id).textContent = JSON.stringify(payload, null, 2);
}

function t(key) {
  return I18N[state.language]?.[key] || I18N.en[key] || key;
}

function statusText(value) {
  const key = `status.${safeClass(value)}`;
  return I18N[state.language]?.[key] || String(value || "-");
}

function translate(key) {
  return escapeHtml(t(key));
}

function applyAdvancedVisibility() {
  if (!state.advancedVisible && ["readiness", "raw"].includes(state.deliveryTab)) {
    setDeliveryTab("overview");
  }
  document.body.classList.toggle("showAdvanced", state.advancedVisible);
  const toggle = el("advancedToggle");
  if (toggle) {
    toggle.textContent = state.advancedVisible ? t("advanced.hide") : t("advanced.show");
    toggle.setAttribute("aria-pressed", state.advancedVisible ? "true" : "false");
  }
  if (state.delivery) {
    renderDeliveryActions(deliveryActionsFor(state.delivery));
  }
  renderProjectWorkspace();
}

function toggleAdvancedVisibility() {
  state.advancedVisible = !state.advancedVisible;
  localStorage.setItem("alchemyAdvancedVisible", state.advancedVisible ? "true" : "false");
  applyAdvancedVisibility();
}

function applyLanguage() {
  document.documentElement.lang = state.language === "zh" ? "zh-CN" : "en";
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    node.setAttribute("placeholder", t(node.dataset.i18nPlaceholder));
  });
  document.querySelectorAll("[data-lang]").forEach((button) => {
    button.classList.toggle("active", button.dataset.lang === state.language);
  });
  if (state.apiStatus !== "checking") {
    el("apiStatus").textContent = state.apiStatus === "online" ? t("api.online") : t("api.offline");
  }
  if (state.delivery) {
    renderDelivery(state.delivery);
  } else {
    renderDeliveryChrome({}, {}, {});
  }
  if (state.evidenceReadiness) {
    renderReadinessReport(state.evidenceReadiness);
  } else if (state.evidenceToolResult) {
    renderEvidenceToolResult(state.evidenceToolResult.titleKey, state.evidenceToolResult.payload, state.evidenceToolResult.metrics);
  } else {
    renderReadinessReport({});
  }
  renderFileSelection();
  renderModelSummary();
  renderEnvironmentSummary(state.environmentReport);
  renderRunStatus(state.runStatusSnapshot);
  renderProjectWorkspace();
  updateSourceCards();
  applyAdvancedVisibility();
}

function setLanguage(language) {
  state.language = language === "zh" ? "zh" : "en";
  localStorage.setItem("alchemyConsoleLanguage", state.language);
  applyLanguage();
}

async function loadProjectHistory({ quiet = true } = {}) {
  try {
    const history = await api("/projects");
    state.projects = Array.isArray(history.projects) ? history.projects : [];
    renderProjectWorkspace();
    if (!quiet) {
      show("eventOutput", [{ level: "info", message: t("message.history_loaded") }, history]);
    }
  } catch (error) {
    if (!quiet) showError(error);
  }
}

function renderProjectWorkspace() {
  renderActiveProjectSummary();
  renderProjectHistory();
}

function renderActiveProjectSummary() {
  const container = el("activeProjectSummary");
  const badge = el("workspaceBadge");
  if (!container || !badge) return;
  const active = currentProjectSummary();
  if (!state.projectId) {
    badge.textContent = t("workspace.new_ready");
    badge.className = "readinessBadge status-ready";
    container.innerHTML = `
      <strong>${translate("workspace.no_active")}</strong>
      <span>${translate("workspace.no_active_detail")}</span>
    `;
    return;
  }
  badge.textContent = t("workspace.active");
  badge.className = "readinessBadge status-ready";
  const objective = active?.objective || state.projectId;
  const runLabel = state.runId || active?.latest_run_id || "-";
  const score = active?.latest_score ?? "-";
  container.innerHTML = `
    <strong>${escapeHtml(String(objective))}</strong>
    <span>${translate("workspace.latest_run")}: ${escapeHtml(String(runLabel))} · ${translate("summary.score")}: ${escapeHtml(String(score))}</span>
    ${state.advancedVisible ? `<small>${escapeHtml(state.projectId)} · ${escapeHtml(String(active?.workspace_path || ""))}</small>` : ""}
  `;
}

function renderProjectHistory() {
  const container = el("projectHistory");
  if (!container) return;
  const projects = Array.isArray(state.projects) ? state.projects : [];
  if (!projects.length) {
    container.innerHTML = `
      <div class="projectHistoryHeader">
        <strong>${translate("workspace.history")}</strong>
        <span>${translate("workspace.no_history")}</span>
      </div>
    `;
    return;
  }
  container.innerHTML = `
    <div class="projectHistoryHeader">
      <strong>${translate("workspace.history")}</strong>
      <span>${escapeHtml(String(projects.length))}</span>
    </div>
    <div class="projectHistoryGrid">
      ${projects.slice(0, 12).map(renderProjectHistoryCard).join("")}
    </div>
  `;
}

function renderProjectHistoryCard(project) {
  const projectId = String(project.project_id || "");
  const runId = String(project.latest_run_id || "");
  const active = projectId && projectId === state.projectId;
  const status = statusText(project.latest_run_status || project.status || "-");
  const score = project.latest_score ?? "-";
  const updated = formatDateTime(project.updated_at);
  const label = escapeHtml(shortText(project.objective || projectId, 82));
  return `
    <article class="projectHistoryCard ${active ? "active" : ""}">
      <button type="button" class="projectHistoryOpen" data-open-project="${escapeHtml(projectId)}" data-open-run="${escapeHtml(runId)}" aria-label="${label}">
        <strong>${label}</strong>
        <span>${translate("workspace.latest_run")}: ${escapeHtml(runId || "-")} · ${escapeHtml(status)} · ${translate("summary.score")}: ${escapeHtml(String(score))}</span>
        <small>${escapeHtml(updated)}</small>
        ${state.advancedVisible ? `<code>${escapeHtml(String(project.workspace_path || projectId))}</code>` : ""}
      </button>
      <button type="button" class="projectHistoryDelete" data-delete-project="${escapeHtml(projectId)}" title="${translate("button.delete_project")}" aria-label="${translate("button.delete_project")}">${translate("button.delete_project")}</button>
    </article>
  `;
}

function currentProjectSummary() {
  return (state.projects || []).find((project) => String(project.project_id || "") === state.projectId) || null;
}

function renderFileSelection() {
  const fileInput = el("uploadFiles");
  const fileSelection = el("fileSelection");
  if (!fileInput || !fileSelection) return;
  const files = Array.from(fileInput.files || []);
  if (files.length) {
    fileSelection.textContent = `${files.length} ${t("file.selected")}`;
  } else if (state.uploadedDocumentPaths.length) {
    fileSelection.textContent = `${state.uploadedDocumentPaths.length} ${t("file.uploaded")}`;
  } else {
    fileSelection.textContent = t("file.no_file");
  }
  setControls();
}

function beginNewProject() {
  closeEventStream();
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = 0;
  }
  state.projectId = "";
  state.runId = "";
  state.runStatusSnapshot = null;
  state.events = [];
  state.sourceType = "";
  state.sourceLocked = false;
  state.projectSourceType = "";
  state.uploadedDocumentPaths = [];
  state.deliveryTab = "overview";
  if (el("uploadFiles")) el("uploadFiles").value = "";
  ["objective", "documentObjective", "githubObjective", "repository"].forEach((id) => {
    const node = el(id);
    if (node) node.value = "";
  });
  history.replaceState(null, "", window.location.pathname);
  setSummary({}, {});
  show("briefOutput", {});
  show("graphOutput", {});
  renderGraphViz({});
  show("eventOutput", [{ level: "info", message: t("message.new_project_ready") }]);
  renderRunStatus(null);
  resetDelivery();
  setDeliveryTab("overview");
  renderFileSelection();
  renderProjectWorkspace();
  updateSourceCards();
  setControls();
}

async function openProjectFromHistory(projectId, runId = "") {
  if (!projectId) return;
  setCurrentUrl(projectId, runId);
  await loadProjectRun(projectId, runId);
  show("eventOutput", [{ level: "info", message: t("workspace.restored") }]);
}

async function deleteProjectFromHistory(projectId) {
  if (!projectId) return;
  const project = (state.projects || []).find((item) => String(item.project_id || "") === projectId);
  const label = project?.objective || projectId;
  if (!window.confirm(`${t("message.delete_project_confirm")}\n\n${label}`)) {
    return;
  }

  const result = await api(`/projects/${encodeURIComponent(projectId)}`, { method: "DELETE" });
  state.projects = (state.projects || []).filter((item) => String(item.project_id || "") !== projectId);
  if (state.projectId === projectId) {
    beginNewProject();
  } else {
    renderProjectWorkspace();
  }
  await loadProjectHistory({ quiet: true });
  show("eventOutput", [{ level: "info", message: t("message.project_deleted") }, result]);
}

function syncModelProviderDefaults() {
  const provider = el("modelProvider").value;
  const envInput = el("modelApiKeyEnv");
  const baseUrlInput = el("modelBaseUrl");
  const orchestrator = el("orchestratorModel");
  const expansion = el("documentExpansionModel");
  const reviewer = el("reviewerModel");
  const advanced = el("advancedModelSettings");
  if (provider === "codex_cli") {
    orchestrator.value = "codex-cli";
    expansion.value = "codex-cli";
    reviewer.value = "codex-cli";
    if (["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "CUSTOM_LLM_API_KEY"].includes(envInput.value.trim())) {
      envInput.value = "";
    }
    envInput.placeholder = "";
    baseUrlInput.placeholder = "";
    if (advanced) advanced.open = false;
    renderModelSummary();
    return;
  }
  if (provider === "openai") {
    envInput.value = defaultModelEnvValue(envInput.value, "OPENAI_API_KEY");
    envInput.placeholder = "OPENAI_API_KEY";
    baseUrlInput.placeholder = "https://api.openai.com/v1";
    orchestrator.value = orchestrator.value === "codex-cli" ? "gpt-5" : orchestrator.value || "gpt-5";
    expansion.value = expansion.value === "codex-cli" ? "gpt-5" : expansion.value || "gpt-5";
    reviewer.value = reviewer.value === "codex-cli" ? "gpt-5" : reviewer.value || "gpt-5";
    if (advanced) advanced.open = true;
    renderModelSummary();
    return;
  }
  if (provider === "anthropic") {
    envInput.value = defaultModelEnvValue(envInput.value, "ANTHROPIC_API_KEY");
    envInput.placeholder = "ANTHROPIC_API_KEY";
    baseUrlInput.placeholder = "https://api.anthropic.com";
    orchestrator.value = orchestrator.value === "codex-cli" ? "claude-sonnet-4-5" : orchestrator.value || "claude-sonnet-4-5";
    expansion.value = expansion.value === "codex-cli" ? "claude-sonnet-4-5" : expansion.value || "claude-sonnet-4-5";
    reviewer.value = reviewer.value === "codex-cli" ? "claude-sonnet-4-5" : reviewer.value || "claude-sonnet-4-5";
    if (advanced) advanced.open = true;
    renderModelSummary();
    return;
  }
  envInput.value = defaultModelEnvValue(envInput.value, "CUSTOM_LLM_API_KEY");
  envInput.placeholder = "CUSTOM_LLM_API_KEY";
  baseUrlInput.placeholder = "https://llm.example.com/v1";
  if (advanced) advanced.open = true;
  renderModelSummary();
}

function defaultModelEnvValue(current, fallback) {
  const clean = String(current || "").trim();
  const known = ["", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "CUSTOM_LLM_API_KEY"];
  return known.includes(clean) ? fallback : clean;
}

function invalidateEnvironment() {
  if (state.environmentReport || state.environmentReady) {
    setEnvironmentReport(null);
  }
  state.sourceType = "";
  state.sourceLocked = false;
  state.projectSourceType = "";
  state.uploadedDocumentPaths = [];
  if (el("uploadFiles")) {
    el("uploadFiles").value = "";
  }
  renderFileSelection();
  updateSourceCards();
  setControls();
}

function environmentPayload() {
  return {
    codex_executable: el("codexExecutable").value.trim() || "codex",
    require_browser: el("autoBrowserVerify").checked,
    model_provider: el("modelProvider").value || "codex_cli",
    orchestrator_model: el("orchestratorModel").value.trim(),
    document_expansion_model: el("documentExpansionModel").value.trim(),
    reviewer_model: el("reviewerModel").value.trim(),
    model_api_key_env: el("modelApiKeyEnv").value.trim(),
    model_base_url: el("modelBaseUrl").value.trim(),
  };
}

async function loadEnvironmentDefaults() {
  try {
    const defaults = await api("/environment/defaults");
    state.environmentDefaults = defaults;
    if (defaults.codex_executable) {
      el("codexExecutable").value = String(defaults.codex_executable);
    }
    el("modelProvider").value = String(defaults.model_provider || "codex_cli");
    el("orchestratorModel").value = String(defaults.orchestrator_model || "codex-cli");
    el("documentExpansionModel").value = String(defaults.document_expansion_model || "codex-cli");
    el("reviewerModel").value = String(defaults.reviewer_model || "codex-cli");
    el("modelApiKeyEnv").value = String(defaults.model_api_key_env || "");
    el("modelBaseUrl").value = String(defaults.model_base_url || "");
    syncModelProviderDefaults();
    show("eventOutput", [{ level: "info", message: t("model.defaults_loaded") }]);
  } catch (error) {
    renderModelSummary();
  }
}

function renderModelSummary() {
  const container = el("modelSummary");
  if (!container) return;
  const provider = el("modelProvider").value || "codex_cli";
  const defaults = state.environmentDefaults || {};
  const keyConfigured = provider === "openai"
    ? Boolean(defaults.openai_api_key_configured)
    : provider === "anthropic"
      ? Boolean(defaults.anthropic_api_key_configured)
      : Boolean(el("modelApiKeyEnv").value.trim());
  const rows = [];
  if (provider === "codex_cli") {
    rows.push([t("model.summary_codex"), "passed"]);
    rows.push([`${t("model.codex_path")}: ${el("codexExecutable").value || "codex"}`, "neutral"]);
    if (defaults.github_cli) rows.push([`${t("model.github_path")}: ${defaults.github_cli}`, "neutral"]);
  } else {
    rows.push([t("model.summary_api"), keyConfigured ? "passed" : "failed"]);
    rows.push([`${el("modelApiKeyEnv").value || "API_KEY"}: ${keyConfigured ? t("model.key_configured") : t("model.key_missing")}`, keyConfigured ? "passed" : "failed"]);
  }
  const badge = el("modelModeBadge");
  if (badge) {
    const recommended = provider === "codex_cli";
    badge.textContent = recommended ? t("config.recommended") : t("config.advanced");
    badge.className = `readinessBadge status-${recommended ? "ready" : "partial"}`;
  }
  container.innerHTML = rows
    .map(([text, status]) => `<div class="modelSummaryRow status-${safeClass(status)}"><span>${escapeHtml(String(text))}</span></div>`)
    .join("");
}

function modelConfigPayload() {
  return {
    model_provider: el("modelProvider").value || "codex_cli",
    orchestrator_model: el("orchestratorModel").value.trim(),
    document_expansion_model: el("documentExpansionModel").value.trim(),
    reviewer_model: el("reviewerModel").value.trim(),
    model_base_url: el("modelBaseUrl").value.trim(),
    model_api_key_env: el("modelApiKeyEnv").value.trim(),
  };
}

function renderEnvironmentSummary(report) {
  const summary = el("environmentSummary");
  if (!summary) return;
  if (!report) {
    summary.innerHTML = `<div class="envEmpty">${translate("message.environment_required")}</div>`;
    return;
  }
  const checks = Array.isArray(report.checks) ? report.checks : [];
  const blockers = Array.isArray(report.blockers) ? report.blockers : [];
  summary.innerHTML = [
    `<div class="envChecks">${checks.map(renderEnvironmentCheck).join("") || `<div class="envEmpty">${translate("common.none")}</div>`}</div>`,
    blockers.length
      ? `<div class="envBlockers"><strong>${translate("summary.blockers")}</strong>${blockers
          .map((blocker) => `<span>${escapeHtml(String(blocker.description || blocker.message || blocker.id || ""))}</span>`)
          .join("")}</div>`
      : "",
  ].join("");
}

function renderEnvironmentCheck(check) {
  const status = safeClass(check.status || "unknown");
  const required = check.required ? "" : ` · ${t("status.skipped")}`;
  return `
    <div class="envCheck status-${status}">
      <strong>${environmentCheckLabel(check.name)}</strong>
      <span>${statusText(check.status)}${required}</span>
      <small>${escapeHtml(String(check.summary || ""))}</small>
    </div>`;
}

function environmentCheckLabel(name) {
  const key = `env.${String(name || "")}`;
  return I18N[state.language]?.[key] || formatLabel(name);
}

function setEnvironmentReport(report) {
  state.environmentReport = report;
  state.environmentReady = Boolean(report && report.status === "ready");
  const badge = el("environmentBadge");
  const checking = state.environmentChecking;
  badge.textContent = checking ? t("config.checking") : state.environmentReady ? t("config.ready") : report ? t("config.blocked") : t("config.not_checked");
  badge.className = `readinessBadge status-${checking ? "running" : state.environmentReady ? "ready" : report ? "blocked" : "unknown"}`;
  renderEnvironmentSummary(report);
  setControls();
}

function setSourceType(type) {
  if (!state.environmentReady || !SOURCE_TYPES.includes(type)) return;
  if (state.sourceLocked && state.sourceType && state.sourceType !== type) return;
  state.sourceType = type;
  state.sourceLocked = true;
  updateSourceCards();
  setControls();
}

function resetSourceChoice() {
  state.sourceType = "";
  state.sourceLocked = false;
  state.projectSourceType = "";
  state.uploadedDocumentPaths = [];
  if (el("uploadFiles")) {
    el("uploadFiles").value = "";
  }
  renderFileSelection();
  show("eventOutput", [{ level: "info", message: t("message.source_reset") }]);
  updateSourceCards();
  setControls();
}

function updateSourceCards() {
  const devPanel = el("sourceCards")?.closest(".devPanel");
  const lockBadge = el("developmentLockBadge");
  if (devPanel) {
    devPanel.classList.toggle("locked", !state.environmentReady);
  }
  if (lockBadge) {
    lockBadge.textContent = state.environmentReady ? (state.sourceLocked ? t("source.selected") : t("source.unlocked")) : t("source.locked");
    lockBadge.className = `readinessBadge status-${state.environmentReady ? "ready" : "blocked"}`;
  }
  document.querySelectorAll("[data-source-card]").forEach((card) => {
    const type = card.dataset.sourceCard || "";
    const selected = state.sourceType === type;
    const disabled = !state.environmentReady || (state.sourceLocked && !selected);
    card.classList.toggle("selected", selected);
    card.classList.toggle("unavailable", disabled);
    card.querySelectorAll("input, textarea").forEach((node) => {
      if (node.classList.contains("sourceRadio")) {
        node.checked = selected;
      }
      node.disabled = disabled;
    });
  });
}

function renderDelivery(delivery) {
  state.delivery = delivery;
  const report = delivery.delivery_report || {};
  const gate = report.final_gate || {};
  const github = report.github || {};
  const merge = github.merge || {};
  const artifact = report.artifact || {};
  const requirements = report.requirements || {};
  const prUrl = realPullRequestUrl(github.pull_request_url);
  const localOnly = Boolean(delivery.local_delivery) && !prUrl;
  const parts = [
    [t("summary.status"), statusText(report.status || delivery.status || "-")],
    [t("summary.gate"), gate.score ?? "-"],
    [t("summary.pr"), prUrl || (localOnly ? t("delivery.local_only") : "-")],
    [t("summary.ci"), statusText(github.ci_status || "-")],
    [t("summary.merge"), statusText(merge.status || "-")],
    [t("summary.artifact"), artifact.profile || "-"],
    [t("summary.semantic"), statusText(artifact.semantic_status || artifact.semantic_probe?.status || "-")],
    [t("summary.scenarios"), statusText(artifact.scenario_status || artifact.scenario_probe?.status || artifact.acceptance_scenarios?.status || "-")],
    [t("summary.gameplay"), statusText(artifact.gameplay_status || artifact.gameplay_probe?.status || "-")],
    [t("summary.coverage"), requirements.coverage_score ?? "-"],
  ];
  renderDeliveryChrome(delivery, report, gate);
  el("deliverySummary").innerHTML = parts
    .map(([label, value]) => `<div><strong>${label}</strong><span>${escapeHtml(String(value))}</span></div>`)
    .join("");
  renderScoreExplanation(delivery);
  renderCentralReview(delivery.central_review || null);
  renderAutoIteration(delivery);
  renderEvidence(delivery.delivery_evidence || fallbackEvidence(delivery));
  renderArtifactPreviews(delivery.artifact_manifest || {});
  renderDeliveryActions(deliveryActionsFor(delivery));
  renderCoverageViz(delivery.requirement_coverage || {});
  renderDeliveryStatusFallback(delivery);
  show("deliveryOutput", delivery);
}

function renderDeliveryChrome(delivery = {}, report = {}, gate = {}) {
  const status = String(report.status || delivery.status || "unknown");
  const ready = Boolean(report.ready_for_review) || status === "ready";
  const blocked = status === "blocked" || status === "failed" || status === "needs_iteration";
  const badge = el("readinessBadge");
  badge.textContent = ready ? t("delivery.ready_for_review") : blocked ? t("delivery.needs_iteration") : status === "unknown" ? t("delivery.no_delivery") : statusText(status);
  badge.className = `readinessBadge status-${ready ? "passed" : blocked ? "failed" : safeClass(status)}`;
  const score = gate.score ?? report.score ?? "-";
  el("gateScore").textContent = score === "-" ? "-" : String(score);
}

function resetDelivery() {
  state.delivery = null;
  state.evidenceIndex = null;
  state.evidencePackage = null;
  state.evidenceReadiness = null;
  state.evidenceToolResult = null;
  renderDeliveryChrome({}, {}, {});
  el("deliverySummary").innerHTML = "";
  el("evidenceCards").innerHTML = "";
  el("evidenceDetails").innerHTML = "";
  el("artifactPreviews").innerHTML = "";
  el("deliveryActions").innerHTML = "";
  if (el("deliveryActionFeedback")) {
    el("deliveryActionFeedback").innerHTML = "";
    el("deliveryActionFeedback").classList.remove("visible");
    delete el("deliveryActionFeedback").dataset.autoIterationActive;
  }
  if (el("scoreExplanation")) {
    el("scoreExplanation").innerHTML = "";
    el("scoreExplanation").classList.remove("visible");
  }
  renderCentralReview(null);
  renderAutoIteration(null);
  el("coverageViz").innerHTML = "";
  show("deliveryOutput", {});
  renderReadinessReport({});
}

function renderRunStatus(snapshot) {
  const panel = el("runProgressPanel");
  const stopButton = el("progressStopRun");
  if (!panel) return;
  if (!snapshot) {
    panel.className = "runProgressPanel idle";
    el("progressTitle").textContent = t("progress.waiting");
    el("progressPercent").textContent = "0%";
    el("progressFill").style.width = "0%";
    el("progressSummary").textContent = t("progress.choose_source");
    renderRoadmapProgress(null);
    renderCentralReviewProgress(null);
    el("progressTasks").textContent = "-";
    el("progressActivity").textContent = "-";
    if (stopButton) {
      stopButton.hidden = true;
      stopButton.disabled = true;
    }
    return;
  }
  const percent = Math.max(0, Math.min(100, Number(snapshot.progress_percent || 0)));
  const phase = String(snapshot.phase || "choose_source");
  const tasks = snapshot.tasks || {};
  panel.className = `runProgressPanel phase-${safeClass(phase)} status-${safeClass(snapshot.status || "unknown")}${snapshot.is_stalled ? " stalled" : ""}`;
  el("progressTitle").textContent = t(`phase.${phase}`) || statusText(snapshot.status || "");
  el("progressPercent").textContent = `${percent}%`;
  el("progressFill").style.width = `${percent}%`;
  el("progressSummary").textContent = snapshot.is_stalled ? t("progress.stalled") : String(snapshot.summary || "");
  renderRoadmapProgress(snapshot.roadmap_progress || null);
  renderCentralReviewProgress(snapshot.central_review || null);
  el("progressTasks").textContent = `${t("progress.tasks")}: ${Number(tasks.completed || 0)}/${Number(tasks.total || 0)}`;
  const elapsed = formatDuration(Number(snapshot.elapsed_seconds || 0));
  const last = formatDuration(Number(snapshot.last_activity_seconds || 0));
  el("progressActivity").textContent = `${t("progress.elapsed")}: ${elapsed} · ${t("progress.last_activity")}: ${last}`;
  if (stopButton) {
    const running = isRunStoppable(snapshot.status);
    stopButton.hidden = !running;
    stopButton.disabled = !running || !state.runId;
  }
}

function renderRoadmapProgress(progress) {
  const node = el("roadmapProgress");
  if (!node) return;
  if (!progress || !progress.enabled) {
    node.hidden = true;
    node.innerHTML = "";
    return;
  }
  const current = progress.current_phase || {};
  const title = current.title || "";
  node.hidden = false;
  node.innerHTML = `
    <strong>${escapeHtml(t("progress.roadmap"))}: ${Number(progress.completed || 0)}/${Number(progress.total || 0)}</strong>
    <span>${escapeHtml(String(title || ""))}</span>
  `;
}

function renderCentralReviewProgress(review) {
  const node = el("centralReviewProgress");
  if (!node) return;
  if (!review) {
    node.innerHTML = "";
    node.classList.remove("visible");
    return;
  }
  const decision = String(review.decision || "wait_for_input");
  node.className = `centralReviewProgress visible status-${safeClass(review.status || decision)}`;
  node.innerHTML = `
    <strong>${escapeHtml(t(`central.decision.${decision}`) || decision)}</strong>
    <span>${escapeHtml(String(review.summary || t("central.waiting")))}</span>
  `;
}

function renderCentralReview(review) {
  const node = el("centralReviewCard");
  if (!node) return;
  if (!review) {
    node.innerHTML = "";
    node.classList.remove("visible");
    return;
  }
  const decision = String(review.decision || "wait_for_input");
  const missing = Array.isArray(review.missing_loop_steps) ? review.missing_loop_steps : [];
  const completed = Array.isArray(review.completed_loop_steps) ? review.completed_loop_steps : [];
  const actions = Array.isArray(review.next_actions) ? review.next_actions : [];
  node.className = `centralReviewCard visible status-${safeClass(review.status || decision)}`;
  node.innerHTML = `
    <header>
      <div>
        <strong>${translate("central.title")}</strong>
        <span>${escapeHtml(t(`central.decision.${decision}`) || decision)} · ${Math.round(Number(review.confidence || 0) * 100)}%</span>
      </div>
    </header>
    <p>${escapeHtml(String(review.summary || t("central.waiting")))}</p>
    ${state.advancedVisible ? `
      <div class="centralReviewGrid">
        ${centralReviewList("central.next_actions", actions)}
        ${centralReviewList("central.missing_steps", missing)}
        ${centralReviewList("central.completed_steps", completed.slice(0, 8))}
      </div>
    ` : ""}
  `;
}

function renderAutoIteration(delivery) {
  const container = el("deliveryActionFeedback");
  if (!container) return;
  const review = delivery?.central_review || {};
  const plan = delivery?.repair_plan || {};
  const autoExecution = plan.auto_execution || {};
  const available = String(review.decision || "") === "iterate" && Boolean(autoExecution.allowed);
  if (!available) {
    container.innerHTML = "";
    container.classList.remove("visible");
    delete container.dataset.autoIterationActive;
    return;
  }
  container.dataset.autoIterationActive = "true";
  const itemCount = Array.isArray(plan.items) ? plan.items.length : 0;
  container.classList.add("visible");
  container.innerHTML = `
    <div class="autoIterationPrompt">
      <div>
        <strong>${escapeHtml(t("auto_iteration.action"))}</strong>
        <span>${escapeHtml(plan.summary || review.summary || "")}</span>
      </div>
      <button type="button" class="primaryButton" id="continueOptimizing" ${state.environmentReady ? "" : "disabled"}>${escapeHtml(t("auto_iteration.action"))}</button>
    </div>
    ${state.advancedVisible ? `
      <details class="autoIterationDetails">
        <summary>${escapeHtml(t("auto_iteration.plan"))} · ${itemCount}</summary>
        <pre>${escapeHtml(JSON.stringify(plan, null, 2))}</pre>
      </details>
    ` : ""}
  `;
  const button = el("continueOptimizing");
  if (button) {
    button.addEventListener("click", () => startAutoIteration().catch(showError));
  }
}

function centralReviewList(titleKey, values) {
  const items = Array.isArray(values) ? values.filter(Boolean).slice(0, 6) : [];
  return `
    <section>
      <h3>${translate(titleKey)}</h3>
      <ul>${items.length ? items.map((item) => `<li>${escapeHtml(String(item))}</li>`).join("") : `<li>${translate("common.none")}</li>`}</ul>
    </section>
  `;
}

function isRunStoppable(status) {
  return ["queued", "running", "paused"].includes(String(status || "").toLowerCase());
}

function renderDeliveryStatusFallback(delivery) {
  const existingStatus = String(state.runStatusSnapshot?.status || "").toLowerCase();
  if (existingStatus && existingStatus !== "unknown") return;
  const status = String(delivery.status || "").toLowerCase();
  if (!status) return;
  const tasks = taskCountsFromDelivery(delivery);
  renderRunStatus({
    status,
    phase: status === "done" ? "ready" : "blocked",
    progress_percent: status === "done" ? 100 : 0,
    summary: status === "done" ? t("progress.delivery_loaded") : statusText(status),
    tasks,
    elapsed_seconds: 0,
    last_activity_seconds: 0,
  });
}

function taskCountsFromDelivery(delivery) {
  const graph = delivery.runtime_state?.task_graph || {};
  const nodes = Array.isArray(graph.nodes) ? graph.nodes : [];
  if (!nodes.length) return {};
  const completed = nodes.filter((node) => ["completed", "done", "passed"].includes(String(node.status || "").toLowerCase())).length;
  const running = nodes.filter((node) => ["running", "in_progress", "active"].includes(String(node.status || "").toLowerCase())).length;
  const failed = nodes.filter((node) => ["failed", "blocked"].includes(String(node.status || "").toLowerCase())).length;
  return { total: nodes.length, completed, running, failed };
}

function renderDeliveryActions(actions) {
  const container = el("deliveryActions");
  if (!container) return;
  const allActions = Array.isArray(actions) ? actions : [];
  const list = state.advancedVisible ? allActions : allActions.filter((action) => Boolean(action.enabled));
  if (!list.length) {
    container.innerHTML = "";
    return;
  }
  container.innerHTML = `
    <h3>${translate("delivery.actions")}</h3>
    <div class="deliveryActionGrid">
      ${list.map(renderDeliveryAction).join("")}
    </div>
  `;
}

function renderDeliveryAction(action) {
  const enabled = Boolean(action.enabled);
  const label = state.language === "zh" ? String(action.label_zh || action.label || action.id || "") : String(action.label || action.id || "");
  const description = state.language === "zh"
    ? String(action.description_zh || action.description || "")
    : String(action.description || "");
  const className = `deliveryAction ${enabled ? "" : "disabled"} kind-${safeClass(action.kind || action.id)}`;
  const url = String(action.url || "");
  const actionId = String(action.id || "");
  const buttonType = actionId === "open_result" ? "button" : "a";
  if (enabled && url && String(action.method || "GET").toUpperCase() === "GET") {
    if (buttonType === "button") {
      return `
        <button type="button" class="${className}" data-delivery-action="${escapeHtml(actionId)}" data-delivery-url="${escapeHtml(url)}">
          <strong>${escapeHtml(label)}</strong>
          <span>${escapeHtml(description)}</span>
        </button>
      `;
    }
    return `
      <a class="${className}" data-delivery-action="${escapeHtml(actionId)}" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">
        <strong>${escapeHtml(label)}</strong>
        <span>${escapeHtml(description)}</span>
      </a>
    `;
  }
  return `
    <button type="button" class="${className}" data-delivery-action="${escapeHtml(actionId)}" ${enabled ? "" : "disabled"}>
      <strong>${escapeHtml(label)}</strong>
      <span>${escapeHtml(description)}</span>
    </button>
  `;
}

function deliveryActionsFor(delivery) {
  const actions = Array.isArray(delivery.delivery_actions) ? delivery.delivery_actions : [];
  return actions.length ? actions : fallbackDeliveryActions(delivery);
}

function allDeliveryActions() {
  const fromDelivery = state.delivery ? deliveryActionsFor(state.delivery) : [];
  const fromStatus = state.runStatusSnapshot && Array.isArray(state.runStatusSnapshot.delivery_actions)
    ? state.runStatusSnapshot.delivery_actions
    : [];
  const seen = new Set();
  return [...fromDelivery, ...fromStatus].filter((action) => {
    const id = String(action.id || "");
    if (!id || seen.has(id)) return false;
    seen.add(id);
    return true;
  });
}

function fallbackDeliveryActions(delivery) {
  const actions = [];
  const artifact = bestDeliveryArtifact(delivery.artifact_manifest || {});
  if (artifact && artifact.url) {
    actions.push({
      id: "open_result",
      kind: "browser",
      label: "Open result",
      label_zh: "打开作品",
      enabled: true,
      url: artifact.url,
      description: "Open the generated result in a browser tab.",
      description_zh: "在浏览器中打开生成结果。",
    });
  }
  const runId = state.runId || delivery.latest_run_id || "";
  if (state.projectId && runId) {
    actions.push({
      id: "open_folder",
      kind: "local_folder",
      label: "Open folder",
      label_zh: "打开结果文件夹",
      enabled: true,
      url: `/projects/${state.projectId}/runs/${runId}/open-folder`,
      method: "POST",
      description: "Open the folder that contains the generated result.",
      description_zh: "打开保存生成结果的文件夹。",
    });
  }
  return actions;
}

function bestDeliveryArtifact(manifest) {
  const items = Array.isArray(manifest.items) ? manifest.items : [];
  if (!items.length) return null;
  const htmlIndex = items.find((item) => String(item.path || "").toLowerCase().endsWith("index.html") && item.url);
  if (htmlIndex) return htmlIndex;
  const html = items.find((item) => String(item.media_type || "").startsWith("text/html") && item.url);
  if (html) return html;
  return items.find((item) => item.url && ["text", "image"].includes(String(item.preview || ""))) || items.find((item) => item.url) || null;
}

function renderScoreExplanation(delivery) {
  const container = el("scoreExplanation");
  if (!container) return;
  const report = delivery.delivery_report || {};
  const gate = report.final_gate || {};
  const score = Number(gate.score ?? report.score ?? 0);
  const reasons = scoreReasonsForDelivery(delivery);
  if (!score && !reasons.length) {
    container.innerHTML = "";
    container.classList.remove("visible");
    return;
  }
  const title = score >= 0.95
    ? t("score.excellent")
    : score >= 0.85
      ? t("score.pass_with_gaps")
      : t("score.needs_work");
  container.innerHTML = `
    <header>
      <strong>${translate("score.title")}</strong>
      <span>${translate("summary.score")}: ${escapeHtml(String(score || "-"))}</span>
    </header>
    <span>${escapeHtml(title)}</span>
    ${reasons.length ? `<ul>${reasons.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("\n")}</ul>` : ""}
    <span>${translate("score.improve")}</span>
  `;
  container.classList.add("visible");
}

function scoreReasonsForDelivery(delivery) {
  const report = delivery.delivery_report || {};
  const gate = report.final_gate || {};
  const requirements = report.requirements || {};
  const artifact = report.artifact || {};
  const github = report.github || {};
  const cycle = delivery.development_cycle || report.development_cycle || {};
  const reasons = [];
  const missingMust = Array.isArray(requirements.missing_must_requirement_ids) ? requirements.missing_must_requirement_ids.length : Number(requirements.missing_must || 0);
  const partialMust = Array.isArray(requirements.partial_must_requirement_ids) ? requirements.partial_must_requirement_ids.length : Number(requirements.partial_must || 0);
  if (missingMust || partialMust || String(requirements.status || "").toLowerCase() === "failed") {
    reasons.push(t("score.reason_requirements"));
  }
  const browserStatus = artifact.browser_status || artifact.browser_probe?.status || "";
  const scenarioStatus = artifact.scenario_status || artifact.scenario_probe?.status || artifact.acceptance_scenarios?.status || "";
  const gameplayStatus = artifact.gameplay_status || artifact.gameplay_probe?.status || "";
  const hasCanvasGame = String(artifact.profile || "").includes("canvas") || String(artifact.profile || "").includes("game");
  if (["failed", "missing", "partial", "blocked"].some((status) => [browserStatus, scenarioStatus, gameplayStatus].map((value) => String(value).toLowerCase()).includes(status))) {
    reasons.push(t("score.reason_browser"));
  } else if ((!browserStatus || !gameplayStatus) && hasCanvasGame) {
    reasons.push(t("score.reason_browser"));
  } else if (String(scenarioStatus).toLowerCase() === "generated" && !browserStatus) {
    reasons.push(t("score.reason_browser"));
  }
  if (cycle && !["", "passed", "done", "completed"].includes(String(cycle.status || "").toLowerCase())) {
    reasons.push(t("score.reason_cycle"));
  }
  const prUrl = realPullRequestUrl(github.pull_request_url);
  const mergeStatus = github.merge?.status || github.merge_status || "";
  if (delivery.local_delivery || !prUrl || ["skipped", "dry_run", "unavailable"].includes(String(mergeStatus).toLowerCase())) {
    reasons.push(t("score.reason_github"));
  }
  const hardFailures = Array.isArray(gate.hard_failures) ? gate.hard_failures : [];
  const requiredChanges = Array.isArray(gate.required_changes) ? gate.required_changes : [];
  const blockers = Array.isArray(delivery.delivery_evidence?.blockers) ? delivery.delivery_evidence.blockers : [];
  if (hardFailures.length || requiredChanges.length || blockers.length) {
    reasons.push(t("score.reason_blockers"));
  }
  return [...new Set(reasons)].slice(0, 5);
}

function renderEvidence(evidence) {
  const cards = Array.isArray(evidence.cards) ? evidence.cards : [];
  el("evidenceCards").innerHTML = cards
    .map((card) => `
      <article class="evidenceCard status-${safeClass(card.status)}">
        <strong>${escapeHtml(String(card.label || "-"))}</strong>
        <span>${escapeHtml(String(card.value || "-"))}</span>
        <small>${escapeHtml(String(card.detail || statusText(card.status) || ""))}</small>
      </article>
    `)
    .join("");
  renderEvidenceDetails(evidence);
}

function renderEvidenceDetails(evidence) {
  const requirements = evidence.requirements || {};
  const probes = evidence.probes || {};
  const nativeTests = evidence.native_ui_tests || {};
  const github = evidence.github || {};
  const cycle = evidence.development_cycle || {};
  const comparison = evidence.recovery_comparison || {};
  const repairSuggestions = Array.isArray(evidence.repair_suggestions) ? evidence.repair_suggestions : (Array.isArray(comparison.repair_suggestions) ? comparison.repair_suggestions : []);
  const blockers = Array.isArray(evidence.blockers) ? evidence.blockers : [];
  const nextActions = Array.isArray(evidence.next_actions) ? evidence.next_actions : [];
  const probeRows = ["semantic", "scenario", "gameplay"]
    .map((name) => probes[name] || { label: name, status: "" })
    .map((probe) => `<li><strong>${escapeHtml(String(probe.label || "-"))}</strong><span>${escapeHtml(String(probe.status || "-"))}</span></li>`)
    .join("");
  const cycleSteps = Array.isArray(cycle.steps) ? cycle.steps.slice(0, 8) : [];
  const probeChanges = Array.isArray(comparison.probe_changes) ? comparison.probe_changes.slice(0, 8) : [];
  el("evidenceDetails").innerHTML = `
    <section>
      <h3>${translate("evidence.requirements")}</h3>
      <p>${escapeHtml(String(requirements.covered ?? 0))}/${escapeHtml(String(requirements.total ?? 0))} ${translate("evidence.covered")} · ${escapeHtml(String(requirements.partial ?? 0))} ${translate("evidence.partial")} · ${escapeHtml(String(requirements.missing ?? 0))} ${translate("evidence.missing")}</p>
      <p>${translate("evidence.must_gaps")}: ${escapeHtml(String(requirements.missing_must ?? 0))} ${translate("evidence.missing")}, ${escapeHtml(String(requirements.partial_must ?? 0))} ${translate("evidence.partial")}</p>
    </section>
    <section>
      <h3>${translate("evidence.browser_probes")}</h3>
      <ul>${probeRows || `<li><strong>Probe</strong><span>-</span></li>`}</ul>
    </section>
    <section>
      <h3>${translate("evidence.native_ui_tests")}</h3>
      <p>${escapeHtml(statusText(nativeTests.status || "-"))} · ${escapeHtml(String(nativeTests.framework || t("common.none")))} · ${escapeHtml(String(nativeTests.write_mode || "-"))}</p>
      <p>${escapeHtml(String(nativeTests.target_path || nativeTests.summary || "-"))}</p>
    </section>
    <section>
      <h3>${translate("evidence.github")}</h3>
      <p>${escapeHtml(String(github.branch || "-"))} · CI ${escapeHtml(statusText(github.ci_status || "-"))} · Merge ${escapeHtml(statusText(github.merge_status || "-"))}</p>
      <p>${realPullRequestUrl(github.pull_request_url) ? `<a href="${escapeHtml(realPullRequestUrl(github.pull_request_url))}" target="_blank" rel="noreferrer">${translate("evidence.pull_request")}</a>` : "-"}</p>
    </section>
    <section>
      <h3>${translate("evidence.development_cycle")}</h3>
      <p>${escapeHtml(statusText(cycle.status || "-"))} · ${escapeHtml(String(cycle.passed_steps ?? 0))}/${escapeHtml(String(cycle.total_steps ?? 0))} ${translate("evidence.steps")} · ${translate("summary.score")} ${escapeHtml(String(cycle.score ?? 0))}</p>
      <ul>${cycleSteps.map((step) => `<li><strong>${escapeHtml(String(step.name || "-"))}</strong><span>${escapeHtml(statusText(step.status || "-"))}</span></li>`).join("")}</ul>
    </section>
    <section>
      <h3>${translate("evidence.repair_comparison")}</h3>
      <p>${escapeHtml(statusText(comparison.status || "-"))} · ${translate("evidence.source")} ${escapeHtml(String(comparison.source_run_id || "-"))} · ${translate("evidence.current")} ${escapeHtml(String(comparison.current_run_id || "-"))}</p>
      <p>${translate("summary.score")} ${formatDelta(comparison.score_delta)} · ${translate("summary.coverage")} ${formatDelta(comparison.coverage_delta)} · ${translate("summary.blockers")} ${formatDelta(comparison.blocker_delta)}</p>
      <ul>${repairRows(comparison, probeChanges)}</ul>
      <h4>${translate("evidence.repair_suggestions")}</h4>
      <ul>${repairSuggestionRows(repairSuggestions)}</ul>
    </section>
    <section>
      <h3>${translate("summary.blockers")}</h3>
      <ul>${blockers.length ? blockers.map((item) => `<li><strong>${escapeHtml(String(item.id || item.type || "blocker"))}</strong><span>${escapeHtml(String(item.description || item.message || item))}</span></li>`).join("") : `<li><strong>${translate("common.none")}</strong><span>${translate("common.no_blockers")}</span></li>`}</ul>
    </section>
    <section>
      <h3>${translate("evidence.next_actions")}</h3>
      <ul>${nextActions.length ? nextActions.map((item) => `<li><strong>${translate("evidence.action")}</strong><span>${escapeHtml(String(item))}</span></li>`).join("") : `<li><strong>${translate("common.none")}</strong><span>${translate("common.no_next_action")}</span></li>`}</ul>
    </section>
  `;
}

function renderArtifactPreviews(manifest) {
  const items = Array.isArray(manifest.items) ? manifest.items : [];
  const container = el("artifactPreviews");
  const visibleItems = artifactItemsForDisplay(items);
  if (!visibleItems.length) {
    container.innerHTML = "";
    return;
  }
  const hiddenCount = Math.max(0, items.length - visibleItems.length);
  container.innerHTML = `
    <h3>${translate("evidence.artifacts")}</h3>
    ${hiddenCount > 0 && !state.advancedVisible ? `<p class="artifactHint">${escapeHtml(String(hiddenCount))} ${translate("artifact.hidden_sources")}</p>` : ""}
    <div class="artifactGrid">
      ${visibleItems.map(renderArtifactItem).join("")}
    </div>
  `;
}

function artifactItemsForDisplay(items) {
  const list = Array.isArray(items) ? items : [];
  if (state.advancedVisible) return list;
  const runnable = list.filter((item) => isRunnableArtifact(item));
  return runnable.length ? runnable : list.filter((item) => String(item.preview || "") === "image");
}

function isRunnableArtifact(item) {
  const path = String(item.path || "").toLowerCase();
  const mediaType = String(item.media_type || "").toLowerCase();
  return Boolean(item.url) && (mediaType.startsWith("text/html") || path.endsWith("index.html") || path.endsWith(".html") || path.endsWith(".htm"));
}

function renderArtifactItem(item) {
  const label = escapeHtml(String(item.label || item.kind || "Artifact"));
  const path = escapeHtml(String(item.path || "-"));
  const mediaType = escapeHtml(String(item.media_type || ""));
  const url = escapeHtml(String(item.url || "#"));
  const size = Number(item.size_bytes || 0);
  const sizeText = size ? `${Math.ceil(size / 1024)} KB` : "-";
  const preview = String(item.preview || "");
  const body = preview === "image"
    ? `<a class="artifactThumb" href="${url}" target="_blank" rel="noreferrer"><img src="${url}" alt="${label}"></a>`
    : `<a class="artifactOpen" href="${url}" target="_blank" rel="noreferrer">${translate("common.open_preview")}</a>`;
  return `
    <article class="artifactItem">
      ${body}
      <strong>${label}</strong>
      <span>${path}</span>
      <small>${mediaType} · ${escapeHtml(sizeText)}</small>
    </article>
  `;
}

function renderGraphViz(graph) {
  const container = el("graphViz");
  const nodes = Array.isArray(graph.nodes) ? graph.nodes : [];
  if (!nodes.length) {
    container.innerHTML = "";
    return;
  }
  const statusCounts = countBy(nodes, (node) => node.status || "pending");
  const agentCounts = countBy(nodes, (node) => node.assigned_agent || "unassigned");
  const blocked = nodes.filter((node) => Array.isArray(node.dependencies) && node.dependencies.length > 0).length;
  container.innerHTML = `
    <div class="vizStats">
      ${statPill(t("summary.tasks"), nodes.length)}
      ${statPill(t("summary.agents"), Object.keys(agentCounts).length)}
      ${statPill(t("summary.with_deps"), blocked)}
    </div>
    <div class="vizBars">${Object.entries(statusCounts).map(([label, value]) => vizBar(label, value, nodes.length, `status-${safeClass(label)}`)).join("")}</div>
    <div class="agentStrip">${Object.entries(agentCounts).map(([label, value]) => `<span>${escapeHtml(label)} ${escapeHtml(String(value))}</span>`).join("")}</div>
    <div class="taskRail">
      ${nodes.map(taskNodeCard).join("")}
    </div>
  `;
}

function taskNodeCard(node) {
  const dependencies = Array.isArray(node.dependencies) ? node.dependencies : [];
  const criteria = Array.isArray(node.completion_criteria) ? node.completion_criteria : [];
  return `
    <article class="taskNode status-${safeClass(node.status || "pending")}">
      <header>
        <strong>${escapeHtml(String(node.id || "-"))}</strong>
        <span>${escapeHtml(String(node.assigned_agent || node.type || "-"))}</span>
      </header>
      <p>${escapeHtml(String(node.title || node.description || "-"))}</p>
      <small>deps ${escapeHtml(dependencies.length ? dependencies.join(", ") : t("common.none"))} · ${escapeHtml(String(criteria.length))} criteria</small>
    </article>
  `;
}

function renderCoverageViz(coverage) {
  const container = el("coverageViz");
  const entries = Array.isArray(coverage.entries) ? coverage.entries : [];
  if (!entries.length) {
    container.innerHTML = "";
    return;
  }
  const counts = countBy(entries, (entry) => entry.coverage_status || "missing");
  const mustGaps = [
    ...(Array.isArray(coverage.missing_must_requirement_ids) ? coverage.missing_must_requirement_ids : []),
    ...(Array.isArray(coverage.partial_must_requirement_ids) ? coverage.partial_must_requirement_ids : []),
  ];
  container.innerHTML = `
    <h3>${translate("evidence.requirement_coverage")}</h3>
    <div class="vizStats">
      ${statPill(t("summary.requirements"), entries.length)}
      ${statPill(t("summary.score"), coverage.coverage_score ?? 0)}
      ${statPill(t("summary.must_gaps"), mustGaps.length)}
    </div>
    <div class="vizBars">${Object.entries(counts).map(([label, value]) => vizBar(label, value, entries.length, `status-${safeClass(label)}`)).join("")}</div>
    <div class="coverageMatrix">
      ${entries.slice(0, 12).map(coverageRow).join("")}
    </div>
  `;
}

function coverageRow(entry) {
  const files = Array.isArray(entry.implementation_files) ? entry.implementation_files : [];
  const tasks = Array.isArray(entry.planned_task_ids) ? entry.planned_task_ids : [];
  return `
    <article class="coverageRow status-${safeClass(entry.coverage_status || "missing")}">
      <header>
        <strong>${escapeHtml(String(entry.requirement_id || "-"))}</strong>
        <span>${escapeHtml(String(entry.coverage_status || "missing"))}</span>
      </header>
      <p>${escapeHtml(String(entry.text || ""))}</p>
      <small>${escapeHtml(files.slice(0, 3).join(", ") || t("common.no_files"))} · tasks ${escapeHtml(tasks.join(", ") || "-")}</small>
    </article>
  `;
}

function setDeliveryTab(tab) {
  state.deliveryTab = tab || "overview";
  document.querySelectorAll("[data-delivery-tab]").forEach((button) => {
    const selected = button.dataset.deliveryTab === state.deliveryTab;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-selected", selected ? "true" : "false");
  });
  document.querySelectorAll("[data-delivery-view]").forEach((view) => {
    view.classList.toggle("active", view.dataset.deliveryView === state.deliveryTab);
  });
}

function bindDeliveryTabs() {
  document.querySelectorAll("[data-delivery-tab]").forEach((button) => {
    button.addEventListener("click", () => setDeliveryTab(button.dataset.deliveryTab || "overview"));
  });
}

function evidenceRootPayload() {
  const roots = (el("evidenceRoot").value.trim() || ".alchemy")
    .split(/[,;\n]/)
    .map((value) => value.trim())
    .filter(Boolean);
  return { roots: roots.length ? roots : [".alchemy"] };
}

async function runEvidenceIndex() {
  const output = el("evidenceIndexOutput").value.trim() || ".alchemy/ui_evidence_index.json";
  const result = await api("/evidence/index", {
    method: "POST",
    body: {
      ...evidenceRootPayload(),
      output,
    },
  });
  state.evidenceIndex = result;
  el("evidenceIndexPath").value = String(result.output_path || output);
  renderEvidenceToolResult("delivery.evidence_index", result, [
    ["summary.status", statusText(result.status || "-")],
    ["summary.entries", result.summary?.total ?? 0],
    ["summary.blocked", result.summary?.blocked_or_failed ?? 0],
  ]);
  setDeliveryTab("readiness");
}

async function runEvidencePackage() {
  const output = el("evidencePackageOutput").value.trim() || ".alchemy/ui_evidence_package";
  const result = await api("/evidence/package", {
    method: "POST",
    body: {
      ...evidenceRootPayload(),
      output,
      clean_output: true,
    },
  });
  state.evidencePackage = result;
  const outputDir = String(result.output_dir || output);
  el("evidencePackagePath").value = `${outputDir.replace(/[\\/]$/, "")}/evidence_package_manifest.json`;
  renderEvidenceToolResult("delivery.evidence_package", result, [
    ["summary.status", statusText(result.status || "-")],
    ["summary.files", result.summary?.file_count ?? 0],
    ["summary.blockers", result.summary?.blocker_count ?? (Array.isArray(result.blockers) ? result.blockers.length : 0)],
  ]);
  setDeliveryTab("readiness");
}

async function runEvidenceReadiness() {
  const result = await api("/evidence/readiness", {
    method: "POST",
    body: {
      evidence_index: el("evidenceIndexPath").value.trim(),
      evidence_package: el("evidencePackagePath").value.trim(),
      benchmark_regression: el("benchmarkRegressionPath").value.trim(),
      output: el("evidenceReadinessOutput").value.trim() || ".alchemy/ui_evidence_readiness",
    },
  });
  state.evidenceReadiness = result;
  state.evidenceToolResult = null;
  renderReadinessReport(result);
  setDeliveryTab("readiness");
}

function renderEvidenceToolResult(titleKey, payload, metrics) {
  state.evidenceToolResult = { titleKey, payload, metrics };
  const status = String(payload.status || "unknown");
  const blockers = Array.isArray(payload.blockers) ? payload.blockers : [];
  el("readinessOutput").innerHTML = `
    <div class="readinessHeader">
      <div>
        <strong>${translate(titleKey)}</strong>
        <span>${escapeHtml(String(payload.output_path || payload.output_dir || ""))}</span>
      </div>
      <span class="readinessBadge status-${status === "passed" || status === "ready" ? "passed" : safeClass(status)}">${escapeHtml(statusText(status))}</span>
    </div>
    <div class="readinessMetrics">
      ${metrics.map(([label, value]) => `<span><strong>${escapeHtml(String(value))}</strong>${translate(label)}</span>`).join("")}
    </div>
    ${blockerList(blockers)}
  `;
}

function renderReadinessReport(report = {}) {
  const container = el("readinessOutput");
  if (!report || !report.status) {
    container.innerHTML = `
      <div class="readinessEmpty">
        <strong>${translate("evidence.awaiting_gate")}</strong>
        <span>${translate("evidence.awaiting_gate_detail")}</span>
      </div>
    `;
    return;
  }
  const status = String(report.status || "unknown");
  const checks = Array.isArray(report.checks) ? report.checks : [];
  const blockers = Array.isArray(report.blockers) ? report.blockers : [];
  const summary = report.summary || {};
  container.innerHTML = `
    <div class="readinessHeader">
      <div>
        <strong>${translate("delivery.evidence_readiness")}</strong>
        <span>${escapeHtml(String(report.output_dir || ""))}</span>
      </div>
      <span class="readinessBadge status-${status === "ready" ? "passed" : safeClass(status)}">${escapeHtml(statusText(status))}</span>
    </div>
    <div class="readinessMetrics">
      <span><strong>${escapeHtml(String(summary.passed_checks ?? 0))}</strong>${translate("summary.passed")}</span>
      <span><strong>${escapeHtml(String(summary.check_count ?? checks.length))}</strong>${translate("summary.checks")}</span>
      <span><strong>${escapeHtml(String(summary.blocker_count ?? blockers.length))}</strong>${translate("summary.blockers")}</span>
    </div>
    <div class="readinessChecks">
      ${checks.length ? checks.map(readinessCheckRow).join("") : `<div class="readinessCheck"><strong>${translate("evidence.no_checks")}</strong><span>-</span></div>`}
    </div>
    ${blockerList(blockers)}
  `;
}

function readinessCheckRow(check) {
  const status = String(check.status || "unknown");
  const passed = status === "passed";
  const message = passed ? "" : String(check.message || "");
  return `
    <div class="readinessCheck status-${safeClass(status)}">
      <strong>${escapeHtml(checkLabel(check.name || "-"))}</strong>
      <span>${escapeHtml(statusText(status))}</span>
      ${message ? `<small>${escapeHtml(message)}</small>` : ""}
    </div>
  `;
}

function blockerList(blockers) {
  if (!Array.isArray(blockers) || !blockers.length) {
    return `
      <div class="readinessBlockers empty">
        <strong>${translate("summary.blockers")}</strong>
        <span>${translate("common.none")}</span>
      </div>
    `;
  }
  return `
    <div class="readinessBlockers">
      <strong>${translate("summary.blockers")}</strong>
      ${blockers.map((item) => `
        <span>${escapeHtml(String(item.id || item.type || "blocker"))}: ${escapeHtml(String(item.description || item.message || item))}</span>
      `).join("")}
    </div>
  `;
}

function statPill(label, value) {
  return `<span><strong>${escapeHtml(String(value))}</strong>${escapeHtml(String(label))}</span>`;
}

function vizBar(label, value, total, className) {
  const percent = total ? Math.round((Number(value) / Number(total)) * 100) : 0;
  return `
    <div class="vizBar ${escapeHtml(className)}">
      <span>${escapeHtml(String(label))}</span>
      <meter min="0" max="100" value="${percent}"></meter>
      <strong>${escapeHtml(String(value))}</strong>
    </div>
  `;
}

function countBy(items, mapper) {
  return items.reduce((counts, item) => {
    const key = String(mapper(item) || "unknown");
    counts[key] = (counts[key] || 0) + 1;
    return counts;
  }, {});
}

function fallbackEvidence(delivery) {
  const report = delivery.delivery_report || {};
  const artifact = report.artifact || {};
  const requirements = report.requirements || {};
  const comparison = delivery.recovery_comparison || report.recovery_comparison || {};
  const cards = [
    { label: t("delivery.final_gate"), status: report.ready_for_review ? "passed" : "unknown", value: String(report.final_gate?.score ?? "-"), detail: report.summary || "" },
    { label: t("evidence.requirements"), status: requirements.status || "unknown", value: String(requirements.coverage_score ?? "-"), detail: t("summary.coverage") },
    { label: t("summary.artifact"), status: artifact.static_status || "unknown", value: artifact.profile || "-", detail: t("evidence.artifacts") },
  ];
  if (comparison.status) {
    cards.push({
      label: "Repair Comparison",
      status: comparisonCardStatus(comparison.status),
      value: `score delta ${formatDelta(comparison.score_delta)}`,
      detail: comparison.summary || "",
    });
  }
  return {
    cards,
    requirements,
    probes: {
      semantic: artifact.semantic_probe || {},
      scenario: artifact.scenario_probe || {},
      gameplay: artifact.gameplay_probe || {},
    },
    native_ui_tests: artifact.native_ui_tests || {},
    github: report.github || {},
    development_cycle: delivery.development_cycle || {},
    recovery_comparison: comparison,
    repair_suggestions: comparison.repair_suggestions || [],
    blockers: report.blockers || [],
    next_actions: report.next_actions || [],
  };
}

function comparisonCardStatus(status) {
  if (["improved", "same_passed"].includes(String(status))) return "passed";
  if (status === "mixed") return "partial";
  if (status === "regressed") return "failed";
  return "skipped";
}

function repairRows(comparison, probeChanges) {
  if (!comparison || !comparison.status) {
    return `<li><strong>${translate("common.none")}</strong><span>${translate("common.no_repair_comparison")}</span></li>`;
  }
  const rows = [
    ["Resolved must gaps", listValue(comparison.resolved_missing_must_requirement_ids)],
    ["New must gaps", listValue(comparison.new_missing_must_requirement_ids)],
    ["Resolved partial must", listValue(comparison.resolved_partial_must_requirement_ids)],
    ["New partial must", listValue(comparison.new_partial_must_requirement_ids)],
    ["Covered new must", listValue(comparison.covered_new_must_requirement_ids)],
    ["Uncovered new must", listValue(comparison.uncovered_new_must_requirement_ids)],
  ];
  probeChanges.forEach((change) => {
    rows.push([
      `Probe ${change.name || "-"}`,
      `${change.source_status || "-"} -> ${change.current_status || "-"} (${change.direction || "-"})`,
    ]);
  });
  return rows
    .map(([label, value]) => `<li><strong>${escapeHtml(String(label))}</strong><span>${escapeHtml(String(value))}</span></li>`)
    .join("");
}

function repairSuggestionRows(suggestions) {
  if (!Array.isArray(suggestions) || !suggestions.length) {
    return `<li><strong>${translate("common.none")}</strong><span>${translate("common.no_repair_suggestions")}</span></li>`;
  }
  return suggestions
    .slice(0, 8)
    .map((suggestion) => {
      const label = `${suggestion.id || "RS"} · ${suggestion.priority || "should"} · ${suggestion.agent || "debug"}`;
      const detail = suggestion.worker_goal || suggestion.reason || suggestion.title || "";
      return `<li><strong>${escapeHtml(String(label))}</strong><span>${escapeHtml(String(suggestion.title || detail))}</span></li>`;
    })
    .join("");
}

function listValue(items) {
  return Array.isArray(items) && items.length ? items.join(", ") : "-";
}

function formatDelta(value) {
  const number = Number(value || 0);
  return `${number >= 0 ? "+" : ""}${number.toFixed(2)}`;
}

function realPullRequestUrl(value) {
  const url = String(value || "");
  return url && !url.startsWith("dry-run://") ? url : "";
}

function formatDuration(seconds) {
  const value = Math.max(0, Math.round(Number(seconds || 0)));
  if (value < 60) return `${value}s`;
  const minutes = Math.floor(value / 60);
  const remainingSeconds = value % 60;
  if (minutes < 60) return `${minutes}m ${remainingSeconds}s`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes}m`;
}

function formatDateTime(value) {
  const raw = String(value || "");
  if (!raw) return "-";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  return date.toLocaleString(state.language === "zh" ? "zh-CN" : "en-US", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function shortText(value, limit = 80) {
  const text = String(value || "");
  return text.length > limit ? `${text.slice(0, Math.max(0, limit - 1))}...` : text;
}

function formatLabel(value) {
  return String(value || "-")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function checkLabel(value) {
  const key = `check.${String(value || "")}`;
  return I18N[state.language]?.[key] || formatLabel(value);
}

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

function safeClass(value) {
  return String(value || "unknown").toLowerCase().replace(/[^a-z0-9_-]/g, "-");
}

function setSummary(project = {}, run = {}) {
  el("projectId").textContent = state.projectId || "-";
  el("projectStatus").textContent = project.status || "-";
  el("runId").textContent = state.runId || "-";
  el("runStatus").textContent = run.status || "-";
}

function setControls() {
  updateSourceCards();
  const envReady = state.environmentReady;
  const hasSource = Boolean(state.sourceType);
  const sourceReady = isSourceReadyForStart();
  const hasProject = Boolean(state.projectId);
  const hasRun = Boolean(state.runId);
  const checking = state.environmentChecking;
  const layout = document.querySelector(".layout");
  if (layout) {
    layout.classList.toggle("envLocked", !envReady);
  }
  el("resetSourceChoice").disabled = !hasSource;
  el("checkEnvironment").disabled = checking;
  el("preflightUnifiedRun").disabled = !envReady || !hasSource || !sourceReady;
  el("startUnifiedRun").disabled = !envReady || !hasSource || !sourceReady;
  el("reopenFeedback").disabled = !envReady || !hasProject || !hasRun;
  el("buildPlan").disabled = !envReady || !hasProject;
  el("startRun").disabled = !envReady || !hasProject;
  el("pauseRun").disabled = !hasRun;
  el("resumeRun").disabled = !hasRun;
  el("stopRun").disabled = !hasRun;
  ["runEvidenceIndex", "runEvidencePackage", "runEvidenceReadiness"].forEach((id) => {
    const node = el(id);
    if (node) node.disabled = !envReady;
  });
  const deliveryPanel = document.querySelector(".deliveryPanel");
  if (deliveryPanel) {
    deliveryPanel.classList.toggle("lockedByEnv", !envReady);
  }
  const continueButton = el("continueOptimizing");
  if (continueButton) {
    continueButton.disabled = !envReady;
  }
}

function isSourceReadyForStart() {
  if (state.sourceType === "idea") {
    return Boolean(el("objective").value.trim());
  }
  if (state.sourceType === "documents") {
    return Boolean((el("uploadFiles").files || []).length || state.uploadedDocumentPaths.length);
  }
  if (state.sourceType === "github") {
    return Boolean(el("repository").value.trim());
  }
  return false;
}

async function checkHealth() {
  try {
    await api("/health");
    state.apiStatus = "online";
    el("apiStatus").textContent = t("api.online");
    el("apiStatus").className = "status ok";
  } catch (error) {
    state.apiStatus = "offline";
    el("apiStatus").textContent = t("api.offline");
    el("apiStatus").className = "status error";
  }
}

async function startUnifiedRun() {
  ensureEnvironmentReady();
  ensureSourceSelected();
  if (state.sourceType === "documents") {
    await startDocumentRun();
    return;
  }
  const payload = unifiedRunPayload();
  const result = await api("/runs", { method: "POST", body: payload });
  state.projectId = result.project_id;
  state.runId = result.run_id;
  setCurrentUrl(state.projectId, state.runId);
  closeEventStream();
  state.events = [];
  state.runStatusSnapshot = null;
  show("briefOutput", result);
  show("graphOutput", {});
  renderGraphViz({});
  show("eventOutput", []);
  renderRunStatus(null);
  resetDelivery();
  setSummary(result.project || {}, result.job || {});
  setControls();
  loadProjectHistory().catch(showError);
  startPolling();
}

async function preflightUnifiedRun() {
  ensureEnvironmentReady();
  ensureSourceSelected();
  if (state.sourceType === "documents") {
    await ensureDocumentProject();
  }
  const result = await api("/runs/preflight", { method: "POST", body: unifiedRunPayload() });
  show("eventOutput", result);
}

function unifiedRunPayload() {
  const payload = {
    ...projectPayloadForSource(),
    ...modelConfigPayload(),
    async: true,
    ...runPayload(),
  };
  if (state.sourceType === "github") {
    payload.prepare_repository = true;
  }
  return payload;
}

function projectPayloadForSource() {
  if (state.sourceType === "idea") {
    const objective = el("objective").value.trim();
    if (!objective) throw new Error(t("message.objective_required"));
    return {
      objective,
      documents: [],
      attachments: [],
      repository: "",
      repository_path: "",
      source_mode: "none",
      primary_input_mode: "document_driven",
      expand_one_line: true,
    };
  }
  if (state.sourceType === "documents") {
    const objective = el("documentObjective").value.trim() || "Build from uploaded development documents.";
    return {
      objective,
      documents: listUploadedDocumentPaths(),
      attachments: [],
      repository: "",
      repository_path: "",
      source_mode: "none",
      primary_input_mode: "document_driven",
    };
  }
  if (state.sourceType === "github") {
    const repository = el("repository").value.trim();
    if (!repository) throw new Error(t("message.github_required"));
    return {
      objective: el("githubObjective").value.trim() || "Build from the supplied GitHub repository.",
      documents: [],
      attachments: [],
      repository,
      repository_path: "",
      repository_visibility: "public",
      source_mode: "github_public",
      primary_input_mode: "document_driven",
    };
  }
  throw new Error(t("message.select_source"));
}

function listUploadedDocumentPaths() {
  return [...state.uploadedDocumentPaths];
}

function ensureEnvironmentReady() {
  if (!state.environmentReady) throw new Error(t("message.environment_required"));
}

function ensureSourceSelected() {
  if (!state.sourceType) throw new Error(t("message.select_source"));
}

async function startDocumentRun() {
  await ensureDocumentProject();
  const result = await api(`/projects/${state.projectId}/runs`, {
    method: "POST",
    body: {
      async: true,
      ...modelConfigPayload(),
      ...runPayload(),
    },
  });
  state.runId = result.run_id;
  setCurrentUrl(state.projectId, state.runId);
  closeEventStream();
  state.events = [];
  state.runStatusSnapshot = null;
  resetDelivery();
  renderRunStatus(null);
  setSummary({}, result.job);
  setControls();
  loadProjectHistory().catch(showError);
  startPolling();
}

async function ensureDocumentProject() {
  const files = Array.from(el("uploadFiles").files || []);
  if (!state.projectId || state.projectSourceType !== "documents") {
    const created = await api("/projects", {
      method: "POST",
      body: {
        ...projectPayloadForSource(),
        documents: [],
      },
    });
    state.projectId = created.project.project_id;
    state.projectSourceType = "documents";
    state.runId = "";
    state.uploadedDocumentPaths = [];
    show("briefOutput", created.brief);
    show("graphOutput", {});
    renderGraphViz({});
    resetDelivery();
    setSummary(created.project, {});
    loadProjectHistory().catch(showError);
  }
  if (files.length) {
    const uploaded = await uploadSelectedFiles("primary_requirements", true);
    state.uploadedDocumentPaths = Array.isArray(uploaded.project?.documents)
      ? uploaded.project.documents
      : (uploaded.uploaded_files || [])
          .filter((file) => file.role === "primary_requirements")
          .map((file) => file.path);
    show("briefOutput", uploaded.brief);
    show("eventOutput", uploaded.uploaded_files || []);
    setSummary(uploaded.project, {});
    el("uploadFiles").value = "";
    renderFileSelection();
  }
  if (!state.uploadedDocumentPaths.length) {
    throw new Error(t("message.select_files"));
  }
}

async function buildPlan() {
  const result = await api(`/projects/${state.projectId}/plan`, { method: "POST", body: {} });
  show("briefOutput", result.context);
  show("graphOutput", result.task_graph);
  renderGraphViz(result.task_graph || {});
  setSummary(result.project, {});
  setControls();
}

async function uploadSelectedFiles(role = "", required = false) {
  const files = Array.from(el("uploadFiles").files || []);
  if (!files.length) {
    throw new Error(t("message.select_files"));
  }
  const formData = new FormData();
  files.forEach((file) => formData.append("file", file, file.name));
  if (role) formData.append("role", role);
  if (required) formData.append("required", "true");
  return api(`/projects/${state.projectId}/files`, {
    method: "POST",
    formData,
  });
}

async function reopenWithFeedback() {
  if (!state.projectId || !state.runId) return;
  const files = Array.from(el("uploadFiles").files || []);
  if (!files.length) {
    show("eventOutput", [{ level: "warning", message: "Select feedback files before reopening." }]);
    return;
  }
  const formData = new FormData();
  files.forEach((file) => formData.append("file", file, file.name));
  formData.append("role", "feedback");
  formData.append("required", "true");
  const uploaded = await api(`/projects/${state.projectId}/files`, {
    method: "POST",
    formData,
  });
  const feedbackFiles = (uploaded.uploaded_files || []).map((file) => file.path);
  const result = await api(`/projects/${state.projectId}/feedback/reopen`, {
    method: "POST",
    body: {
      source_run_id: state.runId,
      feedback_files: feedbackFiles,
      run: runPayload(),
    },
  });
  state.runId = result.run_id;
  setCurrentUrl(state.projectId, state.runId);
  closeEventStream();
  state.events = [];
  show("briefOutput", result.context_bundle || {});
  show("graphOutput", result.task_graph || {});
  renderGraphViz(result.task_graph || {});
  renderDelivery(result);
  setSummary({}, { status: result.status });
  setControls();
  loadProjectHistory().catch(showError);
}

async function startAutoIteration() {
  ensureEnvironmentReady();
  if (!state.projectId || !state.runId) return;
  setDeliveryActionFeedback(t("auto_iteration.starting"));
  const result = await api(`/projects/${state.projectId}/runs/${state.runId}/auto-iteration`, {
    method: "POST",
    body: {
      async: true,
      run: runPayload(),
    },
  });
  if (result.status !== "started" || !result.repair_run_id) {
    show("eventOutput", [result]);
    setDeliveryActionFeedback(result.auto_iteration_report?.reason || t("auto_iteration.unavailable"));
    return;
  }
  state.runId = result.repair_run_id;
  setCurrentUrl(state.projectId, state.runId);
  closeEventStream();
  state.events = [];
  state.runStatusSnapshot = null;
  resetDelivery();
  show("eventOutput", [{ level: "info", message: t("auto_iteration.started") }, result.auto_iteration_report || result]);
  show("graphOutput", result.run?.task_graph || {});
  renderGraphViz(result.run?.task_graph || {});
  setSummary({}, result.job || { status: result.run?.status || "running" });
  setControls();
  loadProjectHistory().catch(showError);
  startPolling();
}

async function startRun() {
  const result = await api(`/projects/${state.projectId}/runs`, {
    method: "POST",
    body: {
      async: true,
      ...runPayload(),
    },
  });
  state.runId = result.run_id;
  setCurrentUrl(state.projectId, state.runId);
  closeEventStream();
  state.events = [];
  resetDelivery();
  setSummary({}, result.job);
  setControls();
  loadProjectHistory().catch(showError);
  startPolling();
}

async function checkEnvironment() {
  state.environmentChecking = true;
  setEnvironmentReport(state.environmentReport);
  try {
    const result = await api("/environment/check", {
      method: "POST",
      body: environmentPayload(),
    });
    state.environmentChecking = false;
    setEnvironmentReport(result);
    show("eventOutput", [{ level: result.status === "ready" ? "info" : "warning", message: t(result.status === "ready" ? "message.environment_ready" : "message.environment_blocked") }, result]);
  } catch (error) {
    state.environmentChecking = false;
    setEnvironmentReport(state.environmentReport);
    throw error;
  }
}

async function controlRun(action) {
  if (!state.projectId || !state.runId) return;
  const body = action === "resume" ? runPayload() : {};
  const result = await api(`/projects/${state.projectId}/runs/${state.runId}/${action}`, {
    method: "POST",
    body,
  });
  if (result.resumed_run_id) {
    state.runId = result.resumed_run_id;
    setCurrentUrl(state.projectId, state.runId);
    setSummary({}, result.resumed_job || {});
    loadProjectHistory().catch(showError);
    startPolling();
    return;
  }
  setSummary({}, result.job);
  await refreshRunStatus();
  await refreshEvents();
}

function runPayload() {
  const payload = {
    real_codex: el("realCodex").checked,
    real_github: el("realGithub").checked,
    prepare_repository: el("prepareRepository").checked,
    codex_executable: el("codexExecutable").value.trim() || "codex",
    max_worker_seconds: 0,
    github_collect_ci: el("githubCollectCi").checked,
    github_ci_wait_seconds: Number(el("githubCiWaitSeconds").value || 0),
    github_ci_poll_interval_seconds: Number(el("githubCiPollSeconds").value || 10),
    isolate_real_run: el("isolateRealRun").checked,
    keep_worktree: el("keepWorktree").checked,
    auto_browser_verify: el("autoBrowserVerify").checked,
    generate_static_ci: el("generateStaticCi").checked,
    write_native_ui_tests: el("writeNativeUiTests").checked,
    auto_merge: el("autoMerge").checked,
    full_roadmap: true,
    max_phases: 50,
  };
  if (state.sourceType === "github") {
    payload.prepare_repository = true;
  }
  return payload;
}

function startPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
  }
  startEventStream();
  state.pollTimer = setInterval(refreshRun, 1000);
  refreshRun();
}

async function refreshRun() {
  if (!state.projectId || !state.runId) return;
  const job = await api(`/projects/${state.projectId}/runs/${state.runId}/job`);
  setSummary({}, job);
  await refreshRunStatus();
  await refreshEvents();
  if (!["queued", "running", "paused"].includes(job.status)) {
    clearInterval(state.pollTimer);
    state.pollTimer = 0;
    try {
      const delivery = await api(`/projects/${state.projectId}/delivery`);
      renderDelivery(delivery);
      loadProjectHistory().catch(showError);
    } catch (error) {
      show("deliveryOutput", { error: error.message });
    }
  }
}

async function refreshRunStatus() {
  if (!state.projectId || !state.runId) return;
  try {
    const snapshot = await api(`/projects/${state.projectId}/runs/${state.runId}/status`);
    state.runStatusSnapshot = snapshot;
    renderRunStatus(snapshot);
    if (snapshot.artifact_manifest && snapshot.artifact_manifest.items) {
      renderArtifactPreviews(snapshot.artifact_manifest);
    }
  } catch (error) {
    renderRunStatus({
      status: "unknown",
      phase: "blocked",
      progress_percent: 0,
      summary: error.message,
      tasks: {},
    });
  }
}

async function refreshEvents() {
  const events = await api(`/projects/${state.projectId}/runs/${state.runId}/events`);
  state.events = events.events || [];
  show("eventOutput", state.events);
}

function startEventStream() {
  closeEventStream();
  state.events = [];
  if (!window.EventSource || !state.projectId || !state.runId) {
    return;
  }
  const source = new EventSource(`/projects/${state.projectId}/runs/${state.runId}/events-stream?timeout=30`);
  state.eventSource = source;
  source.onmessage = (event) => appendStreamEvent(event);
  ["queued", "running", "done", "failed", "blocked", "paused", "needs_iteration", "heartbeat"].forEach((type) => {
    source.addEventListener(type, appendStreamEvent);
  });
  source.onerror = () => {
    closeEventStream();
  };
}

function appendStreamEvent(event) {
  try {
    const payload = JSON.parse(event.data || "{}");
    if (payload.type === "heartbeat") return;
    const eventId = payload.event_id || event.lastEventId || "";
    if (eventId && state.events.some((item) => item.event_id === eventId)) return;
    state.events.push(payload);
    show("eventOutput", state.events);
    if (["done", "failed", "blocked", "paused", "needs_iteration"].includes(String(payload.type || ""))) {
      closeEventStream();
    }
  } catch (error) {
    show("eventOutput", [{ level: "error", message: error.message }]);
  }
}

function closeEventStream() {
  if (state.eventSource) {
    state.eventSource.close();
    state.eventSource = null;
  }
}

async function handleDeliveryAction(event) {
  const button = event.target.closest("[data-delivery-action]");
  if (!button || button.disabled) return;
  const actionId = button.dataset.deliveryAction || "";
  const actions = allDeliveryActions();
  const action = actions.find((item) => String(item.id || "") === actionId);
  if (!action || !action.enabled) {
    show("eventOutput", [{ level: "warning", message: t("delivery.action_unavailable") }]);
    setDeliveryActionFeedback(t("delivery.action_unavailable"));
    return;
  }
  const url = String(button.dataset.deliveryUrl || action.url || "");
  if (String(action.method || "GET").toUpperCase() === "POST") {
    event.preventDefault();
    setDeliveryActionFeedback(t("delivery.folder_opening"));
    try {
      const result = await api(url, { method: "POST", body: {} });
      show("eventOutput", [{ level: "info", message: t("delivery.folder_opened") }, result]);
      setDeliveryActionFeedback(`${t("delivery.folder_opened")} ${result.path || ""}`);
    } catch (error) {
      show("eventOutput", [{ level: "error", message: error.message }]);
      setDeliveryActionFeedback(`${t("delivery.folder_failed")} ${error.message}`);
    }
    return;
  }
  event.preventDefault();
  if (url) {
    const opened = window.open(url, "_blank", "noreferrer");
    setDeliveryActionFeedback(t("delivery.result_opened"));
    if (!opened) {
      window.location.href = url;
    }
  }
}

function setDeliveryActionFeedback(message) {
  const container = el("deliveryActionFeedback");
  if (!container) return;
  delete container.dataset.autoIterationActive;
  container.textContent = message;
  container.classList.add("visible");
}

function bind() {
  document.querySelectorAll("[data-lang]").forEach((button) => {
    button.addEventListener("click", () => setLanguage(button.dataset.lang || "en"));
  });
  el("uploadFiles").addEventListener("change", renderFileSelection);
  ["objective", "documentObjective", "githubObjective", "repository"].forEach((id) => {
    el(id).addEventListener("input", setControls);
  });
  document.querySelectorAll(".sourceRadio").forEach((radio) => {
    radio.addEventListener("change", () => setSourceType(radio.value));
  });
  document.querySelectorAll("[data-source-card]").forEach((card) => {
    card.addEventListener("click", () => setSourceType(card.dataset.sourceCard || ""));
  });
  el("resetSourceChoice").addEventListener("click", resetSourceChoice);
  el("advancedToggle").addEventListener("click", toggleAdvancedVisibility);
  el("modelProvider").addEventListener("change", () => {
    syncModelProviderDefaults();
    setEnvironmentReport(null);
  });
  [
    "codexExecutable",
    "autoBrowserVerify",
    "modelApiKeyEnv",
    "modelBaseUrl",
    "orchestratorModel",
    "documentExpansionModel",
    "reviewerModel",
  ].forEach((id) => {
    const node = el(id);
    const eventName = node.type === "checkbox" ? "change" : "input";
    node.addEventListener(eventName, () => {
      renderModelSummary();
      invalidateEnvironment();
    });
  });
  el("preflightUnifiedRun").addEventListener("click", () => preflightUnifiedRun().catch(showError));
  el("startUnifiedRun").addEventListener("click", () => startUnifiedRun().catch(showError));
  el("reopenFeedback").addEventListener("click", () => reopenWithFeedback().catch(showError));
  el("buildPlan").addEventListener("click", () => buildPlan().catch(showError));
  el("checkEnvironment").addEventListener("click", () => checkEnvironment().catch(showError));
  el("startRun").addEventListener("click", () => startRun().catch(showError));
  el("pauseRun").addEventListener("click", () => controlRun("pause").catch(showError));
  el("resumeRun").addEventListener("click", () => controlRun("resume").catch(showError));
  el("stopRun").addEventListener("click", () => controlRun("stop").catch(showError));
  el("progressStopRun").addEventListener("click", () => controlRun("stop").catch(showError));
  el("runEvidenceIndex").addEventListener("click", () => runEvidenceIndex().catch(showError));
  el("runEvidencePackage").addEventListener("click", () => runEvidencePackage().catch(showError));
  el("runEvidenceReadiness").addEventListener("click", () => runEvidenceReadiness().catch(showError));
  el("deliveryActions").addEventListener("click", (event) => handleDeliveryAction(event).catch(showError));
  el("newProject").addEventListener("click", beginNewProject);
  el("refreshProjectHistory").addEventListener("click", () => loadProjectHistory({ quiet: false }).catch(showError));
  el("projectHistory").addEventListener("click", (event) => {
    const deleteButton = event.target.closest("[data-delete-project]");
    if (deleteButton) {
      event.preventDefault();
      event.stopPropagation();
      deleteProjectFromHistory(deleteButton.dataset.deleteProject || "").catch(showError);
      return;
    }
    const button = event.target.closest("[data-open-project]");
    if (!button) return;
    openProjectFromHistory(button.dataset.openProject || "", button.dataset.openRun || "").catch(showError);
  });
  bindDeliveryTabs();
}

function showError(error) {
  show("eventOutput", [{ level: "error", message: error.message }]);
}

async function loadFromUrl() {
  const params = new URLSearchParams(window.location.search || "");
  const projectId = params.get("project_id") || params.get("projectId") || "";
  const runId = params.get("run_id") || params.get("runId") || "";
  if (!projectId) return;

  await loadProjectRun(projectId, runId);
}

async function loadProjectRun(projectId, runId = "") {
  state.projectId = projectId;
  state.runId = runId;
  state.runStatusSnapshot = null;
  closeEventStream();
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = 0;
  }
  resetDelivery();
  renderRunStatus(null);
  setControls();

  const project = await api(`/projects/${state.projectId}`);
  show("briefOutput", project.brief || project);
  show("graphOutput", project.task_graph || {});
  renderGraphViz(project.task_graph || {});
  setSummary(project, runId ? { status: "loaded" } : {});

  if (runId) {
    await refreshRunStatus();
    const delivery = await api(`/projects/${state.projectId}/runs/${state.runId}/delivery`);
    renderDelivery(delivery);
    setSummary(project, { status: delivery.status || "loaded" });
  }
  renderProjectWorkspace();
  setControls();
}

function setCurrentUrl(projectId, runId = "") {
  const url = new URL(window.location.href);
  if (projectId) {
    url.searchParams.set("project_id", projectId);
  } else {
    url.searchParams.delete("project_id");
  }
  if (runId) {
    url.searchParams.set("run_id", runId);
  } else {
    url.searchParams.delete("run_id");
  }
  history.replaceState(null, "", `${url.pathname}${url.search}`);
}

bind();
setControls();
setDeliveryTab(state.deliveryTab);
applyLanguage();
checkHealth();
loadEnvironmentDefaults()
  .finally(() => {
    setControls();
    return loadProjectHistory().then(loadFromUrl);
  })
  .catch(showError);
