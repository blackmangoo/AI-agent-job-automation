const BACKEND_URL = "http://127.0.0.1:8000";

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

// Load stored settings and stats
chrome.storage.local.get(["dryRun", "skipIneligible", "stats", "logs", "botRunning"], (res) => {
  if (res.dryRun !== undefined) settingDryRun.checked = res.dryRun;
  if (res.skipIneligible !== undefined) settingSkipIneligible.checked = res.skipIneligible;
  if (res.stats) {
    statsScanned.textContent = res.stats.scanned || 0;
    statsApplied.textContent = res.stats.applied || 0;
  }
  if (res.logs) {
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

// Check local backend status
function checkBackendStatus() {
  fetch(`${BACKEND_URL}/status`)
    .then((response) => response.json())
    .then((data) => {
      if (data.status === "online") {
        statusDot.className = "status-dot online";
        statusText.textContent = "Backend Online";
        // Only enable start button if bot is not already running
        chrome.storage.local.get("botRunning", (res) => {
          if (!res.botRunning) btnStart.disabled = false;
        });
      } else {
        setOffline();
      }
    })
    .catch(() => {
      setOffline();
    });
}

function setOffline() {
  statusDot.className = "status-dot offline";
  statusText.textContent = "Backend Offline";
  btnStart.disabled = true;
  chrome.storage.local.set({ botRunning: false });
  toggleBotUI(false);
}

// Check every 3 seconds
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
    // Check if backend is online before enabling
    fetch(`${BACKEND_URL}/status`).then(() => {
      btnStart.disabled = false;
    }).catch(() => {
      btnStart.disabled = true;
    });
  }
}

// Start Bot
btnStart.addEventListener("click", () => {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs[0] && tabs[0].url.includes("indeed.com")) {
      const config = {
        dryRun: settingDryRun.checked,
        skipIneligible: settingSkipIneligible.checked
      };
      
      chrome.storage.local.set({ botRunning: true });
      toggleBotUI(true);

      // Send start message to content script
      chrome.tabs.sendMessage(tabs[0].id, { action: "start", config: config }, (response) => {
        if (chrome.runtime.lastError) {
          logToTerminal("Error: Failed to contact Page. Try reloading the tab.");
          chrome.storage.local.set({ botRunning: false });
          toggleBotUI(false);
        }
      });
    } else {
      logToTerminal("Error: Please open Indeed.com first.");
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
    chrome.storage.local.set({ logs: logs.slice(-100) }); // Keep last 100 logs
  });
}

// Listen for logs and stat updates from content script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "updateLog") {
    // The message is already pre-formatted with timestamp and saved by content.js
    terminal.textContent += `\n${request.message}`;
    scrollToBottom();
  } else if (request.action === "updateStats") {
    statsScanned.textContent = request.stats.scanned;
    statsApplied.textContent = request.stats.applied;
  }
});

// React to storage changes dynamically (e.g. when content script stops bot)
chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName === "local") {
    if (changes.botRunning !== undefined) {
      toggleBotUI(changes.botRunning.newValue);
    }
    if (changes.stats !== undefined) {
      statsScanned.textContent = changes.stats.newValue.scanned || 0;
      statsApplied.textContent = changes.stats.newValue.applied || 0;
    }
  }
});
