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
const settingDryRun = document.getElementById("settingDryRun");
const settingSkipIneligible = document.getElementById("settingSkipIneligible");
const terminal = document.getElementById("terminal");
const btnClearLogs = document.getElementById("btnClearLogs");

// Load stored settings, stats, and active backend URL
chrome.storage.local.get(["dryRun", "skipIneligible", "stats", "logs", "botRunning", "activeBackendUrl"], (res) => {
  if (res.dryRun !== undefined) settingDryRun.checked = res.dryRun;
  if (res.skipIneligible !== undefined) settingSkipIneligible.checked = res.skipIneligible;
  if (res.activeBackendUrl) activeBackendUrl = res.activeBackendUrl;
  if (res.stats) {
    statsScanned.textContent = res.stats.scanned || 0;
    statsApplied.textContent = res.stats.applied || 0;
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
settingDryRun.addEventListener("change", () => {
  chrome.storage.local.set({ dryRun: settingDryRun.checked });
});
settingSkipIneligible.addEventListener("change", () => {
  chrome.storage.local.set({ skipIneligible: settingSkipIneligible.checked });
});

// Clear logs button
btnClearLogs.addEventListener("click", () => {
  terminal.textContent = "";
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
    // Timeout or network error
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
  statusText.textContent = "Backend Online";
  chrome.storage.local.get("botRunning", (res) => {
    if (!res.botRunning) btnStart.disabled = false;
  });
}

function setOffline() {
  statusDot.className = "status-dot offline";
  statusText.textContent = "Backend Offline";
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
  } else {
    btnStart.style.display = "flex";
    btnStop.style.display = "none";
  }
}

// Start Bot
btnStart.addEventListener("click", () => {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs[0] && tabs[0].url && tabs[0].url.includes("indeed.com")) {
      const config = {
        dryRun: settingDryRun.checked,
        skipIneligible: settingSkipIneligible.checked,
        backendUrl: activeBackendUrl
      };

      chrome.storage.local.set({ botRunning: true });
      toggleBotUI(true);

      const tabId = tabs[0].id;

      // Try sending message directly
      chrome.tabs.sendMessage(tabId, { action: "start", config: config }, (response) => {
        if (chrome.runtime.lastError) {
          // Content script is not injected in the tab yet (e.g. extension was just reloaded). Auto-inject it now!
          chrome.scripting.executeScript({
            target: { tabId: tabId, allFrames: true },
            files: ["content.js"]
          }, () => {
            if (chrome.runtime.lastError) {
              logToTerminal("Notice: Please refresh the Indeed tab once and click Start.");
              chrome.storage.local.set({ botRunning: false });
              toggleBotUI(false);
            } else {
              // Retry sending start message after injection
              setTimeout(() => {
                chrome.tabs.sendMessage(tabId, { action: "start", config: config }, (retryResp) => {
                  if (chrome.runtime.lastError) {
                    logToTerminal("Notice: Please refresh the Indeed tab once and click Start.");
                    chrome.storage.local.set({ botRunning: false });
                    toggleBotUI(false);
                  }
                });
              }, 150);
            }
          });
        }
      });
    } else {
      logToTerminal("Error: Please open an Indeed.com job page first.");
    }
  });
});

// Stop Bot
btnStop.addEventListener("click", () => {
  chrome.storage.local.set({ botRunning: false });
  toggleBotUI(false);

  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs[0]) {
      chrome.tabs.sendMessage(tabs[0].id, { action: "stop" });
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
    statsScanned.textContent = request.stats.scanned;
    statsApplied.textContent = request.stats.applied;
  }
});
