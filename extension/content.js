// Indeed Auto-Applier Agent - Content Script
let isRunning = false;
let config = { dryRun: true, skipIneligible: true };
let stats = { scanned: 0, applied: 0 };
let currentJobIndex = 0;
let jobCards = [];

let backendUrl = "http://127.0.0.1:8005";

// Load active backend URL from storage
chrome.storage.local.get("activeBackendUrl", (res) => {
  if (res.activeBackendUrl) backendUrl = res.activeBackendUrl;
});

// Robust backend caller: tries background worker first (no mixed-content/CORS limits) with direct fetch fallback
async function callBackend(endpoint, options = {}) {
  // 1. Try background worker proxy (immune to HTTPS/HTTP mixed content and page CSP)
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
    // Fallback to direct fetch below
  }

  // 2. Direct fetch fallback
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
  if (url.includes("/ia/") || url.includes("apply.indeed.com") || url.includes("smartapply.indeed.com") || url.includes("/applystart")) {
    return true;
  }
  return !!document.querySelector("div[class*='ia-'], div[data-testid='apply-form'], form[action*='apply'], #indeedapply-modal, div.ia-BasePage, div[role='dialog']");
}

// Log a message to the extension popup and save it to storage
function log(msg) {
  const timestamp = new Date().toLocaleTimeString();
  const logLine = `[${timestamp}] ${msg}`;
  console.log(`[Indeed Agent] ${logLine}`);

  // Send live message to popup safely without unhandled rejections if popup is closed
  try {
    chrome.runtime.sendMessage({ action: "updateLog", message: logLine }, () => {
      if (chrome.runtime.lastError) { /* popup closed - safe to ignore */ }
    });
  } catch (e) {}

  // Persist log line in storage so it is not lost on page reload/navigation
  chrome.storage.local.get("logs", (res) => {
    const logs = res.logs || [];
    logs.push(logLine);
    chrome.storage.local.set({ logs: logs.slice(-100) });
  });
}

// Update stats in the extension popup
function updateStats() {
  try {
    chrome.runtime.sendMessage({ action: "updateStats", stats: stats }, () => {
      if (chrome.runtime.lastError) { /* popup closed - safe to ignore */ }
    });
  } catch (e) {}
  chrome.storage.local.set({ stats: stats });
}

// Listen for commands from the popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "start") {
    isRunning = true;
    config = request.config || {};
    if (config.backendUrl) {
      backendUrl = config.backendUrl;
    }
    log("Starting auto-apply process...");
    stats = { scanned: 0, applied: 0 };
    updateStats();

    // Check if we are on a job application page directly
    if (isIndeedApplyPage()) {
      log("Detected Indeed Apply page. Starting auto-filler...");
      autoFillJobApplication();
    } else {
      startJobCrawl();
    }
    sendResponse({ status: "started" });
  } else if (request.action === "stop") {
    isRunning = false;
    log("Stopping auto-apply process...");
    sendResponse({ status: "stopped" });
  }
});

