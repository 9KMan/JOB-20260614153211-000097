// FlowForge — dashboard logic. Plain JS, no framework, talks to the
// REST API in /api/v1. Token in localStorage.

const API = ""; // same origin
const TOKEN_KEY = "flowforge.token";
const USER_KEY = "flowforge.user";

const state = {
  token: localStorage.getItem(TOKEN_KEY),
  user: JSON.parse(localStorage.getItem(USER_KEY) || "null"),
  view: "dashboard",
  workflows: [],
  runs: [],
  integrations: [],
  agents: [],
  audit: [],
  stepTypes: [],
};

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

// ---------- API ----------

async function api(path, opts = {}) {
  const headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
  if (state.token) headers["Authorization"] = `Bearer ${state.token}`;
  const res = await fetch(API + path, { ...opts, headers });
  if (res.status === 401) {
    logout();
    throw new Error("unauthenticated");
  }
  const text = await res.text();
  const body = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const detail = (body && body.detail) || res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return body;
}

// ---------- Auth ----------

function logout() {
  state.token = null;
  state.user = null;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  showLogin();
}

function showLogin() {
  $("#view-login").classList.remove("hidden");
  $$(".view").forEach((v) => v.id !== "view-login" && v.classList.add("hidden"));
  $("#who").textContent = "";
  $("#logout").classList.add("hidden");
}

function showApp() {
  $("#view-login").classList.add("hidden");
  $$(".view").forEach((v) => v.classList.add("hidden"));
  $("#view-" + state.view).classList.remove("hidden");
  $("#who").textContent = state.user ? state.user.email : "";
  $("#logout").classList.remove("hidden");
  $$(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === state.view));
  refresh();
}

$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.currentTarget);
  $("#login-error").classList.add("hidden");
  try {
    const res = await api("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: fd.get("email"), password: fd.get("password") }),
    });
    state.token = res.access_token;
    state.user = res.user;
    localStorage.setItem(TOKEN_KEY, state.token);
    localStorage.setItem(USER_KEY, JSON.stringify(state.user));
    showApp();
  } catch (err) {
    $("#login-error").textContent = err.message || "sign-in failed";
    $("#login-error").classList.remove("hidden");
  }
});

$("#logout").addEventListener("click", logout);

// ---------- Nav ----------

$$(".nav-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    state.view = btn.dataset.view;
    showApp();
  });
});

$("#refresh-dashboard").addEventListener("click", refresh);
$("#refresh-audit").addEventListener("click", loadAudit);

// ---------- Refresh / loaders ----------

async function refresh() {
  if (!state.token) return;
  if (state.view === "dashboard") {
    await Promise.all([loadDashboard(), loadRecent()]);
  } else if (state.view === "workflows") {
    await loadWorkflows();
  } else if (state.view === "integrations") {
    await loadIntegrations();
  } else if (state.view === "agents") {
    await loadAgents();
  } else if (state.view === "audit") {
    await loadAudit();
  } else if (state.view === "etl") {
    // no-op
  } else if (state.view === "docs") {
    // no-op
  }
}

async function loadDashboard() {
  try {
    const [stats] = await Promise.all([api("/api/v1/dashboard")]);
    const kpis = [
      { label: "Workflows", value: stats.workflows.total, sub: `${stats.workflows.active} active` },
      { label: "Runs", value: stats.runs.total, sub: `${stats.runs.succeeded} ok · ${stats.runs.failed} failed` },
      { label: "Success rate", value: `${stats.runs.success_rate}%`, sub: "all-time" },
      { label: "Schedules", value: stats.schedules.jobs.length, sub: "cron jobs" },
    ];
    $("#kpi-row").innerHTML = kpis
      .map(
        (k) => `
        <div class="card kpi">
          <span class="kpi-label">${k.label}</span>
          <span class="kpi-value">${k.value}</span>
          <span class="text-xs text-muted">${k.sub}</span>
        </div>`,
      )
      .join("");
    const sched = stats.schedules.jobs;
    $("#schedules").innerHTML = sched.length
      ? sched
          .map(
            (j) => `
            <div class="flex items-center justify-between py-1.5">
              <span class="font-mono text-xs">${j.id}</span>
              <span class="text-muted text-xs">${j.trigger}</span>
              <span class="text-xs text-muted">${j.next_run || "—"}</span>
            </div>`,
          )
          .join("")
      : "No schedules.";
  } catch (err) {
    console.error(err);
  }
}

