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
}

$("config").addEventListener("submit", async (event) => {
  event.preventDefault();
  const dashboardUrl = $("dashboardUrl").value.trim().replace(/\/+$/, "");
  let origin;
  try {
    origin = new URL(dashboardUrl).origin;
  } catch {
    setMessage("Enter a valid URL, e.g. https://autoapply.example.com", false);
    return;
  }
  // Ask for access to the dashboard origin only (optional host permission).
  const granted = await chrome.permissions.request({ origins: [`${origin}/*`] });
  if (!granted) {
    setMessage("Permission to contact your dashboard was denied.", false);
    return;
  }
  const update = { dashboardUrl };
  const token = $("token").value.trim();
  if (token) update.token = token;
  await chrome.storage.local.set(update);
  $("token").value = "";
  setMessage("Settings saved.", true);
  refresh();
});

$("sync").addEventListener("click", async () => {
  $("sync").disabled = true;
  $("sync").textContent = "Syncing…";
  const result = await chrome.runtime.sendMessage({ type: "sync" });
  $("sync").disabled = false;
  $("sync").textContent = "Sync LinkedIn session";
  setMessage(result.ok ? "Synced! Easy Apply is ready in your dashboard." : result.error, result.ok);
  refresh();
});

refresh();
