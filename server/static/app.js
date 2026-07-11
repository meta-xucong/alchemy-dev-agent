const state = { projects: [], project: null, remote: null, remoteTask: null, localRun: null, poll: null, mode: "local", runtime: null };
const $ = (id) => document.getElementById(id);

async function api(path, { method = "GET", body } = {}) {
  const response = await fetch(path, { method, headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error?.message || "请求未完成");
  return data;
}

function escapeHtml(value) { return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;"); }
function projectTitle(project) { return String(project?.objective || "未命名项目").split(/[。！？!?\n]/)[0].slice(0, 34) || "未命名项目"; }
function statusText(value) { return ({ intake_ready: "准备开始", queued: "等待开始", running: "正在开发", paused: "已暂停", done: "已完成", completed: "已完成", failed: "需要处理", blocked: "需要处理" })[String(value || "").toLowerCase()] || "准备中"; }
function setDialog(id, open) { const dialog = $(id); if (open && !dialog.open) dialog.showModal(); if (!open && dialog.open) dialog.close(); }
function saveMode(mode) { try { localStorage.setItem("alchemy-development-mode", mode); } catch {} }

function setMode(mode) {
  state.mode = mode === "remote" ? "remote" : "local";
  saveMode(state.mode);
  const local = state.mode === "local";
  $("selectLocalMode").classList.toggle("active", local);
  $("selectRemoteMode").classList.toggle("active", !local);
  $("selectLocalMode").setAttribute("aria-selected", String(local));
  $("selectRemoteMode").setAttribute("aria-selected", String(!local));
  $("startAlchemy").hidden = !local;
  $("openConversation").hidden = local;
  $("projectHint").textContent = local
    ? "使用这台电脑上的 Codex CLI 开发；进度和交付都会保存在这个项目里。"
    : "把需求直接发给已绑定的 Remote Codex，并在这里同步它的进度。";
}

async function loadProjects() {
  const data = await api("/projects"); state.projects = data.projects || []; renderProjects();
  if (!state.project && state.projects[0]) await openProject(state.projects[0].project_id);
}
function renderProjects() {
  const root = $("projectList");
  root.innerHTML = state.projects.length ? state.projects.map((project) => `<button class="project-card ${state.project?.project_id === project.project_id ? "active" : ""}" data-project="${escapeHtml(project.project_id)}"><strong>${escapeHtml(projectTitle(project))}</strong><span>${escapeHtml(statusText(project.latest_run_status || project.status))}</span></button>`).join("") : "<p class=\"connection-chip\">还没有项目</p>";
  root.querySelectorAll("[data-project]").forEach((button) => button.addEventListener("click", async () => { await openProject(button.dataset.project); setDialog("projectQuickDialog", true); }));
}
async function openProject(projectId) {
  clearPolling(); const data = await api(`/projects/${encodeURIComponent(projectId)}`); state.project = data.project || data;
  const title = projectTitle(state.project);
  $("workspaceTitle").textContent = title; $("quickProjectTitle").textContent = title;
  $("quickProjectHint").textContent = "打开项目继续开发，或通过 Remote Codex 继续对话。";
  $("emptyState").hidden = true; $("projectHome").hidden = false;
  $("projectObjective").textContent = state.project.objective || "未命名项目"; $("projectStatus").textContent = statusText(state.project.status);
  renderProjects(); setMode(state.mode); await loadLatestRun();
}
async function loadLatestRun() {
  const summary = state.projects.find((item) => item.project_id === state.project?.project_id); const runId = summary?.latest_run_id;
  if (!runId) return renderIdle();
  try { state.localRun = await api(`/projects/${state.project.project_id}/runs/${runId}/status`); renderLocalProgress(state.localRun); if (["queued", "running", "paused"].includes(String(state.localRun.status).toLowerCase())) startPolling(); } catch { renderIdle(); }
}
function renderIdle() { $("progressStatus").textContent = "尚未开始"; $("progressDot").className = "progress-dot"; $("progressTitle").textContent = "等待开始"; $("progressMessage").textContent = "选择本地或 Remote 模式，开始这个项目的开发任务。"; $("progressSteps").innerHTML = ""; $("deliveryCard").textContent = "还没有交付结果。"; }
function renderLocalProgress(run) {
  const phase = run.current_phase || run.status || "running", status = String(run.status || "").toLowerCase();
  $("progressStatus").textContent = statusText(status); $("progressDot").className = `progress-dot ${["done", "completed"].includes(status) ? "done" : status === "failed" || status === "blocked" ? "error" : "running"}`;
  $("progressTitle").textContent = status === "done" ? "开发完成" : status === "failed" ? "开发遇到问题" : "Alchemy 正在开发";
  $("progressMessage").textContent = run.summary || `当前正在：${phase}`;
  $("progressSteps").innerHTML = (run.roadmap_progress?.phases || []).slice(-5).map((item) => `<li class="${item.status === "running" ? "active" : ""}">${escapeHtml(item.title || item.phase_id || "处理中")}</li>`).join("");
  const delivery = run.delivery || run.delivery_report; if (delivery?.ready_for_review || status === "done") $("deliveryCard").textContent = "开发已完成。可以打开项目结果并开始验收。";
}
async function startAlchemy() {
  if (!state.project) return; $("progressTitle").textContent = "正在启动 Alchemy"; $("progressMessage").textContent = "正在准备本地开发环境…";
  try { const result = await api(`/projects/${state.project.project_id}/runs`, { method: "POST", body: { async: true, real_codex: true, isolate_real_run: true, keep_worktree: true } }); state.localRun = { status: "queued", run_id: result.run_id, summary: "开发任务已创建。" }; renderLocalProgress(state.localRun); startPolling(); } catch (error) { showProgressError(error.message); }
}

async function loadRemote() {
  state.remote = await api("/integrations/remote-codex"); const chip = $("remoteStatus"); chip.textContent = state.remote.connected ? "Remote Codex 已就绪" : "Remote Codex 未就绪"; chip.classList.toggle("connected", Boolean(state.remote.connected));
}
function openRemote() {
  if (!state.project) return;
  if (!state.remote?.connected) { $("remoteUrl").value = state.remote?.base_url || "http://127.0.0.1:18766"; $("connectionMessage").textContent = state.remote?.message || "请先完成 Remote Codex 登录和绑定。"; setDialog("connectionDialog", true); return; }
  $("conversationTitle").textContent = projectTitle(state.project); $("conversationHelp").textContent = "把需求、反馈或修改想法直接发给 Remote Codex。"; setDialog("remoteDialog", true); renderConversation();
}
function renderConversation() {
  const feed = $("conversationFeed"), detail = state.remoteTask;
  if (!detail) { feed.innerHTML = '<div class="message assistant"><small>Remote Codex</small>你好，我已准备好帮你继续开发这个项目。告诉我下一步要做什么。</div>'; return; }
  feed.innerHTML = (detail.messages || []).map((item) => `<div class="message ${item.role === "user" ? "user" : "assistant"}"><small>${item.role === "user" ? "你" : "Remote Codex"}</small>${escapeHtml(item.text || "")}</div>`).join("") || '<div class="message assistant">正在连接对话…</div>';
  feed.scrollTop = feed.scrollHeight; renderRemoteProgress(detail);
}
function renderRemoteProgress(detail) {
  const task = detail.task || {}, terminal = Boolean(detail.is_terminal); $("progressStatus").textContent = detail.status_label || statusText(task.state); $("progressDot").className = `progress-dot ${terminal ? task.state === "completed" ? "done" : "error" : "running"}`;
  $("progressTitle").textContent = terminal ? detail.status_label || "Remote Codex 已完成" : "Remote Codex 正在开发"; $("progressMessage").textContent = detail.answer || detail.progress?.at(-1)?.label || "正在同步进度…";
  $("progressSteps").innerHTML = (detail.progress || []).slice(-5).map((item) => `<li class="${item.state === "active" ? "active" : ""}">${escapeHtml(item.label)}</li>`).join("");
}
async function sendConversation(event) {
  event.preventDefault(); const message = $("conversationMessage").value.trim(); if (!message || !state.project) return; $("conversationMessage").value = "";
  try { const result = await api(`/projects/${state.project.project_id}/remote-codex/tasks`, { method: "POST", body: { message, parent_task_id: state.remoteTask?.task?.task_id || "" } }); state.remoteTask = { task: result.task, messages: [{ role: "user", text: message }], progress: [], is_terminal: false }; renderConversation(); startPolling(); }
  catch (error) { $("conversationHelp").textContent = `${error.message} 你可以关闭此窗口后，在“查看运行状态”里确认登录和同步情况。`; await loadRemote(); }
}
async function refreshRemoteTask() { const taskId = state.remoteTask?.task?.task_id; if (!taskId || !state.project) return; try { state.remoteTask = await api(`/projects/${state.project.project_id}/remote-codex/tasks/${encodeURIComponent(taskId)}`); renderConversation(); if (state.remoteTask.is_terminal) clearPolling(); } catch (error) { $("conversationHelp").textContent = error.message; clearPolling(); } }
function startPolling() { clearPolling(); state.poll = window.setInterval(async () => { if (state.remoteTask) await refreshRemoteTask(); else if (state.localRun?.run_id && state.project) { state.localRun = await api(`/projects/${state.project.project_id}/runs/${state.localRun.run_id}/status`); renderLocalProgress(state.localRun); if (!["queued", "running", "paused"].includes(String(state.localRun.status).toLowerCase())) clearPolling(); } }, 1800); }
function clearPolling() { if (state.poll) window.clearInterval(state.poll); state.poll = null; }
function showProgressError(message) { $("progressStatus").textContent = "需要处理"; $("progressDot").className = "progress-dot error"; $("progressTitle").textContent = "暂时无法开始"; $("progressMessage").textContent = message; }

function statusCard(name, connected, detail) { return `<article class="status-card"><div class="status-card-head"><strong>${escapeHtml(name)}</strong><span class="status-state ${connected ? "ready" : "attention"}">${connected ? "已连接" : "需要处理"}</span></div><p>${escapeHtml(detail)}</p></article>`; }
async function showRuntimeStatus() {
  state.runtime = await api("/runtime/status"); const local = state.runtime.local || {}, remote = state.runtime.remote || {}, isLocal = state.mode === "local";
  $("runtimeStatusTitle").textContent = isLocal ? "本地模式状态" : "Remote 模式状态";
  $("runtimeStatusHint").textContent = isLocal ? "本地模式使用本机工具；不会上传你的 CLI 或 GitHub 凭据。" : "Remote 模式使用 Remote Codex 的登录与绑定状态；模型由其控制端上报。";
  $("runtimeStatusCards").innerHTML = isLocal
    ? `${statusCard("Codex CLI", Boolean(local.codex_cli?.connected), `${local.codex_cli?.label || "未检测到"} · 模型：${local.codex_cli?.model || "未上报"}`)}${statusCard("GitHub", Boolean(local.github?.connected), local.github?.label || "未检测到")}`
    : `${statusCard("Remote Codex 同步", Boolean(remote.connected), remote.message || "未连接")}${statusCard("Remote Codex 模型", Boolean(remote.connected && remote.model && remote.model !== "未上报"), remote.model || "未上报")}`;
  setDialog("runtimeStatusDialog", true);
}
async function createProject(event) { event.preventDefault(); const objective = $("projectObjectiveInput").value.trim(), name = $("projectName").value.trim(); if (!objective) return; const created = await api("/projects", { method: "POST", body: { objective: `${name}：${objective}`, primary_input_mode: "one_line", expand_one_line: true } }); setDialog("projectDialog", false); await loadProjects(); await openProject(created.project.project_id); event.target.reset(); }
async function saveConnection(event) { event.preventDefault(); $("connectionMessage").textContent = "正在检查连接…"; try { state.remote = await api("/integrations/remote-codex", { method: "POST", body: { base_url: $("remoteUrl").value } }); await loadRemote(); $("connectionMessage").textContent = state.remote.message || "已保存"; if (state.remote.connected) { setTimeout(() => { setDialog("connectionDialog", false); openRemote(); }, 350); } } catch (error) { $("connectionMessage").textContent = error.message; } }
function bind() {
  $("newProject").addEventListener("click", () => setDialog("projectDialog", true)); $("emptyNewProject").addEventListener("click", () => setDialog("projectDialog", true)); $("projectForm").addEventListener("submit", createProject); $("refreshProjects").addEventListener("click", loadProjects);
  $("connectRemote").addEventListener("click", () => { $("remoteUrl").value = state.remote?.base_url || "http://127.0.0.1:18766"; $("connectionMessage").textContent = state.remote?.message || ""; setDialog("connectionDialog", true); }); $("connectionForm").addEventListener("submit", saveConnection);
  $("selectLocalMode").addEventListener("click", () => setMode("local")); $("selectRemoteMode").addEventListener("click", () => setMode("remote")); $("showRuntimeStatus").addEventListener("click", () => showRuntimeStatus().catch((error) => showProgressError(error.message)));
  $("openConversation").addEventListener("click", openRemote); $("startAlchemy").addEventListener("click", startAlchemy); $("closeRemote").addEventListener("click", () => setDialog("remoteDialog", false)); $("closeProjectQuick").addEventListener("click", () => setDialog("projectQuickDialog", false));
  $("quickOpenWorkspace").addEventListener("click", () => setDialog("projectQuickDialog", false)); $("quickOpenConversation").addEventListener("click", () => { setDialog("projectQuickDialog", false); setMode("remote"); openRemote(); }); $("conversationForm").addEventListener("submit", sendConversation);
  document.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => setDialog(button.dataset.closeDialog, false)));
}
async function init() { try { state.mode = localStorage.getItem("alchemy-development-mode") || "local"; } catch {} bind(); setMode(state.mode); await Promise.all([loadRemote(), loadProjects()]); }
init().catch((error) => { $("emptyState").querySelector("p").textContent = `无法载入工作台：${error.message}`; });
