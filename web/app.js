/* const API = "http://localhost:8080/api"; */
let token = null;

function val(id) { return document.getElementById(id).value; }
function show(msg) { document.getElementById("msg").textContent = msg; }

async function register() {
  const res = await fetch(`/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: val("username"), email: val("email"), password: val("password") }),
  });
  show(res.ok ? "Cadastrado! Agora entre." : "Erro no cadastro.");
}

async function login() {
  const res = await fetch(`/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: val("email"), password: val("password") }),
  });
  if (!res.ok) { show("Credenciais inválidas."); return; }
  token = (await res.json()).access_token;
  document.getElementById("auth").style.display = "none";
  document.getElementById("app").style.display = "block";
  loadTasks(true);
}

async function logout() {
  await fetch(`/auth/logout`, { method: "POST", headers: { Authorization: `Bearer ${token}` } });
  token = null;
  document.getElementById("auth").style.display = "block";
  document.getElementById("app").style.display = "none";
}

async function createTask() {
  await fetch(`/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ title: val("title"), description: val("description"), due_date: val("due_date") || null }),
  });
  loadTasks(true);
}

async function loadTasks(clear = false) {
  const date = clear ? "" : val("filter_date");
  const url = date ? `/tasks?date=${date}` : `/tasks`;
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  const tasks = await res.json();
  const ul = document.getElementById("tasks");
  ul.innerHTML = "";
  tasks.forEach(t => {
    const li = document.createElement("li");
    li.textContent = `${t.title} (${t.due_date || "sem data"}) `;
    const del = document.createElement("button");
    del.textContent = "excluir";
    del.onclick = async () => {
      await fetch(`/tasks/${t.id}`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` } });
      loadTasks(true);
    };
    li.appendChild(del);
    ul.appendChild(li);
  });
}
