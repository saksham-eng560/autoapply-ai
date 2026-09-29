/**
 * AutoApply AI extension service worker.
 *
 * Reads the LinkedIn `li_at` session cookie (only when you're logged in) and sends it to YOUR
 * AutoApply AI dashboard over HTTPS, authenticated with a limited-scope extension token.
 * The backend stores it encrypted (AES-256-GCM). Nothing is sent anywhere else.
 */

const SYNC_ALARM = "autoapply-linkedin-sync";
const SYNC_EVERY_MINUTES = 12 * 60;

async function getConfig() {
  const { dashboardUrl, token, profileUrl, lastSync, lastError } = await chrome.storage.local.get([
    "dashboardUrl", "token", "profileUrl", "lastSync", "lastError",
  ]);
  return { dashboardUrl: (dashboardUrl || "").replace(/\/+$/, ""), token, profileUrl, lastSync, lastError };
}

async function readLinkedInCookie() {
  const cookie = await chrome.cookies.get({ url: "https://www.linkedin.com", name: "li_at" });
  return cookie ? cookie.value : null;
}

async function syncSession(reason = "manual") {
  const config = await getConfig();
  if (!config.dashboardUrl || !config.token) {
    return { ok: false, error: "Set your dashboard URL and extension token first." };
  }
  const liAt = await readLinkedInCookie();
  if (!liAt) {
    const error = "You're not logged into LinkedIn in this browser.";
    await chrome.storage.local.set({ lastError: error });
    return { ok: false, error };
  }
  try {
    const response = await fetch(`${config.dashboardUrl}/api/v1/users/me/integrations/linkedin-cookie`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${config.token}` },
      body: JSON.stringify({ li_at: liAt, profile_url: config.profileUrl || null }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      const error = response.status === 401
        ? "Token rejected — generate a new extension token in Settings → Integrations."
        : `Sync failed (${response.status}) ${body.detail || ""}`.trim();
      await chrome.storage.local.set({ lastError: error });
      return { ok: false, error };
    }
    const lastSync = new Date().toISOString();
    await chrome.storage.local.set({ lastSync, lastError: null, lastReason: reason });
    await chrome.action.setBadgeText({ text: "" });
    return { ok: true, lastSync };
  } catch (err) {
    const error = `Could not reach ${config.dashboardUrl}: ${err.message || err}`;
    await chrome.storage.local.set({ lastError: error });
    return { ok: false, error };
  }
}

// Periodic re-sync keeps the backend's copy fresh (LinkedIn rotates sessions).
chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(SYNC_ALARM, { periodInMinutes: SYNC_EVERY_MINUTES });
});
chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create(SYNC_ALARM, { periodInMinutes: SYNC_EVERY_MINUTES });
});
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === SYNC_ALARM) syncSession("scheduled");
});

// Re-sync shortly after LinkedIn issues a new session cookie (login / rotation).
let debounce;
chrome.cookies.onChanged.addListener(({ cookie, removed }) => {
  if (cookie.name !== "li_at" || !cookie.domain.includes("linkedin.com") || removed) return;
  clearTimeout(debounce);
  debounce = setTimeout(() => syncSession("cookie-changed"), 5000);
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "sync") {
    syncSession("manual").then(sendResponse);
    return true;
  }
  if (message?.type === "profile-url" && typeof message.url === "string" && message.url.includes("linkedin.com/in/")) {
    chrome.storage.local.set({ profileUrl: message.url.split("?")[0] });
  }
  if (message?.type === "status") {
    Promise.all([getConfig(), readLinkedInCookie()]).then(([config, cookie]) =>
      sendResponse({ ...config, token: config.token ? "set" : null, loggedIn: !!cookie }),
    );
    return true;
  }
  return false;
});