// Check if bot was running in background (for page reloads during application)
chrome.storage.local.get(["botRunning", "dryRun", "skipIneligible", "stats"], (res) => {
  if (res.botRunning) {
    isRunning = true;
    config = { 
      dryRun: res.dryRun !== false, 
      skipIneligible: res.skipIneligible !== false 
    };
    stats = res.stats || { scanned: 0, applied: 0 };
    if (isIndeedApplyPage()) {
      setTimeout(() => {
        log("Resuming auto-filler on new step...");
        autoFillJobApplication();
      }, 2000);
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
  if (currentJobIndex >= jobCards.length) {
    log("Processed all jobs on the current page.");
    isRunning = false;
    chrome.storage.local.set({ botRunning: false });
    return;
  }

  const card = jobCards[currentJobIndex];
  currentJobIndex++;

  try {
    // Scroll card into view
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    
    // Extract Job Key/ID
    const jobKey = card.getAttribute("data-extracted-jk") || card.getAttribute("data-jk");

    if (!jobKey) {
      log("Skipping card: could not determine Job Key.");
      setTimeout(processNextJob, 1000);
      return;
    }

    // Click card to open description in panel
    log(`Clicking job card (Key: ${jobKey})...`);
    const clickTarget = card.querySelector("h2.jobTitle, a.jcs-JobTitle") || card;
    await simulateClick(clickTarget);

    // Wait for the job description panel to load
    await sleep(2500);

    // Scrape details from the page
    const jobTitle = getElementText([
      "h2[data-testid='simplified-job-header-title']",
      ".jobsearch-JobInfoHeader-title",
      "h1",
      "h2"
    ]);
    const company = getElementText([
      "[data-testid='inlineHeader-companyName']",
      ".jobsearch-InlineCompanyRating",
      ".companyName"
    ]);
    const description = getElementText([
      "#jobDescriptionText",
      ".jobsearch-jobDescriptionText"
    ]);

    if (!description) {
      log("Error: Could not extract job description. Trying next job.");
      stats.scanned++;
      updateStats();
      setTimeout(processNextJob, 1000);
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

    log(`Eligibility Result: ${llmResponse.eligible ? "YES" : "NO"} (${Math.round(llmResponse.confidence_score * 100)}% confidence)`);
    log(`Reason: ${llmResponse.eligibility_reason}`);

    if (!llmResponse.eligible && config.skipIneligible) {
      log("Job not eligible. Skipping...");
      setTimeout(processNextJob, 2000);
      return;
    }

    // Store analysis response for the form filler
    await chrome.storage.local.set({ 
      currentJobData: { job_title: jobTitle, company: company, url: jobUrl },
      currentLlmResponse: llmResponse 
    });

    if (config.dryRun) {
      log(`[DRY RUN] Would apply to: ${jobTitle} at ${company}`);
      setTimeout(processNextJob, 2500);
      return;
    }

    // Look for Apply button
    const applyButton = findApplyButton();
    if (!applyButton) {
      log("Apply button not found. Maybe already applied or external site.");
      setTimeout(processNextJob, 2000);
      return;
    }

    log(`Found Apply button: ${applyButton.outerHTML.substring(0, 150)}...`);
    log("Waiting for React event listeners to bind...");
    await sleep(1000); // Wait for React props to attach
    
    log("Simulating click on Apply button...");
    await simulateClick(applyButton);
    
    // Give modal/new tab time to open
    await sleep(3500);
    
    // Check if modal popped up on the same page, otherwise we will wait for redirection
    if (isIndeedApplyPage()) {
      autoFillJobApplication();
    } else {
      log("Navigating to Indeed Apply page. The bot will automatically resume there.");
    }

  } catch (err) {
    log(`Error processing job: ${err}`);
    setTimeout(processNextJob, 2000);
  }
}

// --- STEP 2: FORM FILLING ENGINE ---

async function autoFillJobApplication() {
  if (!isRunning) return;

  log("Starting auto-filler for the current application step...");

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

    // Fallback if user clicked Start Bot directly on an apply page without scanning
    if (!llmResponse) {
      log("Direct apply detected: Extracting job details from page header...");
      const extractedTitle = getElementText([
        "[data-testid='job-title']",
        ".ia-JobHeader-title",
        ".jobsearch-JobInfoHeader-title",
        "h1",
        "h2",
        ".job-title"
      ]) || "Position";

      const extractedCompany = getElementText([
        "[data-testid='company-name']",
        ".ia-JobHeader-company",
        ".jobsearch-InlineCompanyRating",
        ".company-name",
        "div[class*='company']"
      ]) || "Employer";

      jobData = {
        job_title: extractedTitle,
        company: extractedCompany,
        url: window.location.href
      };

      llmResponse = {
        eligible: true,
        confidence_score: 1.0,
        eligibility_reason: "Direct application initiated by user",
        resume_objective: `AI/ML Engineer seeking the ${extractedTitle} role at ${extractedCompany} to apply hands-on experience in machine learning, Python, and model deployment.`,
        cover_note: `I am writing to apply for the ${extractedTitle} position at ${extractedCompany}. With a background in AI/ML from FAST-NUCES and experience building end-to-end applications, I look forward to contributing.`,
        screening_answers: []
      };

      await chrome.storage.local.set({
        currentJobData: jobData,
        currentLlmResponse: llmResponse
      });

      log(`Loaded candidate profile for: ${candidate.full_name}`);
      log(`Applying directly to: ${extractedTitle} at ${extractedCompany}`);
    }

    // Wait up to 5 seconds for React form fields to render
    let formFields = [];
    log("Waiting for form fields to render on page...");
    for (let i = 0; i < 10; i++) {
      formFields = Array.from(document.querySelectorAll("input:not([type='hidden']), select, textarea"));
      if (formFields.length > 0) break;
      await sleep(500);
    }

    log(`Found ${formFields.length} interactive form fields on this page.`);
    if (formFields.length === 0) {
      log("No editable fields on this step.");
    } else {
      // 1. Fill standard fields
      await fillStandardFields(formFields, candidate);

      // 2. Fill screening question answers
      await fillScreeningQuestions(formFields, llmResponse);

      // 2b. Query AI Brain to answer any custom screening questions on the screen
      await fillQuestionsWithBrain(formFields, llmResponse);

      // 3. Fill resume objective and cover note if fields exist
      await fillOptionalTextFields(formFields, llmResponse);

      log("Finished filling fields on this step.");
    }

    // Check if we are on a final review/submit step
    const submitBtn = findButtonByText(["Submit your application", "Submit application", "Submit"]);
    const continueBtn = findButtonByText(["Continue", "Next", "Review"]);

    if (submitBtn) {
      log("🎉 REVIEW REQUIRED: Submit button detected. Please review the form and click Submit manually.");

      // Log success to local backend
      await callBackend("/log", {
        method: "POST",
        body: {
          job_data: jobData,
          llm_response: llmResponse,
          status: "applied"
        }
      });

      stats.applied++;
      updateStats();

      // Stop bot so it doesn't navigate away before user review
      isRunning = false;
      chrome.storage.local.set({ botRunning: false });
      log("Bot paused for user review. Submit when ready.");
    } else if (continueBtn) {
      log("Clicking 'Continue' to move to next step...");
      await simulateClick(continueBtn);

      // Wait for next React step to transition and auto-fill it
      await sleep(2500);
      if (isRunning && isIndeedApplyPage()) {
        log("Proceeding to next step...");
        autoFillJobApplication();
      }
    }

  } catch (err) {
    log(`Error during form filling: ${err}`);
  }
}
      log("Clicking 'Continue' to move to next step...");
      await simulateClick(continueBtn);

      // Wait for SPA dynamic page update and resume filling if still running
      await sleep(2500);
      if (isRunning) {
        log("Proceeding with next form step...");
        await autoFillJobApplication();
      }
    }

  } catch (err) {
    log(`Error during form filling: ${err}`);
  }
}

