// Candidate backend URLs in priority order
const BACKEND_CANDIDATES = [
  "http://127.0.0.1:8005",
  "http://localhost:8005",
  "http://127.0.0.1:8000",
  "http://localhost:8000",
  "http://127.0.0.1:8006"
];

let activeBackendUrl = "http://127.0.0.1:8005";
let isChecking = false;

// UI elements
const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");
const btnStart = document.getElementById("btnStart");
const btnStop = document.getElementById("btnStop");
const statsScanned = document.getElementById("statsScanned");
const statsApplied = document.getElementById("statsApplied");
const statsSuccessRate = document.getElementById("statsSuccessRate");
const settingAutoSubmit = document.getElementById("settingAutoSubmit");
const settingSkipIneligible = document.getElementById("settingSkipIneligible");
const terminal = document.getElementById("terminal");
const btnClearLogs = document.getElementById("btnClearLogs");
const activityRole = document.getElementById("activityRole");
const activityStatusText = document.getElementById("activityStatusText");
const activityTime = document.getElementById("activityTime");

function updateSuccessRate(scanned, applied) {
  if (!statsSuccessRate) return;
  const s = parseInt(scanned) || 0;
  const a = parseInt(applied) || 0;
  if (s === 0) {
    statsSuccessRate.textContent = "0%";
  } else {
    statsSuccessRate.textContent = Math.round((a / s) * 100) + "%";
  }
}

// Load stored settings, stats, and active backend URL
chrome.storage.local.get([
  "autoSubmit",
  "dryRun",
  "skipIneligible",
  "stats",
  "logs",
  "botRunning",
  "activeBackendUrl",
  "currentActivity"
], (res) => {
  // autoSubmit defaults to true (dryRun = false)
  if (res.autoSubmit !== undefined) {
    settingAutoSubmit.checked = res.autoSubmit;
  } else if (res.dryRun !== undefined) {
    settingAutoSubmit.checked = !res.dryRun;
  } else {
    settingAutoSubmit.checked = true;
  }

  if (res.skipIneligible !== undefined) {
    settingSkipIneligible.checked = res.skipIneligible;
  } else {
    settingSkipIneligible.checked = true;
  }

  if (res.activeBackendUrl) activeBackendUrl = res.activeBackendUrl;

  const scanned = (res.stats && res.stats.scanned) || 0;
  const applied = (res.stats && res.stats.applied) || 0;
  statsScanned.textContent = scanned;
  statsApplied.textContent = applied;
  updateSuccessRate(scanned, applied);

  if (res.currentActivity) {
    if (activityRole && res.currentActivity.role) activityRole.textContent = res.currentActivity.role;
    if (activityStatusText && res.currentActivity.status) activityStatusText.textContent = res.currentActivity.status;
    if (activityTime) activityTime.textContent = res.currentActivity.time || "Active";
  }

  if (res.logs && res.logs.length > 0) {
    terminal.textContent = res.logs.join("\n");
    scrollToBottom();
  }

  if (res.botRunning) {
    toggleBotUI(true);
  }
});

// Settings change handlers
settingAutoSubmit.addEventListener("change", () => {
  const autoSubmit = settingAutoSubmit.checked;
  chrome.storage.local.set({
    autoSubmit: autoSubmit,
    dryRun: !autoSubmit
  });
});

settingSkipIneligible.addEventListener("change", () => {
  chrome.storage.local.set({ skipIneligible: settingSkipIneligible.checked });
});

// Clear logs button
btnClearLogs.addEventListener("click", () => {
  terminal.textContent = "Logs cleared.";
  chrome.storage.local.set({ logs: [] });
});

// Helper: check a single URL with strict timeout
async function pingUrl(url) {
  try {
    const res = await fetch(`${url}/status`, { signal: AbortSignal.timeout(1200) });
    if (res.ok) {
      const data = await res.json();
      if (data.status === "online") return true;
    }
  } catch (e) {
    // Timeout or connection error
  }
  return false;
}

// Probe all backend candidates
async function checkBackendStatus() {
  if (isChecking) return;
  isChecking = true;

  try {
    // Check currently active URL first
    if (await pingUrl(activeBackendUrl)) {
      setOnline(activeBackendUrl);
      isChecking = false;
      return;
    }

    // Try background worker check as fallback
    const bgResponse = await new Promise((resolve) => {
      chrome.runtime.sendMessage({ action: "checkStatus" }, (resp) => {
        if (chrome.runtime.lastError || !resp) {
          resolve(null);
        } else {
          resolve(resp);
        }
      });
    });

    if (bgResponse && bgResponse.online && bgResponse.url) {
      setOnline(bgResponse.url);
      isChecking = false;
      return;
    }

    // Direct probe all remaining candidate URLs
    for (const url of BACKEND_CANDIDATES) {
      if (url === activeBackendUrl) continue;
      if (await pingUrl(url)) {
        setOnline(url);
        isChecking = false;
        return;
      }
    }

    // None responded
    setOffline();
  } catch (err) {
    setOffline();
  } finally {
    isChecking = false;
  }
}

