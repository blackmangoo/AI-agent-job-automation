// Indeed Auto-Applier Agent - Content Script
(function() {
  if (window.__INDEED_AGENT_ACTIVE__) return;
  window.__INDEED_AGENT_ACTIVE__ = true;

  // Frame filter: only run in top window or genuine Indeed apply iframes
  const isTopWindow = (window.top === window.self);
  const isApplyIframe = !isTopWindow && (
    window.location.href.includes('apply.indeed.com') ||
    window.location.href.includes('smartapply') ||
    window.location.href.includes('/ia/') ||
    window.location.href.includes('indeedapply=1')
  );

  if (!isTopWindow && !isApplyIframe) {
    return; // Ignore third-party tracking, analytics, and advertising iframes
  }

  let isRunning = false;
  let config = { dryRun: false, skipIneligible: true };
  let stats = { scanned: 0, applied: 0 };
  let currentJobIndex = 0;
  let jobCards = [];
  let backendUrl = "http://127.0.0.1:8005";
  let watchdogTimer = null;

  // Track search page URL on main window
  if (isTopWindow && window.location.href.includes("indeed.com")) {
    chrome.storage.local.set({ searchPageUrl: window.location.href });
  }

  // Load active backend URL from storage
  chrome.storage.local.get("activeBackendUrl", (res) => {
    if (res.activeBackendUrl) backendUrl = res.activeBackendUrl;
  });

  // Communication helper: proxy through background service worker or direct fetch
  async function callBackend(endpoint, options = {}) {
    try {
      const bgResponse = await new Promise((resolve) => {
        chrome.runtime.sendMessage({
          action: "backendFetch",
          backendUrl: backendUrl,
          endpoint: endpoint,
          options: options
        }, (resp) => {
          if (chrome.runtime.lastError || !resp) {
            resolve(null);
          } else {
            resolve(resp);
          }
        });
      });

      if (bgResponse && bgResponse.success) {
        return bgResponse.data;
      }
    } catch (e) {
      // Fall through to direct fetch
    }

    const fetchOpts = {
      method: options.method || "GET",
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {})
      },
      signal: AbortSignal.timeout(60000)
    };

    if (options.body) {
      fetchOpts.body = typeof options.body === "string" ? options.body : JSON.stringify(options.body);
    }

    const res = await fetch(`${backendUrl}${endpoint}`, fetchOpts);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    return await res.json();
  }

  function isIndeedApplyPage() {
    const url = window.location.href;
    if (url.includes("/ia/") || url.includes("apply.indeed.com") || url.includes("smartapply.indeed.com") || url.includes("/applystart") || url.includes("indeedapply=1")) {
      return true;
    }

    const activeModal = document.querySelector("#indeedapply-modal, div.ia-BasePage, iframe[src*='apply'], div[data-testid='apply-form']");
    if (activeModal && (activeModal.offsetWidth > 0 || activeModal.offsetHeight > 0)) {
      return true;
    }

    if (url.includes("/jobs?") || url.includes("/jobs/") || url.includes("/m/jobs") || url.endsWith("indeed.com/") || url.includes("pk.indeed.com/?")) {
      return false;
    }

    const applyContainer = document.querySelector("form[action*='apply'], div[data-testid='apply-form'], div.ia-BasePage");
    return !!(applyContainer && applyContainer.offsetWidth > 0);
  }

  function log(msg) {
    const timestamp = new Date().toLocaleTimeString();
    const logLine = `[${timestamp}] ${msg}`;
    console.log(`[Indeed Agent] ${logLine}`);

    try {
      chrome.runtime.sendMessage({ action: "updateLog", message: logLine }, () => {
        if (chrome.runtime.lastError) { /* popup closed */ }
      });
    } catch (e) {}

    chrome.storage.local.get("logs", (res) => {
      const logs = res.logs || [];
      logs.push(logLine);
      chrome.storage.local.set({ logs: logs.slice(-100) });
    });
  }

  function updateStats() {
    try {
      chrome.runtime.sendMessage({ action: "updateStats", stats: stats }, () => {
        if (chrome.runtime.lastError) { /* popup closed */ }
      });
    } catch (e) {}
    chrome.storage.local.set({ stats: stats });
  }

  function updateAgentHud(role, status) {
    if (!isTopWindow) return;
    let hud = document.getElementById("__indeed_agent_hud__");
    if (!hud) {
      hud = document.createElement("div");
      hud.id = "__indeed_agent_hud__";
      hud.style.cssText = `
        position: fixed;
        bottom: 24px;
        right: 24px;
        background: rgba(11, 9, 20, 0.94);
        color: #f8fafc;
        border: 1px solid rgba(0, 245, 160, 0.4);
        box-shadow: 0 12px 40px rgba(0, 0, 0, 0.7), 0 0 20px rgba(0, 245, 160, 0.2);
        border-radius: 14px;
        padding: 12px 18px;
        z-index: 2147483646;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        backdrop-filter: blur(16px);
        display: flex;
        align-items: center;
        gap: 12px;
        min-width: 280px;
        max-width: 420px;
        transition: all 0.25s ease;
      `;
      document.body.appendChild(hud);
    }
    hud.innerHTML = `
      <div style="width: 32px; height: 32px; border-radius: 10px; background: linear-gradient(135deg, #00f5a0, #00d9f5); display:flex; align-items:center; justify-content:center; font-size:16px; flex-shrink:0;">
        🤖
      </div>
      <div style="flex: 1; overflow: hidden;">
        <div style="font-size: 10px; font-weight: 700; color: #38bdf8; text-transform: uppercase; letter-spacing: 0.6px;">AI Job Agent Active</div>
        <div style="font-size: 13px; font-weight: 600; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${role || 'Scanning Indeed feed...'}</div>
        <div style="font-size: 11px; color: #94a3b8; margin-top: 1px;">${status || 'Active'}</div>
      </div>
    `;
  }

  function removeAgentHud() {
    const hud = document.getElementById("__indeed_agent_hud__");
    if (hud) hud.remove();
  }

  function reportActivity(role, status) {
    try {
      chrome.runtime.sendMessage({ action: "updateActivity", role: role, status: status }, () => {
        if (chrome.runtime.lastError) { /* ignore */ }
      });
    } catch (e) {}
    updateAgentHud(role, status);
  }

  function triggerStart(newConfig) {
    if (isRunning) return;
    isRunning = true;
    if (newConfig) {
      config = {
        dryRun: newConfig.dryRun === true,
        skipIneligible: newConfig.skipIneligible !== false,
        backendUrl: newConfig.backendUrl || backendUrl
      };
      if (newConfig.backendUrl) backendUrl = newConfig.backendUrl;
    }
    log("Starting auto-apply process...");
    stats = { scanned: 0, applied: 0 };
    updateStats();

    if (isIndeedApplyPage()) {
      log("Detected Indeed Apply page. Starting auto-filler...");
      autoFillJobApplication();
    } else if (isTopWindow) {
      startJobCrawl();
    }
  }

  function triggerStop() {
    if (!isRunning) return;
    isRunning = false;
    clearTimeout(watchdogTimer);
    removeAgentHud();
    reportActivity("Idle", "Bot stopped by user");
    log("Bot stopped.");
  }

  // Messaging listener
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "start") {
      triggerStart(request.config);
      sendResponse({ status: "started" });
    } else if (request.action === "stop") {
      triggerStop();
      sendResponse({ status: "stopped" });
    } else if (request.action === "resumeNextJob") {
      log("Received completion signal from application tab. Advancing to next listing...");
      closeAnyOpenModal().then(() => {
        setTimeout(() => {
          if (isRunning) processNextJob();
        }, 500);
      });
      sendResponse({ status: "resumed" });
    }
  });

  // Storage listener for cross-tab state syncing
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && changes.botRunning) {
      if (changes.botRunning.newValue === true) {
        chrome.storage.local.get(["dryRun", "skipIneligible", "activeBackendUrl"], (res) => {
          triggerStart({
            dryRun: res.dryRun,
            skipIneligible: res.skipIneligible,
            backendUrl: res.activeBackendUrl
          });
        });
      } else if (changes.botRunning.newValue === false) {
        triggerStop();
      }
    }
  });

  // Resume on background page reload if running
  chrome.storage.local.get(["botRunning", "dryRun", "skipIneligible", "stats"], (res) => {
    if (res.botRunning) {
      isRunning = true;
      config = {
        dryRun: res.dryRun === true,
        skipIneligible: res.skipIneligible !== false
      };
      stats = res.stats || { scanned: 0, applied: 0 };
      if (isIndeedApplyPage()) {
        setTimeout(() => {
          log("Resuming auto-filler on new step...");
          autoFillJobApplication();
        }, 1200);
      }
    }
  });

  // --- STEP 1: JOB CRAWLING AND SELECTION ---

  function startJobCrawl() {
    const rawCards = Array.from(document.querySelectorAll("a[data-jk], div.job_seen_beacon, .cardOutline"));
    const seenKeys = new Set();
    jobCards = [];

    rawCards.forEach(card => {
      let jobKey = card.getAttribute("data-jk");
      if (!jobKey) {
        const link = card.querySelector("a[data-jk], a[href*='jk=']");
        if (link) {
          jobKey = link.getAttribute("data-jk") || new URL(link.href).searchParams.get("jk");
        }
      }

      if (jobKey && !seenKeys.has(jobKey)) {
        seenKeys.add(jobKey);
        card.setAttribute("data-extracted-jk", jobKey);
        jobCards.push(card);
      }
    });

    if (jobCards.length === 0) {
      log("No job cards found. Make sure you are on Indeed Search or Feed page.");
      isRunning = false;
      chrome.storage.local.set({ botRunning: false });
      return;
    }

    log(`Found ${jobCards.length} unique jobs on the current page.`);
    currentJobIndex = 0;
    processNextJob();
  }

  async function processNextJob() {
    if (!isRunning) return;
    clearTimeout(watchdogTimer);

    if (currentJobIndex >= jobCards.length) {
      log("Processed all jobs on the current page.");
      isRunning = false;
      chrome.storage.local.set({ botRunning: false });
      reportActivity("Completed", "All page jobs scanned");
      return;
    }

    const card = jobCards[currentJobIndex];
    currentJobIndex++;

    // Watchdog: auto-advance if stuck for over 35 seconds
    watchdogTimer = setTimeout(async () => {
      if (isRunning && isTopWindow) {
        log("⏱️ Watchdog: Job processing timeout reached. Auto-advancing to next listing...");
        await closeAnyOpenModal();
        processNextJob();
      }
    }, 35000);

    try {
      card.scrollIntoView({ behavior: "smooth", block: "center" });
      const jobKey = card.getAttribute("data-extracted-jk") || card.getAttribute("data-jk");

      if (!jobKey) {
        log("Skipping card: could not determine Job Key.");
        setTimeout(processNextJob, 500);
        return;
      }

      // Click card to open description in panel
      log(`Opening job card (${currentJobIndex}/${jobCards.length})...`);
      const clickTarget = card.querySelector("h2.jobTitle, a.jcs-JobTitle") || card;
      await simulateClick(clickTarget);

      // Fast wait for preview panel to render
      await sleep(600);

      const jobTitle = getElementText([
        "h2[data-testid='simplified-job-header-title']",
        ".jobsearch-JobInfoHeader-title",
        "h1",
        "h2"
      ]) || "Job Role";

      const company = getElementText([
        "[data-testid='inlineHeader-companyName']",
        ".jobsearch-InlineCompanyRating",
        ".companyName"
      ]) || "Company";

      const description = getElementText([
        "#jobDescriptionText",
        ".jobsearch-jobDescriptionText"
      ]);

      reportActivity(`${jobTitle} @ ${company}`, "Analyzing match with AI...");

      if (!description) {
        log(`No description visible for ${jobTitle}. Moving to next job.`);
        stats.scanned++;
        updateStats();
        setTimeout(processNextJob, 400);
        return;
      }

      log(`Analyzing: '${jobTitle}' at '${company}'...`);
      stats.scanned++;
      updateStats();

      const jobUrl = `https://pk.indeed.com/viewjob?jk=${jobKey}`;
      const llmResponse = await callBackend("/analyze", {
        method: "POST",
        body: {
          job_title: jobTitle,
          company: company,
          description: description,
          url: jobUrl
        }
      });

      const matchPct = Math.round(llmResponse.confidence_score * 100);
      log(`Match Result: ${llmResponse.eligible ? "YES" : "NO"} (${matchPct}% match)`);
      log(`Reason: ${llmResponse.eligibility_reason}`);

      reportActivity(`${jobTitle} @ ${company}`, `${matchPct}% Match - ${llmResponse.eligible ? "Eligible" : "Skipped"}`);

      if (!llmResponse.eligible && config.skipIneligible) {
        log("Job not eligible. Skipping...");
        setTimeout(processNextJob, 400);
        return;
      }

      await chrome.storage.local.set({
        currentJobData: { job_title: jobTitle, company: company, url: jobUrl },
        currentLlmResponse: llmResponse
      });

      if (config.dryRun) {
        log(`[DRY RUN] Would apply to: ${jobTitle} at ${company}`);
        setTimeout(processNextJob, 600);
        return;
      }

      // Find and click Apply button
      const applyButton = findApplyButton();
      if (!applyButton) {
        log("Apply button not found (already applied or external career site).");
        setTimeout(processNextJob, 500);
        return;
      }

      reportActivity(`${jobTitle} @ ${company}`, "Opening Apply Form...");
      log("Clicking 'Apply with Indeed' button...");
      await sleep(200);
      await simulateClick(applyButton);

      // Wait for modal or redirect
      await sleep(1500);

      if (isIndeedApplyPage()) {
        await autoFillJobApplication();
      } else {
        log("Application opened in new tab. Bot will auto-fill on the application step.");
      }

    } catch (err) {
      log(`Error processing job: ${err}`);
      setTimeout(processNextJob, 800);
    }
  }

  // --- STEP 2: FORM FILLING ENGINE ---

  async function autoFillJobApplication() {
    if (!isRunning) return;

    log("Starting auto-filler for the current application step...");
    reportActivity("Application Form", "Auto-filling fields with CV data...");

    try {
      const candidate = await callBackend("/candidate");
      if (!candidate) {
        log(`Error: Could not retrieve candidate profile from backend (${backendUrl}). Make sure "python server.py" is running.`);
        isRunning = false;
        chrome.storage.local.set({ botRunning: false });
        return;
      }

      const stored = await chrome.storage.local.get(["currentLlmResponse", "currentJobData"]);
      let llmResponse = stored.currentLlmResponse;
      let jobData = stored.currentJobData;

      if (!llmResponse) {
        const extractedTitle = getElementText([
          "[data-testid='job-title']",
          ".ia-JobHeader-title",
          ".jobsearch-JobInfoHeader-title",
          "h1", "h2", ".job-title"
        ]) || "Job Role";

        const extractedCompany = getElementText([
          "[data-testid='company-name']",
          ".ia-JobHeader-company",
          ".jobsearch-InlineCompanyRating",
          ".company-name", "div[class*='company']"
        ]) || "Company";

        jobData = {
          job_title: extractedTitle,
          company: extractedCompany,
          url: window.location.href
        };

        llmResponse = {
          eligible: true,
          confidence_score: 1.0,
          eligibility_reason: "Direct application",
          resume_objective: `AI/ML Engineer seeking the ${extractedTitle} position at ${extractedCompany} to apply hands-on experience in machine learning, Python, and scalable AI solutions.`,
          cover_note: `I am writing to apply for the ${extractedTitle} position at ${extractedCompany}. With a background in Artificial Intelligence from FAST-NUCES and experience building end-to-end applications, I look forward to contributing.`,
          screening_answers: []
        };

        await chrome.storage.local.set({
          currentJobData: jobData,
          currentLlmResponse: llmResponse
        });
      }

      reportActivity(`${jobData.job_title} @ ${jobData.company}`, "Populating form answers...");

      // Wait up to 3 seconds for form fields to render
      let formFields = [];
      for (let i = 0; i < 10; i++) {
        const container = document.querySelector("#indeedapply-modal, div.ia-BasePage, div[data-testid='apply-form'], form[action*='apply'], main, .ia-Container") || document.body;

        formFields = Array.from(container.querySelectorAll("input:not([type='hidden']), select, textarea"))
          .filter(el => {
            // Strictly exclude search box or header navigation
            if (el.closest("form[role='search'], form#jobsearch, #searchform, .jobsearch-SearchBox, header, nav, #header-search-form")) {
              return false;
            }
            const id = (el.id || "").toLowerCase();
            const name = (el.name || "").toLowerCase();
            const placeholder = (el.placeholder || "").toLowerCase();
            if (id === "text-input-what" || id === "text-input-where" || name === "q" || name === "l") {
              return false;
            }
            if (placeholder.includes("job title, keywords") || placeholder.includes("city, state") || placeholder.includes("postcode")) {
              return false;
            }
            return (el.offsetWidth > 0 || el.offsetHeight > 0);
          });

        if (formFields.length > 0) break;
        await sleep(200);
      }

      log(`Found ${formFields.length} interactive form fields on this step.`);
      if (formFields.length > 0) {
        // 1. Fill standard fields
        await fillStandardFields(formFields, candidate);

        // 2. Fill screening answers
        await fillScreeningQuestions(formFields, llmResponse);

        // 2b. Query AI Brain to answer custom screening questions accurately
        await fillQuestionsWithBrain(formFields, llmResponse, jobData);

        // 3. Fill optional fields (summary, cover letter)
        await fillOptionalTextFields(formFields, llmResponse);

        log("Finished filling fields on this step.");
      }

      // Find the action button to advance or submit this form step
      let action = null;
      for (let attempt = 0; attempt < 6; attempt++) {
        action = findFormActionButton();
        if (action && !action.element.disabled) break;
        await sleep(300);
      }

      if (!action) {
        log("No forward action button found. Checking if application is already completed or if manual review needed.");
        const closeBtn = document.querySelector("button[aria-label='Close'], .ia-BasePage-closeButton");
        if (closeBtn) {
          log("Closing completed dialog and advancing to next listing...");
          await closeAnyOpenModal();
          if (isTopWindow) setTimeout(processNextJob, 500);
        }
        return;
      }

      if (action.type === "submit") {
        const submitBtn = action.element;
        // Human-in-the-Loop: Check if reCAPTCHA or Cloudflare challenge is blocking submission
        if (isCaptchaPresent() && !isCaptchaSolved()) {
          log("🔒 CAPTCHA detected on submission step! Waiting for verification...");
          reportActivity("Verification", "Please solve the 'I'm not a robot' CAPTCHA");
          showCaptchaBanner();
          playAlertChime();

          // Attempt gentle auto-click on the checkbox
          tryAutoClickCaptcha();

          // Wait until user checks/solves the CAPTCHA
          const solved = await waitForCaptchaResolution(120000);
          hideCaptchaBanner();

          if (solved) {
            log("✅ Verification confirmed! Submitting application...");
            await sleep(400);
          } else {
            log("⚠️ CAPTCHA wait timed out. Attempting submit anyway...");
          }
        }

        if (!config.dryRun) {
          reportActivity(`${jobData.job_title} @ ${jobData.company}`, "🚀 Auto-submitting application...");
          log("🚀 Final step reached: Auto-submitting application...");
          await simulateClick(submitBtn);
          await sleep(1000);
          log("✅ Application auto-submitted successfully!");
        } else {
          log("🎉 Form filled! Dry run enabled — submit paused for your review.");
        }

        // Log application asynchronously
        callBackend("/log", {
          method: "POST",
          body: {
            job_data: jobData,
            llm_response: llmResponse,
            status: config.dryRun ? "form_filled" : "applied"
          }
        });

        stats.applied++;
        updateStats();

        if (config.dryRun) {
          isRunning = false;
          chrome.storage.local.set({ botRunning: false });
          reportActivity(`${jobData.job_title}`, "Paused for manual review");
        } else {
          reportActivity(`${jobData.job_title}`, "✅ Submitted! Moving to next job...");
          await sleep(1000);

          if (isTopWindow) {
            // In-page modal on search tab: close modal and proceed!
            log("Closing application view and moving to next listing...");
            await closeAnyOpenModal();
            await sleep(500);
            processNextJob();
          } else {
            // Separate apply tab: notify background to refocus search page and close this tab!
            log("Application completed. Closing apply tab and returning to search results...");
            chrome.runtime.sendMessage({ action: "jobAppliedReturn" });
          }
        }
      } else if (action.type === "continue") {
        const continueBtn = action.element;
        const btnText = (continueBtn.innerText || continueBtn.value || "Continue").trim();
        reportActivity(`${jobData.job_title} @ ${jobData.company}`, `Advancing (${btnText})...`);
        log(`Clicking '${btnText}' to advance to next step...`);
        await simulateClick(continueBtn);

        await sleep(900);
        if (isRunning && isIndeedApplyPage()) {
          await autoFillJobApplication();
        }
      }

    } catch (err) {
      log(`Error during form filling: ${err}`);
    }
  }

  // --- HELPERS ---

  function isCaptchaPresent() {
    const selectors = [
      "iframe[src*='recaptcha']",
      "iframe[src*='hcaptcha']",
      "iframe[src*='turnstile']",
      "iframe[src*='challenges.cloudflare.com']",
      "div.g-recaptcha",
      "div.cf-turnstile",
      "#captcha",
      "div[class*='captcha']"
    ];
    for (const s of selectors) {
      try {
        const el = document.querySelector(s);
        if (el && (el.offsetWidth > 0 || el.offsetHeight > 0)) return true;
      } catch (e) {}
    }
    return false;
  }

  function isCaptchaSolved() {
    // 1. Google reCAPTCHA response token
    const recaptchaToken = document.querySelector("textarea[name='g-recaptcha-response'], #g-recaptcha-response");
    if (recaptchaToken && recaptchaToken.value && recaptchaToken.value.trim().length > 10) return true;

    // 2. Cloudflare Turnstile token
    const turnstileToken = document.querySelector("input[name='cf-turnstile-response']");
    if (turnstileToken && turnstileToken.value && turnstileToken.value.trim().length > 10) return true;

    // 3. hCaptcha token
    const hcaptchaToken = document.querySelector("textarea[name='h-captcha-response']");
    if (hcaptchaToken && hcaptchaToken.value && hcaptchaToken.value.trim().length > 10) return true;

    return false;
  }

  function tryAutoClickCaptcha() {
    const iframe = document.querySelector("iframe[src*='recaptcha/api2/anchor'], iframe[src*='recaptcha']");
    if (iframe) {
      try {
        iframe.scrollIntoView({ behavior: 'smooth', block: 'center' });
        iframe.focus();
        const rect = iframe.getBoundingClientRect();
        const x = rect.left + 28;
        const y = rect.top + 37;
        iframe.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, clientX: x, clientY: y }));
        iframe.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, clientX: x, clientY: y }));
        iframe.dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: x, clientY: y }));
      } catch (e) {}
    }
  }

  async function waitForCaptchaResolution(timeoutMs = 120000) {
    const startTime = Date.now();
    while (Date.now() - startTime < timeoutMs) {
      if (!isRunning) return false;
      if (isCaptchaSolved()) return true;
      if (!isCaptchaPresent()) return true;
      await sleep(400);
    }
    return false;
  }

  function showCaptchaBanner() {
    let banner = document.getElementById("__indeed_captcha_banner__");
    if (!banner) {
      banner = document.createElement("div");
      banner.id = "__indeed_captcha_banner__";
      banner.style.cssText = `
        position: fixed;
        top: 24px;
        left: 50%;
        transform: translateX(-50%);
        background: linear-gradient(135deg, #1e1b4b 0%, #0f172a 100%);
        color: #ffffff;
        border: 1px solid rgba(0, 245, 160, 0.5);
        box-shadow: 0 12px 40px rgba(0, 0, 0, 0.7), 0 0 25px rgba(0, 245, 160, 0.25);
        border-radius: 14px;
        padding: 16px 24px;
        z-index: 2147483647;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        display: flex;
        align-items: center;
        gap: 14px;
        backdrop-filter: blur(16px);
      `;
      banner.innerHTML = `
        <span style="font-size: 24px;">🔒</span>
        <div>
          <div style="font-size: 15px; font-weight: 700; color: #38bdf8;">Human Verification Required</div>
          <div style="font-size: 12px; color: #cbd5e1; margin-top: 3px;">Please complete the "I'm not a robot" check. The bot will automatically submit once verified!</div>
        </div>
      `;
      document.body.appendChild(banner);
    }
  }

  function hideCaptchaBanner() {
    const banner = document.getElementById("__indeed_captcha_banner__");
    if (banner) banner.remove();
  }

  function playAlertChime() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(587.33, ctx.currentTime);
      osc.frequency.setValueAtTime(880.00, ctx.currentTime + 0.15);
      gain.gain.setValueAtTime(0.25, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.45);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.45);
    } catch (e) {}
  }

  async function closeAnyOpenModal() {
    const closeSelectors = [
      "button[aria-label='Close']",
      "button[data-testid='modal-close']",
      "button.ia-BasePage-closeButton",
      "button.ia-dismiss",
      "button:has-text('Return to job search')",
      "button:has-text('Close')",
      "button:has-text('Done')",
      "[data-testid='close-button']"
    ];
    for (const s of closeSelectors) {
      try {
        const btn = document.querySelector(s);
        if (btn && (btn.offsetWidth > 0 || btn.offsetHeight > 0)) {
          await simulateClick(btn);
          await sleep(300);
          return true;
        }
      } catch (e) {}
    }
    const overlay = document.querySelector("#indeedapply-modal, div.ia-BasePage");
    if (overlay) {
      overlay.style.display = "none";
    }
    return false;
  }

  function findFormActionButton() {
    // 1. Check for Submit button first
    const submitBtn = findSubmitButton();
    if (submitBtn) return { type: "submit", element: submitBtn };

    // 2. Specific Indeed continue selectors
    const continueSelectors = [
      "button[data-testid='continue-button']",
      "button#continueButton",
      "button.ia-continueButton",
      "button[data-testid='review-button']",
      "button[data-testid='next-button']",
      "button[aria-label*='continue' i]",
      "button[aria-label*='next' i]",
      "button[aria-label*='review' i]"
    ];
    for (const s of continueSelectors) {
      try {
        const el = document.querySelector(s);
        if (el && (el.offsetWidth > 0 || el.offsetHeight > 0) && !el.disabled) {
          return { type: "continue", element: el };
        }
      } catch (e) {}
    }

    // 3. Search all buttons by text for continue / next / review / save
    const buttons = Array.from(document.querySelectorAll("button, a[role='button'], input[type='submit']"));
    for (const btn of buttons) {
      if (btn.offsetWidth === 0 && btn.offsetHeight === 0) continue;
      if (btn.disabled) continue;

      const txt = (btn.innerText || btn.value || "").trim().toLowerCase();
      if (!txt) continue;

      // Ignore back, cancel, close buttons
      if (txt.includes("back") || txt.includes("cancel") || txt.includes("close") || txt.includes("exit")) {
        continue;
      }

      if (txt.includes("submit") || txt.includes("apply now") || txt.includes("send application")) {
        return { type: "submit", element: btn };
      }

      if (
        txt.includes("continue") ||
        txt.includes("next") ||
        txt.includes("review") ||
        txt.includes("save and") ||
        txt.includes("save &") ||
        txt.includes("proceed") ||
        txt.includes("advance") ||
        txt.includes("agree")
      ) {
        return { type: "continue", element: btn };
      }
    }

    // 4. Form's primary button fallback
    const form = document.querySelector("#indeedapply-modal form, div.ia-BasePage form, div[data-testid='apply-form'] form, form");
    if (form) {
      const primaryBtn = form.querySelector("button[type='submit'], input[type='submit'], button.ia-Button--primary, button:not([class*='secondary']):not([class*='cancel']):not([class*='close'])");
      if (primaryBtn && (primaryBtn.offsetWidth > 0 || primaryBtn.offsetHeight > 0) && !primaryBtn.disabled) {
        const pText = (primaryBtn.innerText || primaryBtn.value || "").trim().toLowerCase();
        if (pText.includes("submit")) {
          return { type: "submit", element: primaryBtn };
        }
        return { type: "continue", element: primaryBtn };
      }
    }

    return null;
  }

  function findSubmitButton() {
    const selectors = [
      "button[data-testid='submit-button']",
      "button#submitButton",
      "button.ia-submitButton",
      "button[aria-label*='Submit your application']",
      "button[aria-label*='Submit application']",
      "button[aria-label*='Submit']",
      "[data-testid='submit-button']",
      "#submitButton"
    ];
    for (const s of selectors) {
      try {
        const btn = document.querySelector(s);
        if (btn && (btn.offsetWidth > 0 || btn.offsetHeight > 0)) return btn;
      } catch(e) {}
    }

    const buttons = Array.from(document.querySelectorAll("button, a[role='button'], input[type='submit']"));
    for (const btn of buttons) {
      const txt = (btn.innerText || btn.value || "").trim().toLowerCase();
      if (txt === "submit your application" || txt === "submit application" || txt === "submit" || txt.startsWith("submit your application") || txt.startsWith("submit application")) {
        if (btn.offsetWidth > 0 || btn.offsetHeight > 0) return btn;
      }
    }
    return null;
  }

  async function simulateClick(element) {
    if (!element) return;
    const eventOptions = { bubbles: true, cancelable: true, view: window };
    element.dispatchEvent(new MouseEvent('mousedown', eventOptions));
    await sleep(80);
    element.dispatchEvent(new MouseEvent('mouseup', eventOptions));
    await sleep(80);
    element.dispatchEvent(new MouseEvent('click', eventOptions));
  }

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  function getElementText(selectors) {
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el && el.innerText.trim()) return el.innerText.trim();
    }
    return "";
  }

  function findApplyButton() {
    const selectors = [
      "button#indeedApplyButton",
      "button[data-testid='indeedApplyButton']",
      "button.jobsearch-IndeedApplyButton-newDesign",
      "button[aria-label*='Apply with Indeed']",
      "button[aria-label*='Apply now']",
      "button.ia-IndeedApplyButton",
      "#indeedApplyButton",
      "[data-testid='indeedApplyButton']",
      ".jobsearch-IndeedApplyButton-newDesign",
      "a[data-testid='indeedApplyButton']"
    ];
    for (const s of selectors) {
      const btn = document.querySelector(s);
      if (btn && (btn.offsetWidth > 0 || btn.offsetHeight > 0)) return btn;
    }

    const candidates = Array.from(document.querySelectorAll("button, a, [role='button']"));
    for (const el of candidates) {
      const txt = (el.innerText || "").trim().toLowerCase();
      if (txt === "apply with indeed" || txt === "apply now" || txt.includes("apply with indeed") || txt.includes("apply now")) {
        if (el.offsetWidth > 0 || el.offsetHeight > 0) return el;
      }
    }
    return null;
  }

  function findButtonByText(texts) {
    const buttons = Array.from(document.querySelectorAll("button, a[role='button']"));
    for (const text of texts) {
      const btn = buttons.find(b => (b.innerText || "").trim().toLowerCase() === text.toLowerCase());
      if (btn && (btn.offsetWidth > 0 || btn.offsetHeight > 0)) return btn;
    }
    return null;
  }

  // Standard fields auto-filler tailored specifically to Ammar Akbar's credentials
  async function fillStandardFields(fields, candidate) {
    const currentUrl = window.location.href.toLowerCase();
    const pageText = document.body.innerText.toLowerCase();
    let targetCity = "Lahore";
    if (currentUrl.includes("islamabad") || currentUrl.includes("rawalpindi") || pageText.includes("islamabad")) {
      targetCity = "Islamabad";
    }

    const mappings = {
      "first name": candidate.full_name.split(" ")[0],
      "last name": candidate.full_name.split(" ").slice(1).join(" "),
      "full name": candidate.full_name,
      "name": candidate.full_name,
      "email": candidate.email,
      "phone": candidate.phone,
      "mobile": candidate.phone,
      "cell": candidate.phone,
      "contact": candidate.phone,
      "linkedin": candidate.linkedin,
      "github": candidate.github,
      "portfolio": candidate.portfolio,
      "website": candidate.portfolio,
      "city": targetCity,
      "location": `${targetCity}, Pakistan`,
      "address": `${targetCity}, Pakistan`,
      "country": "Pakistan",
      "university": candidate.university,
      "school": candidate.university,
      "institution": candidate.university,
      "degree": candidate.degree,
      "major": "Artificial Intelligence",
      "field of study": "Artificial Intelligence",
      "graduation": "2026",
      "headline": "AI/ML Engineer | BS AI (FAST-NUCES)",
      "notice": "Immediately available"
    };

    for (const field of fields) {
      const label = getLabelText(field).toLowerCase();
      const name = (field.getAttribute("name") || "").toLowerCase();
      const id = (field.getAttribute("id") || "").toLowerCase();
      const placeholder = (field.getAttribute("placeholder") || "").toLowerCase();

      for (const [key, val] of Object.entries(mappings)) {
        if (label.includes(key) || name.includes(key) || id.includes(key) || placeholder.includes(key)) {
          if (!field.value) {
            log(`Standard fill: '${key}' -> '${val}'`);
            await setFieldValue(field, val);
          }
          break;
        }
      }
    }
  }

  // Screening questions auto-filler
  async function fillScreeningQuestions(fields, llmResponse) {
    const answers = llmResponse.screening_answers || [];
    if (answers.length === 0) return;

    for (const field of fields) {
      const labelText = getLabelText(field);
      if (!labelText) continue;

      const match = answers.find(ans => {
        const qKeywords = ans.question.toLowerCase().split(/\s+/).filter(k => k.length > 3);
        const labelLower = labelText.toLowerCase();
        const matches = qKeywords.filter(k => labelLower.includes(k)).length;
        return matches >= Math.min(2, qKeywords.length);
      });

      if (match && match.answer) {
        log(`Screening fill: '${labelText.substring(0, 45)}...' -> '${match.answer}'`);
        await setFieldValue(field, match.answer);
      }
    }
  }

  // Fill Cover note & Objective
  async function fillOptionalTextFields(fields, llmResponse) {
    for (const field of fields) {
      if (field.tagName !== "TEXTAREA") continue;
      const label = getLabelText(field).toLowerCase();
      const name = (field.getAttribute("name") || "").toLowerCase();

      if (label.includes("objective") || label.includes("summary") || name.includes("objective")) {
        if (llmResponse.resume_objective && !field.value) {
          log("Filling resume objective...");
          await setFieldValue(field, llmResponse.resume_objective);
        }
      } else if (label.includes("cover") || label.includes("message") || name.includes("cover")) {
        if (llmResponse.cover_note && !field.value) {
          log("Filling cover note...");
          await setFieldValue(field, llmResponse.cover_note);
        }
      }
    }
  }

  // Get associated label text for an input
  function getLabelText(input) {
    const fieldset = input.closest("fieldset");
    if (fieldset) {
      const legend = fieldset.querySelector("legend");
      if (legend && legend.innerText.trim()) return legend.innerText.trim();
    }

    const questionContainer = input.closest("[data-testid*='question'], [class*='Question'], [class*='question']");
    if (questionContainer) {
      const qText = questionContainer.querySelector("h3, h4, span, label, legend");
      if (qText && qText.innerText.trim()) return qText.innerText.trim();
    }

    const id = input.getAttribute("id");
    if (id) {
      const label = document.querySelector(`label[for="${id}"]`);
      if (label) return label.innerText.trim();
    }

    const parentLabel = input.closest("label");
    if (parentLabel) return parentLabel.innerText.trim();

    let prev = input.previousElementSibling;
    while (prev) {
      if (["LABEL", "SPAN", "P", "DIV", "LEGEND", "H3", "H4"].includes(prev.tagName)) {
        const txt = prev.innerText.trim();
        if (txt && txt.length > 2 && txt.length < 150) return txt;
      }
      prev = prev.previousElementSibling;
    }

    let parent = input.parentElement;
    if (parent) {
      let parentPrev = parent.previousElementSibling;
      while (parentPrev) {
        if (["LABEL", "SPAN", "P", "DIV", "LEGEND", "H3", "H4"].includes(parentPrev.tagName)) {
          const txt = parentPrev.innerText.trim();
          if (txt && txt.length > 2 && txt.length < 150) return txt;
        }
        parentPrev = parentPrev.previousElementSibling;
      }
    }

    return input.getAttribute("placeholder") || input.getAttribute("aria-label") || input.getAttribute("name") || input.getAttribute("id") || "";
  }

  // Set form value for various input types
  async function setFieldValue(field, value) {
    if (!field || value === undefined || value === null) return;
    let strValue = String(value).trim();
    if (!strValue) return;

    // Number input validation
    if (field.type === "number") {
      const numMatch = strValue.match(/\d+(\.\d+)?/);
      strValue = numMatch ? numMatch[0] : "2";
    }

    // Phone format validation
    if (field.type === "tel" || (field.name && field.name.toLowerCase().includes("phone"))) {
      if (field.maxLength === 11 || (field.placeholder && field.placeholder.startsWith("03"))) {
        strValue = "03214797778";
      }
    }

    if (field.tagName === "SELECT") {
      const options = Array.from(field.options);
      const target = options.find(o =>
        o.text.toLowerCase().includes(strValue.toLowerCase()) ||
        o.value.toLowerCase().includes(strValue.toLowerCase())
      );
      if (target) {
        field.value = target.value;
        field.dispatchEvent(new Event("change", { bubbles: true }));
      }
    } else if (field.type === "checkbox" || field.type === "radio") {
      const isYes = ["yes", "true", "1", "apply", "agree"].includes(strValue.toLowerCase());
      const isNo = ["no", "false", "0"].includes(strValue.toLowerCase());
      const labelText = getLabelText(field).toLowerCase();

      if (field.type === "checkbox") {
        field.checked = isYes;
        field.dispatchEvent(new Event("change", { bubbles: true }));
      } else {
        if (labelText.includes(strValue.toLowerCase()) || (isYes && (labelText === "yes" || labelText.includes("yes"))) || (isNo && (labelText === "no" || labelText.includes("no")))) {
          field.checked = true;
          field.dispatchEvent(new Event("change", { bubbles: true }));
        }
      }
    } else {
      await simulateTyping(field, strValue);
    }
  }

  // Clean React prototype setter
  async function simulateTyping(field, value) {
    if (!field) return;
    const strValue = String(value).trim();
    if (!strValue) return;

    field.focus();

    const proto = field.tagName === 'TEXTAREA'
      ? window.HTMLTextAreaElement.prototype
      : window.HTMLInputElement.prototype;
    const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;

    if (nativeSetter) {
      nativeSetter.call(field, strValue);
    } else {
      field.value = strValue;
    }

    field.dispatchEvent(new Event('input', { bubbles: true }));
    field.dispatchEvent(new Event('change', { bubbles: true }));

    await sleep(200);

    const suggestions = Array.from(document.querySelectorAll('ul[role="listbox"] li, li[role="option"], [id*="suggestion"], .autocomplete-suggestion'))
      .filter(el => el.offsetWidth > 0 && el.offsetHeight > 0);

    if (suggestions.length > 0) {
      const firstOption = suggestions[0];
      log("Autocomplete option selected: " + firstOption.innerText.trim());
      firstOption.click();
      await sleep(150);
    }

    field.blur();
  }

  // Dynamically answer custom questions using the LLM Brain with full job context & options
  async function fillQuestionsWithBrain(fields, llmResponse, jobData) {
    const customQuestions = [];
    const fieldToQuestion = new Map();

    const standardKeywords = [
      "first name", "last name", "full name", "name", "email", "phone", "mobile",
      "linkedin", "github", "portfolio", "country", "resume", "cv"
    ];

    fields.forEach(field => {
      const label = getLabelText(field);
      if (!label || label.length < 3) return;

      const labelLower = label.toLowerCase();
      const isStandard = standardKeywords.some(keyword => labelLower === keyword || labelLower.startsWith(keyword + " "));
      if (isStandard && field.value) return;

      const hasInitialAnswer = (llmResponse.screening_answers || []).some(ans => {
        const qKeywords = ans.question.toLowerCase().split(/\s+/).filter(k => k.length > 3);
        const matches = qKeywords.filter(k => labelLower.includes(k)).length;
        return matches >= Math.min(2, qKeywords.length);
      });

      if (hasInitialAnswer) return;

      let questionDesc = label;
      if (field.tagName === "SELECT") {
        const opts = Array.from(field.options).map(o => (o.text || "").trim()).filter(t => t && !t.toLowerCase().includes("select"));
        if (opts.length > 0) {
          questionDesc += ` [Choose best option from: ${opts.join(", ")}]`;
        }
      }

      if (!customQuestions.includes(questionDesc)) {
        customQuestions.push(questionDesc);
      }
      fieldToQuestion.set(field, questionDesc);
    });

    if (customQuestions.length === 0) return;

    log(`AI Brain evaluating ${customQuestions.length} custom questions...`);
    reportActivity("AI Brain", `Answering ${customQuestions.length} application questions...`);

    try {
      const data = await callBackend("/ask-brain", {
        method: "POST",
        body: {
          questions: customQuestions,
          job_context: jobData ? {
            job_title: jobData.job_title,
            company: jobData.company,
            url: jobData.url
          } : null
        }
      });
      const answers = data.answers || {};

      for (const field of fields) {
        const question = fieldToQuestion.get(field);
        if (question && answers[question]) {
          const ans = answers[question];
          log(`AI Answer: '${question.substring(0, 35)}...' -> '${ans.substring(0, 50)}'`);
          await setFieldValue(field, ans);
        }
      }
    } catch (err) {
      log(`Error querying AI Brain: ${err}`);
    }
  }

})();