// --- HELPERS ---

async function simulateClick(element) {
  if (!element) return;
  const eventOptions = { bubbles: true, cancelable: true, view: window };
  
  element.dispatchEvent(new MouseEvent('mousedown', eventOptions));
  await sleep(100);
  element.dispatchEvent(new MouseEvent('mouseup', eventOptions));
  await sleep(100);
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
    "button[aria-label*='Apply now']",
    "button.ia-IndeedApplyButton"
  ];
  for (const s of selectors) {
    const btn = document.querySelector(s);
    if (btn) return btn;
  }
  return null;
}

function findButtonByText(texts) {
  const buttons = Array.from(document.querySelectorAll("button"));
  for (const text of texts) {
    const btn = buttons.find(b => b.innerText.trim().toLowerCase() === text.toLowerCase());
    if (btn) return btn;
  }
  return null;
}

// Standard fields auto-filler
async function fillStandardFields(fields, candidate) {
  const mappings = {
    "first name": candidate.full_name.split(" ")[0],
    "last name": candidate.full_name.split(" ").slice(1).join(" "),
    "full name": candidate.full_name,
    "name": candidate.full_name,
    "email": candidate.email,
    "phone": candidate.phone,
    "linkedin": candidate.linkedin,
    "github": candidate.github,
    "portfolio": candidate.portfolio,
    "city": document.body.innerText.includes("54000") ? "Lahore" : "Islamabad",
    "country": "Pakistan",
    "university": candidate.university,
    "school": candidate.university,
    "degree": candidate.degree,
  };

  for (const field of fields) {
    const label = getLabelText(field).toLowerCase();
    const name = (field.getAttribute("name") || "").toLowerCase();
    const id = (field.getAttribute("id") || "").toLowerCase();
    const placeholder = (field.getAttribute("placeholder") || "").toLowerCase();

    for (const [key, val] of Object.entries(mappings)) {
      if (label.includes(key) || name.includes(key) || id.includes(key) || placeholder.includes(key)) {
        if (!field.value) { // Don't overwrite existing input
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

    // Find the matching screening question from LLM
    const match = answers.find(ans => {
      const qKeywords = ans.question.toLowerCase().split(/\s+/).filter(k => k.length > 3);
      const labelLower = labelText.toLowerCase();
      // Match if at least 3 keywords from the question are in the label
      const matches = qKeywords.filter(k => labelLower.includes(k)).length;
      return matches >= Math.min(3, qKeywords.length);
    });

    if (match && match.answer) {
      log(`Screening fill: Question matching label filled with: '${match.answer}'`);
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
        log("Filling resume objective/summary...");
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
  // 1. Try matching label[for="id"]
  const id = input.getAttribute("id");
  if (id) {
    const label = document.querySelector(`label[for="${id}"]`);
    if (label) return label.innerText.trim();
  }
  
  // 2. Try parent label
  const parentLabel = input.closest("label");
  if (parentLabel) return parentLabel.innerText.trim();
  
  // 3. Try previous siblings of the input itself (non-greedy)
  let prev = input.previousElementSibling;
  while (prev) {
    if (["LABEL", "SPAN", "P", "DIV", "LEGEND"].includes(prev.tagName)) {
      const txt = prev.innerText.trim();
      if (txt && txt.length > 2 && txt.length < 100) return txt;
    }
    prev = prev.previousElementSibling;
  }

  // 4. Try the parent's previous siblings (e.g. if input is wrapped, and label is a sibling of the wrapper)
  let parent = input.parentElement;
  if (parent) {
    let parentPrev = parent.previousElementSibling;
    while (parentPrev) {
      if (["LABEL", "SPAN", "P", "DIV", "LEGEND"].includes(parentPrev.tagName)) {
        const txt = parentPrev.innerText.trim();
        if (txt && txt.length > 2 && txt.length < 100) return txt;
      }
      parentPrev = parentPrev.previousElementSibling;
    }
  }

  // 5. Grandparent fallback for deep nesting
  if (parent && parent.parentElement) {
    const textEls = parent.parentElement.querySelectorAll("span, p, legend, label");
    for (const el of textEls) {
      if (el === input || el.contains(input)) continue;
      const txt = el.innerText.trim();
      if (txt && txt.length > 2 && txt.length < 50) return txt;
    }
  }

  // 6. Attribute fallback
  return input.getAttribute("placeholder") || input.getAttribute("name") || input.getAttribute("id") || "";
}

// Set form value for various input types
async function setFieldValue(field, value) {
  if (!field || value === undefined || value === null) return;
  const strValue = String(value);

  if (field.tagName === "SELECT") {
    // Select option by matching text
    const options = Array.from(field.options);
    const target = options.find(o => o.text.toLowerCase().includes(strValue.toLowerCase()) || o.value.toLowerCase().includes(strValue.toLowerCase()));
    if (target) {
      field.value = target.value;
      field.dispatchEvent(new Event("change", { bubbles: true }));
    }
  } else if (field.type === "checkbox" || field.type === "radio") {
    const isYes = ["yes", "true", "1", "apply"].includes(strValue.toLowerCase());
    const isNo = ["no", "false", "0"].includes(strValue.toLowerCase());
    const labelText = getLabelText(field).toLowerCase();

    if (field.type === "checkbox") {
      field.checked = isYes;
      field.dispatchEvent(new Event("change", { bubbles: true }));
    } else {
      // For radio groups, match value text to label
      if (labelText.includes(strValue.toLowerCase()) || (isYes && labelText === "yes") || (isNo && labelText === "no")) {
        field.checked = true;
        field.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }
  } else {
    // Simulate real keyboard typing
    await simulateTyping(field, strValue);
  }
}

// Simulate realistic keypress-by-keypress typing and autocomplete selection
async function simulateTyping(field, value) {
  if (!field || value === undefined || value === null) return;
  const strValue = String(value);
  field.focus();
  field.value = "";

  // Type character by character
  for (let i = 0; i < strValue.length; i++) {
    const char = strValue[i];
    const keydownEvent = new KeyboardEvent('keydown', { key: char, bubbles: true });
    const keypressEvent = new KeyboardEvent('keypress', { key: char, bubbles: true });

    field.dispatchEvent(keydownEvent);
    field.dispatchEvent(keypressEvent);

    field.value += char;

    const inputEvent = new Event('input', { bubbles: true });
    field.dispatchEvent(inputEvent);

    const keyupEvent = new KeyboardEvent('keyup', { key: char, bubbles: true });
    field.dispatchEvent(keyupEvent);

    await sleep(40); // 40ms typing delay per character
  }
  
  field.dispatchEvent(new Event('change', { bubbles: true }));
  
  // Wait for autocomplete lists to appear (specifically for City fields)
  await sleep(600);
  
  // Click first suggestion if autocomplete opens and is visible
  const suggestions = Array.from(document.querySelectorAll('ul[role="listbox"] li, li[role="option"], [id*="suggestion"], .autocomplete-suggestion'))
    .filter(el => el.offsetWidth > 0 && el.offsetHeight > 0);
  
  if (suggestions.length > 0) {
    const firstOption = suggestions[0];
    log(`Autocomplete click: "${firstOption.innerText.trim()}"`);
    firstOption.click();
    await sleep(200);
  }
  
  field.blur();
}

// Dynamically answer custom questions using the LLM Brain
async function fillQuestionsWithBrain(fields, llmResponse) {
  const customQuestions = [];
  const fieldToQuestion = new Map();

  const standardKeywords = [
    "first name", "last name", "full name", "name", "email", "phone", "mobile",
    "linkedin", "github", "portfolio", "city", "country", "university", "school",
    "degree", "street", "address", "postcode", "zip", "postal code", "resume", "cv"
  ];

  fields.forEach(field => {
    const label = getLabelText(field);
    if (!label || label.length < 5) return;

    const labelLower = label.toLowerCase();
    
    // Check if it's a standard field
    const isStandard = standardKeywords.some(keyword => labelLower.includes(keyword));
    if (isStandard) return;

    // Check if we already have an answer in the initial llmResponse
    const hasInitialAnswer = (llmResponse.screening_answers || []).some(ans => {
      const qKeywords = ans.question.toLowerCase().split(/\s+/).filter(k => k.length > 3);
      const matches = qKeywords.filter(k => labelLower.includes(k)).length;
      return matches >= Math.min(3, qKeywords.length);
    });

    if (hasInitialAnswer) return;

    // It's a custom unanswered question!
    if (!customQuestions.includes(label)) {
      customQuestions.push(label);
    }
    fieldToQuestion.set(field, label);
  });

  if (customQuestions.length === 0) {
    log("No custom screening questions detected on this page.");
    return;
  }

  log(`Asking AI Brain to answer ${customQuestions.length} custom questions...`);
  try {
    const data = await callBackend("/ask-brain", {
      method: "POST",
      body: { questions: customQuestions }
    });
    const answers = data.answers || {};

    // Fill the fields with the returned answers
    fields.forEach(field => {
      const question = fieldToQuestion.get(field);
      if (question && answers[question]) {
        const ans = answers[question];
        log(`AI Brain Answer: '${question}' -> '${ans}'`);
        setFieldValue(field, ans);
      }
    });
  } catch (err) {
    log(`Error calling AI Brain: ${err}`);
  }
}