async function loadRecent() {
  try {
    const runs = await api("/api/v1/runs?limit=8");
    state.runs = runs;
    $("#recent-runs").innerHTML = runs.length
      ? runs
          .map(
            (r) => `
            <div class="flex items-center justify-between py-1.5">
              <span class="font-mono text-xs">${r.id.slice(0, 8)}</span>
              <span class="badge ${r.status}">${r.status}</span>
              <span class="text-xs text-muted">${r.duration_ms || 0} ms</span>
            </div>`,
          )
          .join("")
      : "No runs yet.";
  } catch (err) {
    console.error(err);
  }
}

async function loadWorkflows() {
  try {
    state.workflows = await api("/api/v1/workflows?limit=100");
    if (state.workflows.length === 0) {
      $("#workflows-list").innerHTML = `
        <div class="card text-sm text-muted col-span-full">
          No workflows yet. Click <strong>New workflow</strong> to create one,
          or run <code>python -m flowforge.scripts.seed</code> for a demo.
        </div>`;
      return;
    }
    $("#workflows-list").innerHTML = state.workflows
      .map(
        (w) => `
        <div class="card">
          <div class="flex items-start justify-between mb-2">
            <div>
              <h3 class="font-semibold">${escapeHtml(w.name)}</h3>
              <p class="text-xs text-muted">${escapeHtml(w.description || "")}</p>
            </div>
            <span class="badge ${w.is_active ? "active" : "inactive"}">${w.trigger}</span>
          </div>
          <div class="flex flex-wrap gap-1 mb-3">
            ${(w.definition.steps || []).map((s) => `<span class="step-pill">${escapeHtml(s.type)}</span>`).join("")}
          </div>
          <div class="flex gap-2 text-sm">
            <button class="px-3 py-1 border border-line rounded hover:bg-primary-50 cursor-pointer transition-colors duration-150" data-action="run" data-id="${w.id}">Run</button>
            <button class="px-3 py-1 border border-line rounded hover:bg-primary-50 cursor-pointer transition-colors duration-150" data-action="edit" data-id="${w.id}">Edit</button>
            <button class="px-3 py-1 border border-line rounded hover:bg-primary-50 cursor-pointer transition-colors duration-150" data-action="runs" data-id="${w.id}">History</button>
            <button class="px-3 py-1 border border-line rounded text-danger hover:bg-red-50 cursor-pointer transition-colors duration-150" data-action="delete" data-id="${w.id}">Delete</button>
          </div>
        </div>`,
      )
      .join("");
  } catch (err) {
    toast(err.message, "danger");
  }
}

$("#workflows-list").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;
  const id = btn.dataset.id;
  const action = btn.dataset.action;
  if (action === "run") {
    try {
      const run = await api(`/api/v1/workflows/${id}/run`, { method: "POST", body: JSON.stringify({ payload: {} }) });
      toast(`Run ${run.status} in ${run.duration_ms || 0} ms`, run.status === "succeeded" ? "active" : "failed");
      refresh();
    } catch (err) { toast(err.message, "danger"); }
  } else if (action === "delete") {
    if (!confirm("Delete this workflow?")) return;
    try {
      await api(`/api/v1/workflows/${id}`, { method: "DELETE" });
      toast("Deleted", "active");
      refresh();
    } catch (err) { toast(err.message, "danger"); }
  } else if (action === "edit") {
    const wf = state.workflows.find((w) => w.id === id);
    openWorkflowEditor(wf);
  } else if (action === "runs") {
    try {
      const runs = await api(`/api/v1/workflows/${id}/runs`);
      openRunHistory(runs);
    } catch (err) { toast(err.message, "danger"); }
  }
});