function setOnline(url) {
  activeBackendUrl = url;
  chrome.storage.local.set({ activeBackendUrl: url });
  statusDot.className = "status-dot online";
  statusText.textContent = "Online";
  chrome.storage.local.get("botRunning", (res) => {
    if (!res.botRunning) btnStart.disabled = false;
  });
}

function setOffline() {
  statusDot.className = "status-dot offline";
  statusText.textContent = "Offline";
  btnStart.disabled = true;
  chrome.storage.local.set({ botRunning: false });
  toggleBotUI(false);
}

// Initial check and periodic polling
checkBackendStatus();
setInterval(checkBackendStatus, 3000);

// Helper: Scroll terminal to bottom
function scrollToBottom() {
  terminal.scrollTop = terminal.scrollHeight;
}

// Toggle Start/Stop buttons in UI
function toggleBotUI(running) {
  if (running) {
    btnStart.style.display = "none";
    btnStop.style.display = "flex";
    if (activityStatusText) activityStatusText.textContent = "Running auto-apply loop...";
  } else {
    btnStart.style.display = "flex";
    btnStop.style.display = "none";
    if (activityStatusText) activityStatusText.textContent = "Ready";
  }
}

// Start Bot
btnStart.addEventListener("click", () => {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const currentTab = tabs[0];
    if (currentTab && currentTab.url && (currentTab.url.includes("indeed.com") || currentTab.url.includes("smartapply"))) {
      const isAutoSubmit = settingAutoSubmit.checked;
      const config = {
        dryRun: !isAutoSubmit,
        autoSubmit: isAutoSubmit,
        skipIneligible: settingSkipIneligible.checked,
        backendUrl: activeBackendUrl
      };

      // Set storage state - triggers content scripts immediately via storage.onChanged
      chrome.storage.local.set({
        botRunning: true,
        dryRun: config.dryRun,
        autoSubmit: config.autoSubmit,
        skipIneligible: config.skipIneligible,
        activeBackendUrl: activeBackendUrl,
        triggerTime: Date.now()
      });
      toggleBotUI(true);
      logToTerminal("Starting bot on " + (currentTab.title ? currentTab.title.substring(0, 30) : "Indeed tab") + "...");

      const tabId = currentTab.id;

      // Deliver start signal
      chrome.tabs.sendMessage(tabId, { action: "start", config: config }, (response) => {
        if (chrome.runtime.lastError) {
          // Content script not loaded yet (e.g. extension reloaded). Inject into top frame!
          chrome.scripting.executeScript({
            target: { tabId: tabId },
            files: ["content.js"]
          }, () => {
            if (chrome.runtime.lastError) {
              logToTerminal("Notice: Tab connection issue (" + chrome.runtime.lastError.message + "). Refresh the Indeed tab once.");
              chrome.storage.local.set({ botRunning: false });
              toggleBotUI(false);
            } else {
              setTimeout(() => {
                chrome.tabs.sendMessage(tabId, { action: "start", config: config }, () => {
                  if (chrome.runtime.lastError) {
                    // Handled automatically by storage.onChanged
                  }
                });
              }, 100);
            }
          });
        }
      });
    } else {
      logToTerminal("Error: Please open an Indeed.com page first.");
    }
  });
});

// Stop Bot
btnStop.addEventListener("click", () => {
  chrome.storage.local.set({ botRunning: false });
  toggleBotUI(false);

  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs[0]) {
      chrome.tabs.sendMessage(tabs[0].id, { action: "stop" }, () => {
        if (chrome.runtime.lastError) { /* ignore */ }
      });
    }
  });
  logToTerminal("Bot stopped by user.");
});

// Log helper
function logToTerminal(message) {
  const timestamp = new Date().toLocaleTimeString();
  const logLine = `[${timestamp}] ${message}`;
  terminal.textContent += `\n${logLine}`;
  scrollToBottom();

  chrome.storage.local.get("logs", (res) => {
    const logs = res.logs || [];
    logs.push(logLine);
    chrome.storage.local.set({ logs: logs.slice(-100) });
  });
}

// Listen for logs and stat updates from content script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "updateLog") {
    terminal.textContent += `\n${request.message}`;
    scrollToBottom();
  } else if (request.action === "updateStats") {
    const s = request.stats.scanned || 0;
    const a = request.stats.applied || 0;
    statsScanned.textContent = s;
    statsApplied.textContent = a;
    updateSuccessRate(s, a);
  } else if (request.action === "updateActivity") {
    if (activityRole && request.role) activityRole.textContent = request.role;
    if (activityStatusText && request.status) activityStatusText.textContent = request.status;
    if (activityTime) activityTime.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    chrome.storage.local.set({
      currentActivity: {
        role: request.role,
        status: request.status,
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      }
    });
  }
});
