/* Caminhos relativos mantidos — nginx proxy roteia /auth/* e /tasks/* */
let token = null;
let editingId = null;

function val(id) { return document.getElementById(id).value; }

// ===== Toasts =====

function toast(msg, type = "info") {
  const icons = { success: "✓", error: "✕", info: "ℹ" };
  const el = document.createElement("div");
  el.className = `toast toast-${type}`;
  el.innerHTML = `<span class="toast-icon">${icons[type] || "ℹ"}</span><span>${msg}</span>`;
  document.getElementById("toast-container").appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

// ===== Tratamento central de erros de API =====

async function handleApiError(res) {
  if (res.status === 401) {
    toast("Sessão expirada. Faça login novamente.", "error");
    token = null;
    setTimeout(() => {
      document.getElementById("auth-page").style.display = "block";
      document.getElementById("app-page").style.display  = "none";
    }, 1400);
    return true;
  }
  return false;
}

// ===== Loading do botão de criar =====

function setBtnLoading(loading) {
  const btn = document.getElementById("btn-add");
  btn.disabled = loading;
  btn.textContent = loading ? "Adicionando…" : "+ Adicionar";
}

// ===== Auth =====

function showAuthMsg(msg, ok = false) {
  const el = document.getElementById("auth-msg");
  el.textContent = msg;
  el.style.color = ok ? "#16a34a" : "#ef4444";
}

function showTab(tab) {
  document.getElementById("form-login").style.display    = tab === "login"    ? "" : "none";
  document.getElementById("form-register").style.display = tab === "register" ? "" : "none";
  document.getElementById("tab-login").classList.toggle("active",    tab === "login");
  document.getElementById("tab-register").classList.toggle("active", tab === "register");
  document.getElementById("auth-msg").textContent = "";
}

function toggleTheme() {
  const html = document.documentElement;
  const next = html.getAttribute("data-theme") === "dark" ? "light" : "dark";
  html.setAttribute("data-theme", next);
  document.getElementById("theme-btn").textContent = next === "dark" ? "☀️" : "🌙";
  localStorage.setItem("ll-theme", next);
}

(function () {
  const saved = localStorage.getItem("ll-theme") || "light";
  document.documentElement.setAttribute("data-theme", saved);
  const btn = document.getElementById("theme-btn");
  if (btn) btn.textContent = saved === "dark" ? "☀️" : "🌙";
})();

async function register() {
  try {
    const res = await fetch("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: val("reg-username"),
        email:    val("reg-email"),
        password: val("reg-password"),
      }),
    });
    if (res.ok) {
      showAuthMsg("Conta criada! Faça login.", true);
      showTab("login");
    } else {
      showAuthMsg("Erro no cadastro. Tente outro e-mail.");
    }
  } catch {
    showAuthMsg("Sem conexão com o servidor.");
  }
}

async function login() {
  try {
    const res = await fetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: val("login-email"), password: val("login-password") }),
    });
    if (!res.ok) { showAuthMsg("E-mail ou senha incorretos."); return; }
    token = (await res.json()).access_token;
    document.getElementById("auth-page").style.display = "none";
    document.getElementById("app-page").style.display  = "block";
    loadTasks();
  } catch {
    showAuthMsg("Sem conexão com o servidor.");
  }
}

async function logout() {
  try {
    await fetch("/auth/logout", { method: "POST", headers: { Authorization: `Bearer ${token}` } });
  } catch { /* ignora erro no logout */ }
  token = null;
  document.getElementById("auth-page").style.display = "block";
  document.getElementById("app-page").style.display  = "none";
}

// ===== Tarefas =====