$("#new-workflow").addEventListener("click", () => openWorkflowEditor(null));

// ---------- Workflow editor (modal) ----------

function openWorkflowEditor(workflow) {
  const isNew = !workflow;
  const data = workflow
    ? { ...workflow, definition: workflow.definition || { steps: [] } }
    : { name: "", description: "", trigger: "manual", schedule: "", is_active: true, definition: { steps: [] } };

  $("#modal-title").textContent = isNew ? "New workflow" : "Edit workflow";
  $("#modal-body").innerHTML = `
    <form id="wf-form" class="space-y-4">
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label class="block">
          <span class="text-sm font-medium">Name</span>
          <input name="name" required value="${escapeAttr(data.name)}" class="mt-1 w-full px-3 py-2 border border-line rounded-md cursor-text" />
        </label>
        <label class="block">
          <span class="text-sm font-medium">Trigger</span>
          <select name="trigger" class="mt-1 w-full px-3 py-2 border border-line rounded-md bg-white cursor-pointer">
            <option value="manual"   ${data.trigger === "manual" ? "selected" : ""}>manual</option>
            <option value="schedule" ${data.trigger === "schedule" ? "selected" : ""}>schedule (cron)</option>
            <option value="webhook"  ${data.trigger === "webhook" ? "selected" : ""}>webhook</option>
            <option value="etl"      ${data.trigger === "etl" ? "selected" : ""}>etl</option>
          </select>
        </label>
      </div>
      <label class="block" id="schedule-wrap" style="display:${data.trigger === "schedule" ? "block" : "none"}">
        <span class="text-sm font-medium">Cron expression</span>
        <input name="schedule" value="${escapeAttr(data.schedule || "")}" placeholder="0 9 * * 1" class="mt-1 w-full px-3 py-2 border border-line rounded-md font-mono text-xs cursor-text" />
        <span class="text-xs text-muted">5 or 6 fields (e.g. <code>0 9 * * 1</code> = Mon 09:00 UTC).</span>
      </label>
      <label class="block">
        <span class="text-sm font-medium">Description</span>
        <textarea name="description" rows="2" class="mt-1 w-full px-3 py-2 border border-line rounded-md cursor-text">${escapeHtml(data.description || "")}</textarea>
      </label>
      <div>
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm font-medium">Steps</span>
          <button type="button" id="add-step" class="text-sm px-3 py-1 border border-line rounded hover:bg-primary-50 cursor-pointer transition-colors duration-150">+ Add step</button>
        </div>
        <div id="steps-list" class="space-y-3"></div>
      </div>
      <div class="flex justify-end gap-2 pt-3 border-t border-line">
        <button type="button" id="cancel-wf" class="px-4 py-2 border border-line rounded-md hover:bg-primary-50 cursor-pointer transition-colors duration-150">Cancel</button>
        <button type="submit" class="px-4 py-2 bg-primary text-white rounded-md hover:bg-primary-700 cursor-pointer transition-colors duration-150">${isNew ? "Create" : "Save"}</button>
      </div>
    </form>`;

  const steps = data.definition.steps || [];
  renderStepEditor(steps);

  $("#modal").classList.remove("hidden");

  $("select[name='trigger']").addEventListener("change", (e) => {
    $("#schedule-wrap").style.display = e.currentTarget.value === "schedule" ? "block" : "none";
  });

  $("#add-step").addEventListener("click", () => {
    const list = readSteps();
    list.push({ id: "step-" + (list.length + 1), name: "Step " + (list.length + 1), type: "http", config: {} });
    renderStepEditor(list);
  });

  $("#cancel-wf").addEventListener("click", closeModal);

  $("#wf-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const body = {
      name: fd.get("name"),
      description: fd.get("description"),
      trigger: fd.get("trigger"),
      schedule: fd.get("schedule") || null,
      is_active: data.is_active,
      definition: { steps: readSteps() },
    };
    try {
      if (isNew) {
        await api("/api/v1/workflows", { method: "POST", body: JSON.stringify(body) });
        toast("Workflow created", "active");
      } else {
        await api(`/api/v1/workflows/${data.id}`, { method: "PATCH", body: JSON.stringify(body) });
        toast("Workflow saved", "active");
      }
      closeModal();
      refresh();
    } catch (err) {
      toast(err.message, "danger");
    }
  });
}

