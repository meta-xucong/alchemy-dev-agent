const state = {
  projectId: "",
  runId: "",
  pollTimer: 0,
  eventSource: null,
  events: [],
};

const el = (id) => document.getElementById(id);

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

function renderDelivery(delivery) {
  const report = delivery.delivery_report || {};
  const gate = report.final_gate || {};
  const github = report.github || {};
  const merge = github.merge || {};
  const artifact = report.artifact || {};
  const requirements = report.requirements || {};
  const parts = [
    ["Status", report.status || delivery.status || "-"],
    ["Gate", gate.score ?? "-"],
    ["PR", github.pull_request_url || "-"],
    ["CI", github.ci_status || "-"],
    ["Merge", merge.status || "-"],
    ["Artifact", artifact.profile || "-"],
    ["Semantic", artifact.semantic_status || artifact.semantic_probe?.status || "-"],
    ["Scenarios", artifact.scenario_status || artifact.scenario_probe?.status || artifact.acceptance_scenarios?.status || "-"],
    ["Gameplay", artifact.gameplay_status || artifact.gameplay_probe?.status || "-"],
    ["Coverage", requirements.coverage_score ?? "-"],
  ];
  el("deliverySummary").innerHTML = parts
    .map(([label, value]) => `<div><strong>${label}</strong><span>${escapeHtml(String(value))}</span></div>`)
    .join("");
  renderEvidence(delivery.delivery_evidence || fallbackEvidence(delivery));
  renderArtifactPreviews(delivery.artifact_manifest || {});
  renderCoverageViz(delivery.requirement_coverage || {});
  show("deliveryOutput", delivery);
}

