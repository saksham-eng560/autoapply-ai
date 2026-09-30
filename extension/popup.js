const $ = (id) => document.getElementById(id);

function setMessage(text, ok) {
  const el = $("message");
  el.textContent = text || "";
  el.className = ok ? "ok" : "err";
  el.style.marginTop = text ? "6px" : "0";
}

async function refresh() {
  const status = await chrome.runtime.sendMessage({ type: "status" });
  if (status.dashboardUrl) $("dashboardUrl").value = status.dashboardUrl;
  $("token").placeholder = status.token ? "•••••••• (saved — paste to replace)" : $("token").placeholder;
  $("login").textContent = status.loggedIn ? "✓ logged in" : "not logged in";
  $("login").className = status.loggedIn ? "ok" : "err";
  $("lastSync").textContent = status.lastSync ? new Date(status.lastSync).toLocaleString() : "never";
  if (status.lastError) setMessage(status.lastError, false);
  else if (status.dashboardUrl && status.token) setMessage("", true);
}

// Saves whatever is in the form. Settings are stored BEFORE asking for the host permission:
// Chrome often closes the popup when its permission prompt opens, which used to lose the save.
async function saveSettings() {
  const dashboardUrl = $("dashboardUrl").value.trim().replace(/\/+$/, "");
  let origin;
  try {
    origin = new URL(dashboardUrl).origin;
  } catch {
    setMessage("Enter a valid URL, e.g. http://localhost:3000", false);
    return false;
  }
  const update = { dashboardUrl, lastError: null };
  const token = $("token").value.trim();
  if (token) update.token = token;
  await chrome.storage.local.set(update);
  $("token").value = "";
  return ensurePermission(origin);
}

// Asks for access to the dashboard origin only (optional host permission).
async function ensurePermission(origin) {
  const origins = [`${origin}/*`];
  if (await chrome.permissions.contains({ origins })) return true;
  const granted = await chrome.permissions.request({ origins });
  if (!granted) setMessage(`Allow access to ${origin} when Chrome asks, then try again.`, false);
  return granted;
}

function hasUnsavedInput(saved) {
  const url = $("dashboardUrl").value.trim().replace(/\/+$/, "");
  return Boolean($("token").value.trim()) || (url && url !== saved.dashboardUrl);
}

$("config").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (await saveSettings()) setMessage("Settings saved.", true);
  refresh();
});

$("sync").addEventListener("click", async () => {
  const saved = await chrome.runtime.sendMessage({ type: "status" });
  if (hasUnsavedInput(saved) && !(await saveSettings())) return;
  const { dashboardUrl } = await chrome.storage.local.get("dashboardUrl");
  if (dashboardUrl && !(await ensurePermission(new URL(dashboardUrl).origin))) return;
  $("sync").disabled = true;
  $("sync").textContent = "Syncing…";
  const result = await chrome.runtime.sendMessage({ type: "sync" });
  $("sync").disabled = false;
  $("sync").textContent = "Sync LinkedIn session";
  setMessage(result.ok ? "Synced! Easy Apply is ready in your dashboard." : result.error, result.ok);
  refresh();
});


refresh();