function renderStepEditor(steps) {
  if (!state.stepTypes.length) {
    state.stepTypes = [
      { type: "http", description: "HTTP request" },
      { type: "ai", description: "AI completion" },
      { type: "email", description: "Email" },
      { type: "slack", description: "Slack" },
      { type: "transform", description: "Transform" },
      { type: "condition", description: "Condition" },
      { type: "delay", description: "Delay" },
      { type: "log", description: "Log" },
    ];
  }
  $("#steps-list").innerHTML = steps
    .map(
      (s, i) => `
      <div class="border border-line rounded-md p-3" data-step-idx="${i}">
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm font-medium">Step ${i + 1}</span>
          <button type="button" data-rm-step="${i}" class="text-xs text-danger hover:underline cursor-pointer">Remove</button>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <label class="block">
            <span class="text-xs font-medium">ID</span>
            <input value="${escapeAttr(s.id)}" data-field="id" class="mt-1 w-full px-2 py-1.5 border border-line rounded-md text-sm font-mono cursor-text" />
          </label>
          <label class="block">
            <span class="text-xs font-medium">Name</span>
            <input value="${escapeAttr(s.name || "")}" data-field="name" class="mt-1 w-full px-2 py-1.5 border border-line rounded-md text-sm cursor-text" />
          </label>
          <label class="block">
            <span class="text-xs font-medium">Type</span>
            <select data-field="type" class="mt-1 w-full px-2 py-1.5 border border-line rounded-md text-sm bg-white cursor-pointer">
              ${state.stepTypes.map((t) => `<option value="${t.type}" ${s.type === t.type ? "selected" : ""}>${t.type} — ${escapeHtml(t.description || "")}</option>`).join("")}
            </select>
          </label>
        </div>
        <label class="block mt-2">
          <span class="text-xs font-medium">Config (JSON)</span>
          <textarea data-field="config" rows="3" class="mt-1 w-full px-2 py-1.5 border border-line rounded-md text-xs font-mono cursor-text">${escapeHtml(JSON.stringify(s.config || {}, null, 2))}</textarea>
        </label>
      </div>`,
    )
    .join("");

  $$("#steps-list [data-rm-step]").forEach((b) =>
    b.addEventListener("click", () => {
      const idx = parseInt(b.dataset.rmStep, 10);
      const list = readSteps();
      list.splice(idx, 1);
      renderStepEditor(list);
    }),
  );
}

function readSteps() {
  return $$("#steps-list [data-step-idx]").map((row, i) => {
    const id = row.querySelector("[data-field='id']").value || `step-${i}`;
    const name = row.querySelector("[data-field='name']").value || id;
    const type = row.querySelector("[data-field='type']").value;
    let config = {};
    try {
      config = JSON.parse(row.querySelector("[data-field='config']").value || "{}");
    } catch (err) {
      config = { _parse_error: err.message };
    }
    return { id, name, type, config };
  });
}

