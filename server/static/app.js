const state = {
  projectId: "",
  runId: "",
  pollTimer: 0,
  eventSource: null,
  events: [],
  deliveryTab: "overview",
  language: localStorage.getItem("alchemyConsoleLanguage") || "en",
  apiStatus: "checking",
  delivery: null,
  evidenceIndex: null,
  evidencePackage: null,
  evidenceReadiness: null,
  evidenceToolResult: null,
};

const el = (id) => document.getElementById(id);

const I18N = {
  en: {
    "app.subtitle": "Document-driven autonomous development console",
    "api.checking": "Checking API",
    "api.online": "API Online",
    "api.offline": "API Offline",
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
    "source.auto": "Auto",
    "source.none": "No repository",
    "source.local": "Local repository",
    "source.github_public": "Public GitHub",
    "source.github_private": "Private GitHub",
    "button.create": "Create",
    "button.upload": "Upload",
    "button.feedback_reopen": "Feedback Reopen",
    "button.plan": "Plan",
    "button.check_env": "Check Env",
    "button.preflight": "Preflight",
    "button.unified_run": "Unified Run",
    "button.run": "Run",
    "button.pause": "Pause",
    "button.resume": "Resume",
    "button.stop": "Stop",
    "button.index": "Index",
    "button.package": "Package",
    "button.readiness": "Readiness",
    "button.choose_files": "Choose files",
    "file.no_file": "No file selected",
    "file.selected": "files selected",
    "project.title": "Project",
    "project.project_id": "Project ID",
    "project.status": "Status",
    "project.run_id": "Run ID",
    "project.run_status": "Run Status",
    "panel.intake": "Intake",
    "panel.task_graph": "Task Graph",
    "panel.events": "Events",
    "delivery.title": "Delivery Command",
    "delivery.no_delivery": "No delivery",
    "delivery.ready_for_review": "Ready for review",
    "delivery.needs_iteration": "Needs iteration",
    "delivery.final_gate": "Final gate",
    "delivery.evidence_index": "Evidence index",
    "delivery.evidence_package": "Evidence package",
    "delivery.evidence_readiness": "Evidence readiness",
    "tab.overview": "Overview",
    "tab.artifacts": "Artifacts",
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
    "app.subtitle": "文档驱动的自动化软件开发控制台",
    "api.checking": "正在检查 API",
    "api.online": "API 在线",
    "api.offline": "API 离线",
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
    "source.auto": "自动",
    "source.none": "无仓库",
    "source.local": "本地仓库",
    "source.github_public": "公开 GitHub",
    "source.github_private": "私有 GitHub",
    "button.create": "创建",
    "button.upload": "上传",
    "button.feedback_reopen": "反馈重开",
    "button.plan": "生成计划",
    "button.check_env": "检查环境",
    "button.preflight": "预检",
    "button.unified_run": "统一运行",
    "button.run": "运行",
    "button.pause": "暂停",
    "button.resume": "恢复",
    "button.stop": "停止",
    "button.index": "索引",
    "button.package": "打包",
    "button.readiness": "就绪评估",
    "button.choose_files": "选择文件",
    "file.no_file": "未选择文件",
    "file.selected": "个文件已选择",
    "project.title": "项目",
    "project.project_id": "项目 ID",
    "project.status": "项目状态",
    "project.run_id": "运行 ID",
    "project.run_status": "运行状态",
    "panel.intake": "输入解析",
    "panel.task_graph": "任务图",
    "panel.events": "事件",
    "delivery.title": "交付控制台",
    "delivery.no_delivery": "暂无交付",
    "delivery.ready_for_review": "可验收",
    "delivery.needs_iteration": "需迭代",
    "delivery.final_gate": "最终门禁",
    "delivery.evidence_index": "证据索引",
    "delivery.evidence_package": "证据包",
    "delivery.evidence_readiness": "证据就绪",
    "tab.overview": "总览",
    "tab.artifacts": "产物",
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
  return el(id).value
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
}

function setLanguage(language) {
  state.language = language === "zh" ? "zh" : "en";
  localStorage.setItem("alchemyConsoleLanguage", state.language);
  applyLanguage();
}

function renderFileSelection() {
  const files = Array.from(el("uploadFiles").files || []);
  el("fileSelection").textContent = files.length ? `${files.length} ${t("file.selected")}` : t("file.no_file");
}

function renderDelivery(delivery) {
  state.delivery = delivery;
  const report = delivery.delivery_report || {};
  const gate = report.final_gate || {};
  const github = report.github || {};
  const merge = github.merge || {};
  const artifact = report.artifact || {};
  const requirements = report.requirements || {};
  const parts = [
    [t("summary.status"), statusText(report.status || delivery.status || "-")],
    [t("summary.gate"), gate.score ?? "-"],
    [t("summary.pr"), github.pull_request_url || "-"],
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
  renderEvidence(delivery.delivery_evidence || fallbackEvidence(delivery));
  renderArtifactPreviews(delivery.artifact_manifest || {});
  renderCoverageViz(delivery.requirement_coverage || {});
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
  el("coverageViz").innerHTML = "";
  show("deliveryOutput", {});
  renderReadinessReport({});
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
      <p>${github.pull_request_url ? `<a href="${escapeHtml(String(github.pull_request_url))}" target="_blank" rel="noreferrer">${translate("evidence.pull_request")}</a>` : "-"}</p>
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
  if (!items.length) {
    container.innerHTML = "";
    return;
  }
  container.innerHTML = `
    <h3>${translate("evidence.artifacts")}</h3>
    <div class="artifactGrid">
      ${items.map(renderArtifactItem).join("")}
    </div>
  `;
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
  const hasProject = Boolean(state.projectId);
  const hasRun = Boolean(state.runId);
  el("uploadSelected").disabled = !hasProject;
  el("reopenFeedback").disabled = !hasProject || !hasRun;
  el("buildPlan").disabled = !hasProject;
  el("startRun").disabled = !hasProject;
  el("pauseRun").disabled = !hasRun;
  el("resumeRun").disabled = !hasRun;
  el("stopRun").disabled = !hasRun;
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

async function createProject() {
  const payload = {
    objective: el("objective").value.trim(),
    documents: lines("documents"),
    attachments: lines("attachments"),
    repository: el("repository").value.trim(),
    repository_path: el("repositoryPath").value.trim(),
  };
  const result = await api("/projects", { method: "POST", body: payload });
  state.projectId = result.project.project_id;
  state.runId = "";
  closeEventStream();
  state.events = [];
  show("briefOutput", result.brief);
  show("graphOutput", {});
  renderGraphViz({});
  show("eventOutput", []);
  resetDelivery();
  setSummary(result.project, {});
  setControls();
}

async function startUnifiedRun() {
  const payload = unifiedRunPayload();
  const result = await api("/runs", { method: "POST", body: payload });
  state.projectId = result.project_id;
  state.runId = result.run_id;
  closeEventStream();
  state.events = [];
  show("briefOutput", result);
  show("graphOutput", {});
  renderGraphViz({});
  show("eventOutput", []);
  resetDelivery();
  setSummary(result.project || {}, result.job || {});
  setControls();
  startPolling();
}

async function preflightUnifiedRun() {
  const result = await api("/runs/preflight", { method: "POST", body: unifiedRunPayload() });
  show("eventOutput", result);
}

function unifiedRunPayload() {
  const payload = {
    objective: el("objective").value.trim(),
    documents: lines("documents"),
    attachments: lines("attachments"),
    repository: el("repository").value.trim(),
    repository_path: el("repositoryPath").value.trim(),
    source_mode: el("sourceMode").value,
    async: true,
    ...runPayload(),
  };
  return payload;
}

async function buildPlan() {
  const result = await api(`/projects/${state.projectId}/plan`, { method: "POST", body: {} });
  show("briefOutput", result.context);
  show("graphOutput", result.task_graph);
  renderGraphViz(result.task_graph || {});
  setSummary(result.project, {});
  setControls();
}

async function uploadSelected() {
  if (!state.projectId) return;
  const files = Array.from(el("uploadFiles").files || []);
  if (!files.length) {
    show("eventOutput", [{ level: "warning", message: "No files selected." }]);
    return;
  }
  const formData = new FormData();
  files.forEach((file) => formData.append("file", file, file.name));
  const result = await api(`/projects/${state.projectId}/files`, {
    method: "POST",
    formData,
  });
  show("briefOutput", result.brief);
  show("eventOutput", result.uploaded_files || []);
  setSummary(result.project, {});
  setControls();
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
  closeEventStream();
  state.events = [];
  show("briefOutput", result.context_bundle || {});
  show("graphOutput", result.task_graph || {});
  renderGraphViz(result.task_graph || {});
  renderDelivery(result);
  setSummary({}, { status: result.status });
  setControls();
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
  closeEventStream();
  state.events = [];
  resetDelivery();
  setSummary({}, result.job);
  setControls();
  startPolling();
}

async function checkEnvironment() {
  const result = await api("/environment/check", {
    method: "POST",
    body: {
      codex_executable: el("codexExecutable").value.trim() || "codex",
      require_browser: el("autoBrowserVerify").checked,
    },
  });
  show("eventOutput", result);
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
    setSummary({}, result.resumed_job || {});
    startPolling();
    return;
  }
  setSummary({}, result.job);
  await refreshEvents();
}

function runPayload() {
  return {
    real_codex: el("realCodex").checked,
    real_github: el("realGithub").checked,
    prepare_repository: el("prepareRepository").checked,
    codex_executable: el("codexExecutable").value.trim() || "codex",
    github_collect_ci: el("githubCollectCi").checked,
    github_ci_wait_seconds: Number(el("githubCiWaitSeconds").value || 0),
    github_ci_poll_interval_seconds: Number(el("githubCiPollSeconds").value || 10),
    isolate_real_run: el("isolateRealRun").checked,
    keep_worktree: el("keepWorktree").checked,
    auto_browser_verify: el("autoBrowserVerify").checked,
    generate_static_ci: el("generateStaticCi").checked,
    write_native_ui_tests: el("writeNativeUiTests").checked,
    auto_merge: el("autoMerge").checked,
  };
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
  await refreshEvents();
  if (!["queued", "running", "paused"].includes(job.status)) {
    clearInterval(state.pollTimer);
    state.pollTimer = 0;
    try {
      const delivery = await api(`/projects/${state.projectId}/delivery`);
      renderDelivery(delivery);
    } catch (error) {
      show("deliveryOutput", { error: error.message });
    }
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

function bind() {
  document.querySelectorAll("[data-lang]").forEach((button) => {
    button.addEventListener("click", () => setLanguage(button.dataset.lang || "en"));
  });
  el("uploadFiles").addEventListener("change", renderFileSelection);
  el("createProject").addEventListener("click", () => createProject().catch(showError));
  el("preflightUnifiedRun").addEventListener("click", () => preflightUnifiedRun().catch(showError));
  el("startUnifiedRun").addEventListener("click", () => startUnifiedRun().catch(showError));
  el("uploadSelected").addEventListener("click", () => uploadSelected().catch(showError));
  el("reopenFeedback").addEventListener("click", () => reopenWithFeedback().catch(showError));
  el("buildPlan").addEventListener("click", () => buildPlan().catch(showError));
  el("checkEnvironment").addEventListener("click", () => checkEnvironment().catch(showError));
  el("startRun").addEventListener("click", () => startRun().catch(showError));
  el("pauseRun").addEventListener("click", () => controlRun("pause").catch(showError));
  el("resumeRun").addEventListener("click", () => controlRun("resume").catch(showError));
  el("stopRun").addEventListener("click", () => controlRun("stop").catch(showError));
  el("runEvidenceIndex").addEventListener("click", () => runEvidenceIndex().catch(showError));
  el("runEvidencePackage").addEventListener("click", () => runEvidencePackage().catch(showError));
  el("runEvidenceReadiness").addEventListener("click", () => runEvidenceReadiness().catch(showError));
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

  state.projectId = projectId;
  state.runId = runId;
  setControls();

  const project = await api(`/projects/${state.projectId}`);
  show("briefOutput", project.brief || project);
  show("graphOutput", project.task_graph || {});
  renderGraphViz(project.task_graph || {});
  setSummary(project, runId ? { status: "loaded" } : {});

  if (runId) {
    const delivery = await api(`/projects/${state.projectId}/runs/${state.runId}/delivery`);
    renderDelivery(delivery);
    setSummary(project, { status: delivery.status || "loaded" });
  }
}

bind();
setControls();
setDeliveryTab(state.deliveryTab);
applyLanguage();
checkHealth();
loadFromUrl().catch(showError);
