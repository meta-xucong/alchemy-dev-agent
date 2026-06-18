const state = {
  projectId: "",
  runId: "",
  pollTimer: 0,
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
  show("briefOutput", result.brief);
  show("graphOutput", {});
  show("eventOutput", []);
  show("deliveryOutput", {});
  setSummary(result.project, {});
  setControls();
}

async function buildPlan() {
  const result = await api(`/projects/${state.projectId}/plan`, { method: "POST", body: {} });
  show("briefOutput", result.context);
  show("graphOutput", result.task_graph);
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

async function startRun() {
  const result = await api(`/projects/${state.projectId}/runs`, {
    method: "POST",
    body: {
      async: true,
      codex_executable: el("codexExecutable").value.trim() || "codex",
    },
  });
  state.runId = result.run_id;
  setSummary({}, result.job);
  setControls();
  startPolling();
}

async function checkEnvironment() {
  const result = await api("/environment/check", {
    method: "POST",
    body: {
      codex_executable: el("codexExecutable").value.trim() || "codex",
    },
  });
  show("eventOutput", result);
}

async function controlRun(action) {
  if (!state.projectId || !state.runId) return;
  const result = await api(`/projects/${state.projectId}/runs/${state.runId}/${action}`, {
    method: "POST",
    body: {},
  });
  setSummary({}, result.job);
  await refreshEvents();
}

function startPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
  }
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
      show("deliveryOutput", delivery);
    } catch (error) {
      show("deliveryOutput", { error: error.message });
    }
  }
}

async function refreshEvents() {
  const events = await api(`/projects/${state.projectId}/runs/${state.runId}/events`);
  show("eventOutput", events.events);
}

function bind() {
  el("createProject").addEventListener("click", () => createProject().catch(showError));
  el("uploadSelected").addEventListener("click", () => uploadSelected().catch(showError));
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

bind();
setControls();
checkHealth();