function openRunHistory(runs) {
  $("#modal-title").textContent = "Run history";
  $("#modal-body").innerHTML = runs.length
    ? `<div class="space-y-2">${runs
        .map(
          (r) => `
        <div class="border border-line rounded-md p-3">
          <div class="flex items-center justify-between">
            <span class="font-mono text-xs">${r.id}</span>
            <span class="badge ${r.status}">${r.status}</span>
            <span class="text-xs text-muted">${r.duration_ms || 0} ms</span>
          </div>
          ${r.error ? `<p class="text-xs text-danger mt-1">${escapeHtml(r.error)}</p>` : ""}
          <details class="mt-2"><summary class="text-xs text-muted cursor-pointer">Steps</summary>
            <ul class="text-xs font-mono space-y-1 mt-2">${(r.step_runs || [])
              .map((s) => `<li class="flex justify-between gap-2"><span>${s.position}. ${escapeHtml(s.name || s.step_id)} [${s.type}]</span><span class="badge ${s.status}">${s.status}</span></li>`)
              .join("")}</ul>
          </details>
        </div>`,
        )
        .join("")}</div>`
    : `<p class="text-sm text-muted">No runs yet.</p>`;
  $("#modal").classList.remove("hidden");
}

// ---------- Integrations ----------

async function loadIntegrations() {
  try {
    state.integrations = await api("/api/v1/integrations");
    if (!state.integrations.length) {
      $("#integrations-list").innerHTML = `<div class="card text-sm text-muted col-span-full">No integrations yet.</div>`;
      return;
    }
    $("#integrations-list").innerHTML = state.integrations
      .map(
        (i) => `
        <div class="card">
          <div class="flex items-start justify-between mb-2">
            <div>
              <h3 class="font-semibold">${escapeHtml(i.name)}</h3>
              <p class="text-xs text-muted">${i.kind}</p>
            </div>
            <span class="badge ${i.is_active ? "active" : "inactive"}">${i.is_active ? "active" : "inactive"}</span>
          </div>
          <pre class="text-xs text-muted whitespace-pre-wrap">${escapeHtml(JSON.stringify(i.config || {}, null, 2))}</pre>
          <div class="flex gap-2 mt-2">
            <button data-action="delete-integ" data-id="${i.id}" class="text-xs text-danger hover:underline cursor-pointer">Delete</button>
          </div>
        </div>`,
      )
      .join("");
  } catch (err) { toast(err.message, "danger"); }
}

$("#integrations-list").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-action='delete-integ']");
  if (!btn) return;
  if (!confirm("Delete this integration?")) return;
  try {
    await api(`/api/v1/integrations/${btn.dataset.id}`, { method: "DELETE" });
    refresh();
  } catch (err) { toast(err.message, "danger"); }
});

$("#new-integration").addEventListener("click", () => {
  $("#modal-title").textContent = "New integration";
  $("#modal-body").innerHTML = `
    <form id="integ-form" class="space-y-3">
      <div class="grid grid-cols-2 gap-3">
        <label class="block">
          <span class="text-sm font-medium">Name</span>
          <input name="name" required class="mt-1 w-full px-3 py-2 border border-line rounded-md cursor-text" />
        </label>
        <label class="block">
          <span class="text-sm font-medium">Kind</span>
          <select name="kind" class="mt-1 w-full px-3 py-2 border border-line rounded-md bg-white cursor-pointer">
            <option value="http">http</option>
            <option value="email">email</option>
            <option value="slack">slack</option>
            <option value="database">database</option>
            <option value="openai">openai</option>
            <option value="anthropic">anthropic</option>
            <option value="file">file</option>
          </select>
        </label>
      </div>
      <label class="block">
        <span class="text-sm font-medium">Config (JSON)</span>
        <textarea name="config" rows="3" placeholder='{"base_url":"https://api.example.com"}' class="mt-1 w-full px-3 py-2 border border-line rounded-md font-mono text-xs cursor-text">{}</textarea>
      </label>
      <label class="block">
        <span class="text-sm font-medium">Secret (JSON — never echoed back)</span>
        <textarea name="secret" rows="3" placeholder='{"api_key":"..."}' class="mt-1 w-full px-3 py-2 border border-line rounded-md font-mono text-xs cursor-text">{}</textarea>
      </label>
      <div class="flex justify-end gap-2 pt-3 border-t border-line">
        <button type="button" id="cancel-integ" class="px-4 py-2 border border-line rounded-md hover:bg-primary-50 cursor-pointer transition-colors duration-150">Cancel</button>
        <button type="submit" class="px-4 py-2 bg-primary text-white rounded-md hover:bg-primary-700 cursor-pointer transition-colors duration-150">Create</button>
      </div>
    </form>`;
  $("#modal").classList.remove("hidden");
  $("#cancel-integ").addEventListener("click", closeModal);
  $("#integ-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    let config = {}, secret = {};
    try { config = JSON.parse(fd.get("config") || "{}"); } catch (err) { toast("config must be valid JSON", "danger"); return; }
    try { secret = JSON.parse(fd.get("secret") || "{}"); } catch (err) { toast("secret must be valid JSON", "danger"); return; }
    try {
      await api("/api/v1/integrations", {
        method: "POST",
        body: JSON.stringify({ name: fd.get("name"), kind: fd.get("kind"), config, secret, is_active: true }),
      });
      toast("Integration created", "active");
      closeModal();
      refresh();
    } catch (err) { toast(err.message, "danger"); }
  });
});