function renderEvidence(evidence) {
  const cards = Array.isArray(evidence.cards) ? evidence.cards : [];
  el("evidenceCards").innerHTML = cards
    .map((card) => `
      <article class="evidenceCard status-${safeClass(card.status)}">
        <strong>${escapeHtml(String(card.label || "-"))}</strong>
        <span>${escapeHtml(String(card.value || "-"))}</span>
        <small>${escapeHtml(String(card.detail || card.status || ""))}</small>
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
      <h3>Requirements</h3>
      <p>${escapeHtml(String(requirements.covered ?? 0))}/${escapeHtml(String(requirements.total ?? 0))} covered · ${escapeHtml(String(requirements.partial ?? 0))} partial · ${escapeHtml(String(requirements.missing ?? 0))} missing</p>
      <p>Must gaps: ${escapeHtml(String(requirements.missing_must ?? 0))} missing, ${escapeHtml(String(requirements.partial_must ?? 0))} partial</p>
    </section>
    <section>
      <h3>Browser Probes</h3>
      <ul>${probeRows || "<li><strong>Probe</strong><span>-</span></li>"}</ul>
    </section>
    <section>
      <h3>Native UI Tests</h3>
      <p>${escapeHtml(String(nativeTests.status || "-"))} · ${escapeHtml(String(nativeTests.framework || "none"))} · ${escapeHtml(String(nativeTests.write_mode || "-"))}</p>
      <p>${escapeHtml(String(nativeTests.target_path || nativeTests.summary || "-"))}</p>
    </section>
    <section>
      <h3>GitHub</h3>
      <p>${escapeHtml(String(github.branch || "-"))} · CI ${escapeHtml(String(github.ci_status || "-"))} · Merge ${escapeHtml(String(github.merge_status || "-"))}</p>
      <p>${github.pull_request_url ? `<a href="${escapeHtml(String(github.pull_request_url))}" target="_blank" rel="noreferrer">Pull request</a>` : "-"}</p>
    </section>
    <section>
      <h3>Development Cycle</h3>
      <p>${escapeHtml(String(cycle.status || "-"))} · ${escapeHtml(String(cycle.passed_steps ?? 0))}/${escapeHtml(String(cycle.total_steps ?? 0))} steps · score ${escapeHtml(String(cycle.score ?? 0))}</p>
      <ul>${cycleSteps.map((step) => `<li><strong>${escapeHtml(String(step.name || "-"))}</strong><span>${escapeHtml(String(step.status || "-"))}</span></li>`).join("")}</ul>
    </section>
    <section>
      <h3>Repair Comparison</h3>
      <p>${escapeHtml(String(comparison.status || "-"))} · source ${escapeHtml(String(comparison.source_run_id || "-"))} · current ${escapeHtml(String(comparison.current_run_id || "-"))}</p>
      <p>Score ${formatDelta(comparison.score_delta)} · Coverage ${formatDelta(comparison.coverage_delta)} · Blockers ${formatDelta(comparison.blocker_delta)}</p>
      <ul>${repairRows(comparison, probeChanges)}</ul>
      <h4>Repair Suggestions</h4>
      <ul>${repairSuggestionRows(repairSuggestions)}</ul>
    </section>
    <section>
      <h3>Blockers</h3>
      <ul>${blockers.length ? blockers.map((item) => `<li><strong>${escapeHtml(String(item.id || item.type || "blocker"))}</strong><span>${escapeHtml(String(item.description || item.message || item))}</span></li>`).join("") : "<li><strong>None</strong><span>No blockers</span></li>"}</ul>
    </section>
    <section>
      <h3>Next Actions</h3>
      <ul>${nextActions.length ? nextActions.map((item) => `<li><strong>Action</strong><span>${escapeHtml(String(item))}</span></li>`).join("") : "<li><strong>None</strong><span>No next action</span></li>"}</ul>
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
    <h3>Evidence Artifacts</h3>
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
    : `<a class="artifactOpen" href="${url}" target="_blank" rel="noreferrer">Open preview</a>`;
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
      ${statPill("Tasks", nodes.length)}
      ${statPill("Agents", Object.keys(agentCounts).length)}
      ${statPill("With deps", blocked)}
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
      <small>deps ${escapeHtml(dependencies.length ? dependencies.join(", ") : "none")} · ${escapeHtml(String(criteria.length))} criteria</small>
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
    <h3>Requirement Coverage</h3>
    <div class="vizStats">
      ${statPill("Requirements", entries.length)}
      ${statPill("Score", coverage.coverage_score ?? 0)}
      ${statPill("Must gaps", mustGaps.length)}
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
      <small>${escapeHtml(files.slice(0, 3).join(", ") || "no files")} · tasks ${escapeHtml(tasks.join(", ") || "-")}</small>
    </article>
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
    { label: "Final Gate", status: report.ready_for_review ? "passed" : "unknown", value: String(report.final_gate?.score ?? "-"), detail: report.summary || "" },
    { label: "Requirements", status: requirements.status || "unknown", value: String(requirements.coverage_score ?? "-"), detail: "coverage" },
    { label: "Artifact", status: artifact.static_status || "unknown", value: artifact.profile || "-", detail: "artifact evidence" },
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
    return "<li><strong>None</strong><span>No repair comparison</span></li>";
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
    return "<li><strong>None</strong><span>No repair suggestions</span></li>";
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
    el("apiStatus").textContent = "API Online";
    el("apiStatus").className = "status ok";
  } catch (error) {
    el("apiStatus").textContent = "API Offline";
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
  show("deliveryOutput", {});
  el("deliverySummary").innerHTML = "";
  el("evidenceCards").innerHTML = "";
  el("evidenceDetails").innerHTML = "";
  el("artifactPreviews").innerHTML = "";
  el("coverageViz").innerHTML = "";
  setSummary(result.project, {});
  setControls();
}

async function startUnifiedRun() {
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
  const result = await api("/runs", { method: "POST", body: payload });
  state.projectId = result.project_id;
  state.runId = result.run_id;
  closeEventStream();
  state.events = [];
  show("briefOutput", result);
  show("graphOutput", {});
  renderGraphViz({});
  show("eventOutput", []);
  show("deliveryOutput", {});
  el("deliverySummary").innerHTML = "";
  el("evidenceCards").innerHTML = "";
  el("evidenceDetails").innerHTML = "";
  el("artifactPreviews").innerHTML = "";
  el("coverageViz").innerHTML = "";
  setSummary(result.project || {}, result.job || {});
  setControls();
  startPolling();
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
  el("createProject").addEventListener("click", () => createProject().catch(showError));
  el("startUnifiedRun").addEventListener("click", () => startUnifiedRun().catch(showError));
  el("uploadSelected").addEventListener("click", () => uploadSelected().catch(showError));
  el("reopenFeedback").addEventListener("click", () => reopenWithFeedback().catch(showError));
  el("buildPlan").addEventListener("click", () => buildPlan().catch(showError));
  el("checkEnvironment").addEventListener("click", () => checkEnvironment().catch(showError));
  el("startRun").addEventListener("click", () => startRun().catch(showError));
  el("pauseRun").addEventListener("click", () => controlRun("pause").catch(showError));
  el("resumeRun").addEventListener("click", () => controlRun("resume").catch(showError));
  el("stopRun").addEventListener("click", () => controlRun("stop").catch(showError));
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
checkHealth();
loadFromUrl().catch(showError);