async function createTask() {
  if (!val("title").trim()) { toast("Título é obrigatório.", "error"); return; }
  setBtnLoading(true);
  try {
    const res = await fetch("/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({
        title:       val("title"),
        description: val("description"),
        due_date:    val("due_date") || null,
        priority:    val("priority"),
      }),
    });
    if (await handleApiError(res)) return;
    if (res.ok) {
      ["title", "description", "due_date"].forEach(id => (document.getElementById(id).value = ""));
      document.getElementById("priority").value = "media";
      toast("Tarefa criada com sucesso.", "success");
      loadTasks();
    } else {
      const data = await res.json().catch(() => ({}));
      toast(data.error || "Erro ao criar tarefa.", "error");
    }
  } catch {
    toast("Sem conexão com o servidor.", "error");
  } finally {
    setBtnLoading(false);
  }
}

function isOverdue(task) {
  if (!task.due_date || task.done) return false;
  return task.due_date < new Date().toISOString().slice(0, 10);
}

const PRIORITY_LABEL = { baixa: "Baixa", media: "Média", alta: "Alta" };

function updateDashboard(tasks) {
  const total      = tasks.length;
  const concluidas = tasks.filter(t => t.done).length;
  const pendentes  = total - concluidas;
  const atrasadas  = tasks.filter(t => isOverdue(t)).length;

  document.querySelector("#stat-total .stat-num").textContent      = total;
  document.querySelector("#stat-pendentes .stat-num").textContent  = pendentes;
  document.querySelector("#stat-concluidas .stat-num").textContent = concluidas;
  document.querySelector("#stat-atrasadas .stat-num").textContent  = atrasadas;
  document.getElementById("stat-atrasadas").classList.toggle("stat-danger", atrasadas > 0);
}