// ---------- Agents ----------

async function loadAgents() {
  try {
    state.agents = await api("/api/v1/agents");
    if (!state.agents.length) {
      $("#agents-list").innerHTML = `<div class="card text-sm text-muted col-span-full">No agents yet.</div>`;
      return;
    }
    $("#agents-list").innerHTML = state.agents
      .map(
        (a) => `
        <div class="card">
          <div class="flex items-start justify-between mb-1">
            <h3 class="font-semibold">${escapeHtml(a.name)}</h3>
            <span class="badge active">${a.provider}</span>
          </div>
          <p class="text-xs text-muted mb-2">${escapeHtml(a.description || "")}</p>
          <p class="text-xs"><span class="text-muted">Model:</span> <code>${escapeHtml(a.model)}</code></p>
          <p class="text-xs"><span class="text-muted">Temperature:</span> ${a.temperature}</p>
        </div>`,
      )
      .join("");
  } catch (err) { toast(err.message, "danger"); }
}

$("#new-agent").addEventListener("click", () => {
  $("#modal-title").textContent = "New agent";
  $("#modal-body").innerHTML = `
    <form id="agent-form" class="space-y-3">
      <div class="grid grid-cols-2 gap-3">
        <label class="block">
          <span class="text-sm font-medium">Name</span>
          <input name="name" required class="mt-1 w-full px-3 py-2 border border-line rounded-md cursor-text" />
        </label>
        <label class="block">
          <span class="text-sm font-medium">Provider</span>
          <select name="provider" class="mt-1 w-full px-3 py-2 border border-line rounded-md bg-white cursor-pointer">
            <option value="stub">stub</option>
            <option value="openai">openai</option>
            <option value="anthropic">anthropic</option>
          </select>
        </label>
      </div>
      <label class="block">
        <span class="text-sm font-medium">Model</span>
        <input name="model" value="stub-1" class="mt-1 w-full px-3 py-2 border border-line rounded-md cursor-text" />
      </label>
      <label class="block">
        <span class="text-sm font-medium">System prompt</span>
        <textarea name="system_prompt" rows="3" class="mt-1 w-full px-3 py-2 border border-line rounded-md cursor-text"></textarea>
      </label>
      <div class="flex justify-end gap-2 pt-3 border-t border-line">
        <button type="button" id="cancel-agent" class="px-4 py-2 border border-line rounded-md hover:bg-primary-50 cursor-pointer transition-colors duration-150">Cancel</button>
        <button type="submit" class="px-4 py-2 bg-primary text-white rounded-md hover:bg-primary-700 cursor-pointer transition-colors duration-150">Create</button>
      </div>
    </form>`;
  $("#modal").classList.remove("hidden");
  $("#cancel-agent").addEventListener("click", closeModal);
  $("#agent-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    try {
      await api("/api/v1/agents", {
        method: "POST",
        body: JSON.stringify({
          name: fd.get("name"),
          provider: fd.get("provider"),
          model: fd.get("model"),
          system_prompt: fd.get("system_prompt") || "",
          temperature: 0.2,
        }),
      });
      toast("Agent created", "active");
      closeModal();
      refresh();
    } catch (err) { toast(err.message, "danger"); }
  });
});

