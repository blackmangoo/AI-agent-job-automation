// Indeed Auto-Applier Agent - Background Service Worker
const PROBE_URLS = [
  "http://127.0.0.1:8005",
  "http://localhost:8005",
  "http://127.0.0.1:8000",
  "http://localhost:8000"
];

let activeBackendUrl = "http://127.0.0.1:8005";

// Load previously saved active backend URL
chrome.storage.local.get("activeBackendUrl", (res) => {
  if (res.activeBackendUrl) {
    activeBackendUrl = res.activeBackendUrl;
  }
});

// Probe available URLs to find active backend server
async function findActiveBackend() {
  // First test the current active URL
  try {
    const res = await fetch(`${activeBackendUrl}/status`, { signal: AbortSignal.timeout(1500) });
    if (res.ok) {
      const data = await res.json();
      if (data.status === "online") return activeBackendUrl;
    }
  } catch (e) {
    // Continue to probe other candidates
  }

  for (const url of PROBE_URLS) {
    if (url === activeBackendUrl) continue;
    try {
      const res = await fetch(`${url}/status`, { signal: AbortSignal.timeout(1500) });
      if (res.ok) {
        const data = await res.json();
        if (data.status === "online") {
          activeBackendUrl = url;
          chrome.storage.local.set({ activeBackendUrl: url });
          return url;
        }
      }
    } catch (e) {
      // Continue to next probe
    }
  }
  return null;
}

// Handle messages from popup and content scripts
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "checkStatus") {
    findActiveBackend().then((url) => {
      if (url) {
        sendResponse({ online: true, url: url });
      } else {
        sendResponse({ online: false });
      }
    });
    return true; // Keep channel open for async response
  }

  if (request.action === "backendFetch") {
    (async () => {
      try {
        const backend = request.backendUrl || activeBackendUrl;
        const targetUrl = `${backend}${request.endpoint}`;
        const fetchOpts = {
          method: request.options?.method || "GET",
          headers: {
            "Content-Type": "application/json",
            ...(request.options?.headers || {})
          },
          signal: AbortSignal.timeout(60000)
        };

        if (request.options?.body) {
          fetchOpts.body = typeof request.options.body === "string"
            ? request.options.body
            : JSON.stringify(request.options.body);
        }

        const resp = await fetch(targetUrl, fetchOpts);
        const data = await resp.json();
        sendResponse({ success: true, data: data });
      } catch (err) {
        sendResponse({ success: false, error: err.toString() });
      }
    })();
    return true; // Keep channel open for async response
  }

  if (request.action === "jobAppliedReturn") {
    const senderTabId = sender.tab ? sender.tab.id : null;
    chrome.tabs.query({ url: ["*://*.indeed.com/jobs*", "*://*.indeed.com/?*"] }, (tabs) => {
      if (tabs && tabs.length > 0) {
        const searchTab = tabs[0];
        // Focus the search tab
        chrome.tabs.update(searchTab.id, { active: true }).catch(() => {});
        // Tell search tab to advance to next job
        setTimeout(() => {
          chrome.tabs.sendMessage(searchTab.id, { action: "resumeNextJob" }, () => {
            if (chrome.runtime.lastError) { /* ignore */ }
          });
        }, 500);
      }
    });

    // Close the apply tab if it was opened as a separate tab
    if (senderTabId) {
      setTimeout(() => {
        chrome.tabs.remove(senderTabId).catch(() => {});
      }, 1500);
    }
    sendResponse({ success: true });
    return true;
  }
});