async function toggleDone(id, currentDone) {
  try {
    const res = await fetch(`/tasks/${id}/done`, {
      method: "PATCH",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (await handleApiError(res)) return;
    if (res.ok) {
      toast(currentDone ? "Tarefa reaberta." : "Tarefa concluída!", "success");
      loadTasks();
    } else {
      toast("Erro ao atualizar tarefa.", "error");
    }
  } catch {
    toast("Sem conexão com o servidor.", "error");
  }
}

async function deleteTask(id) {
  if (!confirm("Excluir esta tarefa?\n\nEsta ação não pode ser desfeita.")) return;
  try {
    const res = await fetch(`/tasks/${id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (await handleApiError(res)) return;
    if (res.ok) {
      toast("Tarefa excluída.", "info");
      loadTasks();
    } else {
      toast("Erro ao excluir tarefa.", "error");
    }
  } catch {
    toast("Sem conexão com o servidor.", "error");
  }
}

function openEdit(task) {
  editingId = task.id;
  document.getElementById("edit-title").value       = task.title;
  document.getElementById("edit-description").value = task.description || "";
  document.getElementById("edit-due_date").value    = task.due_date || "";
  document.getElementById("edit-priority").value    = task.priority || "media";
  document.getElementById("edit-modal").classList.add("open");
}

function closeEdit() {
  document.getElementById("edit-modal").classList.remove("open");
  editingId = null;
}

async function saveEdit() {
  if (!val("edit-title").trim()) { toast("Título é obrigatório.", "error"); return; }
  const saveBtn = document.querySelector(".edit-actions .btn-primary");
  saveBtn.disabled = true;
  saveBtn.textContent = "Salvando…";
  try {
    const res = await fetch(`/tasks/${editingId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({
        title:       val("edit-title"),
        description: val("edit-description"),
        due_date:    val("edit-due_date") || null,
        priority:    val("edit-priority"),
      }),
    });
    if (await handleApiError(res)) return;
    if (res.ok) {
      toast("Tarefa atualizada.", "success");
      closeEdit();
      loadTasks();
    } else {
      toast("Erro ao salvar tarefa.", "error");
    }
  } catch {
    toast("Sem conexão com o servidor.", "error");
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = "Salvar";
  }
}

// ===== Filtros =====

let _debounceTimer = null;
function debouncedLoad() {
  clearTimeout(_debounceTimer);
  _debounceTimer = setTimeout(loadTasks, 300);
}

function clearFilters() {
  ["search", "filter_status", "filter_priority", "date_from", "date_to"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = "";
  });
  document.getElementById("sort").value = "due_date";
  loadTasks();
}

// ===== Carregamento de tarefas =====

async function loadTasks() {
  const ul         = document.getElementById("tasks");
  const emptyState = document.getElementById("empty-state");

  // Spinner enquanto carrega
  ul.innerHTML = '<li class="loading-row"><div class="spinner"></div></li>';
  emptyState.style.display = "none";

  const params = new URLSearchParams();
  const search   = val("search").trim();
  const status   = val("filter_status");
  const priority = val("filter_priority");
  const sort     = val("sort");
  const dateFrom = val("date_from");
  const dateTo   = val("date_to");

  if (search)   params.set("search",    search);
  if (status)   params.set("status",    status);
  if (priority) params.set("priority",  priority);
  if (sort)     params.set("sort",      sort);
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo)   params.set("date_to",   dateTo);

  let tasks;
  try {
    const res = await fetch(`/tasks${params.toString() ? "?" + params : ""}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (await handleApiError(res)) return;
    if (!res.ok) {
      toast("Erro ao carregar tarefas.", "error");
      ul.innerHTML = "";
      updateDashboard([]);
      return;
    }
    tasks = await res.json();
  } catch {
    toast("Sem conexão com o servidor.", "error");
    ul.innerHTML = "";
    updateDashboard([]);
    return;
  }

  ul.innerHTML = "";

  if (tasks.length === 0) {
    emptyState.style.display = "block";
    updateDashboard([]);
    return;
  }
  emptyState.style.display = "none";

  tasks.forEach(t => {
    const overdue = isOverdue(t);
    const li = document.createElement("li");
    li.className = "task-card" + (t.done ? " task-done" : "") + (overdue ? " task-overdue" : "");

    // Linha superior
    const top = document.createElement("div");
    top.className = "task-top";

    const chk = document.createElement("input");
    chk.type = "checkbox";
    chk.checked = t.done;
    chk.onchange = () => toggleDone(t.id, t.done);

    const titleEl = document.createElement("span");
    titleEl.className = "task-title";
    titleEl.textContent = t.title;

    const badgesEl = document.createElement("div");
    badgesEl.className = "task-badges";

    const pBadge = document.createElement("span");
    pBadge.className = `badge badge-${t.priority}`;
    pBadge.textContent = PRIORITY_LABEL[t.priority] || t.priority;
    badgesEl.appendChild(pBadge);

    if (overdue) {
      const ob = document.createElement("span");
      ob.className = "badge badge-atrasada";
      ob.textContent = "Atrasada";
      badgesEl.appendChild(ob);
    }

    top.append(chk, titleEl, badgesEl);

    // Linha inferior
    const bottom = document.createElement("div");
    bottom.className = "task-bottom";

    const meta = document.createElement("div");
    meta.className = "task-meta";

    const dateLine = document.createElement("span");
    dateLine.textContent = t.due_date ? `📅 ${t.due_date}` : "Sem data";
    meta.appendChild(dateLine);

    if (t.description) {
      const descLine = document.createElement("span");
      descLine.className = "task-desc";
      descLine.textContent = t.description;
      meta.appendChild(descLine);
    }

    const actions = document.createElement("div");
    actions.className = "task-actions";

    const editBtn = document.createElement("button");
    editBtn.className = "btn btn-ghost btn-sm";
    editBtn.textContent = "Editar";
    editBtn.onclick = () => openEdit(t);

    const delBtn = document.createElement("button");
    delBtn.className = "btn btn-ghost btn-sm btn-del";
    delBtn.textContent = "Excluir";
    delBtn.onclick = () => deleteTask(t.id);

    actions.append(editBtn, delBtn);
    bottom.append(meta, actions);
    li.append(top, bottom);
    ul.appendChild(li);
  });

  updateDashboard(tasks);
}