$("#llm-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.currentTarget);
  $("#llm-output").classList.remove("hidden");
  $("#llm-output").textContent = "Running…";
  try {
    const res = await api("/api/v1/agents/complete", {
      method: "POST",
      body: JSON.stringify({
        prompt: fd.get("prompt"),
        provider: fd.get("provider"),
        model: fd.get("model") || null,
        temperature: parseFloat(fd.get("temperature") || "0.2"),
      }),
    });
    $("#llm-output").textContent = JSON.stringify(res, null, 2);
  } catch (err) {
    $("#llm-output").textContent = "Error: " + err.message;
  }
});

// ---------- ETL ----------

$("#etl-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.currentTarget);
  const kind = fd.get("kind");
  const body = fd.get("body") || "";
  let source, transform = null;
  if (kind === "inline") {
    try { source = { kind: "inline", data: JSON.parse(body) }; }
    catch { $("#etl-output").textContent = "Body must be valid JSON array."; return; }
  } else if (kind === "json") {
    source = { kind: "json", text: body };
  } else if (kind === "csv") {
    source = { kind: "csv", text: body };
  } else if (kind === "http") {
    try { source = { kind: "http", ...JSON.parse(body) }; }
    catch { $("#etl-output").textContent = "Body must be valid JSON: {\"url\":\"...\"}."; return; }
  }
  if (fd.get("transform")) {
    try { transform = JSON.parse(fd.get("transform")); }
    catch { $("#etl-output").textContent = "Transform must be valid JSON."; return; }
  }
  try {
    const res = await api("/api/v1/etl/run", { method: "POST", body: JSON.stringify({ source, transform }) });
    $("#etl-output").textContent = JSON.stringify(res, null, 2);
  } catch (err) {
    $("#etl-output").textContent = "Error: " + err.message;
  }
});

// ---------- Audit ----------

async function loadAudit() {
  try {
    state.audit = await api("/api/v1/audit?limit=50");
    if (!state.audit.length) {
      $("#audit-list").innerHTML = `<div class="p-4 text-sm text-muted">No audit entries yet.</div>`;
      return;
    }
    $("#audit-list").innerHTML = state.audit
      .map(
        (a) => `
        <div class="px-5 py-3 flex items-center justify-between">
          <div>
            <span class="font-mono text-xs">${a.action}</span>
            <span class="text-xs text-muted">· ${a.target_type || ""} ${a.target_id ? a.target_id.slice(0, 8) : ""}</span>
          </div>
          <span class="text-xs text-muted">${a.created_at}</span>
        </div>`,
      )
      .join("");
  } catch (err) { toast(err.message, "danger"); }
}

// ---------- Modal helpers ----------

function closeModal() { $("#modal").classList.add("hidden"); }
$("#modal-close").addEventListener("click", closeModal);
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });

// ---------- Toast ----------

let toastTimer;
function toast(message, kind = "active") {
  let el = $("#toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    el.className = "fixed bottom-6 right-6 z-50 px-4 py-2 rounded-md text-white text-sm transition-opacity duration-150";
    document.body.appendChild(el);
  }
  el.className = `fixed bottom-6 right-6 z-50 px-4 py-2 rounded-md text-white text-sm bg-${kind === "danger" ? "danger" : kind === "active" ? "accent" : "primary"}`;
  el.textContent = message;
  el.style.opacity = "1";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.style.opacity = "0"; }, 2400);
}

// ---------- Utils ----------

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function escapeAttr(s) { return escapeHtml(s); }

// ---------- Boot ----------

(async function boot() {
  if (state.token) {
    try {
      state.user = await api("/api/v1/auth/me");
      localStorage.setItem(USER_KEY, JSON.stringify(state.user));
      showApp();
    } catch (err) {
      logout();
    }
  } else {
    showLogin();
  }
})();
